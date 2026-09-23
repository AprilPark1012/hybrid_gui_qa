"""「顶层锚点 + 容器内下钻」的定位合成（P16 批 3 · 唯一新入口）。

**为什么需要**（AprilPark1012 2026-09-22 口径）：真实系统一般只有**顶层容器**有 `data-testid`
（表格 / 弹层 / 工具栏 / 区块），要操作的子元素（行、单元格、行内链接按钮）没有埋点。
框架 Tier1 第一级就是 `data-testid`，demo 又几乎每个控件都埋了 ⇒ 这条"下钻"能力**从没被真实触发**。

**契约**（与 `tests/featureTest/verify_scope_locate.py` 文件头逐字一致）：

    scope_locate(page, anchor, path) -> {"ok", "locator", "locator_obj", "count", "strategy", "reason"}
      anchor = {"kind": "table|dialog|region|form", "by": "test_id|heading|aria_label|role", "value": ...}
      path   = [{"axis": "row",    "by": "text|nth",          "value": ...},
                {"axis": "col",    "by": "header|field|index", "value": ...},
                {"axis": "target", "by": "role|text",         "value": ...}]
      by=None（有容器、没任何埋点信号）⇒ 按 kind 的 tag 取容器，**要求 count()==1**。

**分层**（本模块的设计要点）：
  ① **纯函数层**（无浏览器）：`anchor_expr` / `step_expr` / `path_expr` / `strategy_for` / `ambiguity_reason`
     —— 表达式怎么拼、歧义怎么说，全部在这里，`tests/frameworkTest/test_scope_locate_expr.py` 秒级钉住；
  ② **执行层**：`_anchor_locator` / `_apply_path` / `scope_locate` —— 只做"按上面拼好的表达式去问页面"。

**红线（与项目铁律一致）**：
  · 任一级**歧义**（行/列步 count != 1）⇒ `ok=False` **如实失败**，不许 `nth` 猜第一个（猜错 = 假通过）；
  · 表头文本算不出列序 ⇒ 放弃该步（**绝不默认"第 1 列"**）；
  · 锚点不唯一 / 不认识 ⇒ 如实失败；路径步骤不认识 ⇒ 如实失败（不许静默跳过）；
  · 目标步（`target.*`）允许命中多个 ⇒ **如实返回 count**，由调用方决定（如"容器内有两个输入框"是事实，不是错误）。
"""
from __future__ import annotations

from playwright.sync_api import Page

from framework.tools.probe.anchor import header_index

# 容器 kind ⇒ 无锚点信号时的 tag 表达式（by=None 的降级路径）
_KIND_TAG = {
    "table": 'page.locator("table")',
    "dialog": 'page.locator("[role=dialog]")',
    "form": 'page.locator("form")',
    "region": 'page.locator("section, [role=region]")',
}
# 容器 kind ⇒ CSS 选择器（执行层用；与 _KIND_TAG 同口径）
_KIND_CSS = {
    "table": "table",
    "dialog": "[role=dialog]",
    "form": "form",
    "region": "section, [role=region]",
}
# 显式行序的提示语（strategy 里出现 ⇒ 报告/日志一眼看出"这步靠的是结构顺序，表序变了就错"）
EXPLICIT_ORDER_NOTE = "按显式行序定位"


# ============================== ① 纯函数层 ==============================

def anchor_expr(anchor: dict | None) -> str | None:
    """锚点 ⇒ 可复用的 Playwright 表达式**片段**；不认识/拼不出 ⇒ None（调用方如实失败）。

    四种签名 + 一种降级：
      · `test_id`   ⇒ `page.get_by_test_id("…")`（最稳，契约锚点）
      · `aria_label`⇒ 属性选择器（**不用 `get_by_label`**：那 API 只找表单控件，锚住 `<section>` 会空手而归）
      · `heading`   ⇒ 标题定位后取"其后的第一个同 tag 容器"（真实页面常这么写：`<h1>采购单列表</h1><table>`）
      · `role`      ⇒ `page.get_by_role("…")`
      · `by=None`   ⇒ 按 `kind` 取 tag（零 testid 表格），**要求 count()==1**
    """
    anchor = anchor or {}
    kind = str(anchor.get("kind") or "")
    by = anchor.get("by")
    val = anchor.get("value")
    if kind not in _KIND_TAG:
        return None
    if by in (None, ""):
        return _KIND_TAG[kind]
    if by == "test_id" and val not in (None, ""):
        return f'page.get_by_test_id("{val}")'
    if by == "aria_label" and val not in (None, ""):
        css = _KIND_CSS[kind]
        head = css.split(",")[0].strip()
        return f"page.locator('{head}[aria-label=\"{val}\"]')"
    if by == "heading" and val not in (None, ""):
        css = _KIND_CSS[kind]
        head = css.split(",")[0].strip()
        return (f'page.get_by_role("heading", name="{val}")'
                f'.locator("xpath=following::{head}[1]")')
    if by == "role" and val not in (None, ""):
        return f'page.get_by_role("{val}")'
    return None


