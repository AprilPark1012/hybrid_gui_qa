"""hybrid_gui_qa 数据驱动测试用例 —— 由 cases/*.json 自动生成。
数据抽离到 scripts/datasets/<case_id>.json；脚本与数据分离。
运行（推荐走 cli：自带资源预检 + run-id 隔离的日志/报告）:
  cd hybrid_gui_qa
  python -m framework.cli run --workers 2             # 资源预检：内存不足自动降并发
  python -m framework.cli run --debug                 # 调试开关：有屏幕弹浏览器；没屏幕录视频+逐步截图
  python -m framework.cli run --debug --case <case_id>          # 只调试一条用例
  python -m framework.cli run --debug --slowmo 500 --case <case_id>  # 放慢 500ms/动作，肉眼跟步

裸跑 pytest（未设 HYBRID_RUN_ID 时日志落 log/latest/，会话开始清空）:
  pytest scripts/test_cases.py -v
  pytest scripts/test_cases.py -n 1 --html=log/latest/report.html
"""
from conftest import (_CURRENT_LOG, _log, _data, _act, _goto,
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
                      #    （实测：new 的 _Tabs 漏了 → verify 里 30 步用例第一步就 NameError；
                      #     防复发检查见 tests/test_artifacts_health.py::test_test_cases_imports_every_conftest_helper）
                      _Tabs, _click_row_cell, _assert_first_row)
import pytest
from playwright.sync_api import expect as _pw_expect

def test_ai_contracts_create_and_filter_by_customer_004651(page, ctx):
    """点击“新建合同”按钮打开弹窗；
填写合同名称“合同_{datetime}”，管理单元选 0021，帐套选 001，合同类型选 合同；
点击“选择客户”按钮，在弹出的客户列表里选择「北京华信科技有限公司」那一行（点该行的“选择”按钮）；
业务单元选 bu_a；
点击“提交”按钮；
确认列表中出现刚填写的合同名称“合同_{datetime}”；
然后在本页的客户筛选输入框里输入“北京华信”，点击“搜索”按钮，
确认搜索结果里仍然有刚填写的合同名称“合同_{datetime}”。"""
    _CURRENT_LOG["case_id"] = "ai_contracts_create_and_filter_by_customer_004651"
    _goto(page, 'http://localhost:8000')
    _log(page, "场景开始", f"case=ai_contracts_create_and_filter_by_customer_004651")

    # step 1: 打开合同列表页
    _goto(page, 'http://localhost:8000')
    _log(page, "goto", f"打开合同列表页")

    # step 2: 点击“+ 新建合同”按钮打开新建弹窗
    _act(page, "click", semantic='新建合同', primary=lambda p: p.get_by_test_id("btn-new"))
    _log(page, "click", f"点击“+ 新建合同”按钮打开新建弹窗")

    # step 3: 在弹窗中填写合同名称
    _act(page, "fill", semantic='请输入合同名称', primary=lambda p: p.get_by_test_id("inp-name"), value=_data('fill_0', ctx))
    _log(page, "fill", f"在弹窗中填写合同名称")

    # step 4: 管理单元选择 0021
    _act(page, "select", semantic='请选择_0021_0451_1031', primary=lambda p: p.get_by_test_id("sel-mu"), value=_data('select_1', ctx))
    _log(page, "select", f"管理单元选择 0021")

    # step 5: 帐套选择 001
    _act(page, "select", semantic='请选择_001_002_003', primary=lambda p: p.get_by_test_id("sel-fs"), value=_data('select_2', ctx))
    _log(page, "select", f"帐套选择 001")

    # step 6: 合同类型选择 合同
    _act(page, "select", semantic='请选择_合同_po_预po', primary=lambda p: p.get_by_test_id("sel-type"), value=_data('select_3', ctx))
    _log(page, "select", f"合同类型选择 合同")

    # step 7: 点击“选择客户”按钮弹出客户列表层
    _act(page, "click", semantic='选择客户', primary=lambda p: p.get_by_test_id("btn-pick-c"))
    _log(page, "click", f"点击“选择客户”按钮弹出客户列表层")

    # step 8: 在客户列表中选择北京华信科技有限公司那一行的“选择”按钮
    _act(page, "click", semantic='选择@北京华信科技有限公司', primary=lambda p: p.get_by_test_id("pick-c1"))
    _log(page, "click", f"在客户列表中选择北京华信科技有限公司那一行的“选择”按钮")

    # step 9: 业务单元选择 bu_a
    _act(page, "select", semantic='请选择_bu_a_bu_b_bu_c', primary=lambda p: p.get_by_test_id("sel-b"), value=_data('select_4', ctx))
    _log(page, "select", f"业务单元选择 bu_a")

    # step 10: 点击“提交”按钮提交新建合同
    _act(page, "click", semantic='提交', primary=lambda p: p.get_by_test_id("btn-submit"))
    _log(page, "click", f"点击“提交”按钮提交新建合同")
    _assert_text(page, _data('expect_0', ctx), '确认提交后页面出现“已新增合同”提示')

    # step 11: 在列表页客户筛选输入框输入“北京华信”
    _act(page, "fill", semantic='客户名称_右模糊_前缀匹配', primary=lambda p: p.get_by_test_id("tb-customer"), value=_data('fill_5', ctx))
    _log(page, "fill", f"在列表页客户筛选输入框输入“北京华信”")

    # step 12: 点击“搜索”按钮执行客户右模糊筛选
    _act(page, "click", semantic='搜索', primary=lambda p: p.get_by_test_id("btn-search"))
    _log(page, "click", f"点击“搜索”按钮执行客户右模糊筛选")
    _assert_text(page, _data('expect_1', ctx), '确认搜索结果中仍包含北京华信科技有限公司相关记录')


