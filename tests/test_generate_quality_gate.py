"""映射质量闸的回归测试（V7.5.1，配套 2026-09-15 交付事故）。

事故：现场 probe 不可用时（目标没起 / OOM / 探测失败），`generate` 只打**一句警告**就继续落盘，
产出「16 个用例、每步都是 `pytest.fail(元素未映射)`」的垃圾产物，而且 **exit 0** ——
它被提交、被打包、被交付，直到慢目标闸门跑起来才炸成 50 条失败，真因已无处可查。

本文件用**假 playwright 模块**让探测必失败：不启 Chromium（秒级、零内存风险），
断言「拿不到定位就别产出产物」这条口径真的生效，以及 `--allow-unmapped` 这个显式逃生口仍可用。

跑法（秒级，不需要 demo、不需要浏览器）：
    cd ~/hybrid_gui_qa && source .venv/bin/activate
    python -m pytest tests/test_generate_quality_gate.py -v
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from framework import cli
from framework.tools.generate.generator import UnmappedElementsError, generate_scripts      # noqa: E402

CASES = REPO / "cases"


@pytest.fixture
def probe_down(monkeypatch):
    """把 `playwright.sync_api` 换成「一调 `sync_playwright()` 就抛」的假模块 ⇒ 现场 probe 必失败。"""
    fake = types.ModuleType("playwright.sync_api")

    def _boom(*a, **k):
        raise RuntimeError("模拟：目标连不上 / 探测不可用（ERR_CONNECTION_REFUSED）")

    setattr(fake, "sync_playwright", _boom)
    setattr(fake, "Page", type("Page", (), {}))     # framework.tools.probe.probe 模块级 `from ... import Page`
    setattr(fake, "expect", lambda *a, **k: None)
    setattr(fake, "__getattr__", lambda name: type(name, (), {}))   # 其余名字给哑类
    pkg = types.ModuleType("playwright")
    setattr(pkg, "sync_api", fake)
    monkeypatch.setitem(sys.modules, "playwright", pkg)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", fake)
    return fake


def test_generate_refuses_to_write_when_probe_unavailable(probe_down, tmp_path):
    """探测不可用 ⇒ 抛 UnmappedElementsError，且 **test_cases.py / conftest.py 一个都不许落盘**。"""
    out = tmp_path / "scripts"
    with pytest.raises(UnmappedElementsError) as ei:
        generate_scripts(cases_dir=CASES, scripts_dir=out)

    assert ei.value.missing, "闸门必须带上「缺了哪些语义名」的清单"
    assert ei.value.probe_error and "RuntimeError" in ei.value.probe_error, \
        "闸门必须带上现场 probe 的失败原因（否则排查又要靠猜）"
    assert not (out / "test_cases.py").exists(), "拿不到定位时绝不允许产出测试脚本"
    assert not (out / "conftest.py").exists()


def test_allow_unmapped_still_writes_with_stubs(probe_down, tmp_path):
    """显式 `allow_unmapped=True` 才放行 —— 产物里会有 pytest.fail 存根，且在结果里如实报告。"""
    out = tmp_path / "scripts"
    res = generate_scripts(cases_dir=CASES, scripts_dir=out, allow_unmapped=True)

    tc = (out / "test_cases.py").read_text(encoding="utf-8")
    assert tc.count("元素未映射") > 0
    assert res["unmapped"], "结果里必须带上未映射清单（调用方可据此告警）"
    assert res["probe_error"] and "RuntimeError" in res["probe_error"]


def test_normal_run_reports_zero_unmapped(probe_down, tmp_path, monkeypatch):
    """探测「成功」时（这里用假模块给一份能对齐的最小清单）未映射必须为 0 且正常落盘。

    目的：证明闸门只在**真有缺口**时才拦 —— 别把正常生成也误杀。
    """
    from framework.tools.generate import generator

    real_needed = {st.get("element") for c in _load_cases() for st in c.get("steps", [])}
    real_needed |= {a.get("element") for c in _load_cases() for a in c.get("asserts", [])}
    real_needed.discard(None)
    real_needed.discard("")

    # 造一份「覆盖全部所需语义名」的快照 ⇒ 映射齐全 ⇒ 不需要现场 probe
    snap = tmp_path / "element_map_full.json"
    snap.write_text(_element_map_json(real_needed), encoding="utf-8")

    out = tmp_path / "scripts"
    res = generate_scripts(cases_dir=CASES, scripts_dir=out, element_map_path=snap)

    assert res["unmapped"] == []
    assert (out / "test_cases.py").exists()


def test_cli_generate_exits_2_with_actionable_message(probe_down, tmp_path, monkeypatch, capsys):
    """CLI 层：退出码必须是 2（不是 0/1），并明说「先起 demo」与逃生口（人话，不是 traceback）。

    ⚠️ 这里把「可达性预检」也钉成「不可达」：否则本机 demo 正在跑时，消息会走「目标可达」分支，
    断言就失真了（测试要点是**目标没起**时的那段话）。
    """
    monkeypatch.setattr("framework.tools.generate.generator.SCRIPTS_DIR", tmp_path / "scripts")
    monkeypatch.setattr("framework.tools.common.target_probe.reachability",
                        lambda url=None, timeout=1.5: (False,
                                                       "连不上 http://localhost:8000（ConnectionRefused）"
                                                       "⇒ 被测目标没起：另开一个窗口跑 `python -m demo.app`"))

    with pytest.raises(SystemExit) as si:
        cli.cmd_generate([])
    assert si.value.code == 2, "生成期拿不到定位必须非 0 退出（旧行为是 exit 0）"

    out = capsys.readouterr().out
    assert "映射质量闸" in out
    assert "demo.app" in out, "要给出下一步动作，不能只说『失败了』"
    assert "--allow-unmapped" in out, "要告诉用户逃生口叫什么"
    assert not (tmp_path / "scripts" / "test_cases.py").exists()


def _load_cases():
    import json
    return [json.loads(f.read_text(encoding="utf-8")) for f in sorted(CASES.glob("*.json"))]


def _element_map_json(names) -> str:
    """造一份「覆盖全部所需语义名」的 element_map（explore 产物格式：{"steps":[{"element":{…}}]}）。"""
    import json
    return json.dumps(
        {"steps": [{"element": {"semantic_name": n, "role": "button", "name": n}}
                   for n in sorted(names)]},
        ensure_ascii=False)
