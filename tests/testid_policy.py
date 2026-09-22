"""demo 埋点政策扫描器（纯函数 · 无浏览器 · 秒级）—— P16 批 1 判据先行里的「防回退」判据用它。

**政策口径（AprilPark1012 2026-09-22 拍板）**：
真实项目的埋点一般只落在**顶层元素**上（页面级入口 / 容器：table、弹层、工具栏、分页条、状态区），
要操作的**子元素**（行、单元格、行内链接/按钮）**没有**埋点 ⇒ 必须靠「从顶层锚点下钻」定位。

于是 demo 也必须长这样：
  ✅ 允许：容器级（`tbl-*` / `modal-*` / `pager` / `status` / `total-*` / `page-info`）
          + 页面级入口（`link-orders` / `link-contracts` / `btn-back`）
          + **顶层表单控件**（`btn-search` / `tb-keyword` / `sel-*` / `o-*` / `inp-*` … —— 他选的「口径 A：顶层保留」）
  ❌ 禁止：行级 `tr` / 单元格 `td` / 行内 `a`·`button` 上的 `data-testid`
          （含 `<script>` 里逐行渲染出来的那些，如 `row-${c.no}` / `link-${c.no}` / `pick-${c.id}`）

判定用**结构位置**（不看命名约定，改名也躲不过）：
  ① 元素本身是 `tr`/`td`/`th`/`tbody`/`thead` ⇒ 违规
  ② 元素的祖先里出现上述行/单元格 ⇒ 违规
  ③ 元素位于 `<script>` 块内（前端模板，运行时逐行渲染） ⇒ 违规
  ④ 值里含 `${...}`（动态占位） ⇒ 违规

⚠️ 为什么用规则而不是"名单"：名单只能挡住已知的 30 个，**改名/新增行内埋点就漏**；
规则拦的是**形态**。判据自身必须有负向自证（造违规 HTML 必须被抓、造合法 HTML 必须放行）。
"""
from __future__ import annotations

import re
from pathlib import Path

ROW_TAGS = {"tr", "td", "th", "tbody", "thead"}
VOID_TAGS = {"br", "img", "input", "meta", "link", "hr", "source", "area", "col", "embed"}

_TAG_RE = re.compile(r"<(/?)([a-zA-Z][\w-]*)((?:\"[^\"]*\"|'[^']*'|[^>\"'])*)>", re.S)
_TESTID_RE = re.compile(r'data-testid\s*=\s*"([^"]*)"', re.I)
_SCRIPT_RE = re.compile(r"<script.*?</script>", re.S)


def scan_html(html: str) -> list[dict]:
    """扫描一段 HTML ⇒ 违规清单 `[{line, tag, testid, reasons}]`（空 = 合规）。

    纯函数、无 IO ⇒ 一类判据可以拿它做正/负向自证。
    """
    out: list[dict] = []
    stack: list[str] = []
    script_spans = [(m.start(), m.end()) for m in _SCRIPT_RE.finditer(html)]

    for m in _TAG_RE.finditer(html):
        closing, tag, attrs = m.group(1), m.group(2).lower(), m.group(3) or ""
        if closing:
            for i in range(len(stack) - 1, -1, -1):
                if stack[i] == tag:
                    del stack[i:]
                    break
            continue

        tid_match = _TESTID_RE.search(attrs)
        if tid_match:
            value = tid_match.group(1)
            in_script = any(s <= m.start() <= e for s, e in script_spans)
            anc_row = sorted(set(stack) & ROW_TAGS)
            reasons: list[str] = []
            if tag in ROW_TAGS:
                reasons.append(f"元素本身是行/单元格 <{tag}>")
            if anc_row:
                reasons.append("祖先里有行/单元格 " + ",".join(anc_row))
            if in_script:
                reasons.append("在 <script> 模板内（运行时逐行渲染）")
            if "${" in value:
                reasons.append("值含动态占位 ${...}")
            if reasons:
                out.append({"line": html[:m.start()].count("\n") + 1, "tag": tag,
                            "testid": value, "reasons": reasons})

        if not attrs.rstrip().endswith("/") and tag not in VOID_TAGS:
            stack.append(tag)
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