def test_ai_contracts_cross_page_011030(page, ctx):
    """打开合同列表页，在关键字搜索框输入 1005 并点击搜索；
点击结果行里的编号链接 HT-1005 进入合同详情页，确认已经换页（URL 含 contract_detail）
且详情页显示了编号 HT-1005 与名称 合同5；
然后点击「返回列表」回到列表页，再在关键字搜索框输入 1005 并点击搜索，确认列表里仍有 HT-1005。"""
    _CURRENT_LOG["case_id"] = "ai_contracts_cross_page_011030"
    _goto(page, 'http://localhost:8000/')
    _log(page, "场景开始", f"case=ai_contracts_cross_page_011030")

    # step 1: 打开合同列表页
    _goto(page, 'http://localhost:8000/')
    _log(page, "goto", f"打开合同列表页")

    # step 2: 在关键字搜索框输入 1005
    _act(page, "fill", semantic='合同编号_名称_管理单元_合同类型_帐套', primary=lambda p: p.get_by_test_id("tb-keyword"), value=_data('fill_0', ctx))
    _log(page, "fill", f"在关键字搜索框输入 1005")

    # step 3: 点击列表页搜索按钮
    _act(page, "click", semantic='搜索@列表页', primary=lambda p: p.get_by_test_id("btn-search"))
    _log(page, "click", f"点击列表页搜索按钮")
    _assert_text(page, _data('expect_0', ctx), '确认搜索结果中出现 HT-1005')

    # step 4: 点击结果行中的编号链接 HT-1005 进入详情页
    _act(page, "click", semantic='HT_1005', primary=lambda p: p.get_by_test_id("tbl-contracts").locator("tbody tr").filter(has_text="HT-1005 合同5 0451 002 po 北京中科智慧科技有限公司 bu_c").locator("td[data-field='contractNo']").get_by_role("link"))
    _log(page, "click", f"点击结果行中的编号链接 HT-1005 进入详情页")
    _assert_url(page, _data('expect_1', ctx), '确认已跳转到详情页（URL 含 contract_detail）')
    _assert_text(page, _data('expect_2', ctx), '确认详情页显示合同编号 HT-1005')
    _assert_text(page, _data('expect_3', ctx), '确认详情页显示合同名称 合同5')

    # step 5: 点击返回列表链接回到列表页
    _act(page, "click", semantic='返回列表', primary=lambda p: p.get_by_test_id("btn-back"))
    _log(page, "click", f"点击返回列表链接回到列表页")
    _assert_text(page, _data('expect_4', ctx), '确认已回到列表页（列表页独有的「新建合同」按钮文案 —— 列表页 URL 是根路径、没有独有片段，按弱 url 断言闸口径改用 text 断言做到达证据）')

    # step 6: 再次在关键字搜索框输入 1005
    _act(page, "fill", semantic='合同编号_名称_管理单元_合同类型_帐套', primary=lambda p: p.get_by_test_id("tb-keyword"), value=_data('fill_1', ctx))
    _log(page, "fill", f"再次在关键字搜索框输入 1005")

    # step 7: 再次点击列表页搜索按钮
    _act(page, "click", semantic='搜索@列表页', primary=lambda p: p.get_by_test_id("btn-search"))
    _log(page, "click", f"再次点击列表页搜索按钮")
    _assert_text(page, _data('expect_5', ctx), '确认列表里仍有 HT-1005')


@pytest.mark.parametrize("ctx", _ds_params('ai_contracts_search_by_no_000813'), ids=_ds_ids('ai_contracts_search_by_no_000813'), indirect=True)
def test_ai_contracts_search_by_no_000813(page, ctx):
    """在合同列表页面的搜索框输入 '{关键词}'，点击搜索按钮，
确认结果列表里出现编号为 {期望编号} 的合同记录。
（数据驱动 · L1：本用例由场景 data: 的 3 组数据展开成 3 条独立用例）"""
    _CURRENT_LOG["case_id"] = "ai_contracts_search_by_no_000813"
    _goto(page, 'http://localhost:8000')
    _log(page, "场景开始", f"case=ai_contracts_search_by_no_000813")

    # step 1: 打开合同列表页面
    _goto(page, 'http://localhost:8000')
    _log(page, "goto", f"打开合同列表页面")

    # step 2: 在关键字搜索框输入 {关键词}
    _act(page, "fill", semantic='合同编号_名称_管理单元_合同类型_帐套', primary=lambda p: p.get_by_test_id("tb-keyword"), value=_data('fill_0', ctx))
    _log(page, "fill", f"在关键字搜索框输入 {{关键词}}")

    # step 3: 点击搜索按钮触发查询
    _act(page, "click", semantic='搜索', primary=lambda p: p.get_by_test_id("btn-search"))
    _log(page, "click", f"点击搜索按钮触发查询")
    _assert_text(page, _data('expect_0', ctx), '确认结果列表中出现编号为 {期望编号} 的合同记录')


