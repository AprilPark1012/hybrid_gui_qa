"""回放模式必须允许「带失败原因」推进到下一轮（V8.7.2 · 2026-10-25）。

背景（真机实测挖出来的缺口）：
    录制期必然先失败一轮、第 2 轮才修好（本项目 orders_invoice_full_lifecycle 就是这样：
    第 1 轮 AI 想不到「两步保存」-> 整单没提交 -> 订单状态不流转 -> 实跑 FAILED；
    第 2 轮带着这条失败原因重生成 -> PASSED）。

    旧实现遇到 replay **一刀切放弃**：
        `if replay: print("重试无意义（回放的是同一份录像）"); break / raise SystemExit(3)`
    它假设「下一轮 prompt 与这一轮逐字相同」，但重试会把本轮失败原因写进 feedback
    -> **prompt 必然是新的**。于是这份录像包**永远回放不通**，而「失败→修复」
    恰恰是最需要在无外网机器上复演的一段（客户机器出问题，没法联网调试）。

本文件锁三条判据：
    1. 回放模式 + 实跑失败 -> **必须进下一轮**（不再直接 exit 3）；
    2. 回放模式 + 产出校验不合格 -> 同样进下一轮（旧的 break 必须消失）；
    3. 回放模式 + 下一轮录像缺失 -> **优雅报缺**（exit 2 + 明话），不是未捕获 traceback
       （CassetteError 与 AiExploreError 是兄弟类，原本只在 cassette 构造阶段被捕获）。

跑法（不需要 key、不需要 demo、秒级）：
    cd ~/hybrid_gui_qa && source .venv/bin/activate && \
        python -m pytest tests/特性8-离线回放/test_replay_allows_retry_rounds.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from framework.features.f08_replay.llm_cassette_explore import CassetteError  # noqa: E402
from framework.features.f10_cli import cli as cli_mod  # noqa: E402

SCENARIO = "在订单列表页搜索订单，然后点开详情看一眼"


def _stub_common(monkeypatch, tmp_path, explore_one, verify):
    """把外部依赖全部换掉：不建产物目录、不探测 demo、不真跑 pytest。

    [!] 回放目录必须**先建出来**（空目录即可）：`Cassette` 构造时对 MODE_REPLAY
        校验 `root.is_dir()`，目录不存在会在进入探索之前就报「离线回放目录不存在」。
    """
    cas = tmp_path / "cas"
    cas.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(cli_mod, "ensure_dirs", lambda: None, raising=False)
    monkeypatch.setattr(cli_mod, "target_url", lambda: "http://localhost:8000", raising=False)
    monkeypatch.setattr(cli_mod, "_explore_one", explore_one, raising=False)
    monkeypatch.setattr(cli_mod, "_verify_cases_detailed", verify, raising=False)
    monkeypatch.setenv("HYBRID_AI_RETRY", "2")
    return cas


def _fake_cpath(tmp_path, name: str) -> Path:
    p = tmp_path / "cases" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{}", encoding="utf-8")
    return p


def test_replay_retries_after_verify_failure(tmp_path, monkeypatch):
    """回放 + 实跑失败 -> 必须带着失败原因进下一轮，而不是直接 exit 3。"""
    calls: list[str] = []

    def fake_explore_one(*a, **kw):
        calls.append(kw.get("retry_feedback", "") or "")
        return (None, _fake_cpath(tmp_path, "ai_demo_000001.json"), [], None)

    verify_calls = {"n": 0}

    def fake_verify(entries):
        verify_calls["n"] += 1
        if verify_calls["n"] == 1:
            return (False, "等待超时：表格第一行 orderStatus 始终不含 '已关闭'")
        return (True, "")

    cas = _stub_common(monkeypatch, tmp_path, fake_explore_one, fake_verify)

    cli_mod.cmd_explore(["--ai", "--scenario", SCENARIO, "--llm-cassette", str(cas)])

    assert verify_calls["n"] == 2, f"实跑校验应当跑 2 轮（失败一次后重试），实际 {verify_calls['n']}"
    assert len(calls) == 2, f"生成应当被调用 2 次（第二轮带失败原因），实际 {len(calls)}"
    assert "已关闭" in calls[1], (
        f"第二轮必须把上一轮的实跑失败原因喂给 AI，实际 feedback={calls[1]!r}")


def test_replay_retries_after_quality_failure(tmp_path, monkeypatch, capsys):
    """回放 + 产出校验不合格（L0）-> 也必须进下一轮，不再 break 后报 NG。"""
    calls: list[str] = []

    def fake_explore_one(*a, **kw):
        calls.append(kw.get("retry_feedback", "") or "")
        qerr = None if len(calls) > 1 else "必定位步骤 element 为空（3 步）"
        return (None, _fake_cpath(tmp_path, "ai_demo_000002.json"), [], qerr)

    cas = _stub_common(monkeypatch, tmp_path, fake_explore_one, lambda entries: (True, ""))

    cli_mod.cmd_explore(["--ai", "--scenario", SCENARIO, "--llm-cassette", str(cas)])

    out = capsys.readouterr().out
    assert len(calls) == 2, f"L0 不合格后应当重试一轮，实际生成次数 {len(calls)}"
    assert "重试无意义" not in out, "旧口径「重试无意义」必须消失（它会掐断失败→修复闭环）"
    assert "回放模式" in out, "回放模式下的重试必须在日志里说明（可审计，不静默）"


def test_replay_missing_next_round_fails_loud_not_traceback(tmp_path, monkeypatch, capsys):
    """回放 + 第二轮录像缺失 -> 优雅报缺（exit 2 + 明话），绝不允许 uncaught traceback。"""
    calls = {"n": 0}

    def fake_explore_one(*a, **kw):
        calls["n"] += 1
        if calls["n"] > 1:
            raise CassetteError("目录 X 里有 1 份录像，但没有一份对应现在的 prompt（键不匹配）")
        return (None, _fake_cpath(tmp_path, "ai_demo_000003.json"), [], None)

    cas = _stub_common(monkeypatch, tmp_path, fake_explore_one,
                       lambda entries: (False, "实跑失败：断言没过"))

    with pytest.raises(SystemExit) as ei:
        cli_mod.cmd_explore(["--ai", "--scenario", SCENARIO, "--llm-cassette", str(cas)])

    assert ei.value.code == 2, f"缺录像应当 exit 2（不是 3、不是 traceback），实际 {ei.value.code}"
    out = capsys.readouterr().out
    assert "回放缺这一轮的录像" in out, f"必须明确说「缺哪一轮」，实际输出：{out[-600:]!r}"
    assert "录像包不完整" in out, f"必须给出可执行下一步（重录完整包），实际输出：{out[-600:]!r}"
