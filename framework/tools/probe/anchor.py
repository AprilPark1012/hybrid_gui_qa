"""锚点 + 相对路径：把「从顶层容器下钻到子元素」这件事表达成**数据**（纯函数 · 无浏览器）。

**为什么需要**（AprilPark1012 2026-09-22 现场口径）：真实系统一般只有**顶层元素**有 `data-testid`
（表格 / 弹层 / 工具栏 / 区块），要操作的子元素（行、单元格、行内链接按钮）没有埋点。
框架的 Tier1 第一级是 `data-testid`，而 demo 又几乎每个控件都埋了 ⇒ 这条"下钻"能力**从没被真实触发**。
本模块提供契约化的表达，供 probe 采集、locator_bridge 合成、generator 生成表达式、AI 提示词共用：

    anchor = {"kind": "table|dialog|form|region", "by": "test_id|aria_label|role|heading", "value": ...}
    path   = [{"axis": "row", "by": "text|nth",    "value": ...},      # 行锚：行内唯一文本 / 显式行序
              {"axis": "col", "by": "field|header|index", "value": ...},# 列：data-field → 表头文本 → 列序
              {"axis": "target", "by": "role|text", "value": ...}]     # 目标元素自身语义

**红线（与项目铁律一致）**：
  · 锚不住 / 列找不到 ⇒ **None 或省略该步**，绝不编造、绝不默认"第 1 行 / 第 1 列"（那是假通过的源头）；
  · 本模块只产出"描述"，**不做定位**（唯一性校验与真实 locator 合成在 locator_bridge，必须有 `count()==1`）。
"""
from __future__ import annotations

# 可作锚点的容器类型（其余 tag/role 一律不当锚点）
TABLE_TAGS = {"table"}
DIALOG_ROLES = {"dialog", "alertdialog"}
FORM_TAGS = {"form"}
REGION_TAGS = {"section", "article", "nav", "aside", "main"}

# 锚点信号强弱（越靠前越稳；与 Tier1 的口径一致：契约锚点 > 可访问性语义 > 结构文本）
ANCHOR_SIGNALS = ("test_id", "aria_label", "role", "heading")


def _container_kind(node: dict) -> str | None:
    """这个祖先是不是「可作锚点的容器」？是 ⇒ 返回 kind，否 ⇒ None。"""
    tag = str(node.get("tag") or "").lower()
    role = str(node.get("role") or "").lower()
    cls = str(node.get("class") or "").lower()
    if tag in TABLE_TAGS:
        return "table"
    if role in DIALOG_ROLES or "modal" in cls:
        return "dialog"
    if tag in FORM_TAGS:
        return "form"
    if tag in REGION_TAGS or role == "region":
        return "region"
    return None


def _anchor_of(node: dict) -> tuple[str, object] | None:
    """容器上的可用锚点信号（按 ANCHOR_SIGNALS 取最强的一个）；都没有 ⇒ None。"""
    for key in ANCHOR_SIGNALS:
        val = node.get(key)
        if val not in (None, "", []):
            return key, val
    return None


def container_from_ancestors(ancestors: list[dict] | None) -> dict | None:
    """从祖先链（**由近到远**）里挑出最近的「可锚定容器」。

    返回 `{"kind","by","value"}`；`by`/`value` 可能同时为 None（有容器但没任何锚点信号 —— 如实标注，
    由下游决定是否退化成"表头文本 + 列序"或全页语义定位）。**完全找不到容器 ⇒ None**。
    """
    first_container: dict | None = None
    for node in (ancestors or []):
        kind = _container_kind(node)
        if not kind:
            continue
        sig = _anchor_of(node)
        if sig:
            return {"kind": kind, "by": sig[0], "value": sig[1]}
        if first_container is None:
            first_container = {"kind": kind, "by": None, "value": None}
    return first_container


def path_for_table_row(row_text: str | None = None, cell_field: str | None = None, *,
                       row_index: int | None = None, col_header: str | None = None,
                       col_index: int | None = None, target_role: str | None = None,
                       target_text: str | None = None) -> list[dict]:
    """构造行内元素的下钻路径。

    行锚优先级：`row_text`（行内唯一文本，最稳）> `row_index`（**显式**行序；调用方明确给出才用）。
    **两者都没有 ⇒ 不生成行步**（不许偷偷按第一行猜）。
    列优先级：`cell_field`（`td[data-field]`）> `col_header`（表头文本）> `col_index`（显式列序，1-based）。
    """
    steps: list[dict] = []
    if row_text not in (None, ""):
        steps.append({"axis": "row", "by": "text", "value": row_text})
    elif row_index is not None:
        steps.append({"axis": "row", "by": "nth", "value": int(row_index)})

    if cell_field not in (None, ""):
        steps.append({"axis": "col", "by": "field", "value": cell_field})
    elif col_header not in (None, ""):
        steps.append({"axis": "col", "by": "header", "value": col_header})
    elif col_index is not None:
        steps.append({"axis": "col", "by": "index", "value": int(col_index)})

    if target_role not in (None, ""):
        steps.append({"axis": "target", "by": "role", "value": target_role})
    elif target_text not in (None, ""):
        steps.append({"axis": "target", "by": "text", "value": target_text})
    return steps


def header_index(headers: list[str] | None, text: str | None) -> int | None:
    """表头文本 ⇒ **1-based** 列序（无 `data-field` 时的降级路径）。找不到 ⇒ None（不退化成第 1 列）。"""
    if not headers or text in (None, ""):
        return None
    want = str(text).strip()
    for i, h in enumerate(headers, start=1):
        if str(h or "").strip() == want:
            return i
    return None


def ancestors_from_dom(chain: list[dict] | None) -> list[dict]:
    """（预留）把 DOM 侧采集到的祖先信息规整成本模块认的字段名。

    probe 采集端已按 `tag/role/class/test_id/aria_label/heading` 命名 ⇒ 这里只做一次字段兜底归一，
    避免两个模块对字段名的理解漂移（本项目踩过"两处口径不一致"的坑）。
    """
    out: list[dict] = []
    for node in (chain or []):
        out.append({
            "tag": node.get("tag"),
            "role": node.get("role"),
            "class": node.get("class") or node.get("className"),
            "test_id": node.get("test_id") or node.get("testid"),
            "aria_label": node.get("aria_label") or node.get("ariaLabel"),
            "heading": node.get("heading"),
        })
    return out