def test_ai_orders_return_from_contract_004934(page, ctx):
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
    _CURRENT_LOG["case_id"] = "ai_orders_return_from_contract_004934"
    _t = _Tabs(page)          # 多 tab：点了会开新 tab 的控件后 page 会被重新绑定到新 tab
    _goto(page, 'http://localhost:8000/')
    _log(page, "场景开始", f"case=ai_orders_return_from_contract_004934")

    # step 1: 打开合同列表页
    _goto(page, 'http://localhost:8000/')
    _log(page, "goto", f"打开合同列表页")
    _assert_text(page, _data('expect_0', ctx), '确认合同列表页已加载（右上角查看订单链接）')

    # step 2: 点击右上角「查看订单」，新开 tab 打开订单系统
    page = _t.open_new(lambda: _act(page, "click", semantic='查看订单', primary=lambda p: p.get_by_test_id("link-orders")))
    _log(page, "click_new_tab", f"点击右上角「查看订单」，新开 tab 打开订单系统")
    _assert_url(page, _data('expect_1', ctx), '确认新 tab 是订单系统页')
    _assert_text(page, _data('expect_2', ctx), '确认订单系统页独有文案')

    # step 3: 点击「+ 新建订单」打开弹窗
    _act(page, "click", semantic='新建订单', primary=lambda p: p.get_by_test_id("btn-new-order"))
    _log(page, "click", f"点击「+ 新建订单」打开弹窗")

    # step 4: 填写订单名称
    _act(page, "fill", semantic='请输入订单名称', primary=lambda p: p.get_by_test_id("o-name"), value=_data('fill_0', ctx))
    _log(page, "fill", f"填写订单名称")

    # step 5: 打开选择合同弹层
    _act(page, "click", semantic='选择合同', primary=lambda p: p.get_by_test_id("btn-pick-contract"))
    _log(page, "click", f"打开选择合同弹层")

    # step 6: 选中合同弹层第一行 HT-1001
    _act(page, "click", semantic='选择@HT_1001', primary=lambda p: p.get_by_test_id("pick-contract-HT-1001"))
    _log(page, "click", f"选中合同弹层第一行 HT-1001")

    # step 7: 打开业务单元弹层
    _act(page, "click", semantic='选择业务单元', primary=lambda p: p.get_by_test_id("btn-pick-bu"))
    _log(page, "click", f"打开业务单元弹层")

    # step 8: 选中业务单元第一行 bu_a
    _act(page, "click", semantic='选择@bu_a', primary=lambda p: p.get_by_test_id("pick-bu-bu_a"))
    _log(page, "click", f"选中业务单元第一行 bu_a")

    # step 9: 打开管理单元弹层
    _act(page, "click", semantic='选择管理单元', primary=lambda p: p.get_by_test_id("btn-pick-mu"))
    _log(page, "click", f"打开管理单元弹层")

    # step 10: 选中管理单元第一行 0021
    _act(page, "click", semantic='选择@0021', primary=lambda p: p.get_by_test_id("pick-mu-0021"))
    _log(page, "click", f"选中管理单元第一行 0021")

    # step 11: 打开帐套弹层
    _act(page, "click", semantic='选择帐套', primary=lambda p: p.get_by_test_id("btn-pick-file"))
    _log(page, "click", f"打开帐套弹层")

    # step 12: 选中帐套第一行 001
    _act(page, "click", semantic='选择@001', primary=lambda p: p.get_by_test_id("pick-file-001"))
    _log(page, "click", f"选中帐套第一行 001")

    # step 13: 订单类型下拉选「退货订单」
    _act(page, "select", semantic='请选择_标准销售订单_退货订单_服务订单_电商订单', primary=lambda p: p.get_by_test_id("o-type"), value=_data('select_1', ctx))
    _log(page, "select", f"订单类型下拉选「退货订单」")

    # step 14: 打开选择客户弹层
    _act(page, "click", semantic='选择客户@订单系统', primary=lambda p: p.get_by_test_id("btn-pick-cust"))
    _log(page, "click", f"打开选择客户弹层")

    # step 15: 选中第一个客户
    _act(page, "click", semantic='选择@北京华信科技有限公司@订单系统', primary=lambda p: p.get_by_test_id("pick-cust-c1"))
    _log(page, "click", f"选中第一个客户")

    # step 16: 打开选择销售员弹层
    _act(page, "click", semantic='选择销售员', primary=lambda p: p.get_by_test_id("btn-pick-salesman"))
    _log(page, "click", f"打开选择销售员弹层")

    # step 17: 选中第一个销售员
    _act(page, "click", semantic='选择@张伟', primary=lambda p: p.get_by_test_id("pick-salesman-s1"))
    _log(page, "click", f"选中第一个销售员")

    # step 18: 填写订单备注
    _act(page, "fill", semantic='订单备注_可不填', primary=lambda p: p.get_by_test_id("o-remark"), value=_data('fill_2', ctx))
    _log(page, "fill", f"填写订单备注")

    # step 19: 提交新建订单
    _act(page, "click", semantic='提交@订单系统', primary=lambda p: p.get_by_test_id("btn-submit-order"))
    _log(page, "click", f"提交新建订单")
    _assert_first_row(page, 'orderName', _data('expect_3', ctx), '确认列表第一行订单名称就是刚填的值')

    # step 20: 点击该行合同编号链接，新开 tab 打开合同详情页
    page = _click_row_cell(page, row_text=_data('row_text_3', ctx), cell_field='contractNo', tabs=_t)
    _log(page, "click_new_tab", f"点击该行合同编号链接，新开 tab 打开合同详情页")
    _assert_url(page, _data('expect_4', ctx), '确认新 tab 是合同详情页')
    _assert_text(page, _data('expect_5', ctx), '确认详情页显示合同编号 HT-1001')
    _assert_text(page, _data('expect_6', ctx), '确认详情页显示合同名称 合同1')

    # step 21: 点击详情页「返回」关闭本 tab
    page = _t.close_current(lambda: _act(page, "click", semantic='返回', primary=lambda p: p.get_by_test_id("btn-back")))
    _log(page, "close_tab", f"点击详情页「返回」关闭本 tab")
    _assert_url(page, _data('expect_7', ctx), '确认回到订单列表页')
    _assert_text(page, _data('expect_8', ctx), '确认仍在订单系统页')


