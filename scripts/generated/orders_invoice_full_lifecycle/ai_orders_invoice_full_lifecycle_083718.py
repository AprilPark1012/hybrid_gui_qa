"""hybrid_gui_qa 用例模块：ai_orders_invoice_full_lifecycle_083718（场景 orders_invoice_full_lifecycle）—— 由 cases/orders_invoice_full_lifecycle/ai_orders_invoice_full_lifecycle_083718.json 自动生成。

**不要手改本文件**：改用例后重跑 generate 会覆盖它。要改行为 → 改用例 json / 场景 yml。
数据抽离在 scripts/datasets/ai_orders_invoice_full_lifecycle_083718.json（脚本与数据分离）。
一个用例一个文件（P20）：便于按 id 管理、按变化增量重生成。

运行（推荐走 cli：自带资源预检 + run-id 隔离的日志/报告）:
  python -m framework.cli run --workers 2                 # 全量
  python -m framework.cli run --debug --case ai_orders_invoice_full_lifecycle_083718        # 只调试这一条
裸跑 pytest（未设 HYBRID_RUN_ID 时日志落 log/latest/）:
  pytest scripts/generated/orders_invoice_full_lifecycle/ai_orders_invoice_full_lifecycle_083718.py -v
"""
from _harness import (_CURRENT_LOG, _log, _data, _act, _goto,
                      # L1 数据参数化（2026-09-21）：用例上的 parametrize 要用这两个
                      # [!] 同 `_Tabs` 那条教训：模板里渲染出的调用必须在这里同时 import，漏一个就是 NameError
                      _ds_params, _ds_ids,
                      _assert_text, _assert_url,
                      _assert_visible, _assert_hidden, _assert_count,
                      _assert_attr, _assert_value,
                      _assert_checked, _assert_unchecked,
                      _assert_enabled, _assert_disabled,
                      # 2026-09-17 跨 tab / 行内定位 / 首行断言用的辅助
                      # [!] 模板里渲染出的调用必须**同时**在这里 import —— 漏一个就是运行时 NameError
                      _Tabs, _click_row_cell, _assert_first_row,
                      # P22 批 4/5：等待式断言（wait_text；批 5 起支持 selector 限定范围）
                      _assert_wait_text)
# P16 批 5：运行期「锚点 + 容器内相对路径」下钻（col.header 这类列口径只有运行时才算得出列序）
from framework.tools.probe.scope_locate import drill as _drill
import pytest
from playwright.sync_api import expect as _pw_expect

