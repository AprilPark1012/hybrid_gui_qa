"""V8.7.11 判据：文档 / `--help` 里不许写死「会过时的具体值」。

由来（用户 2026-10-28 确认加这条）：
  `cli --help` 里有这么一条示例 —— `run --debug --case contracts_search_by_no`。
  那个 case **仓库里根本不存在**（`cases/` 下只有 `orders_invoice_full_lifecycle`）。
  更根本的问题：真实 case id **带时间戳**（`ai_xxx_161243`），每次生成都变
  所以 **写死任何一个具体 id 都注定过时**。

  这是那条老原则的又一次现形：**不拿「观测到的具体值」当地基**。
  示例命令应该用占位符（`--case <case_id>`）并说明取值来源。

判据边界（**宁漏不误伤**）：
  · 写死的值**不存在** -> 红（这是实打实的错，读者照敲就报错）
  · 写死的值**带时间戳**（6 位 HHMMSS 尾） -> 红（下次生成就变，必然过时）
  · 写死的值存在且稳定 -> **不红**（可能确实是个好例子），但用 assert 的 message 提醒
  · `<case_id>` / `<场景>` / `…` 这类占位符 -> 合法
"""
from __future__ import annotations

import re
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]

# 扫这些地方：README（引导文档）+ cli.py（`--help` 的 docstring 来源）
DOC_SOURCES = [
    BASE / "README.md",
    BASE / "framework/features/f10_cli/cli.py",
]

# --case 后面跟的那个值
CASE_ARG_RE = re.compile(r"--case\s+([^\s`'\"]+)")
# 只把「长得像 case id」的值纳入检查：纯 ASCII 标识符。
# 排除中文说明（如 `--case 可重复；case_id = …` 里的「可重复；case_id」）——
# 那是人话，不是示例值，误伤了只会让人为了过判据去改写说明文字。
ID_LIKE_RE = re.compile(r"^[A-Za-z0-9_.\-]+$")
# 占位符形态：整体 <...>、单字母泛指（文档里用 --case a --case b 说明「可重复」）、或含占位标记
PLACEHOLDER_RE = re.compile(r"^<.+>$|^…$|^\.\.\.$|^\{.+\}$|^x+$|^[A-Za-z]$")
PLACEHOLDER_ANY_RE = re.compile(r"[<>{…]")
# 带时间戳：ai_<name>_<6位数字>
TS_SUFFIX_RE = re.compile(r"_\d{6}$")


def _real_case_ids() -> set[str]:
    """磁盘上真实存在的 case id（cases/**/ai_*.json 的 stem）。"""
    return {p.stem for p in (BASE / "cases").rglob("ai_*.json")}


def _scan() -> list[tuple[str, str, str]]:
    """返回 [(文件, 写死的值, 为什么算问题)]。"""
    real = _real_case_ids()
    problems: list[tuple[str, str, str]] = []
    for path in DOC_SOURCES:
        if not path.exists():
            continue
        rel = path.relative_to(BASE).as_posix()
        txt = path.read_text(encoding="utf-8")
        for m in CASE_ARG_RE.finditer(txt):
            val = m.group(1).strip()
            if not ID_LIKE_RE.match(val):
                continue                      # 中文说明等，不是示例值
            if PLACEHOLDER_RE.match(val) or PLACEHOLDER_ANY_RE.search(val):
                continue                      # 占位符合法（含 ai_xxx_<时间戳> 这种中段占位）
            if TS_SUFFIX_RE.search(val):
                problems.append((rel, val, "带时间戳，下次生成就变（必然过时）"))
            elif val not in real:
                problems.append((rel, val, f"仓库里不存在这个 case（真实的有 {sorted(real)}）"))
    return problems


def test_no_dead_case_id_in_docs_and_help() -> None:
    """`--case` 示例里写死的 case id 必须真实存在，且不许带时间戳。"""
    problems = _scan()
    assert not problems, (
        "文档 / `--help` 里的 --case 示例写死了会过时的具体值：\n  "
        + "\n  ".join(f"{rel}: --case {val}  -> {why}" for rel, val, why in problems)
        + "\n\n修法：改用占位符 `--case <case_id>`，并在旁边说明取值来源"
          "（如「case_id = cases/ 里的文件名」）。"
    )


def test_placeholder_form_is_actually_used() -> None:
    """正向自证：**必须真的用占位符**，不能靠「把示例删光」蒙混过第一条。

    否则第一条判据可以被「一个 --case 示例都不写」轻松满足 —— 那是把能力藏起来，
    不是修好。要求 README 与 cli.py 各自至少有一处 `--case <...>` 形式的说明。
    """
    for path in DOC_SOURCES:
        if not path.exists():
            continue
        rel = path.relative_to(BASE).as_posix()
        txt = path.read_text(encoding="utf-8")
        hits = [v for v in CASE_ARG_RE.findall(txt) if PLACEHOLDER_RE.match(v.strip())]
        assert hits, f"{rel} 里一处 `--case <case_id>` 式说明都没有 —— 别用删示例来糊弄判据"
