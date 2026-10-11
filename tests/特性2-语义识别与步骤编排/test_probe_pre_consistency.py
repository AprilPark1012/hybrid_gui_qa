# -*- coding: utf-8 -*-
"""特性2 · `probe_pre` 与场景声明**强制一致**契约（P25 片 0 · 判据先行，V8.5）

## 口径（AprilPark1012 2026-10-11 拍定，D9 / D10 / D11）

**场景声明是唯一权威**，用例里的 `probe_pre` 只能是它的**逐字副本（有序）**：

- **D9**：不一致 -> **硬红**（拒产、exit 2），**不给任何"忽略/放行/只警告"开关**；文案要指出「第 N 步：用例 X != 场景 Y」。
- **D10**：场景声明了 `probe_pre` 却**没给** `probe_pre_host`（前置在哪一页跑）-> **硬红**。
  机制：`probe_pre_host: <页名>` 引用 `pages[].name`；**取代框架现在用 `"login"`/`"登录"` 猜 host 的做法**
  （generator.py:1234），保证框架层零业务词。
- **D11**：用例分两类 —— 绑定场景的（带 `scenario_id`）必须逐字一致；
  **独立于场景的（不带 `scenario_id`）**可自带 `probe_pre`，但**必须带 `probe_pre_fingerprint` 自证**。

顺序敏感：`[A, B]` 与 `[B, A]` 判为**不一致**（前置是序列：先点开菜单才能点子项）。

## 现状（片 0 基线，本判据**应当红**）

- 场景 yml **没有** `probe_pre_host` 字段，加载时也不校验；
- 没有"用例 vs 场景"的一致性判定入口；
- 手搓用例带 `probe_pre` 但**没有** `probe_pre_fingerprint`（无同步保护）。

## 契约面（新建能力，判据锁的是**契约名与行为**，不是实现）

`framework.features.f02_semantic.scenario_generate` 需提供纯函数：

    probe_pre_conflicts(case: dict, scenario) -> list[str]
        返回空列表 = 一致；非空 = 逐条差异说明（含第几步、两边各是什么）。

保持"不依赖浏览器、可在秒级一类判据里跑"。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from framework.features.f02_semantic.scenario_generate import ScenarioError, load_scenario_file

REPO = Path(__file__).resolve().parents[2]

MIN_YML = """id: p25_probe_pre_case
scenario: |
  打开列表页，点一下搜索。
probe_pre:
  - 超
  - 切换为订单管理员
pages:
  - name: 列表页
    url: http://host/list.html