def test_ai_在合同列表页面的搜索框输入_1005_点击搜索按_235545(page, ctx):
    """在合同列表页面的搜索框输入'1005'，点击搜索按钮，确认出现 HT-1005"""
    _CURRENT_LOG["case_id"] = "ai_在合同列表页面的搜索框输入_1005_点击搜索按_235545"
    _goto(page, 'http://localhost:8000')
    _log(page, "场景开始", f"case=ai_在合同列表页面的搜索框输入_1005_点击搜索按_235545")

    # step 1: 打开合同列表页面
    _goto(page, 'http://localhost:8000')
    _log(page, "goto", f"打开合同列表页面")

    # step 2: 在关键字搜索框输入 1005
    _act(page, "fill", semantic='合同编号_名称_管理单元_合同类型_帐套', primary=lambda p: p.get_by_test_id("tb-keyword"), value=_data('fill_0', ctx))
    _log(page, "fill", f"在关键字搜索框输入 1005")

    # step 3: 点击搜索按钮触发查询
    _act(page, "click", semantic='搜索', primary=lambda p: p.get_by_test_id("btn-search"))
    _log(page, "click", f"点击搜索按钮触发查询")
    _assert_text(page, _data('expect_0', ctx), '确认搜索结果中出现 HT-1005')


def test_assert_kinds_modal(page, ctx):
    """点开新建合同弹窗 → 断言弹窗与其字段可见（visible/count，弹窗内容需真页覆盖）"""
    _CURRENT_LOG["case_id"] = "assert_kinds_modal"
    _goto(page, 'http://localhost:8000')
    _log(page, "场景开始", f"case=assert_kinds_modal")

    # step 1: 打开合同列表页
    _goto(page, 'http://localhost:8000')
    _log(page, "goto", f"打开合同列表页")

    # step 2: 点击新建合同按钮打开弹窗
    _act(page, "click", semantic='新建合同', primary=lambda p: p.get_by_test_id("btn-new"))
    _log(page, "click", f"点击新建合同按钮打开弹窗")

    # ---- 断言（用例末尾）----
    _assert_visible(page, lambda p: p.locator('#modal-new'), semantic=None, desc='弹窗遮罩可见（visible）')
    _assert_visible(page, lambda p: p.locator("[data-testid='inp-name']"), semantic=None, desc='弹窗里的合同名称输入框可见')
    _assert_count(page, _data('expect_2', ctx), lambda p: p.locator('#modal-new select'), semantic=None, desc='弹窗内 4 个下拉（管理单元/帐套/合同类型/业务单元）—— 客户已改为弹层选择，不再是下拉')
    _assert_enabled(page, lambda p: p.locator("[data-testid='btn-submit']"), semantic=None, desc='提交按钮可用')


def test_assert_kinds_reset(page, ctx):
    """填关键字→搜索→重置：断言输入框被清空（value，验的是「被改写」不是「输入回显」）+ 列表恢复 20 行"""
    _CURRENT_LOG["case_id"] = "assert_kinds_reset"
    _goto(page, 'http://localhost:8000')
    _log(page, "场景开始", f"case=assert_kinds_reset")

    # step 1: 打开合同列表页
    _goto(page, 'http://localhost:8000')
    _log(page, "goto", f"打开合同列表页")

    # step 2: 关键字输入 1005
    _act(page, "fill", semantic='合同编号_名称_管理单元_合同类型_帐套', primary=lambda p: p.get_by_test_id("tb-keyword"), value=_data('fill_0', ctx))
    _log(page, "fill", f"关键字输入 1005")

    # step 3: 点击搜索按钮
    _act(page, "click", semantic='搜索', primary=lambda p: p.get_by_test_id("btn-search"))
    _log(page, "click", f"点击搜索按钮")

    # step 4: 点击重置按钮
    _act(page, "click", semantic='重置', primary=lambda p: p.get_by_test_id("btn-reset"))
    _log(page, "click", f"点击重置按钮")

    # ---- 断言（用例末尾）----
    _assert_value(page, _data('expect_0', ctx), lambda p: p.get_by_test_id("tb-keyword"), semantic='合同编号_名称_管理单元_合同类型_帐套', desc='重置后关键字输入框被清空（value：空串也是合法期望值）')
    _assert_count(page, _data('expect_1', ctx), lambda p: p.locator('#tbody-contracts tr'), semantic=None, desc='列表恢复全量 20 行')
    _assert_text(page, _data('expect_2', ctx), '状态行提示已重置')


