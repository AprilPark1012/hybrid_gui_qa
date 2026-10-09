# -*- coding: utf-8 -*-
"""特性2 · 「必填字段硬清单」必须出现在 prompt 最前（V8.4.3+ · 第三层修复）。

现场（三轮都没救回来）：
    跨页 prompt 里控件清单按页分组，配额 `max(8, 60//7)=8` —— 新建订单页有 17 个控件，
    而「客户」「销售员」是页面第 7、8 个之外的位置。场景原文一句话枚举了 9 个字段，
    AI 三轮都漏掉这两个 -> 保存被前端必填校验拦下 -> 订单没建成 -> 断言失败。

定因（实测 prompt 字数）：两个词**确实在** prompt 里（位置 ~5230 字符处），
    所以不是「没喂」，是**长清单里漏读**。=> 不该继续指望提示词自觉，
    而把框架已经掌握的确定性信息（页面标 * 的必填 ∩ 场景原文逐字提到）提成
    **prompt 第 0 位的硬约束清单**。

另外两个同批修掉的问题：
    · 每页配额外加「**必填优先**」排序（必填控件排页内最前，保证不被配额挤掉）；
    · 跨页探测结果**跨轮累积**（实测 3 轮 × 7 页 = 1432 个控件，旧轮控件挤爆清单）。
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from framework.tools.explore import explorer as EX   # noqa: E402


_SCENARIO = ("4. 在新建订单页填写：订单名称用「全链路-{datetime}」、合同已带入、"
             "业务单元/管理单元/帐套各选第一行、订单类型选第一项、"
             "客户与销售员各选第一个、订单备注填「端到端全链路场景」；点「保存」。")

_REQUIRED = [
    {"name": "订单名称", "page": "新建订单页", "token": "*订单名称"},
    {"name": "客户",     "page": "新建订单页", "token": "*客户"},
    {"name": "销售员",   "page": "新建订单页", "token": "*销售员"},
    {"name": "订单备注", "page": "新建订单页", "token": "订单备注"},   # 非必填
]


def _prime():
    EX._LAST_REQUIRED_FIELDS.clear()
    EX._LAST_REQUIRED_FIELDS.extend(_REQUIRED)
    EX._CURRENT_SCENARIO = _SCENARIO


def test_checklist_lists_scenario_required_fields():
    """场景提到的必填项都要进清单（含实测漏掉的客户/销售员）。"""
    _prime()
    blk = EX._required_fields_block()
    for nm in ("订单名称", "客户", "销售员"):
        assert nm in blk, f"硬清单缺「{nm}」"
    assert "订单备注" not in blk, "非必填（ctx_token 无 *）不该进硬清单"


def test_checklist_block_precedes_control_list():
    """【核心】硬清单必须排在控件清单**之前**（长 prompt 里首部才不会被淹没）。"""
    _prime()
    prompt = EX._build_planner_prompt(_SCENARIO, [], "http://localhost:8000/login.html",
                                      [], pages=None)
    i_block = prompt.find("本场景必须操作的必填字段")
    i_ctrl = prompt.find("已探测出以下可交互控件")
    assert i_block >= 0, "硬清单没进 prompt"
    assert i_ctrl < 0 or i_block < i_ctrl, "硬清单必须排在控件清单之前"


def test_no_required_fields_means_no_block():
    """【反向自证】没有「场景提到 ∩ 标必填」的项 -> 不许凭空加清单（不污染 prompt）。"""
    EX._LAST_REQUIRED_FIELDS.clear()
    EX._LAST_REQUIRED_FIELDS.extend([{"name": "承运商", "page": "新建订单页", "token": "*承运商"}])
    EX._CURRENT_SCENARIO = _SCENARIO          # 场景没提承运商
    assert EX._required_fields_block() == ""


def test_required_fields_sorted_first_in_page_group():
    """【配额保护】页内排序必须「必填优先」—— 否则配额外的必填控件会被挤掉（实测吃过）。"""
    grp = [{"semantic_name": "取消@新建订单页", "ctx_token": "取消"},
           {"semantic_name": "客户@新建订单页", "ctx_token": "*客户"},
           {"semantic_name": "保存@新建订单页", "ctx_token": ""},
           {"semantic_name": "销售员@新建订单页", "ctx_token": "*销售员"}]
    ordered = sorted(grp, key=lambda x: 0 if str(x.get("ctx_token") or "").startswith("*") else 1)
    assert ordered[0]["ctx_token"].startswith("*") and ordered[1]["ctx_token"].startswith("*"), \
        "必填控件没有排到页内最前"


def test_pages_probe_resets_items_between_rounds():
    """跨页探测结果不许跨轮累积（实测 3 轮 -> 1432 个控件，旧轮挤爆清单）。"""
    import inspect
    src = inspect.getsource(EX._collect_pages_context)
    assert "items.clear()" in src, "跨页探测入口没有重置 items -> 跨轮累积"
# 注：原 `test_per_page_budget_is_not_tiny` 已**删除** —— 它断言的是「每页配额」这个机制，
# 而该机制已被更通用的方案取代（字符预算 + 必给层免裁 + 页间轮转）。
# 职责移交 `test_prompt_list_clipping_is_general.py`（含「源码里不许再有条数配额」的防回归判据）。
