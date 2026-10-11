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
    # --- P25 第 4 个真缺陷（2026-10-11）：元素**自身**的 `id` --------------------------
    # 为什么与 test_id 同级单列：真实页面上"容器没有任何语义（裸 <div>）"的控件很常见
    #   （如订单详情页底部按钮行的「保存」），那时 test_id / anchor / role+name 都定不住它，
    #   而它自身往往有稳定 id（demo: #btn-detail-edit）-> 这是唯一可用的稳定身份。
    # 优先级（生成期与 locator_bridge 同一口径）：test_id > element_id > 锚点下钻 > role+name。
    # 老产物 / 老录像没有这个键 -> from_dict 留 None（向后兼容，绝不编造）。
    element_id: str | None = None
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
    # --- P25 片 3（2026-10-11，要求6）：控件**有效性**标记 -------------------------------
    # 默认 true = 「探测时说它在」。generate 阶段补探/复核时若发现该控件在页面上
    # **已经找不到**（页面改版、容器收起、行数变少），把它置 false。
    # 口径（D3）：置 false 的条目**保留在产物里**（留痕/可审计）+ **排除定位映射**
    # （否则失效控件照样被点到，报出来的错还指向别处）+ **不进 AI 提示词**（省 token）。
    # 为什么用「默认 true + 显式置 false」而不是「有没有出现过」：绝大多数控件一直有效，
    #   记录"无效"这个**例外事实**体积最小，且老产物缺这个键时行为与改造前一致（向后兼容）。
    isValid: bool = True

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
            # [!] P25 片 3：`order` / `action` 允许缺省 —— 老产物、手工构造的产物、
            #   以及只关心「哪个控件」的夹具都可能有 steps 条目而没这两个键。
            #   抛 KeyError 的后果是**整份产物读不动**（缺一个展示字段 vs 整条链断掉，
            #   孰轻孰重很清楚）。order 缺失按 0 处理：它只用于展示与排序，不参与定位。
            order=int(d.get("order") or 0), action=d.get("action") or "", element=el,
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


def apply_scene_start_fallback(steps, first_page_url: str = "", has_scene_pre: bool = False,
                               host_page_url: str = ""):
    """【框架兜底 · 唯一入口】删掉「用例第一步把页面导航回场景起始页」的多余步骤。

    为什么要有它：场景声明的登录/身份前置由 `probe_pre` 在**每条用例执行前**自动完成，
    用例起手页面已经在前置结束的那一页。AI 却常把场景里的"以超管登录"写成用例第 1 步
    `goto 登录页` -> 页面被导航回去 -> 紧接着的步骤在**错的页面**上找控件 -> 必然失败
    （实测两次：`选择合同_HT_1001` 定位失败，现场 URL 就是 login.html）。

    **这是模型对负向指令的遵从度问题**（把"登录"标成"背景条件"后它照旧写），
    因此不能只靠场景描述治理；而它又**可由用例结构判死** -> 正属框架确定性兜底的适用范围。

    判据（C1/C2/C3 同时成立才动手）：
      C1 场景**声明了** `probe_pre`（框架确实会做前置）；
      C2 第 1 步是 `goto` 且不带 element；
      C3 该 URL 与场景声明的**第一个页**（起始页）同路径。

    任一不成立 -> **一步都不动**（宁漏不误伤：改错步骤比不改危险得多）。

    命中后的动作（两条路）：
      · `host_page_url` 给了且与起手页不同 -> **把这一步 retarget 成 `probe_pre_host` 那一页**
        （AI 少写了"进入工作页"那一步，前置做完后页面并不保证在工作页上 —— 实测如此）；
      · 没给 host 页 -> 保守**删掉**这一步（页面本来就在起手页，多这一次导航纯属多余）。

    返回留痕 `[{"index": 0, "url": ..., "rule": "C1C2C3_scene_start"}]`（可审计、可在日志里明示）。
    """
    out: list = []
    if not has_scene_pre:
        return out
    seq = list(steps or [])
    if not seq:
        return out
    st = seq[0]
    op = str(step_get(st, "op") or step_get(st, "action") or "").strip().lower()
    if op != "goto":
        return out
    if step_get(st, "element"):
        return out
    url = str(step_get(st, "value") or step_get(st, "url") or "").strip()
    # [!] 字段名必须**同时认 `value` 与 `url`**（2026-10-12 实测踩到）：
    #   AI 产出的 goto 步骤用的是 `url` 键 —— 用例 JSON 原文：
    #     {"op":"goto","url":"http://localhost:8000/login.html","desc":"打开 【登录页】…"}
    #   只读 `value` 会取到空串 -> 规则 C3 不成立 -> 兜底**静默失效**（框架兜底失效最危险：
    #   看着有这道闸，实际一步都没删，链路照旧失败还得再查一遍）。
    if not url or not first_page_url:
        return out
    # 同路径判定（只比 path，忽略 query/末尾斜杠差异 —— 起始页在场景里可能带参数）
    def _path(u: str) -> str:
        import urllib.parse as _up
        try:
            return (_up.urlparse(str(u or "")).path or "").rstrip("/") or "/"
        except Exception:
            return ""
    if _path(url) != _path(first_page_url):
        return out
    # ---- 命中：AI 把「起手页」又 goto 了一遍 ----
    # [!] **不能直接删**（2026-10-12 实测踩到，这是本函数第一版的错）：
    #   直接删掉后，页面就停在"前置结束那一刻"——而前置结束**不保证**停在用例要操作的那一页
    #   （本场景：登录前置做完后停在登录跳转页）=> 下一步照样「等了 5000ms 仍是 0 个」而失败。
    #   正确做法：把它**改成 goto 到 `probe_pre_host` 声明的那一页**（那才是用例的起手工作页）。
    #   对照铁证：同场景的手搓用例**显式 goto 了工作页**（日志原文"打开合同列表页（登录由场景级
    #   登录前置完成，无需手工登录）"）-> 15 步全绿；AI 用例缺这一步 -> 秒挂。
    if host_page_url and _path(host_page_url) != _path(url):
        set_step(st, "value", host_page_url)
        set_step(st, "url", host_page_url)          # AI 产出的 goto 用的是 `url` 键，两个都写上
        out.append({"index": 0, "url": url, "retarget_to": host_page_url,
                    "rule": "C1C2C3_retarget_to_host"})
        return out
    # 拿不到 host 页 -> 保守：删掉这一步（页面本来就在起手页，多这一次导航纯属多余）
    out.append({"index": 0, "url": url, "rule": "C1C2C3_scene_start_dropped"})
    del seq[0]
    # 重排 order（下游渲染/落盘按 order 走，留洞会让"第 N 步"对不上）
    for i, s in enumerate(seq):
        if step_get(s, "order") is not None:
            set_step(s, "order", i + 1)
    steps[:] = seq
    return out


