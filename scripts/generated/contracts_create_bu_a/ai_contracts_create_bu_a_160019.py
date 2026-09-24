"""hybrid_gui_qa 用例模块：ai_contracts_create_bu_a_160019（场景 contracts_create_bu_a）—— 由 cases/contracts_create_bu_a/ai_contracts_create_bu_a_160019.json 自动生成。

**不要手改本文件**：改用例后重跑 generate 会覆盖它。要改行为 → 改用例 json / 场景 yml。
数据抽离在 scripts/datasets/ai_contracts_create_bu_a_160019.json（脚本与数据分离）。
一个用例一个文件（P20）：便于按 id 管理、按变化增量重生成。

运行（推荐走 cli：自带资源预检 + run-id 隔离的日志/报告）:
  python -m framework.cli run --workers 2                 # 全量
  python -m framework.cli run --debug --case ai_contracts_create_bu_a_160019        # 只调试这一条
裸跑 pytest（未设 HYBRID_RUN_ID 时日志落 log/latest/）:
  pytest scripts/generated/contracts_create_bu_a/ai_contracts_create_bu_a_160019.py -v
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

def test_ai_contracts_create_bu_a_160019(page, ctx):
    """点击“新建合同”按钮打开弹窗；
填写合同名称“合同_{datetime}”，管理单元选 0021，帐套选 001，合同类型选 合同；
点击“选择客户”按钮，在弹出的客户列表里选「北京华信科技有限公司」那一行（点该行的“选择”按钮）；
业务单元选 bu_a；
点击“提交”按钮；
确认列表中出现刚填写的合同名称“合同_{datetime}”。"""
    _CURRENT_LOG["case_id"] = "ai_contracts_create_bu_a_160019"
    _goto(page, 'http://localhost:8000')
    _log(page, "场景开始", f"case=ai_contracts_create_bu_a_160019")

    # step 1: 打开 http://localhost:8000
    _goto(page, 'http://localhost:8000')
    _log(page, "goto", f"打开 http://localhost:8000")

    # step 2: 点击“+ 新建合同”按钮打开新建合同弹窗
    _act(page, "click", semantic='新建合同', primary=lambda p: p.get_by_role("button", name="+ 新建合同"))
    _log(page, "click", f"点击“+ 新建合同”按钮打开新建合同弹窗")

    # step 3: 在弹窗中填写合同名称
    _act(page, "fill", semantic='请输入合同名称', primary=lambda p: p.get_by_test_id("modal-new").get_by_placeholder("请输入合同名称"), value=_data('fill_0', ctx))
    _log(page, "fill", f"在弹窗中填写合同名称")

    # step 4: 选择管理单元 0021
    _act(page, "select", semantic='管理单元', primary=lambda p: _drill(p, {'kind': 'dialog', 'by': 'test_id', 'value': 'modal-new'}, [{'axis': 'target', 'by': 'label', 'value': '管理单元'}]), value=_data('select_1', ctx))
    _log(page, "select", f"选择管理单元 0021")

    # step 5: 选择帐套 001
    _act(page, "select", semantic='帐套', primary=lambda p: _drill(p, {'kind': 'dialog', 'by': 'test_id', 'value': 'modal-new'}, [{'axis': 'target', 'by': 'label', 'value': '帐套'}]), value=_data('select_2', ctx))
    _log(page, "select", f"选择帐套 001")

    # step 6: 选择合同类型 合同
    _act(page, "select", semantic='合同类型', primary=lambda p: _drill(p, {'kind': 'dialog', 'by': 'test_id', 'value': 'modal-new'}, [{'axis': 'target', 'by': 'label', 'value': '合同类型'}]), value=_data('select_3', ctx))
    _log(page, "select", f"选择合同类型 合同")

    # step 7: 点击“选择客户”按钮打开客户列表弹层
    _act(page, "click", semantic='选择客户', primary=lambda p: p.get_by_test_id("modal-new").get_by_text("选择客户", exact=True))
    _log(page, "click", f"点击“选择客户”按钮打开客户列表弹层")

    # step 8: 在客户列表中选择「北京华信科技有限公司」那一行的“选择”按钮
    _act(page, "click", semantic='选择@北京华信科技有限公司', primary=lambda p: _drill(p, {'kind': 'dialog', 'by': 'test_id', 'value': 'modal-customer'}, [{'axis': 'row', 'by': 'text', 'value': '北京华信科技有限公司 北京市朝阳区建国路88号 选择'}, {'axis': 'col', 'by': 'header', 'value': '操作'}, {'axis': 'target', 'by': 'role', 'value': 'button'}]))
    _log(page, "click", f"在客户列表中选择「北京华信科技有限公司」那一行的“选择”按钮")

    # step 9: 选择业务单元 bu_a
    _act(page, "select", semantic='业务单元', primary=lambda p: _drill(p, {'kind': 'dialog', 'by': 'test_id', 'value': 'modal-new'}, [{'axis': 'target', 'by': 'label', 'value': '业务单元'}]), value=_data('select_4', ctx))
    _log(page, "select", f"选择业务单元 bu_a")

    # step 10: 点击“提交”按钮提交新建合同
    _act(page, "click", semantic='提交', primary=lambda p: p.get_by_test_id("modal-new").get_by_text("提交", exact=True))
    _log(page, "click", f"点击“提交”按钮提交新建合同")
    _assert_first_row(page, 'contractName', _data('expect_0', ctx), '确认列表第一行出现刚填写的合同名称')

