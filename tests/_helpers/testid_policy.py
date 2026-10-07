"""demo 埋点政策扫描器（纯函数 · 无浏览器 · 秒级）—— P16 批 1 判据先行里的「防回退」判据用它。

**政策口径（AprilPark1012 2026-09-22 拍板）**：
真实项目的埋点一般只落在**顶层元素**上（页面级入口 / 容器：table、弹层、工具栏、分页条、状态区），
要操作的**子元素**（行、单元格、行内链接/按钮）**没有**埋点 ⇒ 必须靠「从顶层锚点下钻」定位。

于是 demo 也必须长这样：
  ✅ 允许：**页面级**容器/入口（`tbl-*` / `pager` / `status` / `total-*` / `page-info` / `link-orders` / `btn-back`）
          + **页面级**顶层控件（`btn-search` / `tb-keyword` / `sel-*` / `inp-*` … —— 「口径 A：顶层保留」）
          + **弹层容器本身**（`modal-*`）
  ❌ 禁止：行级 `tr` / 单元格 `td` / 行内 `a`·`button` 上的 `data-testid`
          （含 `<script>` 里逐行渲染出来的那些，如 `row-${c.no}` / `link-${c.no}` / `pick-${c.id}`）
  ❌ 禁止（★2026-09-22 需求方收紧口径）：**弹层内部的一切**（除弹层容器本身）——
          字段 `o-*` / `tb-o-*` / `nc-*`、弹层内按钮 `btn-pick-*` / `btn-*-cancel` / `btn-*-submit`、
          弹层内表格 `tbl-pick-*` …
          理由：**生产环境的弹层只有顶层挂埋点**，内层全靠「弹层锚点 + 相对路径」定位；
          demo 若给内层留埋点，等于给框架一条生产里不存在的捷径 ⇒ 框架就练不出真本事。

判定用**结构位置**（不看命名约定，改名也躲不过）：
  ① 元素本身是 `tr`/`td`/`th`/`tbody`/`thead` ⇒ 违规
  ② 元素的祖先里出现上述行/单元格 ⇒ 违规
  ③ 元素位于 `<script>` 块内（前端模板，运行时逐行渲染） ⇒ 违规
  ④ 值里含 `${...}`（动态占位） ⇒ 违规
  ⑤ 元素的祖先里有**弹层容器**（`class` 含 `modal` / `data-testid` 以 `modal-` 开头 / `role="dialog"`），
     而它自己不是那个容器 ⇒ 违规（弹层内部不留埋点，对齐生产）

⚠️ 为什么用规则而不是"名单"：名单只能挡住已知的 30 个，**改名/新增行内埋点就漏**；
规则拦的是**形态**。判据自身必须有负向自证（造违规 HTML 必须被抓、造合法 HTML 必须放行）。
"""
from __future__ import annotations

import re
from pathlib import Path

ROW_TAGS = {"tr", "td", "th", "tbody", "thead"}
# 交互控件：**顶层容器**才允许挂埋点，这些一律不行（页面级也一样）
CONTROL_TAGS = {"input", "select", "textarea", "button", "a", "label", "option"}
# 弹层容器判定（结构启发式，不看命名约定）：class 里有 modal 这个词 / testid 以 modal- 开头 / role=dialog
_POPUP_RE = re.compile(r'(?:class\s*=\s*"[^"]*(?:^|\s)modal(?:\s|$)[^"]*"'
                       r'|data-testid\s*=\s*"modal-'
                       r'|role\s*=\s*"dialog")', re.I)
VOID_TAGS = {"br", "img", "input", "meta", "link", "hr", "source", "area", "col", "embed"}

_TAG_RE = re.compile(r"<(/?)([a-zA-Z][\w-]*)((?:\"[^\"]*\"|'[^']*'|[^>\"'])*)>", re.S)
_TESTID_RE = re.compile(r'data-testid\s*=\s*"([^"]*)"', re.I)
_SCRIPT_RE = re.compile(r"<script.*?</script>", re.S)


def scan_html(html: str) -> list[dict]:
    """扫描一段 HTML ⇒ 违规清单 `[{line, tag, testid, reasons}]`（空 = 合规）。

    纯函数、无 IO ⇒ 一类判据可以拿它做正/负向自证。
    """
    out: list[dict] = []
    stack: list[dict] = []          # [{tag, popup}] —— 带弹层标记，规则⑤ 需要
    script_spans = [(m.start(), m.end()) for m in _SCRIPT_RE.finditer(html)]

    for m in _TAG_RE.finditer(html):
        closing, tag, attrs = m.group(1), m.group(2).lower(), m.group(3) or ""
        if closing:
            for i in range(len(stack) - 1, -1, -1):
                if stack[i]["tag"] == tag:
                    del stack[i:]
                    break
            continue

        is_popup = bool(_POPUP_RE.search(attrs))
        anc_in_popup = any(f["popup"] for f in stack)
        tid_match = _TESTID_RE.search(attrs)
        if tid_match:
            value = tid_match.group(1)
            in_script = any(s <= m.start() <= e for s, e in script_spans)
            anc_row = sorted({f["tag"] for f in stack} & ROW_TAGS)
            reasons: list[str] = []
            if tag in ROW_TAGS:
                reasons.append(f"元素本身是行/单元格 <{tag}>")
            if anc_row:
                reasons.append("祖先里有行/单元格 " + ",".join(anc_row))
            if in_script:
                reasons.append("在 <script> 模板内（运行时逐行渲染）")
            if "${" in value:
                reasons.append("值含动态占位 ${...}")
            # ⑤ 弹层内部（容器本身除外）：生产环境弹层只有顶层挂埋点，内层必须靠「锚点 + 相对路径」
            if anc_in_popup and not is_popup:
                reasons.append("在弹层内部（弹层只有顶层容器允许埋点，内层要对齐生产）")
            # ⑥ 交互控件（页面级也一样）：埋点只允许落在**结构容器**上（table / 弹层 / pager / status…），
            #    输入框/下拉/按钮/链接这些"会操作的东西"在生产里没有埋点 ⇒ 必须靠锚点 + 相对路径定位。
            if tag in CONTROL_TAGS and not is_popup:
                reasons.append(f"埋点落在交互控件 <{tag}> 上（只有顶层容器允许埋点，页面级也一样）")
            if reasons:
                out.append({"line": html[:m.start()].count("\n") + 1, "tag": tag,
                            "testid": value, "reasons": reasons})

        if not attrs.rstrip().endswith("/") and tag not in VOID_TAGS:
            stack.append({"tag": tag, "popup": is_popup})
    return out


def scan_dir(demo_dir: Path) -> dict[str, list[dict]]:
    """扫 demo 目录下所有 .html ⇒ `{文件名: 违规清单}`（只列有违规的页面）。"""
    found: dict[str, list[dict]] = {}
    for p in sorted(Path(demo_dir).glob("*.html")):
        v = scan_html(p.read_text(encoding="utf-8"))
        if v:
            found[p.name] = v
    return found


def format_violations(found: dict[str, list[dict]], limit: int = 40) -> str:
    """人话版清单（判据失败信息 / 修的时候照着改）。"""
    lines, n = [], 0
    for page, items in found.items():
        lines.append(f"  {page}（{len(items)} 处）")
        for it in items:
            if n >= limit:
                lines.append("  …（更多省略）")
                return "\n".join(lines)
            lines.append(f"    L{it['line']:<5d} <{it['tag']}> {it['testid']:<28s} ← {' + '.join(it['reasons'])}")
            n += 1
    return "\n".join(lines)