def step_expr(prev: str, step: dict, *, col_index: int | None = None) -> str | None:
    """在当前表达式上套一级路径 ⇒ 新表达式；这一步拼不出（不认识 / 缺运行时候算值）⇒ None。"""
    axis = str((step or {}).get("axis") or "")
    by = (step or {}).get("by")
    val = (step or {}).get("value")
    if axis == "row":
        if by == "text" and val not in (None, ""):
            return f'{prev}.locator("tbody tr").filter(has_text="{val}")'
        if by == "nth" and isinstance(val, (int, float)):
            return f'{prev}.locator("tbody tr").nth({int(val) - 1})'
        return None
    if axis == "col":
        if by == "field" and val not in (None, ""):
            return f"{prev}.locator(\"td[data-field='{val}']\")"
        if by == "header" and val not in (None, ""):
            if col_index is None:          # 运行时读表头算列序；算不出 ⇒ 放弃（绝不默认第 1 列）
                return None
            return f'{prev}.locator("td").nth({int(col_index) - 1})'
        if by == "index" and isinstance(val, (int, float)):
            return f'{prev}.locator("td").nth({int(val) - 1})'
        return None
    if axis == "target":
        if by == "role" and val not in (None, ""):
            return f'{prev}.get_by_role("{val}")'
        if by == "text" and val not in (None, ""):
            return f'{prev}.get_by_text("{val}", exact=True)'
        # ★2026-09-22：图标按钮（"…"）靠 title 定位 —— 同位 text 必然歧义（弹层里 3 个"…"）。
        if by == "title" and val not in (None, ""):
            return f'{prev}.get_by_title("{val}")'
        # P16 批 6（口径 C）：**弹层内表单字段**的定位口径。撤掉内层埋点后，字段是"最需要下钻"的一类
        # （实测：`modal-new-order` 里的订单名称输入框，撤掉 `o-name` 后没有路径可走 ⇒ 框架定位不了）。
        # 按字段自身的稳定信号定位：placeholder（最稳）→ label（非 exact，真实表单的 label 常带必填星号）
        if by == "placeholder" and val not in (None, ""):
            return f'{prev}.get_by_placeholder("{val}")'
        if by == "label" and val not in (None, ""):
            # ★2026-09-22（口径 C 实测：合同弹层的管理单元/帐套/合同类型/业务单元四个下拉）：
            # 真实表单的 `<label>` 常常**没有 for**、也没包住控件 ⇒ get_by_label 空手而归。
            # ⇒ 把**确定性兜底写进表达式本身**（label 之后的第一个表单控件），靠 Playwright 的惰性
            # 求值在运行时二选一。**不能**改成"返回 None 让调用方退到 _drill"——drill 也要先合成
            # 表达式，那样会把运行期通道一起堵死（实测踩过：4 条用例的 primary 直接抛 RuntimeError）。
            _fb = (f'{prev}.locator("xpath=.//label[normalize-space()="{val}" '
                   f'or contains(normalize-space(), "{val}")]'
                   f'/following::*[self::input or self::select or self::textarea][1]")')
            return (f'({prev}.get_by_label("{val}") '
                    f'if {prev}.get_by_label("{val}").count() else {_fb})')
        return None
    return None


def path_expr(anchor: dict | None, path: list | None, *,
              col_indexes: dict | None = None) -> str | None:
    """锚点 + 整条路径 ⇒ 完整表达式（进日志 / 生成物 / 报告）；任一步拼不出 ⇒ None。

    `col_indexes`：`{步骤序号: 运行时候算出的列序}` —— `col.header` 必须由调用方提供（表头只有运行时读得到）。
    """
    base = anchor_expr(anchor)
    if base is None:
        return None
    cur = base
    for i, step in enumerate(list(path or [])):
        idx = (col_indexes or {}).get(i)
        nxt = step_expr(cur, step, col_index=idx)
        if nxt is None:
            return None
        cur = nxt
    return cur


