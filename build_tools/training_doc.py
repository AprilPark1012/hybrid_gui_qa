# -*- coding: utf-8 -*-
"""培训页渲染底座（V8.9.9 重构）：一份内容，两种产物（html / md）。

## 为什么要有这层

旧实现把整页塞进 `build_html.py` 的一个 1000 行 f-string 里，导致三件事：
  1. **改内容 = 在大括号里搏斗**（`{{` 转义），稍不留神整页崩掉；
  2. **只能出 html**，想拿 markdown 复制片段得人工转；
  3. **目录树是硬编码字符串** -> 代码新增模块时没人回头改它（历史真事故，见
     `tests/特性9-质量闸门体系/test_docs_sync.py` 的注释）。

现在：
  · 内容写在 `training_content_*.py`，用 `Doc` 累积；
  · 目录树**从磁盘生成**，不再手抄；
  · `Doc` 同时累积 html 与 markdown -> 两种产物天然不会漂。

## 用法

    d = Doc()
    d.h3("3.5.1 放哪")
    d.p("场景文件住在 " + C("scenarios/<模块>/<场景id>.yml") + "。")
    d.table(["字段", "必填"], [["id", "是"]])
    sec = section("3.5", "scenario 怎么写", "写完 AI 就会照着排步骤", d)
"""
from __future__ import annotations

import html as _html
import re
from pathlib import Path
from typing import Callable, Iterable, Sequence

BASE = Path(__file__).resolve().parent.parent      # 仓库根


# ---------------------------------------------------------------- 内联小工具
def esc(t) -> str:
    return _html.escape(str(t), quote=False)


def C(text: str) -> str:
    """行内代码（两态：html 用 span，md 用反引号）。"""
    return f"<code>{esc(text)}</code>"


def B(text: str) -> str:
    return f"<b>{text}</b>"


_MD_INLINE = re.compile(r"\*\*([^*]+)\*\*|`([^`]+)`")
_MD_TICK = re.compile(r"`([^`]+)`")
_MD_BOLD = re.compile(r"\*\*([^*]+)\*\*")


def inline_md(text: str, *, escape: bool = True) -> str:
    """轻量 markdown（**加粗** / `代码`）-> 内联 HTML（先转义再替换，安全）。

    [!] 为什么需要：`feature_spec` 的目标文案与 `TUNABLE_CATALOG` 的说明都是**给终端看的**
    纯文本写法，直接塞进网页会把 `**xxx**` 与反引号原样显示出来（旧培训页就这样，
    实测 body 文本里能搜到裸 `**放宽阈值**`）。
    """
    src = esc(text) if escape else str(text)
    # [!] 必须两遍：先反引号后加粗。单趟交替时 `**...`x`...**` 会先命中加粗规则，
    #   里面那对反引号就被吞掉、原样留在页面上（实测正文里能搜到裸反引号）。
    src = _MD_TICK.sub(lambda m: '<code class="code-inline">' + m.group(1) + "</code>", src)
    return _MD_BOLD.sub(lambda m: "<b>" + m.group(1) + "</b>", src)


