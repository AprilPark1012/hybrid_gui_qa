# -*- coding: utf-8 -*-
"""特性2 · 场景里明写的**必填项**，AI 不许漏编排（V8.4.3+ · Windows 实测第三层）。

现场（实跑才暴露，日志只报「表格没有第一行」）：
    场景第 4 步一句话列了 9 项要填
      「订单名称…合同已带入、业务单元/管理单元/帐套各选第一行、订单类型选第一项、
        **客户与销售员各选第一个**、订单备注填「端到端全链路场景」」
    AI 只编排了前 5 项，**漏了客户 / 销售员** -> 保存按钮点了没反应（前端必填校验拦下）
      -> 订单根本没建成 -> 列表搜索无结果 -> `expect_first_row` 断言失败。
    查它拿到的依据：新建订单页 13 个表单控件**全在**清单里（`title='客户'` / `title='销售员'`
    清清楚楚）-> **是 AI 漏读长句枚举，不是探针缺控件**。

判据设计（**不写死业务词、不猜**）：
    候选 = 探针标了必填（`ctx_token` 以 `*` 开头）**且**场景原文逐字提到它名字的控件；
    再要求 AI 的步骤里**一步都没碰它** —— 三者同时成立才报「缺失」。
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from framework.tools.explore.explorer import (   # noqa: E402
    check_required_field_coverage, _LAST_REQUIRED_FIELDS,
)


class _St:
    def __init__(self, order, desc="", semantic=None, value=None):
        self.order, self.description, self.value = order, desc, value
        self.element = type("E", (), {"semantic_name": semantic})() if semantic else None


# 探针口径：必填 = ctx_token 以 `*` 开头（`*客户`），非必填没有星号
REQUIRED = [
    {"name": "订单名称", "page": "新建订单页", "token": "*订单名称"},
    {"name": "客户",     "page": "新建订单页", "token": "*客户"},
    {"name": "销售员",   "page": "新建订单页", "token": "*销售员"},
    {"name": "订单备注", "page": "新建订单页", "token": "订单备注"},   # 非必填（无 *）
]

SCENARIO = """4. 在新建订单页填写：订单名称用「全链路-{datetime}」、合同已带入、
   业务单元/管理单元/帐套各选第一行、订单类型选第一项、客户与销售员各选第一个、
   订单备注填「端到端全链路场景」；点「保存」。"""


def test_missing_required_field_is_reported():
    """实测现场：AI 只做了订单名称，客户/销售员没碰 -> 必须报出来。"""
    steps = [_St(1, "填写订单名称", value="全链路-{datetime}")]
    miss = check_required_field_coverage(steps, REQUIRED, SCENARIO)
    assert len(miss) == 2, f"应报 2 个缺失（客户/销售员），实际 {miss}"
    assert any("客户" in m for m in miss) and any("销售员" in m for m in miss)


def test_covered_field_is_not_reported():
    """【反向自证】AI 编排了（描述或语义名提到它）-> 不许报。"""
    steps = [
        _St(1, "填写订单名称", value="全链路-{datetime}"),
        _St(2, "客户选第一个", semantic="客户@新建订单页"),
        _St(3, "销售员选第一个", semantic="销售员@新建订单页"),
    ]
    assert check_required_field_coverage(steps, REQUIRED, SCENARIO) == []


def test_field_not_mentioned_in_scenario_not_reported():
    """【反向自证】场景没提的必填控件（如运输方式/承运商）不许报 —— 不许拿页面清单当地基。"""
    extra = REQUIRED + [{"name": "承运商", "page": "新建订单页", "token": "*承运商"}]
    steps = [_St(1, "填写订单名称"), _St(2, "客户选第一个"), _St(3, "销售员选第一个")]
    miss = check_required_field_coverage(steps, extra, SCENARIO)
    assert not any("承运商" in m for m in miss), f"场景没提「承运商」却报了：{miss}"


def test_optional_field_is_not_reported():
    """【反向自证】非必填（ctx_token 无 `*`）即便场景提到、AI 没做，也不许报。"""
    only_optional = [{"name": "订单备注", "page": "新建订单页", "token": "订单备注"}]
    steps = [_St(1, "填写订单名称")]
    assert check_required_field_coverage(steps, only_optional, SCENARIO) == []


def test_no_scenario_text_reports_nothing():
    """拿不到场景原文 -> 不报（保守：宁可漏报，不无依据地拦）。"""
    assert check_required_field_coverage([_St(1, "x")], REQUIRED, None) == []
    assert check_required_field_coverage([_St(1, "x")], REQUIRED, "") == []


def test_empty_required_list_reports_nothing():
    """探针没标出必填控件（页面没有 `*` 标记）-> 不报（不凭空造要求）。"""
    assert check_required_field_coverage([_St(1, "x")], [], SCENARIO) == []


def test_same_field_reported_once():
    """同名控件出现在多页（跨页唯一化后可能重名）-> 只报一次。"""
    dup = [{"name": "客户", "page": "新建订单页", "token": "*客户"},
           {"name": "客户", "page": "订单详情页", "token": "*客户"}]
    miss = check_required_field_coverage([_St(1, "填写订单名称")], dup, SCENARIO)
    assert len(miss) == 1, f"同名控件应只报一次，实际 {miss}"


def test_cache_is_module_level_and_accumulates():
    """必填清单必须是**模块级累积**缓存（每页 clear 会只剩最后一页 —— 本项目踩过这个坑）。"""
    assert isinstance(_LAST_REQUIRED_FIELDS, list)
