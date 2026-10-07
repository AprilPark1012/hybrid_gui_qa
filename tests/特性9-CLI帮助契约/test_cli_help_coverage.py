"""`--help` 契约：新增子命令 / 参数必须**自动**出现在总览里（2026-09-28 新增）。

现场起因：总览（`python -m framework.cli --help`）只列了子命令**名字**，
V8.2.x 之后加的参数（`--llm-cassette` / `--only` / `--forced` 系列 / `--keep-runs` /
`--force-browser` …）在总览里**一个都看不到** ⇒ 新人只能翻代码才知道能带什么。
旧判据（`test_help_overview_lists_all_commands`）只断言「命令名出现在输出里」，
所以这类漂移**永远不会被抓到** —— 这就是它漂了这么久的原因。

判据口径（四条）：
  ① 总览必须**逐条**列出每个子命令 + 它**全部**可用参数（与 `CMD_FLAGS` 同源，不许手写第二份）；
  ② 参数清单由代码生成 ⇒ 新增命令/参数**不改文案**就会出现在总览里（机制自证）；
  ③ 反向：模块 docstring 里的示例**不许出现** `FLAG_SPECS` 里不存在的参数
     （防「文档写了不存在的参数」这种反向漂移）；
  ④ 判据自身先做负向证明 —— 漏一个 flag 的文本必须被判据判定为缺口（否则等于没写）。

跑法：
    python -m pytest tests/特性9-CLI帮助契约/test_cli_help_coverage.py -q
（秒级、不需要被测 demo、不需要 key）
"""
from __future__ import annotations

import re
import subprocess
import sys

import pytest

from framework.cli import CMD_FLAGS, FLAG_SPECS, REMOVED_FLAGS, _CMD_FUNCS, _print_help
from framework.tools.common.text_io import utf8_env

# `--help` / `--version` 由 main() 在校验之前拦截，不在 FLAG_SPECS 里 ⇒ 单独放行
_UNIVERSAL_FLAGS = {"--help", "--version"}


def _cli(*args: str) -> subprocess.CompletedProcess:
    """跑真实 CLI（只碰参数层，任何分支都在开浏览器之前 return）。"""
    return subprocess.run([sys.executable, "-m", "framework.cli", *args],
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          env=utf8_env(), timeout=60)


# ---------- 解析器（判据自己的「读 help」口径，供负向证明一起用）----------
_CMD_LINE = re.compile(r"^  (\S+)\s+(.+)$")          # 两个空格缩进 = 子命令条目
_ARGS_LINE = re.compile(r"^\s+参数[：:]\s*(.*)$")


