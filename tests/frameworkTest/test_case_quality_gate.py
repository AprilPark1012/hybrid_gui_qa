"""换页证据质量闸（弱 url 断言 = 假绿）的回归测试（2026-09-17，服务目标 ② AI 语义准）。

背景（2026-09-14 实测挖出）：AI 给「点返回列表回到列表页」产的 `expect_url` 只是 `localhost`
—— 而**上一个页面的 URL 也含 localhost** ⇒ 点击后立刻就能通过，「确实换页了」这件事根本没被验到。
当时 AI 提示词甚至**在教 AI 这么写**（「列表页写 localhost 或留空不要写」），所以这是**根因级**修复：
提示词纠正 + 闸门拦 + 历史产物修正，三层一起。

本文件在秒级、不启浏览器下钉住三件事：
 1. **闸门自己不能崩** —— `case_warnings` 遇到结构化断言的期望值（int / 0 / "" / None / 布尔 / 列表）
    以前直接 `TypeError`（守门人倒下 = 等于没守门）；11 种断言 kind × 各种形态都要平安。
 2. **弱证据必须被拦、真证据不许误伤** —— 跨页用例里 host-only 片段 = 红线；详情页独有片段放行；
    单页用例里的 host 断言只告警（手写用例可能是有意的）。
 3. **红线真的会拒绝产物** —— AI 落盘（`elementmap_to_cases_file`）与生成（`_gate_false_green`）
    两条路都拦；外加**仓库现状扫描**：`cases/*.json` 不许再出现弱断言（防历史产物回流）。

跑法（秒级，不需要 demo、不需要浏览器）：
    cd ~/hybrid_gui_qa && source .venv/bin/activate
    python -m pytest tests/frameworkTest/test_case_quality_gate.py -v
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from framework.tools.generate.case_builder import (                                   # noqa: E402
    CaseQualityError,
    case_errors,
    case_warnings,
    elementmap_to_cases_file,
)
from framework.tools.probe.element_map import ElementMap, TestStep as _TestStep          # noqa: E402
from framework.tools.generate.generator import _gate_false_green                      # noqa: E402

CASES = REPO / "cases"

PAGES = [
    {"name": "列表页", "url": "http://localhost:8000/"},
    {"name": "详情页", "url": "http://localhost:8000/contract_detail.html?no=HT-1005"},
]


def _cross(asserts: list[dict]) -> dict:
    """一个跨页用例骨架（列表页 → 详情页），断言由调用方给。"""
    return {
        "case_id": "demo_cross",
        "pages": PAGES,
        "steps": [
            {"op": "goto", "url": "http://localhost:8000/"},
            {"op": "click", "element": "HT_1005"},
        ],
        "asserts": asserts,
    }


# ---------------------------------------------------------------- 1. 闸门自己不能崩
def test_warnings_never_crash_on_structured_expect():
    """11 种断言 kind × 各种期望值形态 ⇒ 质量闸必须给出结论，不许抛异常。

    回归的正是 2026-09-17 实测踩到的：`case_warnings({"asserts":[{"kind":"count","expect":20}]})`
    → `TypeError: expected string or bytes-like object, got 'int'`。
    """
    kinds = ["text", "visible", "hidden", "count", "attr", "value", "url",
             "checked", "unchecked", "enabled", "disabled", "不认识的kind"]
    values = [20, 0, "", None, True, ["a", "b"], {"k": "v"}]
    for kind in kinds:
        for val in values:
            for extra in ({}, {"name": "data-cust"}, {"selector": "#x"}, {"element": "搜索"}):
                a = {"kind": kind, "expect": val, **extra}
                case_warnings({"asserts": [a]})          # 不崩即通过（返回值这里不看）
                case_errors({"asserts": [a]})


def test_fill_value_echo_check_survives_non_string_values():
    """「断言回显输入」检查对非字符串期望值也要平安（旧写法把 int 丢进 set 比较/正则）。"""
    case = {
        "steps": [{"op": "fill", "value": 1005}],
        "asserts": [{"expect": 1005}, {"expect": "1005"}, {"expect": None}],
    }
    warns = case_warnings(case)
    assert any("回显" in w for w in warns)               # 字符串形态要抓到
    assert any("回显" in w for w in warns if "1005" in w)


# ---------------------------------------------------------------- 2. 该拦的拦、该放的放
def test_host_only_evidence_is_redline_in_cross_page_case():
    errs = case_errors(_cross([{"kind": "url", "expect": "localhost"}]))
    assert len(errs) == 1
    assert "假绿" in errs[0] and "host" in errs[0]
    # 端口形态同样拦（localhost:8000 也一样两页都含）
    assert case_errors(_cross([{"kind": "url", "expect": "localhost:8000"}]))


def test_discriminating_fragment_passes():
    assert case_errors(_cross([{"kind": "url", "expect": "contract_detail"}])) == []
    # 精确 URL 形态同样放行
    assert case_errors(_cross([{"kind": "url", "expect": PAGES[1]["url"]}])) == []


def test_host_only_in_single_page_case_only_warns():
    """单页用例里的 host 断言只告警 —— 它可能就是想验「URL 含 host:port」，不该拦。

    现实依据：`cases/assert_kinds_search.json` 就有这种手写断言（单页、无 pages 声明）。
    """
    case = {"steps": [{"op": "goto", "url": "http://localhost:8000/"}],
            "asserts": [{"kind": "url", "expect": "localhost:8000"}]}
    assert case_errors(case) == []
    assert any("host" in w for w in case_warnings(case))


def test_fabricated_fragment_warns_but_does_not_block():
    """片段跟声明的页面 URL 都对不上 ⇒ 是「可能永远不通过」的假红风险，告警但不拦（可能清单不全）。"""
    case = _cross([{"kind": "url", "expect": "index.html"}])
    assert case_errors(case) == []
    assert any("都对不上" in w for w in case_warnings(case))


def test_missing_url_assertion_warning_still_there():
    """回归：跨页用例完全没有 url 断言时，原有的「没有换页证据」告警不许消失。"""
    warns = case_warnings(_cross([{"expect": "HT-1005"}]))
    assert any("URL 断言" in w for w in warns)


def test_url_assert_without_expect_is_redline():
    """url 断言不给 expect ⇒ 无法判断指向哪一页（生成脚本里也是结构性错误）⇒ 红线。"""
    assert case_errors({"asserts": [{"kind": "url"}]})


# ---------------------------------------------------------------- 3. 红线真的拒绝产物
def test_ai_case_written_nowhere_when_redline(tmp_path):
    """AI 落盘路径：有红线 ⇒ 抛 CaseQualityError，且**一个文件都不写**。

    走真实管线形态：页面清单由 `scenario.case_extra()` 带进 `extra["pages"]`
    —— 跨页质量闸正是靠它判「这条片段被几页含」。
    """
    m = ElementMap(
        url="http://localhost:8000/",
        scenario="回到列表页",
        steps=[
            _TestStep(order=1, action="goto", value="http://localhost:8000/", description="打开列表页"),
            _TestStep(order=2, action="expect_url", value="localhost", description="确认已回到列表页"),
        ],
    )
    with pytest.raises(CaseQualityError) as ei:
        elementmap_to_cases_file(m, cases_dir=tmp_path, extra={"pages": PAGES})
    assert ei.value.total == 1
    assert list(tmp_path.glob("*.json")) == []          # 拒绝落盘 = 目录里啥也没有


def test_cross_page_by_goto_without_pages_still_blocks_host_fragment():
    """跨页信号只在 goto 上体现（没声明 pages）时，host 片段同样必须拦。

    回归：闸门最初把「没声明 pages 但两次 goto」的 host 断言只落到告警 ⇒ 洞。
    """
    case = {
        "case_id": "no_pages",
        "steps": [{"op": "goto", "url": "http://localhost:8000/"},
                  {"op": "goto", "url": "http://localhost:8000/contract_detail.html?no=HT-1005"}],
        "asserts": [{"kind": "url", "expect": "localhost"}],
    }
    assert case_errors(case)


def test_generate_gate_blocks_redline_cases():
    """生成路径：坏用例 ⇒ 抛；好用例 ⇒ 放行（假拦会逼人绕过，所以两态都要测）。"""
    with pytest.raises(CaseQualityError) as ei:
        _gate_false_green([_cross([{"kind": "url", "expect": "localhost"}])])
    assert ei.value.entries[0][0] == "demo_cross"
    _gate_false_green([_cross([{"kind": "url", "expect": "contract_detail"}])])   # 不抛


def test_repo_cases_have_no_weak_evidence():
    """仓库现状扫描：`cases/*.json` 里不许再有弱换页证据（防历史产物回流）。

    2026-09-17 之前，`cases/ai_contracts_cross_page_011030.json` 就带着 `expect: localhost`
    —— 它躲过了当时所有告警，一路跑到报告里。
    """
    bad: list[str] = []
    for f in sorted(CASES.rglob("*.json")):
        case = json.loads(f.read_text(encoding="utf-8"))
        bad += [f"{f.name}: {m}" for m in case_errors(case)]
    assert bad == [], f"以下用例带弱换页证据（假绿）：{bad}"


# ---------------------------------------------------------------- 4. 根因层的提示词锁
def test_prompt_no_longer_teaches_weak_evidence():
    """源码判据：AI 提示词不许再教「列表页写 localhost」，且必须写明禁止。

    只修闸门不修提示词 = 每次 AI 跑都撞红线（用户反复重跑）——那就是把 bug 从假绿换成假红。
    """
    src = (REPO / "framework" / "tools" / "explore" / "explorer.py").read_text(encoding="utf-8")
    assert "列表页写 localhost" not in src, "提示词还在教 AI 产弱换页证据"
    assert "每个页面都含" in src, "提示词缺少「禁止 host 片段」的说明"
