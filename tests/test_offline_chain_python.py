"""离线一键脚本的「解释器选择」判据（一类 · 秒级 · 不需要真实依赖）。

为什么要有它：2026-09-21 现场反馈 —— 在 Windows 上按文档敲
r9-legacy-ok（下一行是**当时用户照文档敲的旧命令原文**，用来还原现场；
V8.0 已把仓库根 tools/ 改名成 build_tools/ —— 这里刻意保留旧写法，请勿「顺手修」成新路径）
`python tools/offline_explore_chain.py --repo . --run`，脚本报
`[FAIL] 这个解释器缺依赖：No module named 'dotenv'`，而用户 `pip list` 里明明有 dotenv，
手动三步（explore / generate / run）却都能跑通。
根因：脚本**只挑一个解释器就判死** —— 探测 `.venv/{bin,Scripts}` 两个固定位置，没命中就默默退回
「跑脚本的那个解释器」（在 Windows 上常是系统 python，没装项目依赖），然后只甩一句「缺依赖」。
用户看到的因此是「框架坏了/依赖没装」，而不是「你该换个解释器跑」。

本判据锁住修复后的两个语义（都用注入的假 probe，与真实环境解耦）：
  ① **候选逐个探测**：第一个可用就用；不可用就继续试下一个 —— 最终选到能用的那个；
  ② **显式指定不偷换**：`--python` / `HYBRID_PYTHON` 指了某个解释器，它缺依赖就必须停手报错，
     绝不静默换一个「能跑的」（否则用户以为在跑 A、实际跑的是 B）。
外加：全候选都不可用时，诊断清单必须覆盖**每一个**候选（不能只说最后一个）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "build_tools"))
import offline_explore_chain as chain          # noqa: E402


def _probe_factory(ok_cmds):
    """造一个假 probe：只有命令行匹配 ok_cmds 里的前缀才算「可用」。"""
    calls = []

    def probe(cmd):
        calls.append(list(cmd))
        joined = " ".join(cmd)
        for good in ok_cmds:
            if joined.startswith(good):
                return True, "deps-ok"
        return False, "ModuleNotFoundError: No module named 'dotenv'"
    return probe, calls


# ---------------- 候选清单的契约 ----------------

def test_candidates_priority_order(tmp_path):
    """优先级：显式指定 → 仓库 venv → 当前进程解释器 → PATH → (Windows) py -3。"""
    (tmp_path / ".venv" / "bin").mkdir(parents=True)
    (tmp_path / ".venv" / "bin" / "python").write_text("", encoding="utf-8")
    srcs = [s for s, _ in chain.python_candidates(tmp_path, explicit="/usr/bin/env python9")]
    assert srcs[0].startswith("--python"), srcs
    assert srcs[1].startswith("仓库 venv"), srcs
    assert any("当前进程" in s for s in srcs), srcs
    assert any("PATH" in s for s in srcs), srcs


def test_candidates_without_venv(tmp_path):
    """仓库没 venv 时不该出现 venv 候选（也不该崩）。"""
    srcs = [s for s, _ in chain.python_candidates(tmp_path)]
    assert not any("仓库 venv" in s for s in srcs), srcs


# ---------------- ① 逐个探测（本次修复的核心）----------------

def test_first_candidate_ok(tmp_path):
    vpy = tmp_path / ".venv" / "bin" / "python"
    vpy.parent.mkdir(parents=True)
    vpy.write_text("", encoding="utf-8")
    probe, calls = _probe_factory([str(vpy)])
    cmd, src, tried = chain.pick_python(tmp_path, probe=probe)
    assert cmd == [str(vpy)] and "仓库 venv" in src
    assert len(calls) == 1, "第一个就可用，不该再试别的"


def test_falls_through_to_later_candidate(tmp_path):
    """★ 核心：跑脚本的解释器缺依赖时，必须继续试后面的候选（而不是当场判死）。"""
    (tmp_path / ".venv" / "bin").mkdir(parents=True)
    (tmp_path / ".venv" / "bin" / "python").write_text("", encoding="utf-8")
    probe, calls = _probe_factory(["python3"])                   # 只有 PATH 上的 python3 可用
    cmd, src, tried = chain.pick_python(tmp_path, probe=probe)
    assert cmd == ["python3"], f"应选到 python3，实际 {cmd}"
    assert "PATH" in src
    assert len(calls) >= 2, "应该试过至少两个候选"
    assert any(not good for _, _, good, _ in tried[:-1]), "失败过的候选要留在诊断清单里"


# ---------------- ② 显式指定不偷换（负向）----------------

def test_explicit_unavailable_stops_immediately(tmp_path):
    """★ 负向：显式指定的解释器缺依赖 ⇒ 立刻停，不许换别的（只探测 1 次）。"""
    probe, calls = _probe_factory(["/usr/bin/python3"])          # 别的候选可用，但显式指定的不可用
    cmd, src, tried = chain.pick_python(tmp_path, explicit="/bad/python", probe=probe)
    assert cmd is None, f"显式指定不可用时必须返回 None，实际 {cmd}"
    assert len(calls) == 1, f"只应探测显式指定那一个，实际探测了 {len(calls)} 次"
    assert tried[0][0].startswith("--python")


def test_explicit_available_is_used(tmp_path):
    probe, _ = _probe_factory(["/good/python"])
    cmd, src, _ = chain.pick_python(tmp_path, explicit="/good/python", probe=probe)
    assert cmd == ["/good/python"] and src.startswith("--python")


# ---------------- 全失败：诊断必须覆盖每个候选 ----------------

def test_all_candidates_fail_reports_every_candidate(tmp_path):
    probe, calls = _probe_factory([])                            # 全部不可用
    cmd, src, tried = chain.pick_python(tmp_path, probe=probe)
    assert cmd is None and src == ""
    assert len(tried) == len(calls) >= 3, f"候选 {len(calls)} 个，诊断只列了 {len(tried)}"
    assert all(not good for _, _, good, _ in tried)
    assert all(why for _, _, _, why in tried), "每个失败候选都要有原因（否则用户没法判断）"


def test_explicit_cmd_splitting_handles_multi_word():
    """`py -3` 这种带参数的解释器描述要能拆成命令行（Windows 场景）。"""
    assert chain._split_cmd("py -3") == ["py", "-3"]
    assert chain._split_cmd("/usr/bin/python3") == ["/usr/bin/python3"]


# ---------------- 真实探测（环境相关，缺环境就 SKIP 不当通过）----------------

def test_probe_deps_on_repo_venv_if_present():
    venv = REPO / ".venv" / "bin" / "python"
    if not venv.exists():
        pytest.skip("本机没有 <repo>/.venv（跳过真实探测；判据本体已由假 probe 覆盖）")
    good, why = chain.probe_deps([str(venv)], REPO)
    assert good, f"仓库 venv 应依赖齐全，实际：{why}"