def strategy_for(path: list | None) -> str:
    """给人看的策略标签；用了**显式行序**时必须一眼看出来（那种定位表序一变就错）。"""
    steps = list(path or [])
    labels = [f'{s.get("axis")}.{s.get("by")}' for s in steps]
    used_nth = any(s.get("axis") == "row" and s.get("by") == "nth" for s in steps)
    base = "+".join(labels) if labels else "anchor_only"
    return f"{base}（{EXPLICIT_ORDER_NOTE}）" if used_nth else base


def ambiguity_reason(axis: str, value, count: int) -> str:
    """歧义理由文案（二类负向判据靠「歧义/唯一」这两个词识别"如实失败"，改文案要同步判据）。"""
    where = "行" if axis == "row" else ("列" if axis == "col" else "目标")
    return (f'{where}「{value}」命中 {count} 个 ⇒ 歧义（要求唯一，'
            f'禁止按行序猜第一个；请给更精确的行锚/列锚）')


# ============================== ② 执行层 ==============================

def _anchor_candidates(page: Page, anchor: dict):
    """按签名给出**候选** locator（先精确后退化）；返回 [(locator, expr), ...]。"""
    anchor = anchor or {}
    kind = str(anchor.get("kind") or "")
    by = anchor.get("by")
    val = anchor.get("value")
    if kind not in _KIND_CSS:
        return []
    tag = _KIND_CSS[kind]
    head = tag.split(",")[0].strip()
    out = []
    if by in (None, ""):
        out.append((page.locator(tag), _KIND_TAG[kind]))
    elif by == "test_id" and val not in (None, ""):
        out.append((page.get_by_test_id(val), f'page.get_by_test_id("{val}")'))
    elif by == "aria_label" and val not in (None, ""):
        out.append((page.locator(f'{head}[aria-label="{val}"]'), f"locator('{head}[aria-label=\"{val}\"]')"))
        out.append((page.locator(f'[aria-label="{val}"]'), f'locator(\'[aria-label="{val}"]\')'))
    elif by == "heading" and val not in (None, ""):
        # 主路径：标题之后第一个同 tag 容器（夹具页 `<h1>采购单列表</h1><table>` 就是这种写法）
        h = page.get_by_role("heading", name=val, exact=True)
        out.append((h.locator(f"xpath=following::{head}[1]"),
                    f'page.get_by_role("heading", name="{val}").locator("xpath=following::{head}[1]")'))
        # 退化：容器**内含**该标题（`<section><h2>…</h2><table>`）
        out.append((page.locator(tag).filter(has=h),
                    f'page.locator("{tag}").filter(has=page.get_by_role("heading", name="{val}"))'))
    elif by == "role" and val not in (None, ""):
        out.append((page.get_by_role(val), f'page.get_by_role("{val}")'))
        # 隐藏降级（同上）：容器锚是隐藏弹层时，可见语义找不到它
        out.append((page.get_by_role(val, include_hidden=True),
                    f'page.get_by_role("{val}", include_hidden=True)'))
    return out


def anchor_locator(page: Page, anchor: dict):
    """取容器主作用域。返回 `(locator | None, expr, reason)`；不唯一/不命中 ⇒ locator=None 且给理由。"""
    cands = _anchor_candidates(page, anchor)
    if not cands:
        return None, "", (f"锚点无法识别：kind={anchor.get('kind')!r} by={anchor.get('by')!r}"
                          f"（支持的 kind：table/dialog/form/region）")
    counts = []
    for loc, expr in cands:
        try:
            n = loc.count()
        except Exception as e:                                             # noqa: BLE001
            counts.append((0, expr, f"{type(e).__name__}: {e}"))
            continue
        if n == 1:
            return loc, expr, ""
        counts.append((n, expr, ""))
    # 一个都不唯一 ⇒ 把实际命中数写进理由（越像"歧义"越好定位）
    detail = "；".join(f"{e} ⇒ {n} 个" for n, e, _ in counts)
    if any(n == 0 for n, _, _ in counts):
        return None, "", f"锚点未命中（容器找不到，要求唯一）：{detail}"
    return None, "", f"锚点不唯一 ⇒ 歧义（要求唯一）：{detail}"


