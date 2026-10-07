"""生成物**转义安全**判据（2026-09-24 事故复盘）。

**事故**：demo 下拉 `<option>` 的文本里有**换行**，生成器把它原样塞进 Python 字符串：
    `f'get_by_role("combobox", name="{it["name"]}")'`
⇒ `scripts/test_cases.py` 里字符串没闭合 ⇒ `py_compile` 失败 ⇒ 那个 AI 用例
   被判定「实测 FAILED」（其实它不是语义错，是**根本编译不过**），一类也红了。

**规矩**：生成器里任何「把数据写进代码」的地方，都必须走 `_py_str()`（json 转义，
在 Python 字面量里同样合法）⇒ 「数据里有什么字符」不得决定「生成物是否合法」。

本判据做两件事：
  ① 直接打 `_semantic_to_locator_expr()`：喂进换行/引号/反斜杠/制表符等恶劣名字，
     输出必须是**能编译**的表达式，而且**求值后拿到的 needle 与输入一致**（往返一致）；
  ② 源码级守门：`generator.py` 里不许再出现"把 `{it[...]}` 直接塞进引号"的裸拼写法。
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

import sys

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from framework.tools.generate.generator import _semantic_to_locator_expr  # noqa: E402

# 恶劣输入：换行（真实事故）、双引号、单引号、反斜杠、制表符、中文与 emoji
NASTY = [
    ("换行（真实事故形态）", "请选择管理单元\n0021\n0451\n1031"),
    ("双引号", '说"你好"'),
    ("单引号", "it's fine"),
    ("反斜杠", "路径 C:\\temp\\x"),
    ("制表符", "名称\t值"),
    ("emoji", "提交✅完成"),
]


@pytest.mark.parametrize("label,raw", NASTY, ids=[n[0] for n in NASTY])
def test_locator_expr_is_compilable_and_roundtrips(label, raw):
    """① 恶劣名字必须生成**可编译**且**往返一致**的定位表达式。"""
    for it in (
        {"role": "combobox", "name": raw, "semantic_name": "s"},
        {"placeholder": raw, "semantic_name": "s"},
        {"text": raw, "semantic_name": "s"},
        {"test_id": raw, "semantic_name": "s"},
    ):
        expr = _semantic_to_locator_expr(it)
        compile(f"lambda p: p.{expr}", "<gen>", "eval")   # 片段接在 p. 后必须能编译
        # 从生成物里把**字符串字面量取回来**（AST 解析，转义会正确还原；不做求值更稳）。
        lits = [n.value for n in ast.walk(ast.parse(expr, mode="eval"))
                if isinstance(n, ast.Constant) and isinstance(n.value, str)]
        # role+name 走 Playwright 的 accessible name 口径 ⇒ 空白归一化；其余必须**原样**（精确匹配）。
        want = " ".join(raw.split()) if it.get("name") else raw
        assert want in lits, f"{label}：needle 与预期不符\n  期望: {want!r}\n  实际: {lits!r}"


def test_real_world_option_text_with_newline_compiles():
    """① 复刻事故输入：换行的 option 文本 ⇒ 生成物必须合法。"""
    it = {"role": "combobox", "name": "请选择管理单元\n0021\n0451\n1031", "semantic_name": "选择管理单元"}
    expr = _semantic_to_locator_expr(it)
    compile(f"lambda p: {expr}", "<gen>", "eval")
    # 归一化后是单空格（不是 "\n"）：这才是浏览器 accessible name 的匹配口径
    assert "请选择管理单元 0021 0451 1031" in expr
    compile(f"lambda p: p.{expr}", "<gen>", "eval")


def test_role_name_needle_is_whitespace_normalized():
    """★事故②守门：带换行的控件文本 ⇒ needle 必须归一化成单空格（否则定位必然失败）。

    实测证据（2026-09-24 重新生成后跑校验）：
      RuntimeError: 元素定位失败且自愈未成功: 请选择_0021_0451_1031
    —— 那个选项的文本是 "请选择管理单元\n0021\n0451\n1031"，浏览器算 accessible name 时
       把连续空白归一化为一个空格，needle 不归一化就永远匹配不到。
    """
    it = {"role": "combobox", "name": "请选择管理单元\n0021\n0451\n1031", "semantic_name": "x"}
    expr = _semantic_to_locator_expr(it)
    lits = [n.value for n in ast.walk(ast.parse(expr, mode="eval"))
            if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    assert "请选择管理单元 0021 0451 1031" in lits, f"needle 没做空白归一化：{lits!r}"
    assert not any("\n" in x for x in lits), f"needle 里仍含换行 ⇒ 定位会失败：{lits!r}"
    compile(f"lambda p: p.{expr}", "<gen>", "eval")


def test_no_raw_interpolation_into_quotes_in_generator():
    """② 源码守门：不许再出现把 `{it[...]}` 直接塞进引号的裸拼写法。"""
    src = (REPO / "framework" / "tools" / "generate" / "generator.py").read_text(
        encoding="utf-8", errors="replace"
    )
    # 允许 `!r`（repr，安全）；禁止 `"...{it[..."` 与 `'{it[...'` 这种裸塞
    bad = []
    for m in re.finditer(r"""(f["'])((?:[^"'\n]|\\.)*?)\{it\[[^}]*\}((?:[^"'\n]|\\.)*?)\1""", src):
        seg = m.group(0)
        if "!r" in seg:
            continue
        bad.append(seg.strip()[:120])
    assert not bad, (
        "generator.py 里仍有把数据裸拼进引号的写法（数据含引号/换行就会生成非法代码）：\n  - "
        + "\n  - ".join(bad)
        + "\n请改用 _py_str()。"
    )