def test_assert_kinds_search(page, ctx):
    """搜索 1005：覆盖 url/count/attr/text/hidden/enabled/disabled 断言类型（真页）"""
    _CURRENT_LOG["case_id"] = "assert_kinds_search"
    _goto(page, 'http://localhost:8000')
    _log(page, "场景开始", f"case=assert_kinds_search")

    # step 1: 打开合同列表页
    _goto(page, 'http://localhost:8000')
    _log(page, "goto", f"打开合同列表页")

    # step 2: 关键字输入 1005
    _act(page, "fill", semantic='合同编号_名称_管理单元_合同类型_帐套', primary=lambda p: p.get_by_test_id("tb-keyword"), value=_data('fill_0', ctx))
    _log(page, "fill", f"关键字输入 1005")

    # step 3: 点击搜索按钮
    _act(page, "click", semantic='搜索', primary=lambda p: p.get_by_test_id("btn-search"))
    _log(page, "click", f"点击搜索按钮")

    # ---- 断言（用例末尾）----
    _assert_url(page, _data('expect_0', ctx), 'URL 仍在合同列表页（url 断言：子串匹配）')
    _assert_count(page, _data('expect_1', ctx), lambda p: p.locator('#tbody-contracts tr'), semantic=None, desc='搜索结果恰好 1 行（count：结果行数）')
    _assert_count(page, _data('expect_2', ctx), lambda p: p.locator("#tbody-contracts tr[data-testid='row-HT-1005']"), semantic=None, desc='命中的正是 HT-1005 那一行')
    _assert_attr(page, 'data-field', _data('expect_3', ctx), lambda p: p.locator("#tbody-contracts tr:first-child td[data-field='contractNo']"), semantic=None, desc='首单元格是合同编号列（attr：data-field）')
    _assert_text(page, _data('expect_4', ctx), '列表里出现编号 HT-1005（text，原有类型）')
    _assert_text(page, _data('expect_5', ctx), '状态行提示搜索完成')
    _assert_hidden(page, lambda p: p.locator('#modal-new'), semantic=None, desc='新建弹窗保持关闭（hidden）')
    _assert_enabled(page, lambda p: p.get_by_test_id("btn-search"), semantic='搜索', desc='搜索按钮可用（enabled，走 element→语义映射的 locator）')
    _assert_disabled(page, lambda p: p.locator("[data-testid='btn-export']"), semantic=None, desc='导出按钮未接入 → 禁用（disabled）')


def test_assert_kinds_todo(page, ctx):
    """待办页：断言 checkbox 状态（checked/unchecked）+ 列表行数（count）"""
    _CURRENT_LOG["case_id"] = "assert_kinds_todo"
    _goto(page, 'http://localhost:8000/todo.html')
    _log(page, "场景开始", f"case=assert_kinds_todo")

    # step 1: 打开待办页
    _goto(page, 'http://localhost:8000/todo.html')
    _log(page, "goto", f"打开待办页")

    # ---- 断言（用例末尾）----
    _assert_checked(page, lambda p: p.locator("li:has-text('买牛奶') input[type=checkbox]"), semantic=None, desc='买牛奶 那条已勾选（checked）')
    _assert_unchecked(page, lambda p: p.locator("li:has-text('写周报') input[type=checkbox]"), semantic=None, desc='写周报 那条未勾选（unchecked）')
    _assert_count(page, _data('expect_2', ctx), lambda p: p.locator('#todo-list li'), semantic=None, desc='初始有 2 条待办')
    _assert_text(page, _data('expect_3', ctx), '列表里能看到 买牛奶')


def test_create_bu_a_c1(page, ctx):
    """新建合同(bu_a/c1)（客户从弹层列表选择）"""
    _CURRENT_LOG["case_id"] = "create_bu_a_c1"
    _goto(page, 'http://localhost:8000')
    _log(page, "场景开始", f"case=create_bu_a_c1")

    # step 1: 打开合同列表页
    _goto(page, 'http://localhost:8000')
    _log(page, "goto", f"打开合同列表页")

    # step 2: 点击新建合同按钮
    _act(page, "click", semantic='新建合同', primary=lambda p: p.get_by_test_id("btn-new"))
    _log(page, "click", f"点击新建合同按钮")

    # step 3: 在合同名称输入框输入名称
    _act(page, "fill", semantic='请输入合同名称', primary=lambda p: p.get_by_test_id("inp-name"), value=_data('fill_0', ctx))
    _log(page, "fill", f"在合同名称输入框输入名称")

    # step 4: 选择管理单元0021
    _act(page, "select", semantic='请选择_0021_0451_1031', primary=lambda p: p.get_by_test_id("sel-mu"), value=_data('select_1', ctx))
    _log(page, "select", f"选择管理单元0021")

    # step 5: 选择帐套001
    _act(page, "select", semantic='请选择_001_002_003', primary=lambda p: p.get_by_test_id("sel-fs"), value=_data('select_2', ctx))
    _log(page, "select", f"选择帐套001")

    # step 6: 选择合同类型'合同'
    _act(page, "select", semantic='请选择_合同_po_预po', primary=lambda p: p.get_by_test_id("sel-type"), value=_data('select_3', ctx))
    _log(page, "select", f"选择合同类型'合同'")

    # step 7: 点『选择客户』打开客户列表弹层
    _act(page, "click", semantic='选择客户', primary=lambda p: p.get_by_test_id("btn-pick-c"))
    _log(page, "click", f"点『选择客户』打开客户列表弹层")

    # step 8: 在客户列表里选『北京华信科技有限公司』那一行
    _act(page, "click", semantic='选择@北京华信科技有限公司', primary=lambda p: p.get_by_test_id("pick-c1"))
    _log(page, "click", f"在客户列表里选『北京华信科技有限公司』那一行")

    # step 9: 选择业务单元bu_a
    _act(page, "select", semantic='请选择_bu_a_bu_b_bu_c', primary=lambda p: p.get_by_test_id("sel-b"), value=_data('select_4', ctx))
    _log(page, "select", f"选择业务单元bu_a")

    # step 10: 点击提交按钮
    _act(page, "click", semantic='提交', primary=lambda p: p.get_by_test_id("btn-submit"))
    _log(page, "click", f"点击提交按钮")

    # ---- 断言（用例末尾）----
    _assert_value(page, _data('expect_0', ctx), lambda p: p.get_by_test_id("inp-c"), semantic='请选择客户', desc='提交前：客户输入框已被弹层回填为『北京华信科技有限公司』(value)')
    _assert_text(page, _data('expect_1', ctx), '断言列表出现新建的合同名称')