def _parse_overview(text: str) -> dict[str, set[str]]:
    """把总览文本解析成 {子命令: {参数}}。

    只认「两空格缩进的行 + 紧邻的『参数：』行」这一种形态 ⇒ 文案变了判据就红
    （这正是我们要守的：参数清单必须在总览里**结构化**地出现，而不是散落在说明文字里）。
    """
    parsed: dict[str, set[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        m = _ARGS_LINE.match(line)
        if m and current:
            body = m.group(1).strip()
            parsed[current] = set() if body in ("", "(无参数)") else set(body.split())
            continue
        m = _CMD_LINE.match(line)
        if m and m.group(1) in CMD_FLAGS:
            current = m.group(1)
            parsed.setdefault(current, None)      # type: ignore[arg-type]
        elif line.strip() and not line.startswith(" "):
            current = None                        # 段落结束（正文行）
    return {k: (v or set()) for k, v in parsed.items()}


def _gaps(parsed: dict[str, set[str]]) -> list[str]:
    """把「注册表 ⇄ 总览」的差异报成人话（判据与负向证明共用同一口径）。"""
    out: list[str] = []
    for cmd, flags in CMD_FLAGS.items():
        got = parsed.get(cmd)
        if got is None:
            out.append(f"{cmd}: 总览里没有这个子命令（或没给出结构化的『参数：』行）")
            continue
        missing, extra = sorted(flags - got), sorted(got - flags)
        if missing:
            out.append(f"{cmd}: 总览漏了参数 {missing}")
        if extra:
            out.append(f"{cmd}: 总览列了未注册的参数 {extra}")
    return out


# ---------- ① 总览逐条列出「子命令 + 全部参数」----------
@pytest.mark.parametrize("cmd", sorted(CMD_FLAGS))
def test_overview_lists_command_with_all_its_flags(cmd):
    r = _cli("--help")
    assert r.returncode == 0
    parsed = _parse_overview(r.stdout)
    assert cmd in parsed, f"总览里没有 {cmd} 的结构化条目；实际解析到：{sorted(parsed)}"
    assert parsed[cmd] == set(CMD_FLAGS[cmd]), (
        f"{cmd} 的参数清单与注册表不一致：总览={sorted(parsed[cmd])} 注册表={sorted(CMD_FLAGS[cmd])}")


def test_overview_has_no_undocumented_command():
    """反向：总览里列出的每个命令都必须是注册表里的（防陈旧命令名留在文案里）。"""
    parsed = _parse_overview(_cli("--help").stdout)
    unknown = sorted(set(parsed) - set(CMD_FLAGS))
    assert not unknown, f"总览里出现了未注册的子命令：{unknown}"


def test_overview_covers_every_registered_flag():
    """全集口径：注册表里的每个参数都必须在总览里露面（一条都不许漏）。"""
    parsed = _parse_overview(_cli("--help").stdout)
    gaps = _gaps(parsed)
    assert not gaps, "总览与参数注册表不一致：\n  - " + "\n  - ".join(gaps)


# ---------- ② 机制自证：注册即显示（不用改文案）----------
def test_new_command_and_flag_show_up_without_editing_help_text(monkeypatch, capsys):
    """造一个假子命令 + 假参数 ⇒ 总览必须**自动**带上它。

    这条是「新增命令必须刷新 --help」的机制保证：help 由注册表生成，
    所以**漂移在结构上不可能发生**；人只需要写函数 docstring（一句话说明）。
    """
    def cmd_frobnicate(rest=None):            # noqa: ANN001
        """frobnicate 一句话说明（机制自证用）。"""

    monkeypatch.setitem(CMD_FLAGS, "frobnicate2", {"--zzz-flag"})
    monkeypatch.setitem(FLAG_SPECS, "--zzz-flag", "value")
    monkeypatch.setitem(_CMD_FUNCS, "frobnicate2", cmd_frobnicate)
    try:
        _print_help()
        out = capsys.readouterr().out
        assert "frobnicate2" in out, "新增子命令没有自动出现在总览里"
        assert "--zzz-flag" in out, "新增参数没有自动出现在总览里"
    finally:
        CMD_FLAGS.pop("frobnicate2", None)
        FLAG_SPECS.pop("--zzz-flag", None)
        _CMD_FUNCS.pop("frobnicate2", None)


# ---------- ③ 反向：docstring 里不许写不存在的参数 ----------
def test_docstring_examples_only_use_real_flags():
    import framework.cli as cli_mod
    doc = cli_mod.__doc__ or ""
    used = set(re.findall(r"--[A-Za-z][A-Za-z0-9-]*", doc))
    unknown = sorted(used - set(FLAG_SPECS) - set(REMOVED_FLAGS) - _UNIVERSAL_FLAGS)
    assert not unknown, (f"模块 docstring 里写了不存在的参数 {unknown}；"
                         f"真实参数见 FLAG_SPECS（防『示例教坏新人』）")


# ---------- ④ 子命令级 help（守住既有能力，别改坏）----------
@pytest.mark.parametrize("cmd", sorted(CMD_FLAGS))
def test_subcommand_help_lists_all_its_flags(cmd):
    r = _cli(cmd, "--help")
    assert r.returncode == 0
    missing = sorted(f for f in CMD_FLAGS[cmd] if f not in r.stdout)
    assert not missing, f"{cmd} --help 漏了参数：{missing}"


# ---------- 判据自身的负向证明 ----------
def test_negative_parser_flags_a_missing_flag():
    """喂一段「少一个参数」的总览文本 ⇒ 判定必须报出缺口（防判据写成恒真）。"""
    good = "子命令：\n  generate  读用例生成脚本。\n            参数：--changed --force --only\n"
    gaps = [g for g in _gaps(_parse_overview(good)) if g.startswith("generate:")]
    assert gaps == ["generate: 总览漏了参数 %s" % sorted(
        set(CMD_FLAGS["generate"]) - {"--changed", "--force", "--only"})]


def test_negative_parser_flags_a_stale_flag():
    """喂一段「多一个假参数」的文本 ⇒ 也必须被抓（防只查漏、不查多）。"""
    bad = "子命令：\n  generate  说明。\n            参数：--changed --force --only --ghost\n"
    gaps = [g for g in _gaps(_parse_overview(bad)) if g.startswith("generate:")]
    assert any("--ghost" in g for g in gaps), f"假参数没被抓：{gaps}"