def test_ai_orders_invoice_full_lifecycle_083718(page, ctx):
    """1. 以**超级管理员**登录系统。
2. 切换到**订单管理员**角色（不切的话下一步的保存按钮是置灰的）。
3. 进入合同列表页，**选中一条合同**（第一行，HT-1001）。
   [!] 点「新建订单」在 demo 里打开的是 **iframe 弹层**（探测链路暂不覆盖弹层内控件，已单独立项）；
   故本条走**等价直达**：打开新建订单页并把该合同带进去（`order_new.html?contract_no=HT-1001`）。
4. 在新建订单页填写：订单名称用「全链路-{datetime}」、合同已带入、业务单元/管理单元/帐套各选第一行、
   订单类型选第一项、客户与销售员各选第一个、订单备注填「端到端全链路场景」；点「保存」。
5. 回到合同列表页点「查看订单」跳到订单系统页面；在**订单名称**搜索框输入刚填的订单名称，点「搜索」，
   列表里出现这条订单。
6. 点这条订单的**订单名称**进入订单详情页；点「编辑」进入编辑态（进编辑态后行工具栏的
   「新增行 / 保存 / 取消」才可用，只读态是置灰的）。
   然后**新增 2 个订单行**：每新增一行都要**填满该行的 4 个必填项**（物料编码 / 产品编码 / 数量 / 行类型），
   两行都填好后，点**行工具栏里的「保存」**把订单行**先保存**下来。
   [!] 业务前提（必须遵守，否则后面白给）：**页面上有未保存的修改时，点「提交」不会生效**
   —— 它只会提示「请先点保存再提交」，订单不会真的被提交、状态也不会开始流转。
   所以顺序必须是「填行 → 保存行 → 再提交」。
   最后点底部的**「提交」**提交整个订单（提交成功后订单进入履行状态，开始按时间自动流转）。
7. 点底部「返回」回到订单列表；用订单名称搜索找到它，**等待**它的状态自动流转到「已关闭」。
   该流转是**按时间自动推进**的：提交订单后**最长约 150 秒**才会变成「已关闭」，所以这一步要
   **有界等待**（轮询到状态变化为止），既不要固定 sleep 硬等，也不要只等几秒就判失败。
8. 切换到**发票管理员**角色；在订单列表里**选中该订单**，点「去开票」。
9. 在开票页确认订单编号/合同编号已带入（发票号是系统生成的），填写发票行后点「保存」，完成发票创建。
10. 进入发票列表页，在**订单名称**搜索框输入该订单名称，点「搜索」-> 能搜到刚创建的那张发票。"""
    _CURRENT_LOG["case_id"] = "ai_orders_invoice_full_lifecycle_083718"
    _goto(page, 'http://localhost:8000/login.html')
    _log(page, "场景开始", f"case=ai_orders_invoice_full_lifecycle_083718")

    # step 1: 进入合同列表页
    _goto(page, 'http://localhost:8000/')
    _log(page, "goto", f"进入合同列表页")
    _assert_text(page, _data('expect_0', ctx), '确认到达合同列表页')

    # step 2: 打开角色切换菜单
    _act(page, "click", semantic='超@合同列表页', primary=lambda p: p.get_by_role("button", name="超"))
    _log(page, "click", f"打开角色切换菜单")

    # step 3: 切换为订单管理员角色
    _act(page, "click", semantic='切换为订单管理员@合同列表页', primary=lambda p: p.get_by_role("button", name="切换为订单管理员"))
    _log(page, "click", f"切换为订单管理员角色")

    # step 4: 等价直达新建订单页并带入合同 HT-1001
    _goto(page, 'http://localhost:8000/order_new.html?contract_no=HT-1001')
    _log(page, "goto", f"等价直达新建订单页并带入合同 HT-1001")
    _assert_text(page, _data('expect_1', ctx), '确认到达新建订单页')

    # step 5: 填写订单名称
    _act(page, "fill", semantic='订单名称@新建订单页', primary=lambda p: p.get_by_role("textbox", name="订单名称"), value=_data('fill_0', ctx))
    _log(page, "fill", f"填写订单名称")

    # step 6: 业务单元选第一项
    _act(page, "select", semantic='业务单元@新建订单页', primary=lambda p: p.get_by_role("combobox", name="业务单元"))
    _log(page, "select", f"业务单元选第一项")

    # step 7: 管理单元选第一项
    _act(page, "select", semantic='管理单元@新建订单页', primary=lambda p: p.get_by_role("combobox", name="管理单元"))
    _log(page, "select", f"管理单元选第一项")

    # step 8: 帐套选第一项
    _act(page, "select", semantic='帐套@新建订单页', primary=lambda p: p.get_by_role("combobox", name="帐套"))
    _log(page, "select", f"帐套选第一项")

    # step 9: 订单类型选第一项
    _act(page, "select", semantic='订单类型@新建订单页', primary=lambda p: p.get_by_role("combobox", name="订单类型"))
    _log(page, "select", f"订单类型选第一项")

    # step 10: 客户选第一个
    _act(page, "select", semantic='客户@新建订单页', primary=lambda p: p.get_by_role("combobox", name="客户"))
    _log(page, "select", f"客户选第一个")

    # step 11: 销售员选第一个
    _act(page, "select", semantic='销售员@新建订单页', primary=lambda p: p.get_by_role("combobox", name="销售员"))
    _log(page, "select", f"销售员选第一个")

    # step 12: 保存新建订单
    _act(page, "click", semantic='保存@新建订单页', primary=lambda p: p.get_by_role("button", name="保存"))
    _log(page, "click", f"保存新建订单")

    # step 13: 进入订单列表页
    _goto(page, 'http://localhost:8000/orders.html')
    _log(page, "goto", f"进入订单列表页")
    _assert_text(page, _data('expect_2', ctx), '确认到达订单列表页')

    # step 14: 按订单名称搜索
    _act(page, "fill", semantic='订单名称@订单列表页', primary=lambda p: p.get_by_role("textbox", name="订单名称"), value=_data('fill_1', ctx))
    _log(page, "fill", f"按订单名称搜索")

    # step 15: 点击搜索
    _act(page, "click", semantic='搜索@订单列表页', primary=lambda p: p.get_by_role("button", name="搜索"))
    _log(page, "click", f"点击搜索")
    _assert_first_row(page, 'orderName', _data('expect_3', ctx), '确认首行就是刚创建的订单')

    # step 16: 点订单名称进入订单详情页
    _click_row_cell(page, row_text=_data('row_text_2', ctx), cell_field='orderName', tabs=None, op='click')
    _log(page, "click", f"点订单名称进入订单详情页")
    _assert_text(page, _data('expect_4', ctx), '确认到达订单详情页')

    # step 17: 进入编辑态
    _act(page, "click", semantic='编辑', primary=lambda p: p.get_by_role("button", name="编辑"))
    _log(page, "click", f"进入编辑态")

    # step 18: 新增第 1 个订单行
    _act(page, "click", semantic='新增行@订单详情页', primary=lambda p: p.get_by_role("button", name="新增行"))
    _log(page, "click", f"新增第 1 个订单行")

    # step 19: 新增第 2 个订单行
    _act(page, "click", semantic='新增行@订单详情页', primary=lambda p: p.get_by_role("button", name="新增行"))
    _log(page, "click", f"新增第 2 个订单行")

    # step 20: 提交整个订单
    _act(page, "click", semantic='提交', primary=lambda p: p.get_by_role("button", name="提交"))
    _log(page, "click", f"提交整个订单")

    # step 21: 点底部返回回到订单列表
    _act(page, "click", semantic='返回', primary=lambda p: p.get_by_role("link", name="返回"))
    _log(page, "click", f"点底部返回回到订单列表")
    _assert_text(page, _data('expect_5', ctx), '确认回到订单列表页')

    # step 22: 再次按订单名称搜索
    _act(page, "fill", semantic='订单名称@订单列表页', primary=lambda p: p.get_by_role("textbox", name="订单名称"), value=_data('fill_3', ctx))
    _log(page, "fill", f"再次按订单名称搜索")

    # step 23: 点击搜索
    _act(page, "click", semantic='搜索@订单列表页', primary=lambda p: p.get_by_role("button", name="搜索"))
    _log(page, "click", f"点击搜索")
    _assert_wait_text(page, _data('expect_6', ctx), timeout_ms=150000, refresh='research', desc='有界等待订单状态自动流转到已关闭', selector='')

    # step 24: 打开角色切换菜单
    _act(page, "click", semantic='超@订单列表页', primary=lambda p: p.get_by_role("button", name="超"))
    _log(page, "click", f"打开角色切换菜单")

    # step 25: 切换为发票管理员角色
    _act(page, "click", semantic='切换为发票管理员@订单列表页', primary=lambda p: p.get_by_role("button", name="切换为发票管理员"))
    _log(page, "click", f"切换为发票管理员角色")

    # step 26: 选中该订单行
    _click_row_cell(page, row_text=_data('row_text_4', ctx), cell_field='pick', tabs=None, op='check')
    _log(page, "check", f"选中该订单行")

    # step 27: 点去开票跳转开票页
    _act(page, "click", semantic='去开票', primary=lambda p: p.get_by_role("button", name="去开票"))
    _log(page, "click", f"点去开票跳转开票页")
    _assert_text(page, _data('expect_7', ctx), '确认到达开票页')
    _assert_text(page, _data('expect_8', ctx), '确认订单编号与合同编号已带入')

    # step 28: 新增发票行
    _act(page, "click", semantic='新增行@开票页', primary=lambda p: p.get_by_role("button", name="新增行"))
    _log(page, "click", f"新增发票行")

    # step 29: 保存发票
    _act(page, "click", semantic='保存@应收发票创建@开票页', primary=lambda p: p.get_by_role("button", name="保存"))
    _log(page, "click", f"保存发票")

    # step 30: 进入发票列表页
    _goto(page, 'http://localhost:8000/invoice_list.html')
    _log(page, "goto", f"进入发票列表页")
    _assert_text(page, _data('expect_9', ctx), '确认到达发票列表页')

    # step 31: 按订单名称搜索发票
    _act(page, "fill", semantic='订单名称@发票列表页', primary=lambda p: p.get_by_role("textbox", name="订单名称"), value=_data('fill_5', ctx))
    _log(page, "fill", f"按订单名称搜索发票")

    # step 32: 点击搜索
    _act(page, "click", semantic='搜索@发票列表页', primary=lambda p: p.get_by_role("button", name="搜索"))
    _log(page, "click", f"点击搜索")
    _assert_text(page, _data('expect_10', ctx), '确认搜到刚创建的发票')

