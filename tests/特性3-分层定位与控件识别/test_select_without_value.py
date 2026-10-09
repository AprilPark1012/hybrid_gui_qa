# -*- coding: utf-8 -*-
"""特性3 · 分层定位与控件识别：**select 没给值 = 选第一项**（V8.4）。

事故（2026-10-09 干净环境 E2E 实录，重试闭环连跑 3 轮都被同一处挡住）：
    AI 按新约束产出「`select` 只给 element、不给 value」（人话是「业务单元选第一项」），
    落到脚本执行时：
        playwright._impl._errors.TimeoutError: Locator.select_option: Timeout 30000ms exceeded
          - waiting for get_by_role("combobox", name="订单类型")
          - did not find some options
    根因：`_act()` 的 select 分支是
        if index is not None: <跳过空占位选第 N 项>
        else:                 loc.select_option(value if value is not None else "")   # <- 传 ""
    传空串会让 Playwright 去找 `value=""` 的选项 -> 找不到 -> 30s 超时。
    **「没给值」在语义上就是「选第一项」** —— 框架没接住 AI 的这个（完全合理的）写法。

判据口径：纯函数/源码级（不启浏览器）。
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
GENERATOR = REPO / "framework" / "tools" / "generate" / "generator.py"
RUNNER = REPO / "framework" / "tools" / "run" / "runner.py"


def _harness_select_segment() -> str:
    """取生成器里「渲染 _harness.py」的模板中 `select` 那一段。

    [!] 为什么不能用 AST 找 `_act()`：`_act` 是**模板字符串里的文本**（生成物 `_harness.py`
        的内容），不是 `generator.py` 的真函数 —— 用 `ast` 找必然失败（这是判据自身的坑，
        踩过一次：报 "generator.py 里找不到 _act()"）。
    """
    src = GENERATOR.read_text(encoding="utf-8")
    i = src.index('elif action == "select":')
    return src[i: i + 1400]


def test_harness_act_select_treats_missing_value_as_first():
    """`_act` 的 select 分支：**没给 value 也没给 index** 时必须「选第一项」，不许传空串。

    这是渲染层（`generator.py` 里生成 `_harness.py` 的模板）—— 改这里才治本，
    只改生成物 `scripts/generated/_harness.py` 下次生成就被覆盖。
    """
    seg = _harness_select_segment()
    assert 'select_option(value if value is not None else "")' not in seg, (
        "select 分支仍会在「没给 value」时传空串 —— Playwright 会去找 value='' 的选项并超时"
    )
    assert "index = 0" in seg or "index=0" in seg, (
        "select 分支没有「没给值就当第 0 项」的兜底 —— AI 的『选第一项』落不了地"
    )
    assert "value" in seg and ("None" in seg or "strip()" in seg), (
        "select 分支缺少「value 为空」的判定"
    )


def test_harness_act_select_uses_first_real_option():
    """兜底选第一项时要**跳过空占位**（demo 的首项是 `<option value="">请选择</option>`）。

    口径与既有 `index=N` 分支一致：按「第 N 个**非空**选项」算 —— 否则会落进「请选择」，
    表单校验不过、订单建不出来（2026-09-30 已经为此卡过两轮）。
    """
    seg = _harness_select_segment()
    assert "_real" in seg, (
        "select 分支没有过滤空占位选项 —— 「选第一项」会选到「请选择」"
    )


def test_runner_select_has_same_semantics():
    """`run/runner.py` 里的 select 同族实现必须**同一口径**（项目铁律：同一能力收敛成唯一入口）。

    两处不一致的话，手搓用例与 AI 用例在同一个下拉上会有不同行为 —— 那是最难查的一类问题。
    """
    src = RUNNER.read_text(encoding="utf-8")
    assert 'select_option(t.value or "")' not in src, (
        "runner.py 仍在「没给 value」时传空串 —— 与 _harness 的修正口径不一致"
    )
