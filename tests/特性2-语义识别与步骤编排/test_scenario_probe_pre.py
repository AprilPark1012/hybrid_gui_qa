# -*- coding: utf-8 -*-
"""特性2 · 场景级探测前置 `probe_pre`（2026-10-10 · A 方案 S1）。

背景（实测链条）：探测期若没切到业务身份，详情页「编辑」是置灰(aria-disabled) ->
    `[explore] [!] [订单详情页] 前置动作「编辑」执行失败（TimeoutError ...）`
    -> 编辑态控件采不到 -> AI 拿不到行内字段语义名 -> 行必填填不了 -> 保存无效
    -> 提交被前端静默拒绝 -> 订单永远到不了「已关闭」（等待给多大都白等）。
所以必须有「**探测期一开始就要处的状态**」这一层声明；它与页面级 `pages[].pre`
是**两个层级、同一个执行引擎**（`_run_pre_actions`）—— 不是第二套机制。
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

REPO = Path(__file__).resolve().parents[2]
ORDERS = REPO / "scenarios" / "orders" / "orders_invoice_full_lifecycle.yml"


def _scenario_from_text(tmp_path: Path, extra: str):
    from framework.tools.generate.scenario import load_scenario_file
    f = tmp_path / "s.yml"
    f.write_text("id: t" + chr(10) + "title: t" + chr(10) + extra + chr(10)
                 + "scenario: |" + chr(10) + "  打开列表页看订单。" + chr(10), encoding="utf-8")
    return load_scenario_file(f)


def test_probe_pre_is_parsed(tmp_path):
    sc = _scenario_from_text(tmp_path, "probe_pre:" + chr(10) + "  - 切换为订单管理员")
    assert sc.probe_pre == ["切换为订单管理员"], f"probe_pre 没解析出来：{sc.probe_pre!r}"


def test_probe_pre_absent_is_empty(tmp_path):
    sc = _scenario_from_text(tmp_path, "notes: 无前置")
    assert sc.probe_pre == [], "没声明时必须是空列表（缺省行为与改造前一致）"


def test_probe_pre_must_be_list(tmp_path):
    from framework.tools.generate.scenario import ScenarioError
    try:
        _scenario_from_text(tmp_path, "probe_pre: 切换为订单管理员")
    except ScenarioError:
        return
    raise AssertionError("probe_pre 不是列表时应当报错（否则会静默当字符串逐字符处理）")


def test_orders_scenario_declares_probe_pre():
    """守门：本条业务链要靠它才能采到编辑态控件 —— 谁把它删了必须立刻红。"""
    from framework.tools.generate.scenario import load_scenario_file
    sc = load_scenario_file(ORDERS)
    assert any("订单管理员" in str(x) for x in sc.probe_pre), (
        f"orders 场景没有声明切身份的探测前置：{sc.probe_pre!r}")


def test_probe_pre_is_threaded_to_ai_explore():
    """接线锁：字段必须一路透传到探测入口（少接一处 -> 静默失效，零报错）。"""
    from framework.tools.explore.explorer import ai_explore
    assert "probe_pre" in inspect.signature(ai_explore).parameters


def test_probe_pre_runs_before_scan_in_both_paths():
    """接线锁（源码契约）：场景级前置必须跑在**页面级前置**与 **scan** 之前。

    顺序错了 -> 扫到的是旧权限上下文（置灰态），编辑态控件照样采不到。
    """
    src = (REPO / "framework" / "tools" / "explore" / "explorer.py").read_text(encoding="utf-8")
    code = chr(10).join(l for l in src.splitlines() if not l.strip().startswith("#"))
    # 多页路径：场景级前置 -> 页面级前置 -> scan
    i_pp = code.index("_run_pre_actions(pg, _pp_pending")
    i_page = code.index('_run_pre_actions(pg, spec.get("pre")')
    i_scan = code.index('_sc = scan_page(pg, page_name=spec["name"]')
    assert i_pp < i_page < i_scan, "多页路径顺序不对：场景级前置必须在页面级前置与 scan 之前"
    # 单页路径同款
    i_spp = code.index("_run_pre_actions(pg, probe_pre")
    i_sscan = code.index("_sc = scan_page(pg)", i_spp)
    assert i_spp < i_sscan, "单页路径：场景级前置没跑在 scan 之前"
