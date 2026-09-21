# -*- coding: utf-8 -*-
"""build_html.hl() 的判据：单遍分词 ⇒ 无畸形嵌套 · 可复现 · 字符串真高亮。

背景（2026-09-19 实测，三个真 bug）：
- 老实现是三趟 `re.sub` 串起来跑，关键字那趟在**前一趟注入的 HTML** 上再跑 ⇒ 把
  `<span class="k">` 里的 `class` 又包一层：`<span <span class="k">class</span>="k">raise</span>`
  （已发布的 `docs/training.html` 里实测 **1520 处**）。
- `KEYWORDS` 是 set，`sorted(key=len)` 对**同长度**词按哈希序排，而哈希序每个进程不同 ⇒
  同一份代码重跑两次 `build_html.py`，html 的 md5 都不一样（实测差 140 行）⇒
  「html 与代码是否同步」这条判据被废掉（重跑必出 diff，分不清同步还是没同步）。
- 字符串高亮**早就死了**：先 `html.escape` 把引号变成 `&quot;`/`&#x27;`，字符串正则
  `['"][^'"]*['"]` 永远匹配不上 —— 一个静默退化的功能。

本文件把这三条钉成判据，退化即红。
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
TOOLS = BASE / "build_tools"          # build_html.py 住在框架工具目录（2026-09-19 从仓库根挪入）
sys.path.insert(0, str(TOOLS))

from build_html import hl          # noqa: E402

# 覆盖三类高危形态：关键字、字符串里的关键字、注释里的关键字、行内 HTML、方法调用链
TRICKY = [
    "class Foo: pass",
    "raise RuntimeError('x')",
    "x = 'class def import'  # 关键字在字符串里",
    "# raise class async await 注释里的关键字",
    "async def _f(): await g()",
    "s = \"<span class='k'>literal html</span>\"",
    "if a in b and not c: return None",
    "for i in range(3): pass",
    "lambda x: x + 1",
    "try: ... except Exception as e: raise",
    "yield from gen()",
    "with open(p) as f: global G",
]


def test_no_malformed_nesting():
    """注入的标签不得被二次包裹：不许出现 `<span <span`，标签必须都是 <span class="X"> 形态。"""
    for line in TRICKY:
        out = hl(line)
        assert "<span <span" not in out, f"畸形嵌套：{line!r} → {out}"
        for tag in re.findall(r"<span[^>]*>", out):
            assert re.fullmatch(r'<span class="[cks]">', tag), f"标签形态不对：{tag}（来自 {line!r}）"


def test_span_balanced():
    for line in TRICKY:
        out = hl(line)
        assert out.count("<span") == out.count("</span>"), f"标签不配对：{line!r} → {out}"


def test_string_highlighted():
    """字符串高亮必须真的生效（老实现这里必挂）。"""
    assert '<span class="s">' in hl("x = 'abc'")
    assert '<span class="s">' in hl('y = "abc"')


def test_comment_highlighted():
    assert '<span class="c">' in hl("x = 1  # note")


def test_keyword_inside_string_not_highlighted():
    """字符串里的关键字不许被当关键字高亮（左起优先，字符串先吃掉）。"""
    out = hl("x = 'def class'")
    assert '<span class="k">' not in out, out
    assert '<span class="s">' in out, out


def test_keyword_inside_comment_not_highlighted():
    out = hl("# raise return")
    assert '<span class="k">' not in out, out


def test_html_in_line_is_escaped():
    """代码里的 <b> 必须被转义成文本，不许当标签漏出去。"""
    out = hl("s = '<b>x</b>'")
    assert "<b>" not in out, out
    assert "&lt;b&gt;" in out, out


def test_deterministic_across_processes():
    """换哈希种子重跑同一条 → 必须逐字节相同（老实现这里必挂：同长度词序由哈希决定）。"""
    code = (
        "import sys; sys.path.insert(0, r'" + str(TOOLS) + "');"
        "from build_html import hl;"
        "print('\\n'.join(hl(l) for l in " + repr(TRICKY) + "))"
    )
    outs = set()
    for seed in ("0", "1", "12345"):
        r = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            env={**os.environ, "PYTHONHASHSEED": seed}, cwd=str(BASE),
        )
        assert r.returncode == 0, r.stderr
        outs.add(r.stdout)
    assert len(outs) == 1, "同一输入在不同哈希种子下输出不同 ⇒ 生成结果不可复现"


def test_committed_html_has_no_malformed_nesting():
    """仓库不变量：已提交的培训页里零畸形 span（有 ⇒ 说明生成器退化了或忘了重跑）。"""
    f = BASE / "docs" / "training.html"
    if not f.exists():
        return
    t = f.read_text(encoding="utf-8")
    assert "<span <span" not in t, (
        "docs/training.html 里有畸形 span（共 %d 处）⇒ 用修好的生成器重跑：python build_html.py"
        % t.count("<span <span")
    )
