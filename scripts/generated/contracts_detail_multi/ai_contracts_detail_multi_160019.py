"""hybrid_gui_qa 用例模块：ai_contracts_detail_multi_160019（场景 contracts_detail_multi）—— 由 cases/contracts_detail_multi/ai_contracts_detail_multi_160019.json 自动生成。

**不要手改本文件**：改用例后重跑 generate 会覆盖它。要改行为 → 改用例 json / 场景 yml。
数据抽离在 scripts/datasets/ai_contracts_detail_multi_160019.json（脚本与数据分离）。
一个用例一个文件（P20）：便于按 id 管理、按变化增量重生成。

运行（推荐走 cli：自带资源预检 + run-id 隔离的日志/报告）:
  python -m framework.cli run --workers 2                 # 全量
  python -m framework.cli run --debug --case ai_contracts_detail_multi_160019        # 只调试这一条
裸跑 pytest（未设 HYBRID_RUN_ID 时日志落 log/latest/）:
  pytest scripts/generated/contracts_detail_multi/ai_contracts_detail_multi_160019.py -v
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

@pytest.mark.parametrize("ctx", _ds_params('ai_contracts_detail_multi_160019'), ids=_ds_ids('ai_contracts_detail_multi_160019'), indirect=True)
def test_ai_contracts_detail_multi_160019(page, ctx):
    """打开合同详情页 {详情地址}，确认页面显示的合同编号是 {期望编号}、客户是 {期望客户}。"""
    _CURRENT_LOG["case_id"] = "ai_contracts_detail_multi_160019"
    _goto(page, 'http://localhost:8000/contract_detail.html?no=HT-1005')
    _log(page, "场景开始", f"case=ai_contracts_detail_multi_160019")

    # step 1: 打开合同详情页 {详情地址}
    _goto(page, _data('goto_0', ctx))
    _log(page, "goto", f"打开合同详情页 {{详情地址}}")
    _assert_text(page, _data('expect_0', ctx), '确认页面显示的合同编号是 {期望编号}')
    _assert_text(page, _data('expect_1', ctx), '确认页面显示的客户是 {期望客户}')

