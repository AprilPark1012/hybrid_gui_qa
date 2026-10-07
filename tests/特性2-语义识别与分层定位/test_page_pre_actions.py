"""场景「前置动作」（`pages[].pre`）契约 —— P22 批 5 缺口 ④⑤（一类，不需浏览器）。

为什么（真值 2026-09-30）：
  · 合同列表页的「新建订单」是弹层，**不先选中合同**点它只会弹「请选择某个合同」⇒ 弹层不开、里面控件探不到；
  · 订单详情页的行控件（数量/单位/行类型/收入）**只在「编辑」+「新增行」之后**才存在 ⇒ 探针一次都探不到。
  两条都是同一类：**需要前置动作才能探到的控件**。解法定为「场景声明式 pre」，与 `auth:` 段同一口径。

判据：
  J1 解析：`pages[].pre` 进 `ScenarioPage.pre`，`to_dict()` 带出；
  J2 类型错 ⇒ ScenarioError（与别的字段同口径，不静默吞）；
  J4 不声明 pre ⇒ 行为与今天一致（向后兼容；老场景不受影响）。
（探针执行顺序由二类真跑 verify_page_pre_actions.py 的 V1/V2 覆盖。）
"""
from __future__ import annotations

import pytest

from framework.tools.generate.scenario import ScenarioError, load_scenario_file

_YML = """
id: t_pre
scenario: 前置动作解析用例
title: 前置动作
url: http://localhost:8000/
pages:
  - name: 订单详情页
    url: http://localhost:8000/order_detail.html?no=SO-2301
    pre:
      - 编辑
      - 新增行
"""

_YML_NO_PRE = """
id: t_pre2
scenario: 没有前置动作
title: 无 pre
url: http://localhost:8000/
pages:
  - name: 合同列表页
    url: http://localhost:8000/
"""

_YML_BAD = """
id: t_pre3
scenario: pre 类型写错
title: 坏 pre
url: http://localhost:8000/
pages:
  - name: 合同列表页
    url: http://localhost:8000/
    pre: "编辑"
"""


def _load(tmp_path, body: str):
    p = tmp_path / "s.yml"
    p.write_text(body, encoding="utf-8")
    return load_scenario_file(p)


def test_pre_is_parsed_and_exposed(tmp_path):
    """J1：pre 进对象、进 to_dict（下游只认 all_pages() 的这一个形态）。"""
    sc = _load(tmp_path, _YML)
    page = sc.all_pages()[0]
    assert page.pre == ["编辑", "新增行"], page.pre
    assert page.to_dict()["pre"] == ["编辑", "新增行"]


def test_pre_wrong_type_fails_loud(tmp_path):
    """J2：pre 写成字符串 ⇒ 明确报错（不许静默当空）。"""
    with pytest.raises(ScenarioError):
        _load(tmp_path, _YML_BAD)


def test_no_pre_is_backward_compatible(tmp_path):
    """J4：不声明 pre ⇒ 空列表，行为与今天完全一致。"""
    sc = _load(tmp_path, _YML_NO_PRE)
    page = sc.all_pages()[0]
    assert page.pre == []
    assert page.to_dict()["pre"] == []
