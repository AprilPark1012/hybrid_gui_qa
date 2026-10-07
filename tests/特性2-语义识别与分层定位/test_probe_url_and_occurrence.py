"""两个通用能力契约（P22 批 5；一类，不需浏览器）—— 遵守「补能力必须与场景解耦、不写死」。

AprilPark1012 2026-09-30 定：框架补能力要和场景解耦、不能写死、要适用各种情况。
本判据守的就是"零业务词"这条：框架只认【探测地址】与【实例序号】两个概念，
具体值（哪个订单号、哪个控件第几个）全部由场景/用例给。

A 探测地址 `probe_url`：页面 url 里带运行时值（订单号之类）时，探测期该对象还不存在
  -> 场景另给一个"探测期用的地址"。缺省回落 url（老场景不受影响）。
B 实例序号 `occurrence`：同一语义名有多个实例（表单第 1/2 行的「数量」）时，用例用
  `occurrence: N` 表达"第 N 个"，框架翻成 `.nth(N-1)` —— 而不是把观测到的实例名（`数量_2`）写死。
"""
from __future__ import annotations

import pytest

import framework.tools.generate.generator as gen
from framework.tools.generate.generator import _add_payload_refs, _render_pytest_case
from framework.tools.generate.scenario import ScenarioError, load_scenario_file

_YML = """
id: t_gen
scenario: 通用能力
title: 通用能力
url: http://localhost:8000/
pages:
  - name: 订单详情页
    url: http://localhost:8000/order_detail.html?no={{order_no}}
    probe_url: http://localhost:8000/order_detail.html?no=SO-1101
"""

_YML_NO_PROBE = """
id: t_gen2
scenario: 没有探测地址
title: 无 probe_url
url: http://localhost:8000/
pages:
  - name: 合同列表页
    url: http://localhost:8000/
"""

_YML_BAD_PROBE = """
id: t_gen3
scenario: 探测地址写错
title: 坏 probe_url
url: http://localhost:8000/
pages:
  - name: 合同列表页
    url: http://localhost:8000/
    probe_url: /relative/path
"""


def _load(tmp_path, body: str):
    f = tmp_path / "s.yml"
    f.write_text(body, encoding="utf-8")
    return load_scenario_file(f)


# ---------------- A 探测地址 ----------------
def test_probe_url_parsed_and_exposed(tmp_path):
    page = _load(tmp_path, _YML).all_pages()[0]
    assert page.url == "http://localhost:8000/order_detail.html?no={{order_no}}"
    assert page.probe_url == "http://localhost:8000/order_detail.html?no=SO-1101"
    assert page.to_dict()["probe_url"].endswith("SO-1101")
    assert page.probe_url_for() == "http://localhost:8000/order_detail.html?no=SO-1101"


def test_probe_url_defaults_to_url(tmp_path):
    """不声明 -> 探测地址 == url（向后兼容，老场景行为不变）。"""
    page = _load(tmp_path, _YML_NO_PROBE).all_pages()[0]
    assert page.probe_url == ""
    assert page.probe_url_for() == page.url


def test_probe_url_must_be_absolute(tmp_path):
    with pytest.raises(ScenarioError):
        _load(tmp_path, _YML_BAD_PROBE)


# ---------------- B 实例序号 ----------------
LOC = {"数量@详细信息": 'get_by_role("textbox", name="数量")'}


def _render_step(step: dict) -> str:
    gen._DUP_PAGES.clear()
    gen._DUP_RAW_NAMES.clear()
    case = _add_payload_refs({"case_id": "t", "pages": [{"name": "订单详情页"}], "steps": [step]})
    return _render_pytest_case(case, LOC)


def test_occurrence_renders_nth():
    out = _render_step({"op": "fill", "element": "数量@详细信息", "occurrence": 2,
                        "value": "20", "desc": "第 2 行数量"})
    assert ".nth(1)" in out, out
    assert "pytest.fail" not in out, out


def test_no_occurrence_is_backward_compatible():
    out = _render_step({"op": "fill", "element": "数量@详细信息", "value": "10", "desc": "第 1 行数量"})
    assert ".nth(" not in out, out
    assert "pytest.fail" not in out, out


def test_occurrence_must_be_positive_int():
    out = _render_step({"op": "fill", "element": "数量@详细信息", "occurrence": 0,
                        "value": "10", "desc": "非法序号"})
    assert "pytest.fail" in out, "occurrence 非法（从 1 起）必须显式失败，不许静默当第 1 个"