def merge_entry_fields(primary: dict | None, fallback: dict | None) -> dict:
    """同名条目**字段级合并**（唯一入口）：以 `primary` 定名与身份，用 `fallback` 补它缺的字段。

    [!] 为什么不能「谁优先就用整条」（2026-10-11 实测的真 bug）：
      两个来源承载的信息**不同** ——
        · `steps[].element` 是 **AI 写的名字引用**（语义名 + role，**天然没有** anchor/path）；
        · `probe_items` 是 **探测期的完整条目**（含 `anchor` / `path` / `test_id` 等定位信号）。
      原来按「同名先到先得」整条取舍、且 `steps` 排在前面 => 快照与定位映射里存下
      **没有定位信号的那一份** => 运行期合成不出唯一 locator =>
      `RuntimeError: 元素定位失败且自愈未成功: 物料编码@订单详情页`。
      铁证：同一个名字在 elementMap 的 `probe_items` 里**有** anchor+path、
      在 `_probe_snapshot.json` 里**没有**。

    口径：**名字归属仍按调用方的优先级**（steps 优先，判据锁着）；本函数只负责
    "把 primary 缺的字段用 fallback 补上"，绝不覆盖 primary 已有的值（那是 AI 明确表达的意图）。
    """
    out: dict = dict(primary or {})
    for k, v in (fallback or {}).items():
        if out.get(k) in (None, "", [], {}):
            out[k] = v
    return out


def with_isvalid(items) -> list[dict]:
    """给清单里每条补上 `isValid` 默认值（**唯一一处**补默认值的地方）。

    为什么要有它：`isValid` 的口径是「默认有效，例外才置 false」——
    于是上游（探测器 / 场景 / 老产物）可以**不带**这个键，落盘/出站时统一补 true。
    一处补，处处一致；散着补就会「有的入口带、有的入口不带」，下游判 false 时被 None 骗过。
    """
    out: list[dict] = []
    for it in items or []:
        if isinstance(it, dict):
            d = dict(it)
            d.setdefault("isValid", True)
            out.append(d)
        else:
            out.append(it)
    return out


def _url_key(url: str) -> str:
    """URL 归一化成「页身份」：去掉 scheme / host / query / fragment / 首尾斜杠，只留 path。

    为什么要归一：同一次探索里同一个页面可能以多种写法出现
    （`http://localhost:8000/order_new.html?contract_no=HT-1`、`/order_new.html`、`order_new.html`），
    而「这是不是一个页」必须由**结构**判断，不能由字符串逐字判断。
    只留 path：host 随部署变、query 常带业务数据值（都是运行期观测，不是页面身份）。
    """
    t = str(url or "").strip()
    if "://" in t:
        rest = t.split("://", 1)[1]
        t = rest.split("/", 1)[1] if "/" in rest else ""
    t = t.split("?", 1)[0].split("#", 1)[0]
    return t.strip("/").lower()


