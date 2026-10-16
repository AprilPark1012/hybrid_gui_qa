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
GENERATOR = REPO / "framework" / "features" / "f02_semantic" / "generator_generate.py"


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


def test_harness_select_semantics_is_single_source():
    """`_harness` 模板里的 select **只有一个口径**（项目铁律：同一能力收敛成唯一入口）。

    [!] V8.6.3：原实现拿 `framework/features/f06_healer/runner_unused.py`（无 import 的死模块）
    做对照 —— 该模块已删。现在钉**真实生效的实现**：`_harness` 模板就是生成物
    `scripts/generated/_harness.py` 的**唯一真源**（由 generator 渲染），改生成物下次生成就被覆盖。
    元素级（`_act`）与行内（`_act_row`）两条 select 分支必须同口径：
    都不许把空串喂给 `select_option`，没给 value 一律按「选第一个真选项（跳过空占位）」。
    """
    src = GENERATOR.read_text(encoding="utf-8")
    i = src.index('elif action == "select":')
    seg_act = src[i: i + 1400]
    j = src.index('elif op == "select":')
    seg_row = src[j: j + 1400]
    # [!] 断言前先剔注释行：事故经过**就写在注释里**（原文含 `select_option("")`），
    #     不剔会把「注释里描述旧实现」误判成「代码还在犯」（判据空转/误红，本项目踩过多次）。
    segs = ["\n".join(ln for ln in s.splitlines() if not ln.lstrip().startswith("#"))
            for s in (seg_act, seg_row)]
    for seg in segs:
        assert 'select_option("")' not in seg, (
            "select 分支仍会把空串喂给 select_option —— Playwright 会去找 value='' 的选项并超时")
        assert "select_option(index=" in seg, (
            "select 分支没给 value 时没有按索引选第一项 —— 两条链路口径不一致"
            "（同一能力不许有两个语义）")