"""


def _write(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "p25_probe_pre_case.yml"
    p.write_text(text, encoding="utf-8")
    return p


def test_missing_probe_pre_host_is_rejected(tmp_path):
    """D10：声明了 probe_pre 却没给 probe_pre_host -> 必须硬红（ScenarioError）。"""
    p = _write(tmp_path, MIN_YML)
    with pytest.raises(ScenarioError) as ei:
        load_scenario_file(p)
    assert "probe_pre_host" in str(ei.value), (
        f"报错文案必须点名缺失的字段 probe_pre_host；实际：{ei.value}")


def test_probe_pre_host_must_reference_declared_page(tmp_path):
    """probe_pre_host 必须是 pages 里声明过的页名（写错 -> 硬红）。"""
    p = _write(tmp_path, MIN_YML.replace(
        "pages:", "probe_pre_host: 不存在的页\npages:"))
    with pytest.raises(ScenarioError) as ei:
        load_scenario_file(p)
    assert "页名" in str(ei.value) or "page" in str(ei.value).lower(), (
        f"报错必须说明页名对不上；实际：{ei.value}")


def test_probe_pre_host_valid_is_accepted(tmp_path):
    """正向：页名对得上时场景必须能正常加载（防止判据只会报错）。"""
    p = _write(tmp_path, MIN_YML.replace(
        "pages:", "probe_pre_host: 列表页\npages:"))
    sc = load_scenario_file(p)
    assert sc.probe_pre == ["超", "切换为订单管理员"]


def test_consistency_entry_exists():
    """D9：必须存在不依赖浏览器的一致性判定入口。"""
    from framework.features.f02_semantic import scenario_generate as sc_mod
    fn = getattr(sc_mod, "probe_pre_conflicts", None)
    assert callable(fn), (
        "缺一致性判定入口 scenario.probe_pre_conflicts(case, scenario) -> list[str]；"
        "generate 与一类判据都要用它（唯一入口，不许各写一份）")


def test_inconsistent_probe_pre_is_reported(tmp_path):
    """D9：用例与场景不一致 -> 必须报出差异（含第几步）。"""
    from framework.features.f02_semantic import scenario_generate as sc_mod
    fn = getattr(sc_mod, "probe_pre_conflicts", None)
    if not callable(fn):
        pytest.fail("probe_pre_conflicts 未实现（见上一条）")
    sc = load_scenario_file(_write(tmp_path, MIN_YML.replace(
        "pages:", "probe_pre_host: 列表页\npages:")))
    diff = fn({"case_id": "x", "probe_pre": ["超"]}, sc)
    assert diff, "用例少了一步（超）却没有报出差异 -> 前置会在错误状态下执行"


def test_order_matters(tmp_path):
    """顺序敏感：颠倒顺序也算不一致。"""
    from framework.features.f02_semantic import scenario_generate as sc_mod
    fn = getattr(sc_mod, "probe_pre_conflicts", None)
    if not callable(fn):
        pytest.fail("probe_pre_conflicts 未实现（见上文）")
    sc = load_scenario_file(_write(tmp_path, MIN_YML.replace(
        "pages:", "probe_pre_host: 列表页\npages:")))
    diff = fn({"case_id": "x", "probe_pre": ["切换为订单管理员", "超"]}, sc)
    assert diff, "顺序颠倒必须判为不一致（先点开菜单才能点子项）"


def test_extra_probe_pre_also_reported(tmp_path):
    """用例多写了一步（场景里没有）同样是不一致。"""
    from framework.features.f02_semantic import scenario_generate as sc_mod
    fn = getattr(sc_mod, "probe_pre_conflicts", None)
    if not callable(fn):
        pytest.fail("probe_pre_conflicts 未实现（见上文）")
    sc = load_scenario_file(_write(tmp_path, MIN_YML.replace(
        "pages:", "probe_pre_host: 列表页\npages:")))
    diff = fn({"case_id": "x", "probe_pre": ["超", "切换为订单管理员", "多点一下"]}, sc)
    assert diff, "用例多出的前置步骤也必须报出来（否则执行期会做场景没声明的事）"


def test_no_escape_hatch_flag():
    """D9：不许有"忽略不一致"的逃生开关。"""
    from framework.features.f10_cli import cli   # P25 片 8：patch 要打在**真实现**上（framework.cli 现在是转发薄壳）
    flags = set(getattr(cli, "FLAG_SPECS", {}))
    bad = {f for f in flags if "stale" in f or "allow-pre" in f or "ignore-pre" in f}
    assert not bad, f"不允许出现放行开关（{sorted(bad)}）；口径是硬红、无逃生口"


def test_standalone_case_needs_fingerprint():
    """D11：独立于场景的用例（无 scenario_id）必须带 probe_pre_fingerprint 自证。"""
    cases = sorted((REPO / "cases").rglob("*.json"))
    if not cases:
        pytest.skip("仓库里没有用例文件")
    bad = []
    for f in cases:
        d = json.loads(f.read_text(encoding="utf-8"))
        if d.get("scenario_id"):
            continue                       # 绑定场景的 -> 走"逐字一致"那条判据
        if d.get("probe_pre") and not d.get("probe_pre_fingerprint"):
            bad.append(f.relative_to(REPO).as_posix())
    assert not bad, (
        "独立于场景的用例自带 probe_pre 时必须带 probe_pre_fingerprint（防悄悄漂移）：" + ", ".join(bad))


def test_generator_uses_declared_host_not_business_words():
    """D10 配套：框架层不许再用业务词猜前置 host。"""
    src = (REPO / "framework" / "features" / "f02_semantic" / "generator_generate.py").read_text(
        encoding="utf-8", errors="replace")
    assert '"login" in _u.lower()' not in src and '"\u767b\u5f55" in _n' not in src, (
        "generator 仍在用 login/登录 猜前置 host（业务词进框架层）；" 
        "应改为读场景的 probe_pre_host")