def split_steps_by_page(steps, pages=None) -> list[dict]:
    """把一串步骤按 **goto 边界**切成「页」-> `[{"page": 页名, "url": <该页地址>, "steps": [...]}]`。

    为什么要切（要求6 + D2）：`steps` 原先是**一整条流水**，而页对象要「一页一个」；
    不切的话每页都会带上全流程步骤，页与步骤的关系就丢了（下游「按页复核控件」也没法做）。

    页名怎么定：优先用场景声明的 `pages[].name`（按 URL 归一化匹配，声明是权威）；
    声明里没有这个 URL 时用**归一化后的 path**兜底 —— 客观、不猜、可读。

    [!] 只认 `goto`（含 `op`/`action` 两种写法）作为边界：它是链路里唯一的「换页」动作，
        其余动作都发生在当前页上。goto 步本身归**它打开的那一页**（它是那页的第 0 步）。
    """
    name_by_key: dict[str, str] = {}
    for pg in (pages or []):
        if not isinstance(pg, dict):
            continue
        k = _url_key(pg.get("url") or "")
        if k and pg.get("name"):
            name_by_key[k] = str(pg["name"])
    groups: list[dict] = []
    cur: dict | None = None
    for st in steps or []:
        op = str(step_get(st, "op") or step_get(st, "action") or "").strip().lower()
        url = step_get(st, "url") if op == "goto" else None
        if url is None and op == "goto":
            url = step_get(st, "value")
        if op == "goto" and url:
            k = _url_key(url)
            cur = {"page": name_by_key.get(k) or k, "url": str(url), "steps": [st]}
            groups.append(cur)
            continue
        if cur is None:                      # goto 之前的步骤（如登录前置）：独立成「首页组」
            cur = {"page": name_by_key.get("") or "", "url": "", "steps": []}
            groups.append(cur)
        cur["steps"].append(st)
    return groups


def _partition_items(items, page_name: str, total_pages: int) -> list[dict]:
    """把整份控件清单按页分给某个页对象。

    单页（`total_pages <= 1`）-> **整份给它**：此时清单里通常没有 `page` 字段，
    按页过滤会把清单过滤空（那是实打实的数据丢失，不是"分桶"）。
    多页 -> 按条目的 `page` 字段匹配页名；匹配不上的归**第一页**（宁可留在第一页看得见，
    也不静默丢掉 —— 丢一条控件 = 少一个能定位的名字）。
    """
    items = list(items or [])
    if total_pages <= 1:
        return items
    hit = [it for it in items if isinstance(it, dict) and str(it.get("page") or "") == page_name]
    return hit


@dataclass
class ElementMapPage:
    """**一个页面**的探索产物（要求6：一页一个对象）。

    字段就是AprilPark1012定的那五个：`page`（页名）+ `url` + `scenario` + `steps` + `probe_items`。
    `probe`（单页快照）与 `explore`（跨页）**共用这一个形状** —— 两种形状是下游写两套读法的根源。
    """
    page: str = ""
    url: str = ""
    scenario: str = ""
    steps: list[TestStep] = field(default_factory=list)
    probe_items: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"page": self.page, "url": self.url, "scenario": self.scenario,
                "steps": [s.to_dict() if hasattr(s, "to_dict") else s for s in self.steps],
                "probe_items": with_isvalid(self.probe_items)}

    @classmethod
    def from_dict(cls, d: dict) -> "ElementMapPage":
        d = d or {}
        return cls(
            page=str(d.get("page") or ""),
            url=str(d.get("url") or ""),
            scenario=str(d.get("scenario") or ""),
            steps=[TestStep.from_dict(x) for x in (d.get("steps") or []) if isinstance(x, dict)],
            probe_items=with_isvalid(d.get("probe_items") or []),
        )


