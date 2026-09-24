"""hybrid_gui_qa 用例模块：ai_orders_return_from_contract_160019（场景 orders_return_from_contract）—— 由 cases/orders_return_from_contract/ai_orders_return_from_contract_160019.json 自动生成。

**不要手改本文件**：改用例后重跑 generate 会覆盖它。要改行为 → 改用例 json / 场景 yml。
数据抽离在 scripts/datasets/ai_orders_return_from_contract_160019.json（脚本与数据分离）。
一个用例一个文件（P20）：便于按 id 管理、按变化增量重生成。

运行（推荐走 cli：自带资源预检 + run-id 隔离的日志/报告）:
  python -m framework.cli run --workers 2                 # 全量
  python -m framework.cli run --debug --case ai_orders_return_from_contract_160019        # 只调试这一条
裸跑 pytest（未设 HYBRID_RUN_ID 时日志落 log/latest/）:
  pytest scripts/generated/orders_return_from_contract/ai_orders_return_from_contract_160019.py -v
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

def test_ai_orders_return_from_contract_160019(page, ctx):
    """打开合同列表页，点击右上角的「查看订单」，系统会**新开一个 tab** 打开订单系统页面（订单列表页）；
在该页点击「+ 新建订单」按钮，弹出「新建订单」弹窗：
填写订单名称（用「退货订单-{datetime}」这个值）；
点击「选择合同」打开合同弹层，选第一行（HT-1001）的「选择」；
点击业务单元旁的「...」按钮打开弹层选第一行，同样方式给管理单元、帐套各选第一行；
订单类型下拉选「退货订单」；
点击「选择客户」选第一个客户，点击「选择销售员」选第一个销售员；
在订单备注里填「AI 端到端自动化用例」；
点击「提交」，弹窗关闭、订单列表刷新，确认**列表第一行的订单名称**就是我们刚填的那个订单名称；
然后在订单列表里点击这一行的「合同编号」链接，它会**新开一个 tab** 打开该合同的详情页，
确认新 tab 的 URL 是合同详情页且页面显示合同编号 HT-1001、合同名称 合同1；
最后点击该详情页的「返回」按钮，这个 tab 被关闭，回到订单列表页面（确认还在订单列表页）。"""
    _CURRENT_LOG["case_id"] = "ai_orders_return_from_contract_160019"
    _t = _Tabs(page)          # 多 tab：点了会开新 tab 的控件后 page 会被重新绑定到新 tab
    _goto(page, 'http://localhost:8000/')
    _log(page, "场景开始", f"case=ai_orders_return_from_contract_160019")

    # step 1: 打开合同列表页
    _goto(page, 'http://localhost:8000/')
    _log(page, "goto", f"打开合同列表页")
    _assert_text(page, _data('expect_0', ctx), '确认合同列表页已加载（表头合同编号）')

    # step 2: 点击右上角「查看订单」，新开 tab 打开订单系统
    page = _t.open_new(lambda: _act(page, "click", semantic='查看订单', primary=lambda p: p.get_by_role("link", name="查看订单")))
    _log(page, "click_new_tab", f"点击右上角「查看订单」，新开 tab 打开订单系统")
    _assert_url(page, _data('expect_1', ctx), '确认新 tab 是订单系统页')
    _assert_text(page, _data('expect_2', ctx), '确认订单列表已加载（表头订单编号）')

    # step 3: 点击「+ 新建订单」打开弹窗
    _act(page, "click", semantic='新建订单', primary=lambda p: p.get_by_role("button", name="+ 新建订单"))
    _log(page, "click", f"点击「+ 新建订单」打开弹窗")

    # step 4: 填写订单名称
    _act(page, "fill", semantic='请输入订单名称', primary=lambda p: p.get_by_test_id("modal-new-order").get_by_placeholder("请输入订单名称"), value=_data('fill_0', ctx))
    _log(page, "fill", f"填写订单名称")

    # step 5: 打开选择合同弹层
    _act(page, "click", semantic='选择合同', primary=lambda p: p.get_by_test_id("modal-new-order").get_by_text("选择合同", exact=True))
    _log(page, "click", f"打开选择合同弹层")

    # step 6: 选第一行合同 HT-1001
    _act(page, "click", semantic='选择@HT_1001', primary=lambda p: _drill(p, {'kind': 'dialog', 'by': 'test_id', 'value': 'modal-pick-contract'}, [{'axis': 'row', 'by': 'text', 'value': 'HT-1001 合同1 北京华信科技有限公司 选择'}, {'axis': 'col', 'by': 'header', 'value': '操作'}, {'axis': 'target', 'by': 'role', 'value': 'button'}]))
    _log(page, "click", f"选第一行合同 HT-1001")

    # step 7: 打开业务单元弹层
    _act(page, "click", semantic='选择业务单元', primary=lambda p: p.get_by_test_id("modal-new-order").get_by_title("选择业务单元"))
    _log(page, "click", f"打开业务单元弹层")

    # step 8: 选业务单元第一行 bu_a
    _act(page, "click", semantic='选择@bu_a', primary=lambda p: _drill(p, {'kind': 'dialog', 'by': 'test_id', 'value': 'modal-pick-bu'}, [{'axis': 'row', 'by': 'text', 'value': 'bu_a选择'}, {'axis': 'col', 'by': 'header', 'value': '操作'}, {'axis': 'target', 'by': 'role', 'value': 'button'}]))
    _log(page, "click", f"选业务单元第一行 bu_a")

    # step 9: 打开管理单元弹层
    _act(page, "click", semantic='选择管理单元', primary=lambda p: p.get_by_test_id("modal-new-order").get_by_title("选择管理单元"))
    _log(page, "click", f"打开管理单元弹层")

    # step 10: 选管理单元第一行 0021
    _act(page, "click", semantic='选择@0021', primary=lambda p: _drill(p, {'kind': 'dialog', 'by': 'test_id', 'value': 'modal-pick-mu'}, [{'axis': 'row', 'by': 'text', 'value': '0021选择'}, {'axis': 'col', 'by': 'header', 'value': '操作'}, {'axis': 'target', 'by': 'role', 'value': 'button'}]))
    _log(page, "click", f"选管理单元第一行 0021")

    # step 11: 打开帐套弹层
    _act(page, "click", semantic='选择帐套', primary=lambda p: p.get_by_test_id("modal-new-order").get_by_title("选择帐套"))
    _log(page, "click", f"打开帐套弹层")

    # step 12: 选帐套第一行 001
    _act(page, "click", semantic='选择@001', primary=lambda p: _drill(p, {'kind': 'dialog', 'by': 'test_id', 'value': 'modal-pick-file'}, [{'axis': 'row', 'by': 'text', 'value': '001选择'}, {'axis': 'col', 'by': 'header', 'value': '操作'}, {'axis': 'target', 'by': 'role', 'value': 'button'}]))
    _log(page, "click", f"选帐套第一行 001")

    # step 13: 订单类型下拉选「退货订单」
    _act(page, "select", semantic='订单类型', primary=lambda p: _drill(p, {'kind': 'dialog', 'by': 'test_id', 'value': 'modal-new-order'}, [{'axis': 'target', 'by': 'label', 'value': '订单类型 *'}]), value=_data('select_1', ctx))
    _log(page, "select", f"订单类型下拉选「退货订单」")

    # step 14: 打开选择客户弹层
    _act(page, "click", semantic='选择客户@订单系统', primary=lambda p: p.get_by_test_id("modal-new-order").get_by_text("选择客户", exact=True))
    _log(page, "click", f"打开选择客户弹层")

    # step 15: 选第一个客户
    _act(page, "click", semantic='选择@北京华信科技有限公司@订单系统', primary=lambda p: _drill(p, {'kind': 'dialog', 'by': 'test_id', 'value': 'modal-pick-cust'}, [{'axis': 'row', 'by': 'text', 'value': '北京华信科技有限公司 北京市朝阳区建国路88号 选择'}, {'axis': 'col', 'by': 'header', 'value': '操作'}, {'axis': 'target', 'by': 'role', 'value': 'button'}]))
    _log(page, "click", f"选第一个客户")

    # step 16: 打开选择销售员弹层
    _act(page, "click", semantic='选择销售员', primary=lambda p: p.get_by_test_id("modal-new-order").get_by_text("选择销售员", exact=True))
    _log(page, "click", f"打开选择销售员弹层")

    # step 17: 选第一个销售员
    _act(page, "click", semantic='选择@张伟', primary=lambda p: _drill(p, {'kind': 'dialog', 'by': 'test_id', 'value': 'modal-pick-salesman'}, [{'axis': 'row', 'by': 'text', 'value': '张伟选择'}, {'axis': 'col', 'by': 'header', 'value': '操作'}, {'axis': 'target', 'by': 'role', 'value': 'button'}]))
    _log(page, "click", f"选第一个销售员")

    # step 18: 填写订单备注
    _act(page, "fill", semantic='订单备注_可不填', primary=lambda p: p.get_by_test_id("modal-new-order").get_by_placeholder("订单备注（可不填）"), value=_data('fill_2', ctx))
    _log(page, "fill", f"填写订单备注")

    # step 19: 提交新建订单
    _act(page, "click", semantic='提交@订单系统', primary=lambda p: p.get_by_test_id("modal-new-order").get_by_text("提交", exact=True))
    _log(page, "click", f"提交新建订单")
    _assert_first_row(page, 'orderName', _data('expect_3', ctx), '确认列表第一行订单名称就是刚填的值')

    # step 20: 点该行合同编号链接，新开 tab 打开合同详情页
    page = _click_row_cell(page, row_text=_data('row_text_3', ctx), cell_field='contractNo', tabs=_t)
    _log(page, "click_new_tab", f"点该行合同编号链接，新开 tab 打开合同详情页")
    _assert_url(page, _data('expect_4', ctx), '确认新 tab 是合同详情页')
    _assert_text(page, _data('expect_5', ctx), '确认详情页显示合同编号 HT-1001')
    _assert_text(page, _data('expect_6', ctx), '确认详情页显示合同名称 合同1')

    # step 21: 点击详情页「返回」，关闭本 tab
    page = _t.close_current(lambda: _act(page, "click", semantic='返回', primary=lambda p: p.get_by_role("link", name="返回")))
    _log(page, "close_tab", f"点击详情页「返回」，关闭本 tab")
    _assert_url(page, _data('expect_7', ctx), '确认回到订单列表页')
    _assert_text(page, _data('expect_8', ctx), '确认仍在订单列表页（表头订单编号）')