def test_create_bu_b_c2(page, ctx):
    """新建合同(bu_b/c2)（客户从弹层列表选择）"""
    _CURRENT_LOG["case_id"] = "create_bu_b_c2"
    _goto(page, 'http://localhost:8000')
    _log(page, "场景开始", f"case=create_bu_b_c2")

    # step 1: 打开合同列表页
    _goto(page, 'http://localhost:8000')
    _log(page, "goto", f"打开合同列表页")

    # step 2: 点击新建合同按钮
    _act(page, "click", semantic='新建合同', primary=lambda p: p.get_by_test_id("btn-new"))
    _log(page, "click", f"点击新建合同按钮")

    # step 3: 在合同名称输入框输入名称
    _act(page, "fill", semantic='请输入合同名称', primary=lambda p: p.get_by_test_id("inp-name"), value=_data('fill_0', ctx))
    _log(page, "fill", f"在合同名称输入框输入名称")

    # step 4: 选择管理单元0451
    _act(page, "select", semantic='请选择_0021_0451_1031', primary=lambda p: p.get_by_test_id("sel-mu"), value=_data('select_1', ctx))
    _log(page, "select", f"选择管理单元0451")

    # step 5: 选择帐套002
    _act(page, "select", semantic='请选择_001_002_003', primary=lambda p: p.get_by_test_id("sel-fs"), value=_data('select_2', ctx))
    _log(page, "select", f"选择帐套002")

    # step 6: 选择合同类型po
    _act(page, "select", semantic='请选择_合同_po_预po', primary=lambda p: p.get_by_test_id("sel-type"), value=_data('select_3', ctx))
    _log(page, "select", f"选择合同类型po")

    # step 7: 点『选择客户』打开客户列表弹层
    _act(page, "click", semantic='选择客户', primary=lambda p: p.get_by_test_id("btn-pick-c"))
    _log(page, "click", f"点『选择客户』打开客户列表弹层")

    # step 8: 在客户列表里选『上海远东贸易有限公司』那一行
    _act(page, "click", semantic='选择@上海远东贸易有限公司', primary=lambda p: p.get_by_test_id("pick-c2"))
    _log(page, "click", f"在客户列表里选『上海远东贸易有限公司』那一行")

    # step 9: 选择业务单元bu_b
    _act(page, "select", semantic='请选择_bu_a_bu_b_bu_c', primary=lambda p: p.get_by_test_id("sel-b"), value=_data('select_4', ctx))
    _log(page, "select", f"选择业务单元bu_b")

    # step 10: 点击提交按钮
    _act(page, "click", semantic='提交', primary=lambda p: p.get_by_test_id("btn-submit"))
    _log(page, "click", f"点击提交按钮")

    # ---- 断言（用例末尾）----
    _assert_value(page, _data('expect_0', ctx), lambda p: p.get_by_test_id("inp-c"), semantic='请选择客户', desc='提交前：客户输入框已被弹层回填为『上海远东贸易有限公司』(value)')
    _assert_text(page, _data('expect_1', ctx), '断言列表出现新建的合同名称')