def load_pages(data) -> list[ElementMapPage]:
    """把**任意形态**的 elementMap 产物归一化成 `[ElementMapPage]`（下游**唯一**读取入口）。

    认三种形态：
      · 新形态：`[ {page, url, scenario, steps, probe_items}, ... ]`（一页一个对象）；
      · 老形态：`{url, scenario, steps, probe_items}`（单页 / 交付包里存着的老文件）；
      · 包裹形态：`{"pages": [...]}`。
    为什么要这一个入口：`to_dict()` 改成 list 之后，读原始 JSON 的地方（generate 侧的定位来源、
    快照重建）各写一套「先判 list 还是 dict」就是**同一能力多入口** —— 日后再改形态必漏一处。
    """
    if data is None:
        return []
    if isinstance(data, dict) and isinstance(data.get("pages"), list):
        data = data["pages"]
    # 运行时快照 `_probe_snapshot.json` 的容器形态：`{"items": [条目...]}` ——
    # 它不是探测产物、而是运行期索引缓存；但读法同样收敛在这里（下游不写第二套）。
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        return [ElementMapPage(probe_items=with_isvalid(data["items"]))]
    if isinstance(data, list):
        # [!] 裸**条目**列表（probe_*.json 的老形态）**不是**「页对象列表」——
        #   判据：条目键里是控件字段（semantic_name/role/...），而没有 steps/probe_items。
        #   整份当作一个页的 `probe_items` 读（两种产物同形之前的兼容读法，
        #   收敛在本入口里 —— 下游不准各写一套 "先判 list 还是 dict"）。
        is_item_list = bool(data) and all(
            isinstance(x, dict) and "semantic_name" in x
            and "steps" not in x and "probe_items" not in x
            for x in data)
        if is_item_list:
            return [ElementMapPage(probe_items=with_isvalid(data))]
        pages = [ElementMapPage.from_dict(x) for x in data if isinstance(x, dict)]
        return [x for x in pages if x.steps or x.probe_items]
    if isinstance(data, dict):
        one = ElementMapPage.from_dict(data)
        return [one] if (one.steps or one.probe_items) else []
    return []


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
    #: 页对象列表（要求6：一页一个对象），**落盘形态就是它**（`to_dict()` 返回 list of page）。
    #: 为空时 `to_dict()` 会用 `url/scenario/steps/probe_items` **自动切页**（按 goto 边界）——
    #: 这样"只给整条流水"的老调用方（含判据/夹具）也能拿到合法的新形态，不必被迫改构造方式。
    pages: list[ElementMapPage] = field(default_factory=list)
    #: 场景声明的页元数据（`[{"name":..., "url":...}]`），只用于**切页时定页名**。
    page_meta: list[dict] = field(default_factory=list)

    def normalized_pages(self) -> list[ElementMapPage]:
        """返回页对象列表（有 pages 用 pages；否则按 goto 现切）—— **读取侧唯一入口**。"""
        if self.pages:
            return list(self.pages)
        groups = split_steps_by_page(self.steps, self.page_meta)
        if not groups:
            return [ElementMapPage(page="", url=self.url, scenario=self.scenario,
                                   steps=[], probe_items=with_isvalid(self.probe_items))]
        total = len(groups)
        out: list[ElementMapPage] = []
        for i, g in enumerate(groups):
            items = _partition_items(self.probe_items, g["page"], total)
            if total > 1 and i == 0:          # 多页时匹配不上的条目归第一页（不静默丢）
                rest = [it for it in (self.probe_items or [])
                        if isinstance(it, dict) and str(it.get("page") or "") not in
                        {str(x["page"]) for x in groups}]
                items = list(items) + rest
            out.append(ElementMapPage(page=g["page"], url=g["url"] or self.url,
                                      scenario=self.scenario,
                                      steps=[s if hasattr(s, "to_dict") else TestStep.from_dict(s)
                                             for s in g["steps"]],
                                      probe_items=items))
        return out

    def to_dict(self) -> list:
        """落盘形态 = **list（一页一个对象）**；单页 = 长度 1 的数组。

        为什么统一成 list（要求6）：probe（单页快照）与 explore（跨页）**同形**，
        下游只写一套读法；页与步骤/控件的从属关系也随对象结构显式表达出来。
        """
        return [pg.to_dict() for pg in self.normalized_pages()]

    def to_json(self, path) -> None:
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
                        encoding="utf-8")

    @classmethod
    def from_data(cls, d) -> "ElementMap":
        """从任意形态的产物数据建对象（list / 老 dict / {"pages": [...]} 都认）。

        老形态读进来后：`steps/probe_items` 汇总成整条流水（保持"整条链路视图"可用），
        同时 `pages` 也填好（页级视图可用）—— 两种视图同时成立，调用方按需取。
        """
        pages = load_pages(d)
        if isinstance(d, dict) and not isinstance(d.get("pages"), list):
            # 老 dict 形态：原样保留顶层 url/scenario（它们可能比页对象更权威）
            return cls(url=str(d.get("url") or ""), scenario=str(d.get("scenario") or ""),
                       steps=[TestStep.from_dict(x) for x in (d.get("steps") or [])
                              if isinstance(x, dict)],
                       probe_items=with_isvalid(d.get("probe_items") or []))
        first = pages[0] if pages else None
        return cls(url=(first.url if first else ""), scenario=(first.scenario if first else ""),
                   steps=[s for pg in pages for s in pg.steps],
                   probe_items=[it for pg in pages for it in pg.probe_items],
                   pages=pages)

    @classmethod
    def from_json(cls, path) -> "ElementMap":
        return cls.from_data(json.loads(path.read_text(encoding="utf-8")))
