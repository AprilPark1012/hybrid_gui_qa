"""元素数据模型：AI 探索产出的"语义"，经 bridge 转成 Playwright locator。

ElementRef 记录的是【用户能看到的语义】，不是 DOM 结构——
这正是业界"locator 绑定到用户可见语义而非脆弱结构"
getByRole/getByLabel/getByText 优先的根基。
"""
from __future__ import annotations
from dataclasses import dataclass, asdict, field
import json


@dataclass
class ElementRef:
    semantic_name: str        # 测试里的逻辑名，如 "add_button"、"todo_input"
    role: str | None = None   # ARIA role：button / textbox / checkbox ...
    name: str | None = None   # accessible name 或可见按钮文本
    label: str | None = None  # get_by_label 用（表单字段 label 文本）
    placeholder: str | None = None
    test_id: str | None = None
    text: str | None = None   # get_by_text 用（稳定静态文案）
    page_hint: str | None = None  # 所在页面/区块的语义提示
    # --- P4 新增：AI 语义上下文（近邻结构 + 帮助文本），解决同 role+name 元素的消歧 ---
    container_heading: str | None = None  # 所属区块标题（最近 heading 祖先文本）
    nearby_text: str | None = None        # 同一逻辑单元的关键文本（如列表项的 span 等待办内容）
    help_text: str | None = None          # aria-describedby / title / 邻近提示文本
    notes: str = ""
    # --- P16 新增（2026-09-22）：顶层锚点 + 容器内相对路径 -------------------------------
    # 为什么：真实系统一般只有**顶层元素**（表格/弹层/工具栏/区块）有 data-testid，
    # 子元素（行、单元格、行内链接按钮）没有 -> 必须"从锚点下钻"。见 framework/tools/probe/anchor.py。
    # 老生成物 / 老录像里没有这两个字段 -> from_dict 会留 None（向后兼容，绝不编造）。
    anchor: dict | None = None   # {"kind": table|dialog|form|region, "by": test_id|aria_label|role|heading, "value": ...}
    path: list | None = None     # [{"axis": row|col|target, "by": ..., "value": ...}, ...]

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ElementRef":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class TestStep:
    """一条测试步骤：动作动作 + 断言 + 依赖的元素。由 AI 规划，Playwright 执行。"""
    order: int
    action: str                  # "goto" / "click" / "fill" / "check" / "expect_text" / ...
    element: ElementRef | None = None  # 动作目标元素
    value: str | None = None     # fill 的输入值
    assertion: str | None = None # expect 断言文本
    description: str = ""        # 人类可读步骤说明
    # --- 跨 tab / 行内定位（2026-09-17 新增，均可选）---
    # row_text + cell_field：**行内定位**（在「含 row_text 的那一行」里操作 cell_field 那一列）。
    #   为什么需要：新建记录的编号是服务端动态分配的，AI 无法按语义名引用那一条记录。
    # cell_field 同时用于 expect_first_row 断言（要验第一行的哪一列）。
    row_text: str | None = None
    cell_field: str | None = None
    # V8.4.3：列指定方式（field / header / index）与序号 —— 给**没有 data-field 的列**用
    # （最典型 = 表格最左的勾选列）。生成器早就在读这两个键（_row_col_step 白名单），
    # 但 AI 产出这一侧一路都没接上，导致 AI 想表达也只能丢掉。
    cell_by: str | None = None
    cell_index: int | None = None
    # 2026-10-10（方案 2）：**按行下标定位**（从 1 起；-1 = 最后一行）。
    # 为什么需要：`row_text` 按**内容**锚定行，而「刚刚新增的那一行」是空的 —— 没有内容可锚，
    #   于是"新增行后逐字段填写"这类需求根本无法表达，实测表现为运行期多匹配歧义
    #   （同一个语义名在页面 3 行里各有一个同名输入框 -> primary 命中 3 个 -> 定位失败）。
    row_index: int | None = None

    def to_dict(self) -> dict:
        return {
            "order": self.order,
            "action": self.action,
            "element": self.element.to_dict() if self.element else None,
            "value": self.value,
            "assertion": self.assertion,
            "description": self.description,
            "row_text": self.row_text,
            "cell_field": self.cell_field,
            "cell_by": self.cell_by,
            "cell_index": self.cell_index,
            "row_index": self.row_index,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TestStep":
        el = ElementRef.from_dict(d["element"]) if d.get("element") else None
        return cls(
            order=d["order"], action=d["action"], element=el,
            value=d.get("value"), assertion=d.get("assertion"),
            description=d.get("description", ""),
            row_text=d.get("row_text"), cell_field=d.get("cell_field"),
            cell_by=d.get("cell_by"), cell_index=d.get("cell_index"),
            row_index=d.get("row_index"),
        )


def item_multi_match_map(items) -> dict:
    """从**清单条目**建「名字 -> 重复个数」—— 收录该条目**出现过的所有名字口径**。

    为什么三个都要（2026-10-10 三次踩坑，每次都是"名字对不上 -> 判据静默失效"）：
      · `semantic_name`  —— **对外**权威名（AI 看到、用例引用；跨页唯一化后带 `@页名`）；
      · `original_name`  —— 跨页唯一化**之前**的 semantic_name（`uniquify_across_pages` 写的留痕；
                            探测期那一刻步骤引用的就是它，实测「撞上重复控件的 0 个」就是漏了它）；
      · `base_name`      —— 上下文后缀之前的基础名（`assign_semantic_names` 写的留痕）。
    同一能力只留这一处构建逻辑（generate 侧也从这里取）。
    """
    out: dict = {}
    # 基名 -> 出现过的**页集合**：只有"这个基名在所有页上只对应同一个多匹配数"时才用它兜底，
    #   否则（同名控件分布在不同页、多匹配数不同）**不兜底** —— 否则会给别的页面的同名字段
    #   误加"必须给行定位"的要求（误伤比漏拦更糟：会诱发绕过）。
    base_pages: dict = {}
    for it in (items or []):
        if not isinstance(it, dict) or int(it.get("multi_match") or 1) <= 1:
            continue
        for key in (it.get("semantic_name"), it.get("original_name"), it.get("base_name")):
            if not key:
                continue
            base = str(key).split("@", 1)[0]
            if base:
                base_pages.setdefault(base, set()).add(str(it.get("page") or ""))
    for it in (items or []):
        if not isinstance(it, dict):
            continue
        n = int(it.get("multi_match") or 1)
        if n <= 1:
            continue
        for key in (it.get("semantic_name"), it.get("original_name"), it.get("base_name")):
            if key:
                out[str(key)] = max(int(out.get(str(key), 1)), n)
                # [!] 再收录一次「`@` 之前的基名」：清单侧后缀是**页名**（`删除@订单详情页`），
                #     而探测期步骤侧后缀可能是**容器上下文**（`保存@详细信息`）—— 两边后缀
                #     根本不同源，逐个枚举口径是追不完的（2026-10-10 为此连踩三次）。
                base = str(key).split("@", 1)[0]
                if base and len(base_pages.get(base, ())) <= 1:
                    out[base] = max(int(out.get(base, 1)), n)
    return out


def multi_match_of_name(mm_map: dict, name) -> "int | None":
    """按名字查重复个数：先精确，再退回 `@页名` 前的基础名。查不到返回 None。"""
    if not name:
        return None
    key = str(name)
    if key in mm_map:
        return mm_map[key]
    base = key.split("@", 1)[0]
    return mm_map.get(base)


def step_get(step: "dict | TestStep | None", key: str):
    """读一步的字段 —— **dict 与 TestStep 两种形态都认**。

    为什么要这个：同一份 `steps` 在框架里有两副面孔（explore 内部用 dict，`ElementMap`/
    测试夹具常拿 dataclass）—— 2026-10-10 实测栽过：产出校验里 `.get()` 直接
    `AttributeError: 'TestStep' object has no attribute 'get'`（7 条判据连带红）。
    拿"观测到的那一种形态"当地基 = 换条路径就崩，所以读取只留这一处。
    """
    if step is None:
        return None
    if isinstance(step, dict):
        return step.get(key)
    return getattr(step, key, None)


def row_scope_violation(step: "dict | TestStep | None", multi_match: "int | None") -> "str | None":
    """「引用了重复出现的控件、却没给行定位」-> 返回**可改的原因**；否则返回 None。

    **唯一入口**（项目口径：同一能力必须收敛成唯一入口）。两个调用点共用这一段判据与措辞：
      · `explorer._finalize_map`：AI 产出成型时收集成 `_ROW_SCOPE_NOTES`，
        由 `cli._verify_cases_detailed` 读走 -> **带原因让 AI 重生成**（既有重试闭环）；
      · `generator`：生成用例脚本时的闸门（手搓用例 / 任何来源的用例都覆盖）。

    为什么必须共用（2026-10-10 实测）：闸门原先只在 generate 阶段说话，而重试闭环在 explore
    阶段 —— 原因**到不了 AI 手里**，AI 没有第二次机会（能力、`multi_match` 信号、第 0 位硬清单
    全都到位，flash 依旧只给语义名）。
    """
    if int(multi_match or 1) <= 1:
        return None
    if has_row_locator(step):
        return None
    elem = step_get(step, "element") or step_get(step, "desc") or ""
    if not isinstance(elem, str):        # dataclass 的 element 可能是 ElementRef
        elem = getattr(elem, "semantic_name", None) or str(elem)
    return (f"控件 {elem!r} 在页面上**重复出现 {int(multi_match)} 个**（同一容器内每行/每条一个）"
            f"-> 只给语义名会同时命中多个，运行期必红。请补行定位："
            f"`row_index`（第 N 行，从 1 起；`-1` = 最后一行）或 `row_text` + 列字段；"
            f"**刚新增的空行只能用 `row_index`**。")


# ---- 行内定位的字段口径（**唯一一处**）：什么才算「这步已经给了行定位」 ----
# 判据（row_scope_violation）与兜底（apply_row_locator_fallback）都读它：
# 两处各写一份字段清单 = 日后只改一处 -> 又是静默失效（2026-10-11 L30 的教训）。
ROW_LOCATOR_FIELDS = ("row_text", "row_index", "cell_field", "cell_by")


def has_row_locator(step) -> bool:
    """这步是否已经给了行定位（行锚 / 行下标 / 列字段任一）。"""
    for f in ROW_LOCATOR_FIELDS:
        v = step_get(step, f)
        if v is not None and v != "":
            return True
    return False


def set_step(step, key, value) -> None:
    """写一步的字段 —— 与 `step_get` 对称的**唯一写入入口**（dict 与 TestStep 都认）。"""
    if step is None:
        return
    if isinstance(step, dict):
        step[key] = value
        return
    if hasattr(step, key):
        setattr(step, key, value)
        return
    object.__setattr__(step, key, value)      # dataclass 未声明该字段时也不炸


# 「往行区新增了一行」的动作识别 —— 只认**事实**：op 白名单，或控件名以新增/添加/追加类词开头。
# [!] 框架层零业务词：这里只有「行的增删」这类通用语义，不涉及任何具体页面/业务字段。
_ROW_ADD_OPS = ("add_row", "append_row", "addrow")
_ROW_ADD_NAME_HINTS = ("新增行", "添加行", "增加行", "追加行", "新增明细", "添加明细", "加一行")


def step_name_of(step) -> str:
    """取一步引用的语义名（element 可能是 str，也可能是 ElementRef）。"""
    elem = step_get(step, "element")
    if elem is None:
        return ""
    if isinstance(elem, str):
        return elem
    return getattr(elem, "semantic_name", None) or str(elem)


def is_row_add_step(step) -> bool:
    """这步是不是「往行区新增/追加了一行」（兜底推断的前提事实）。"""
    op = str(step_get(step, "op") or step_get(step, "action") or "").strip().lower()
    if op in _ROW_ADD_OPS:
        return True
    base = step_name_of(step).split("@", 1)[0]
    return any(base.startswith(h) for h in _ROW_ADD_NAME_HINTS)


def apply_row_locator_fallback(steps, mm_map) -> list[dict]:
    """【框架兜底 · 唯一入口】给整条用例补「能判死」的行定位；推不出的**不动**（照旧报红）。

    为什么要有它（2026-10-11，方案 ③）：AI（deepseek-flash）稳定不写 `row_index`
    —— 能力/信号/硬清单/闸门/原因喂回都到位了它也不写。与其指望模型，不如**框架确定性兜底**：
    凡是能由用例自身结构判死的，就补上；判不出来的，宁可红着让人看清楚（绝不猜）。

    只认一条能判死的规则：
      R1 **刚新增的那一行** —— 该步没有任何行定位 + 它前面**存在**「新增行」动作 +
         自那次新增之后**没有**任何步骤给出过行锚（row_text / 列字段）。此时该步引用的
         重复控件只可能是**刚建的那行**：想指别的行就必须给锚，否则它无法定位 -> 补
         `row_index: -1`（最后一行，引擎已支持）。

    保守原则（宁漏不误伤）：新增之后只要出现过一次行锚，本批**不再兜底** —— 那时
    「这几步填的是不是同一行」已经说不准了，宁可红。

    返回补过的清单 `[{"index": i, "name": ..., "rule": "R1_last_added_row"}, ...]`（可审计）。
    """
    out: list[dict] = []
    last_add = -1
    anchor_seen = False
    for i, st in enumerate(steps or []):
        if is_row_add_step(st):
            last_add, anchor_seen = i, False
            continue
        if last_add < 0:
            continue
        if has_row_locator(st):
            anchor_seen = True
            continue
        name = step_name_of(st)
        if not name:
            continue
        # [!] 这里**只认精确键**，不用 `multi_match_of_name()` 的基名兜底 ——
        #   基名兜底会把**别的页面**上的同名控件算进来：2026-10-11 实测，
        #   开票页的 `单位@开票页` / `数量@开票页` 被订单详情页的同名重复控件带下水，
        #   补出了错误的 `row_index=-1`。判据（只读、报红）误伤还看得见，
        #   兜底是**直接改用例**的行为 —— 必须宁漏不误伤（补错比不补危险得多）。
        mm = (mm_map or {}).get(str(name))
        if not mm or int(mm) <= 1:
            continue
        if anchor_seen:
            continue
        set_step(st, "row_index", -1)
        out.append({"index": i, "name": name, "rule": "R1_last_added_row"})
    return out


@dataclass
class ElementMap:
    """一次探索的完整产物：页面目标 + 步骤列表 + 用到的元素。"""
    url: str = ""
    scenario: str = ""           # 自然语言测试意图（用户输入）
    steps: list[TestStep] = field(default_factory=list)
    #: 本次探索**喂给 AI 的完整元素清单**（含跨页唯一化后的最终名 = 权威名字来源）。
    #:
    #: 为什么必须落盘（2026-10-10 S1 收口，实测）：`steps` 里只有 **AI 实际用到**的名字；
    #: 手搓用例、断言、其它用例引用到的控件名（AI 没用过）在 generate 期只能靠**现场重探**
    #: 缺口所属那一两页去重建，而重探拿不到跨页唯一化的上下文：
    #:   · `超@合同列表页` 要同探 >=2 页才会出现页名后缀 -> 只探 1 页 -> 探不到（实测补 0/1）；
    #:   · 页内消歧的名（`订单名称@订单系统`）与用例里猜写的 `订单名称@订单列表页` 对不上 -> 永远探不到；
    #: => 报出「缺失项」把整条链卡死，看着像命名口径冲突，实为**权威清单丢在内存里没落盘**。
    #: 老产物没有这个键 -> 空列表（向后兼容，行为与改造前一致）。
    probe_items: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"url": self.url, "scenario": self.scenario,
                "steps": [s.to_dict() for s in self.steps],
                "probe_items": self.probe_items}

    def to_json(self, path) -> None:
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
                        encoding="utf-8")

    @classmethod
    def from_json(cls, path) -> "ElementMap":
        d = json.loads(path.read_text(encoding="utf-8"))
        return cls(url=d["url"], scenario=d["scenario"],
                   steps=[TestStep.from_dict(s) for s in d["steps"]],
                   probe_items=list(d.get("probe_items") or []))
