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
        )


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