def test_cross_page_detail(page, ctx):
    """跨页：列表搜索 → 点编号进详情页（换页有 url 断言）→ 返回列表再搜索核验"""
    _CURRENT_LOG["case_id"] = "cross_page_detail"
    _goto(page, 'http://localhost:8000')
    _log(page, "场景开始", f"case=cross_page_detail")

    # step 1: 打开合同列表页
    _goto(page, 'http://localhost:8000/')
    _log(page, "goto", f"打开合同列表页")

    # step 2: 关键字输入 1005
    _act(page, "fill", semantic='合同编号_名称_管理单元_合同类型_帐套', primary=lambda p: p.get_by_test_id("tb-keyword"), value=_data('fill_0', ctx))
    _log(page, "fill", f"关键字输入 1005")

    # step 3: 点击列表页的搜索按钮
    _act(page, "click", semantic='搜索@列表页', primary=lambda p: p.get_by_test_id("btn-search"))
    _log(page, "click", f"点击列表页的搜索按钮")
    _assert_count(page, _data('expect_0', ctx), lambda p: p.locator('#tbody-contracts tr'), semantic=None, desc='【列表页·搜索后】结果恰好 1 行')
    _assert_attr(page, 'data-cust', _data('expect_1', ctx), lambda p: p.locator("#tbody-contracts tr[data-testid='row-HT-1005'] td[data-field='customer']"), semantic=None, desc='【列表页】HT-1005 的客户编号 = c5（客户按序号确定：HT-1001→c1、HT-1005→c5、HT-1007→c1…）')

    # step 4: 点击结果里的编号链接 HT-1005 进入详情页
    _act(page, "click", semantic='HT_1005', primary=lambda p: p.get_by_test_id("tbl-contracts").locator("tbody tr").filter(has_text="HT-1005 合同5 0451 002 po 北京中科智慧科技有限公司 bu_c").locator("td[data-field='contractNo']").get_by_role("link"))
    _log(page, "click", f"点击结果里的编号链接 HT-1005 进入详情页")
    _assert_url(page, _data('expect_2', ctx), '【换页证据】点击编号后 URL 已变为详情页')
    _assert_count(page, _data('expect_3', ctx), lambda p: p.locator("[data-testid='detail-no']"), semantic=None, desc='【详情页】编号单元格存在（确认换的是详情页而不是别的页）')
    _assert_text(page, _data('expect_4', ctx), '【详情页】显示名称 合同5（与列表页 HT-1005 一致）')
    _assert_attr(page, 'data-cust', _data('expect_5', ctx), lambda p: p.locator("[data-testid='detail-cust']"), semantic=None, desc='【详情页·客户跨页一致】HT-1005 的客户编号也是 c5 —— 2026-09-14 起两页读服务端的同一条记录，客户不再各自推导')

    # step 5: 点击详情页的「返回列表」回到列表页
    _act(page, "click", semantic='返回列表', primary=lambda p: p.get_by_test_id("btn-back"))
    _log(page, "click", f"点击详情页的「返回列表」回到列表页")
    _assert_visible(page, lambda p: p.locator("[data-testid='btn-new']"), semantic=None, desc='【回到列表页】「+ 新建合同」按钮可见（列表页特征）')
    _assert_count(page, _data('expect_7', ctx), lambda p: p.locator("#tbody-contracts tr[data-testid='row-HT-1001']"), semantic=None, desc='【回到列表页·基线】预置首行 HT-1001 在列表里（F5 稳健化：不再用「全量 20 行」——那条会被本次运行新建的数据顶掉，与「回到列表页」要验的事无关）')

    # step 6: 回到列表页后再输入关键字 1005
    _act(page, "fill", semantic='合同编号_名称_管理单元_合同类型_帐套', primary=lambda p: p.get_by_test_id("tb-keyword"), value=_data('fill_1', ctx))
    _log(page, "fill", f"回到列表页后再输入关键字 1005")

    # step 7: 再次点击搜索
    _act(page, "click", semantic='搜索@列表页', primary=lambda p: p.get_by_test_id("btn-search"))
    _log(page, "click", f"再次点击搜索")
    _assert_count(page, _data('expect_8', ctx), lambda p: p.locator("#tbody-contracts tr[data-testid='row-HT-1005']"), semantic=None, desc='【末尾】再搜索 1005 仍能命中 HT-1005')
    _assert_text(page, _data('expect_9', ctx), '【末尾】列表里出现编号 HT-1005')


def test_hand_enter_search(page, ctx):
    """手搓用例 · 回车触发搜索 + 客户右模糊筛选"""
    _CURRENT_LOG["case_id"] = "hand_enter_search"
    _goto(page, 'http://localhost:8000')
    _log(page, "场景开始", f"case=hand_enter_search")

    # step 1: 打开合同列表页
    _goto(page, 'http://localhost:8000')
    _log(page, "goto", f"打开合同列表页")

    # step 2: 在搜索框输入'合同7'
    _act(page, "fill", semantic='合同编号_名称_管理单元_合同类型_帐套', primary=lambda p: p.get_by_test_id("tb-keyword"), value=_data('fill_0', ctx))
    _log(page, "fill", f"在搜索框输入'合同7'")

    # step 3: 在搜索框按回车触发查询
    _act(page, "press_enter", semantic='合同编号_名称_管理单元_合同类型_帐套', primary=lambda p: p.get_by_test_id("tb-keyword"))
    _log(page, "press_enter", f"在搜索框按回车触发查询")

    # step 4: 客户筛选框输入前缀『北京』（右模糊：c1/c5 两家）
    _act(page, "fill", semantic='客户名称_右模糊_前缀匹配', primary=lambda p: p.get_by_test_id("tb-customer"), value=_data('fill_1', ctx))
    _log(page, "fill", f"客户筛选框输入前缀『北京』（右模糊：c1/c5 两家）")

    # step 5: 点击搜索按钮
    _act(page, "click", semantic='搜索', primary=lambda p: p.get_by_test_id("btn-search"))
    _log(page, "click", f"点击搜索按钮")

    # ---- 断言（用例末尾）----
    _assert_count(page, _data('expect_0', ctx), lambda p: p.locator("#tbody-contracts tr[data-testid^='row-']"), semantic=None, desc='关键字『合同7』(HT-1007) × 客户前缀『北京』(北京华信) ⇒ 1 条')
    _assert_text(page, _data('expect_1', ctx), '断言列表状态行出现搜索完成前缀')