def _apply_path(scope, path: list, base_expr: str):
    """逐级套用路径。返回 `(locator, expr, count, reason)`；中途如实失败 ⇒ locator=None。

    中间步（row / col）**必须唯一**（count==1）；目标步（target）允许命中多个 ⇒ 如实返回 count
    （"容器内有两个同名输入框"是事实，不是错误 —— 二类判据 ④ 就靠这个区分容器）。
    """
    cur, expr, cnt = scope, base_expr, None
    for i, step in enumerate(list(path or [])):
        axis = str((step or {}).get("axis") or "")
        by = (step or {}).get("by")
        val = (step or {}).get("value")

        # col.header 的列序**必须运行时**从该表 thead 读出来（表头文本 ⇒ 列序）
        col_idx = None
        if axis == "col" and by == "header":
            headers = _table_headers(cur)
            col_idx = header_index(headers, val)
            if col_idx is None:
                return None, expr, None, (
                    f'表头「{val}」在本表找不到（表头={headers}）⇒ 放弃列定位'
                    f'（**不默认第 1 列**；请补 data-field 或用 col.index 显式指定）')

        # ⚠️ 传**表达式字符串** expr，不是 cur（cur 是 Locator 对象，f-string 会写成 `<Locator …>` repr）
        nxt = step_expr(expr, step, col_index=col_idx)
        if nxt is None:
            return None, expr, None, (
                f"路径第 {i + 1} 步无法合成：axis={axis!r} by={by!r} value={val!r}"
                f"（不认识的轴/口径，或缺少运行时候算值）")

        loc = None
        if axis == "row" and by == "text" and val not in (None, ""):
            loc = cur.locator("tbody tr").filter(has_text=str(val))
        elif axis == "row" and by == "nth" and isinstance(val, (int, float)):
            loc = cur.locator("tbody tr").nth(int(val) - 1)
        elif axis == "col" and by == "field" and val not in (None, ""):
            loc = cur.locator(f"td[data-field='{val}']")
        elif axis == "col" and by == "header" and col_idx is not None:
            loc = cur.locator("td").nth(int(col_idx) - 1)
        elif axis == "col" and by == "index" and isinstance(val, (int, float)):
            loc = cur.locator("td").nth(int(val) - 1)
        elif axis == "target" and by == "role" and val not in (None, ""):
            loc = cur.get_by_role(str(val))
            # 隐藏降级：`display:none` 的弹层**不在 ARIA 树里** ⇒ 默认口径必然 0 命中
            # （实测：夹具弹层 get_by_role("button")=0 / include_hidden=True=2；demo 关闭态弹层同理）。
            # 先按可见语义找，找不到才含隐藏 —— 且表达式**如实带上参数**，日志里能看出走的是哪条路。
            if loc.count() == 0:
                loc_hidden = cur.get_by_role(str(val), include_hidden=True)
                if loc_hidden.count() > 0:
                    loc = loc_hidden
                    nxt = f'{expr}.get_by_role("{val}", include_hidden=True)'  # noqa: F841
        elif axis == "target" and by == "title" and val not in (None, ""):
            loc = cur.get_by_title(str(val))            # 图标按钮（"…"）：title 是唯一稳定标识
        elif axis == "target" and by == "placeholder" and val not in (None, ""):
            loc = cur.get_by_placeholder(str(val))     # 属性选择，隐藏元素也能命中（无需可见性降级）
        elif axis == "target" and by == "label" and val not in (None, ""):
            loc = cur.get_by_label(str(val))           # 非 exact：label 常带必填星号
            # ★2026-09-22（口径 C 实测：合同弹层的「管理单元/帐套/合同类型/业务单元」四个下拉）：
            # 真实表单里 `<label>` **经常没有 for、也没包住控件** ⇒ get_by_label 关联不上（实测 0 个）。
            # 补一条**结构性**兜底：label 之后的第一个表单控件。这是**确定性规则**（不是猜 CSS，
            # 本项目的铁律照旧：locator 一律由框架合成），且只在"关联失败"时才走。
            if loc.count() == 0:
                loc = cur.locator(
                    f"xpath=.//label[normalize-space()='{val}' or contains(normalize-space(), '{val}')]"
                    f"/following::*[self::input or self::select or self::textarea][1]")
        elif axis == "target" and by == "text" and val not in (None, ""):
            loc = cur.get_by_text(str(val), exact=True)
        if loc is None:
            return None, expr, None, f"路径第 {i + 1} 步口径不支持：axis={axis!r} by={by!r}"

        try:
            n = loc.count()
        except Exception as e:                                             # noqa: BLE001
            return None, expr, None, f"路径第 {i + 1} 步定位失败：{type(e).__name__}: {e}"

        if axis in ("row", "col"):
            if n == 0:
                return None, expr, None, (
                    f'{("行" if axis == "row" else "列")}「{val}」未命中（0 个）⇒ 无把握，不猜')
            if n != 1:                       # 歧义 ⇒ 如实失败，**绝不 nth 猜第一个**
                return None, expr, None, ambiguity_reason(axis, val, n)
        else:
            if n == 0:
                return None, expr, None, f"目标「{val}」未命中（0 个）"
            cnt = n
        cur, expr = loc, nxt

    if cnt is None:
        try:
            cnt = cur.count()
        except Exception:                                                  # noqa: BLE001
            cnt = None
    return cur, expr, cnt, ""


