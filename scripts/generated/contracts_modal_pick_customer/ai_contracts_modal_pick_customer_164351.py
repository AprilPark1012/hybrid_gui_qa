"""hybrid_gui_qa 用例模块：ai_contracts_modal_pick_customer_164351（场景 contracts_modal_pick_customer）—— 由 cases/contracts_modal_pick_customer/ai_contracts_modal_pick_customer_164351.json 自动生成。

**不要手改本文件**：改用例后重跑 generate 会覆盖它。要改行为 → 改用例 json / 场景 yml。
数据抽离在 scripts/datasets/ai_contracts_modal_pick_customer_164351.json（脚本与数据分离）。
一个用例一个文件（P20）：便于按 id 管理、按变化增量重生成。

运行（推荐走 cli：自带资源预检 + run-id 隔离的日志/报告）:
  python -m framework.cli run --workers 2                 # 全量
  python -m framework.cli run --debug --case ai_contracts_modal_pick_customer_164351        # 只调试这一条
裸跑 pytest（未设 HYBRID_RUN_ID 时日志落 log/latest/）:
  pytest scripts/generated/contracts_modal_pick_customer/ai_contracts_modal_pick_customer_164351.py -v
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

@pytest.mark.parametrize("ctx", _ds_params('ai_contracts_modal_pick_customer_164351'), ids=_ds_ids('ai_contracts_modal_pick_customer_164351'), indirect=True)
def test_ai_contracts_modal_pick_customer_164351(page, ctx):
    """在合同列表页点击「+ 新建合同」按钮，打开「新建合同」弹窗；
在新建弹窗里点击「选择客户」按钮，打开客户列表弹层；
在客户列表弹层里点击客户「{客户名称}」所在的那一行，把它选中；
确认新建弹窗里的客户输入框已经回填为该客户名称。"""
    _CURRENT_LOG["case_id"] = "ai_contracts_modal_pick_customer_164351"
    _goto(page, 'http://localhost:8000/')
    _log(page, "场景开始", f"case=ai_contracts_modal_pick_customer_164351")

    # step 1: 打开 http://localhost:8000/
    _goto(page, 'http://localhost:8000/')
    _log(page, "goto", f"打开 http://localhost:8000/")

    # step 2: 在合同列表页点击「+ 新建合同」按钮，打开新建合同弹窗
    _act(page, "click", semantic='新建合同', primary=lambda p: p.get_by_role("button", name="+ 新建合同"))
    _log(page, "click", f"在合同列表页点击「+ 新建合同」按钮，打开新建合同弹窗")

    # step 3: 在新建弹窗里点击「选择客户」按钮，打开客户列表弹层
    _act(page, "click", semantic='选择客户', primary=lambda p: p.get_by_test_id("modal-new").get_by_text("选择客户", exact=True))
    _log(page, "click", f"在新建弹窗里点击「选择客户」按钮，打开客户列表弹层")

    # step 4: 在客户列表弹层里点击客户「{客户名称}」所在的那一行，把它选中
    _click_row_cell(page, row_text=_data('row_text_0', ctx), cell_field='custName', tabs=None)
    _log(page, "click", f"在客户列表弹层里点击客户「{{客户名称}}」所在的那一行，把它选中")
    _assert_text(page, _data('expect_0', ctx), '确认新建弹窗里的客户输入框已回填为该客户名称')