# ---------------------------------------------------------------- Doc
class Doc:
    """同时累积 html 与 markdown 的极简块级 DSL。

    约定：`*_html` 方法收**已含内联标签**的 html 串；`*_md` 方法收**纯文本/已含反引号**
    的 markdown。成对方法由本类提供（`p/h3/ul/table/code/note/details`），
    内容层只调这些，不自己拼 `<>` 与 markdown，从而两态一致。
    """

    def __init__(self) -> None:
        self.h: list[str] = []
        self.m: list[str] = []

    # -- 段落：html 与 md 内容一致，只差标签
    def p(self, html: str, md: str | None = None) -> "Doc":
        self.h.append(f'<p class="lead">{html}</p>')
        self.m.append((md if md is not None else _strip(html)) + "\n")
        return self

    def h3(self, title: str) -> "Doc":
        self.h.append(f'<h3 style="margin:26px 0 6px">{title}</h3>')
        self.m.append(f"\n### {_strip(title)}\n")
        return self

    def h4(self, title: str) -> "Doc":
        self.h.append(f'<h4 style="margin:18px 0 4px">{title}</h4>')
        self.m.append(f"\n#### {_strip(title)}\n")
        return self

    def ul(self, items: Sequence[str], md: Sequence[str] | None = None) -> "Doc":
        self.h.append("<ul>" + "".join(f"<li>{i}</li>" for i in items) + "</ul>")
        mds = md if md is not None else [_strip(i) for i in items]
        self.m.append("\n".join(f"- {x}" for x in mds) + "\n")
        return self

    def ol(self, items: Sequence[str], md: Sequence[str] | None = None) -> "Doc":
        self.h.append("<ol>" + "".join(f"<li>{i}</li>" for i in items) + "</ol>")
        mds = md if md is not None else [_strip(i) for i in items]
        self.m.append("\n".join(f"{n}. {x}" for n, x in enumerate(mds, 1)) + "\n")
        return self

    def table(self, head: Sequence[str], rows: Iterable[Sequence[str]],
              md: list[list[str]] | None = None, cls: str = "") -> "Doc":
        rows = list(rows)
        cls_attr = f' class="{cls}"' if cls else ""
        h = [f'<table class="tbl"{cls_attr} style="width:100%;border-collapse:collapse">',
             "<thead><tr>" + "".join(f"<th>{c}</th>" for c in head) + "</tr></thead><tbody>"]
        for r in rows:
            h.append("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>")
        h.append("</tbody></table>")
        self.h.append("\n".join(h))
        mrows = md if md is not None else [[_strip(c) for c in r] for r in rows]
        # [!] 内容层常常把表头也写进 md 行里（肉眼对着表格抄就会这样），
        #   这里统一去重，否则 markdown 里会出现两行表头。
        _h = [_strip(c) for c in head]
        if mrows and [_strip(c) for c in mrows[0]] == _h:
            mrows = mrows[1:]
        m = ["| " + " | ".join(_h) + " |",
             "|" + "|".join("---" for _ in head) + "|"]
        for r in mrows:
            m.append("| " + " | ".join(str(c).replace("\n", " / ") for c in r) + " |")
        self.m.append("\n".join(m) + "\n")
        return self

    def code(self, text: str, lang: str = "") -> "Doc":
        body = "<br>".join(esc(line) if line.strip() else "&nbsp;" for line in text.splitlines())
        self.h.append(f'<div class="cmd">{body}</div>')
        self.m.append("```" + lang + "\n" + text.rstrip() + "\n```\n")
        return self

    def note(self, kind: str, html: str, md: str | None = None) -> "Doc":
        """kind: ok / warn / bad（分别是绿/黄/红提示条）。"""
        cls = {"ok": "ok-tip", "warn": "warn-tip", "bad": "bad-tip"}.get(kind, "warn-tip")
        self.h.append(f'<div class="{cls}">{html}</div>')
        flag = {"ok": "OK", "warn": "注意", "bad": "禁止"}.get(kind, "注意")
        self.m.append(f"> **[{flag}]** {(md if md is not None else _strip(html))}\n")
        return self

    def card(self, html: str, md: str | None = None) -> "Doc":
        self.h.append(f'<div class="card">{html}</div>')
        self.m.append((md if md is not None else _strip(html)) + "\n")
        return self

    def details(self, summary: str, build: Callable[["Doc"], None], *,
                open_: bool = False, md_keep: bool = True) -> "Doc":
        """可折叠区块（html 里折叠，md 里展开成一个小节）。"""
        sub = Doc()
        build(sub)
        self.h.append('<details' + (" open" if open_ else "") + ">")
        self.h.append(f"<summary>{summary}</summary>")
        self.h.append('<div class="inner">' + "\n".join(sub.h) + "</div>")
        self.h.append("</details>")
        if md_keep:
            self.m.append(f"\n#### {_strip(summary)}\n")
            self.m.append("\n".join(sub.m))
        return self

    def raw(self, html_str: str, md: str = "") -> "Doc":
        """原样注入（表格/SVG 之类由上游生成好的片段）。"""
        self.h.append(html_str)
        if md:
            self.m.append(md)
        return self

    @property
    def html(self) -> str:
        return "\n".join(self.h)

    @property
    def md(self) -> str:
        return "\n".join(self.m)


def _strip(s: str) -> str:
    """html 片段 -> 纯文本（给 md 用）。"""
    s = re.sub(r"</?(b|strong|i|em|u)>", "", s)
    s = re.sub(r"<code>([^<]*)</code>", r"`\1`", s)
    s = re.sub(r"<span[^>]*>", "", s)
    s = s.replace("</span>", "")
    s = re.sub(r"<br\s*/?>", " / ", s)
    s = re.sub(r"<[^>]+>", "", s)
    return _html.unescape(s).strip()


# ---------------------------------------------------------------- 章节
def section(no: str, title: str, sub: str, doc: Doc, *, anchor: str = "") -> dict:
    return {"no": no, "title": title, "sub": sub, "doc": doc, "anchor": anchor}


# ---------------------------------------------------------------- 目录树（从磁盘生成）
_SKIP_DIRS = {".venv", "__pycache__", ".git", ".pytest_cache", "node_modules",
              ".mypy_cache", ".ruff_cache", "htmlcov"}
_SKIP_SUFFIX = {".pyc", ".pyo"}
#: 运行期目录：内容天天变，列出来只会让树噪音爆炸 -> 只列名字不展开
_RUNTIME_ONLY = {"output", "log"}