def test_search_customer_fuzzy(page, ctx):
    """客户右模糊（前缀）筛选：前缀命中并收窄到 4 条"""
    _CURRENT_LOG["case_id"] = "search_customer_fuzzy"
    _goto(page, 'http://localhost:8000')
    _log(page, "场景开始", f"case=search_customer_fuzzy")

    # step 1: 打开合同列表页
    _goto(page, 'http://localhost:8000')
    _log(page, "goto", f"打开合同列表页")

    # step 2: 客户筛选框输入前缀『北京』
    _act(page, "fill", semantic='客户名称_右模糊_前缀匹配', primary=lambda p: p.get_by_test_id("tb-customer"), value=_data('fill_0', ctx))
    _log(page, "fill", f"客户筛选框输入前缀『北京』")

    # step 3: 点击搜索按钮
    _act(page, "click", semantic='搜索', primary=lambda p: p.get_by_test_id("btn-search"))
    _log(page, "click", f"点击搜索按钮")

    # step 4: 把客户筛选改成更窄的前缀『北京华』
    _act(page, "fill", semantic='客户名称_右模糊_前缀匹配', primary=lambda p: p.get_by_test_id("tb-customer"), value=_data('fill_1', ctx))
    _log(page, "fill", f"把客户筛选改成更窄的前缀『北京华』")

    # step 5: 再次点击搜索按钮
    _act(page, "click", semantic='搜索', primary=lambda p: p.get_by_test_id("btn-search"))
    _log(page, "click", f"再次点击搜索按钮")

    # ---- 断言（用例末尾）----
    _assert_count(page, _data('expect_0', ctx), lambda p: p.locator("#tbody-contracts tr[data-testid^='row-']"), semantic=None, desc='前缀『北京华』命中 4 条（c1 北京华信科技有限公司名下的合同：HT-1001/1007/1013/1019）')
    _assert_value(page, _data('expect_1', ctx), lambda p: p.get_by_test_id("tb-customer"), semantic='客户名称_右模糊_前缀匹配', desc='筛选框里保留的是更窄的那个前缀')
    _assert_attr(page, 'data-cust', _data('expect_2', ctx), lambda p: p.locator("#tbody-contracts tr:first-child td[data-field='customer']"), semantic=None, desc='首行客户编号是 c1（北京华信科技有限公司）')
    _assert_text(page, _data('expect_3', ctx), '状态行报告右模糊口径')


def test_search_customer_fuzzy_negative(page, ctx):
    """客户右模糊（前缀）筛选：非前缀『华信』必须不命中"""
    _CURRENT_LOG["case_id"] = "search_customer_fuzzy_negative"
    _goto(page, 'http://localhost:8000')
    _log(page, "场景开始", f"case=search_customer_fuzzy_negative")

    # step 1: 打开合同列表页
    _goto(page, 'http://localhost:8000')
    _log(page, "goto", f"打开合同列表页")

    # step 2: 客户筛选框输入**非前缀**的『华信』
    _act(page, "fill", semantic='客户名称_右模糊_前缀匹配', primary=lambda p: p.get_by_test_id("tb-customer"), value=_data('fill_0', ctx))
    _log(page, "fill", f"客户筛选框输入**非前缀**的『华信』")

    # step 3: 点击搜索按钮
    _act(page, "click", semantic='搜索', primary=lambda p: p.get_by_test_id("btn-search"))
    _log(page, "click", f"点击搜索按钮")

    # ---- 断言（用例末尾）----
    _assert_count(page, _data('expect_0', ctx), lambda p: p.locator("#tbody-contracts tr[data-testid^='row-']"), semantic=None, desc='『华信』不是任何客户名的前缀 ⇒ 0 条（若命中就说明实现成了包含匹配，不是右模糊）')
    _assert_text(page, _data('expect_1', ctx), '空结果提示')


def test_search_mixed(page, ctx):
    """混合搜索：名称模糊 + 客户右模糊"""
    _CURRENT_LOG["case_id"] = "search_mixed"
    _goto(page, 'http://localhost:8000')
    _log(page, "场景开始", f"case=search_mixed")

    # step 1: 打开合同列表页
    _goto(page, 'http://localhost:8000')
    _log(page, "goto", f"打开合同列表页")

    # step 2: 在搜索框输入关键字'合同'
    _act(page, "fill", semantic='合同编号_名称_管理单元_合同类型_帐套', primary=lambda p: p.get_by_test_id("tb-keyword"), value=_data('fill_0', ctx))
    _log(page, "fill", f"在搜索框输入关键字'合同'")

    # step 3: 客户筛选框输入前缀『广州』（右模糊）
    _act(page, "fill", semantic='客户名称_右模糊_前缀匹配', primary=lambda p: p.get_by_test_id("tb-customer"), value=_data('fill_1', ctx))
    _log(page, "fill", f"客户筛选框输入前缀『广州』（右模糊）")

    # step 4: 点击搜索按钮
    _act(page, "click", semantic='搜索', primary=lambda p: p.get_by_test_id("btn-search"))
    _log(page, "click", f"点击搜索按钮")

    # ---- 断言（用例末尾）----
    _assert_count(page, _data('expect_0', ctx), lambda p: p.locator("#tbody-contracts tr[data-testid^='row-']"), semantic=None, desc='关键字『合同』(全命中) × 客户前缀『广州』(c3) ⇒ 3 条：HT-1003/1009/1015')
    _assert_text(page, _data('expect_1', ctx), '断言页面出现搜索结果')


def test_search_name_fuzzy(page, ctx):
    """按合同名称模糊搜索"""
    _CURRENT_LOG["case_id"] = "search_name_fuzzy"
    _goto(page, 'http://localhost:8000')
    _log(page, "场景开始", f"case=search_name_fuzzy")

    # step 1: 打开合同列表页
    _goto(page, 'http://localhost:8000')
    _log(page, "goto", f"打开合同列表页")

    # step 2: 在搜索框输入关键字'合同1'
    _act(page, "fill", semantic='合同编号_名称_管理单元_合同类型_帐套', primary=lambda p: p.get_by_test_id("tb-keyword"), value=_data('fill_0', ctx))
    _log(page, "fill", f"在搜索框输入关键字'合同1'")

    # step 3: 点击搜索按钮
    _act(page, "click", semantic='搜索', primary=lambda p: p.get_by_test_id("btn-search"))
    _log(page, "click", f"点击搜索按钮")

    # ---- 断言（用例末尾）----
    _assert_text(page, _data('expect_0', ctx), '断言页面出现搜索结果')

