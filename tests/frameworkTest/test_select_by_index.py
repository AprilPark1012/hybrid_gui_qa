"""select 的「按序号选第 N 项」契约（P22 批 5；不需要 demo/浏览器，秒级）。

为什么需要（真值 2026-09-30）：
  demo 的 `<select id="sel-o-bu">` 选项值是 bu_a/bu_b 之类，而 AI 用例把场景里的
  「业务单元/管理单元/帐套各选第一行」写成了 value="1" ⇒ Playwright
  `select_option("1")` 报 `did not find some options`（30s 超时才失败）。
  「第 N 项」必须是**显式的 index 语义**：不靠猜 value，也不许「找不到就随便挑一个」。

判据：
  1. 带 index 的步骤 ⇒ 渲染出 `index=N`，且**不再**按 value 选（那正是超时的原因）；
  2. 带 value 的步骤 ⇒ 行为不变（向后兼容）；
  3. index 与 value 同时给 ⇒ 明确 pytest.fail（结构性错误不许静默挑一个）。
"""
from __future__ import annotations

import framework.tools.generate.generator as gen
from framework.tools.generate.generator import _add_payload_refs, _render_pytest_case

LOC = {"业务单元": 'get_by_role("combobox", name="业务单元")'}


def _render(steps: list[dict]) -> str:
    gen._DUP_PAGES.clear()                      # 别让别的判据留下的跨页名单干扰本判据
    gen._DUP_RAW_NAMES.clear()
    case = _add_payload_refs({"case_id": "t", "pages": [{"name": "新建订单页"}], "steps": steps})
    return _render_pytest_case(case, LOC)


def test_index_step_renders_index_instead_of_value():
    """带 index ⇒ 渲染 index=0，且不落 value=_data(...)。"""
    out = _render([{"op": "select", "element": "业务单元", "index": 0, "desc": "业务单元选第一项"}])
    assert "index=0" in out, out
    assert "value=_data(" not in out, "带 index 的步骤不许再按 value 选（就是它超时的）"
    assert "pytest.fail" not in out, out


def test_value_step_still_renders_value():
    """老写法（按 value 选）保持原样 —— 向后兼容。"""
    out = _render([{"op": "select", "element": "业务单元", "value": "bu_a", "desc": "选 bu_a"}])
    assert "value=_data(" in out, out
    assert "index=" not in out, out


def test_index_and_value_together_fail_loud():
    """index 与 value 同时给 ⇒ 明确失败，绝不静默挑一个。"""
    out = _render([{"op": "select", "element": "业务单元", "index": 0, "value": "bu_a", "desc": "x"}])
    assert "pytest.fail" in out, out
    assert "index" in out and "value" in out, out