def _table_headers(scope) -> list[str]:
    """从当前作用域往上找最近的表，读 `thead th` 文本（算列序用）；读不到 ⇒ 空列表（调用方据此放弃）。"""
    try:
        table = scope.locator("xpath=ancestor-or-self::table[1]")
        return [str(h).strip() for h in table.locator("thead th").all_inner_texts()]
    except Exception:                                                      # noqa: BLE001
        return []


def locate_in_scope(scope, path: list | None = None, *, base_expr: str = "<scope>") -> dict:
    """在**已经拿到的作用域**里下钻（动态锚点场景：先按行文本找到唯一行，再下钻到列）。

    与 `scope_locate` 共用 `_apply_path` —— 同一条通道、同一套唯一性口径（歧义如实失败），
    所以 `generator._click_row_cell` 不需要再维护一份自己的行/列判断逻辑。
    """
    steps = list(path or [])
    loc, expr, cnt, why = _apply_path(scope, steps, base_expr)
    if loc is None:
        return {"ok": False, "locator": None, "locator_obj": None, "count": None,
                "strategy": strategy_for(steps), "reason": why}
    return {"ok": True, "locator": expr, "locator_obj": loc, "count": cnt,
            "strategy": strategy_for(steps), "reason": ""}


def drill(page: Page, anchor: dict, path: list | None = None):
    """运行期下钻：**直接返回 Locator**，定位不唯一/失败就抛错并带上 reason（P16 批 5）。

    为什么要有它：`col.header` 这类列口径**必须运行时读表头算列序** ⇒ 生成物没法把它拼成
    静态表达式链（`get_by_test_id(...).locator(...)…`）⇒ 生成期的表达式退化成 `get_by_role(...)`
    这种**会歧义**的裸语义（实测：6 个挑选层的按钮全变成 `get_by_role("button", name="选择")`，
    在"每行一个选择按钮"的表里必然 count>1）。有它就能把「锚点 + 路径」原样搬到运行期执行。
    """
    r = scope_locate(page, anchor, path)
    if not r.get("ok"):
        raise RuntimeError(f"下钻定位失败（anchor={anchor} path={path}）：{r.get('reason')}")
    return r["locator_obj"]


def scope_locate(page: Page, anchor: dict, path: list | None = None) -> dict:
    """按「锚点 + 容器内相对路径」定位；唯一性不过 ⇒ `ok=False` 且 `reason` 说清为什么。"""
    steps = list(path or [])
    scope, base_expr, why = anchor_locator(page, anchor)
    if scope is None:
        return {"ok": False, "locator": None, "locator_obj": None, "count": None,
                "strategy": strategy_for(steps), "reason": why}
    loc, expr, cnt, why = _apply_path(scope, steps, base_expr)
    if loc is None:
        return {"ok": False, "locator": None, "locator_obj": None, "count": None,
                "strategy": strategy_for(steps), "reason": why}
    return {"ok": True, "locator": expr, "locator_obj": loc, "count": cnt,
            "strategy": strategy_for(steps), "reason": ""}
