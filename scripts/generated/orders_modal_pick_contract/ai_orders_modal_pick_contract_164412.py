"""hybrid_gui_qa 用例模块：ai_orders_modal_pick_contract_164412（场景 orders_modal_pick_contract）—— 由 cases/orders_modal_pick_contract/ai_orders_modal_pick_contract_164412.json 自动生成。

**不要手改本文件**：改用例后重跑 generate 会覆盖它。要改行为 → 改用例 json / 场景 yml。
数据抽离在 scripts/datasets/ai_orders_modal_pick_contract_164412.json（脚本与数据分离）。
一个用例一个文件（P20）：便于按 id 管理、按变化增量重生成。

运行（推荐走 cli：自带资源预检 + run-id 隔离的日志/报告）:
  python -m framework.cli run --workers 2                 # 全量
  python -m framework.cli run --debug --case ai_orders_modal_pick_contract_164412        # 只调试这一条
裸跑 pytest（未设 HYBRID_RUN_ID 时日志落 log/latest/）:
  pytest scripts/generated/orders_modal_pick_contract/ai_orders_modal_pick_contract_164412.py -v
"""
from _harness import (_CURRENT_LOG, _log, _data, _act, _goto,
                      # L1 数据参数化（2026-09-21）：用例上的 parametrize 要用这两个
                      # ⚠️ 同 `_Tabs` 那条教训：模板里渲染出的调用必须在这里同时 import，漏一个就是 NameError
                      _ds_params, _ds_ids,
                      _assert_text, _assert_url,
                      _assert_visible, _assert_hidden, _assert_count,
                      _assert_attr, _assert_value,
                      _assert_checked, _assert_unchecked,
                      _assert_enabled, _assert_disabled,
                      # 2026-09-17 跨 tab / 行内定位 / 首行断言用的辅助
                      # ⚠️ 模板里渲染出的调用必须**同时**在这里 import —— 漏一个就是运行时 NameError
                      _Tabs, _click_row_cell, _assert_first_row)
# P16 批 5：运行期「锚点 + 容器内相对路径」下钻（col.header 这类列口径只有运行时才算得出列序）
from framework.tools.probe.scope_locate import drill as _drill
import pytest
from playwright.sync_api import expect as _pw_expect

@pytest.mark.parametrize("ctx", _ds_params('ai_orders_modal_pick_contract_164412'), ids=_ds_ids('ai_orders_modal_pick_contract_164412'), indirect=True)
def test_ai_orders_modal_pick_contract_164412(page, ctx):
    """在订单列表页点击「+ 新建订单」按钮，打开「新建订单」弹窗；
在弹窗里点击挑合同的按钮，打开合同选择弹层；
在合同选择弹层里点击合同编号为 {合同编号} 的那一行，把它选中；
确认新建订单弹窗里已经回填了该合同的编号。"""
    _CURRENT_LOG["case_id"] = "ai_orders_modal_pick_contract_164412"
    _goto(page, 'http://localhost:8000/orders.html')
    _log(page, "场景开始", f"case=ai_orders_modal_pick_contract_164412")

    # step 1: 打开订单列表页
    _goto(page, 'http://localhost:8000/orders.html')
    _log(page, "goto", f"打开订单列表页")

    # step 2: 点击「+ 新建订单」按钮，打开新建订单弹窗
    _act(page, "click", semantic='新建订单', primary=lambda p: p.get_by_role("button", name="+ 新建订单"))
    _log(page, "click", f"点击「+ 新建订单」按钮，打开新建订单弹窗")

    # step 3: 在新建订单弹窗里点击挑合同按钮，打开合同选择弹层
    _act(page, "click", semantic='选择合同', primary=lambda p: p.get_by_test_id("modal-new-order").get_by_text("选择合同", exact=True))
    _log(page, "click", f"在新建订单弹窗里点击挑合同按钮，打开合同选择弹层")

    # step 4: 在合同选择弹层里点击合同编号为 {合同编号} 的那一行，把它选中
    _click_row_cell(page, row_text=_data('row_text_0', ctx), cell_field='contractNo', tabs=None)
    _log(page, "click", f"在合同选择弹层里点击合同编号为 {{合同编号}} 的那一行，把它选中")
    _assert_text(page, _data('expect_0', ctx), '确认新建订单弹窗里已回填该合同编号')