_ANNOTATE: dict[str, str] = {
    "framework": "运行期代码（按特性分夹 f02..f11；shared/ 是底座）",
    "tests": "判据（一类 test_*.py 与二类 verify_*.py 都在特性夹里）",
    "scenarios": "人写的场景声明（AI 的输入）",
    "cases": "AI 产出的用例（explore 落盘）",
    "scripts": "generate 产物（脚本 + 抽离数据）",
    "demo": "自带被测应用（本地练习用，端口 8000）",
    "docs": "生成物文档（培训页 / 特性地图）",
    "build_tools": "开发期工具（构建 / 打包 / 录像）",
    "releases": "发行包与校验清单",
    "output": "运行产物：element_map / 录像 cassette / 自愈记录（不进交付包）",
    "log": "pytest 运行现场：报告 / 截图 / 视频（不进交付包）",
}


def _walk(path: Path, prefix: str, depth: int, max_depth: int) -> list[str]:
    if depth > max_depth:
        return []
    try:
        kids = sorted([p for p in path.iterdir() if p.name not in _SKIP_DIRS
                       and p.suffix not in _SKIP_SUFFIX], key=lambda p: (p.is_file(), p.name))
    except PermissionError:
        return []
    lines: list[str] = []
    for i, kid in enumerate(kids):
        last = i == len(kids) - 1
        branch = "└── " if last else "├── "
        name = kid.name + ("/" if kid.is_dir() else "")
        note = _ANNOTATE.get(kid.name, "") if depth == 1 else ""
        lines.append(f"{prefix}{branch}{name}" + (f"    {note}" if note else ""))
        if kid.is_dir() and not (kid.name in _RUNTIME_ONLY and depth >= 1):
            ext = "    " if last else "│   "
            lines.extend(_walk(kid, prefix + ext, depth + 1, max_depth))
    return lines


def dir_tree_text(max_depth: int = 2) -> str:
    """仓库目录树（从磁盘生成 —— 不再手抄，新增模块自动出现）。"""
    root = BASE.name + "/"
    body = _walk(BASE, "", 1, max_depth)
    return "\n".join([root] + body)


def dir_tree_html(max_depth: int = 2) -> str:
    return f'<pre class="tree">{esc(dir_tree_text(max_depth))}</pre>'


def modules_by_feature() -> list[tuple[str, str, list[str]]]:
    """按特性夹列出真实模块文件（给「特性说明 + 关键实现」用）。"""
    feat = BASE / "framework" / "features"
    out: list[tuple[str, str, list[str]]] = []
    if not feat.exists():
        return out
    for d in sorted(p for p in feat.iterdir() if p.is_dir() and re.fullmatch(r"f\d\d_\w+", p.name)):
        files = sorted(f.name for f in d.glob("*.py") if f.name != "__init__.py")
        out.append((d.name, _feature_dir_note(d.name), files))
    return out


def _feature_dir_note(name: str) -> str:
    from framework.features.f09_gate.feature_spec import FEATURES      # 单一来源
    no = int(name[1:3])
    for f in FEATURES:
        if int(f.get("no", -1)) == no:
            return str(f.get("name") or "")
    return ""


# ---------------------------------------------------------------- 整页渲染
_FOOTER_TPL = (
    '<footer>hybrid_gui_qa · AI 混合 GUI 测试框架培训页 · <b>V{ver}</b>（{date}）'
    "· 由 build_tools/build_html.py 生成</footer>"
)


def render_page(sections: list[dict], *, hero: str, ver: str, date: str) -> str:
    from build_tools.training_css import CSS
    parts: list[str] = [
        "<!DOCTYPE html>",
        '<html lang="zh-CN">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>AI 混合 GUI 测试框架 · 新员工培训（V{ver}）</title>",
        "<style>",
        CSS,
        "</style>",
        "</head>",
        "<body>",
        hero,
        '<div class="wrap">',
    ]
    for s in sections:
        anchor = f' id="{s["anchor"]}"' if s.get("anchor") else ""
        parts.append(f"<section{anchor}>")
        parts.append(f'  <h2 class="sec-title"><span class="n">{s["no"]}</span>{s["title"]}</h2>')
        if s.get("sub"):
            parts.append(f'  <p class="sec-sub">{s["sub"]}</p>')
        parts.append(s["doc"].html)
        parts.append("</section>")
    parts.append(_FOOTER_TPL.format(ver=ver, date=date))
    parts.append("</div>")
    parts.append("<!--TOC_PLACEHOLDER-->")
    parts.append("{TOC_FAB}")
    parts.append("{TOC_JS}")
    parts.append("</body>")
    parts.append("</html>")
    return "\n".join(parts)


def render_md(sections: list[dict], *, ver: str, date: str) -> str:
    out = [f"# AI 混合 GUI 测试框架 · 新员工培训（V{ver}）", "",
           f"> 与 `docs/training.html` 同源生成（`python build_tools/build_html.py`）· {date}", ""]
    for s in sections:
        out.append(f"## {s['no']} {_strip(s['title'])}")
        if s.get("sub"):
            out.append(f"*{_strip(s['sub'])}*")
        out.append("")
        out.append(s["doc"].md)
    return "\n".join(out).rstrip() + "\n"
