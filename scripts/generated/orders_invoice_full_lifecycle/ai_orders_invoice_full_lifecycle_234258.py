"""hybrid_gui_qa 用例模块：ai_orders_invoice_full_lifecycle_234258（场景 orders_invoice_full_lifecycle）—— 由 cases/orders_invoice_full_lifecycle/ai_orders_invoice_full_lifecycle_234258.json 自动生成。

**不要手改本文件**：改用例后重跑 generate 会覆盖它。要改行为 → 改用例 json / 场景 yml。
数据抽离在 scripts/datasets/ai_orders_invoice_full_lifecycle_234258.json（脚本与数据分离）。
一个用例一个文件（P20）：便于按 id 管理、按变化增量重生成。

运行（推荐走 cli：自带资源预检 + run-id 隔离的日志/报告）:
  python -m framework.cli run --workers 2                 # 全量
  python -m framework.cli run --debug --case ai_orders_invoice_full_lifecycle_234258        # 只调试这一条
裸跑 pytest（未设 HYBRID_RUN_ID 时日志落 log/latest/）:
  pytest scripts/generated/orders_invoice_full_lifecycle/ai_orders_invoice_full_lifecycle_234258.py -v
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
                      # 2026-10-11 V8.4.6 行下标定位（`row_index`，含 `-1` = 最后一行）：
                      #   [!] 方案 ③ 框架兜底会**自动补** `row_index=-1` -> 渲染出 `_act_row(...)`，
                      #   而这里原先漏了它 -> 真跑 `NameError: name '_act_row' is not defined`
                      #   （2026-10-11 实测：生成期闸门全绿、真跑才红）。模板渲染出的调用
                      #   与这里的 import 必须**成对**维护 —— 判据 test_generated_helpers_are_imported 兜着。
                      _act_row,
                      # P22 批 4/5：等待式断言（wait_text；批 5 起支持 selector 限定范围）
                      _assert_wait_text)
# P16 批 5：运行期「锚点 + 容器内相对路径」下钻（col.header 这类列口径只有运行时才算得出列序）
from framework.tools.probe.scope_locate import drill as _drill
import pytest
from playwright.sync_api import expect as _pw_expect

def test_ai_orders_invoice_full_lifecycle_234258(page, ctx):
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
    _CURRENT_LOG["case_id"] = "ai_orders_invoice_full_lifecycle_234258"
    _goto(page, 'http://localhost:8000/login.html')
    _log(page, "场景开始", f"case=ai_orders_invoice_full_lifecycle_234258")

    # step 1: 等价直达新建订单页并带入合同 HT-1001
    _goto(page, 'http://localhost:8000/order_new.html?contract_no=HT-1001')
    _log(page, "goto", f"等价直达新建订单页并带入合同 HT-1001")
    _assert_text(page, _data('expect_0', ctx), '确认已进入新建订单页')

    # step 2: 填写订单名称
    _act(page, "fill", semantic='订单名称@新建订单页', primary=lambda p: p.get_by_role("textbox", name="订单名称"), value=_data('fill_0', ctx))
    _log(page, "fill", f"填写订单名称")

    # step 3: 业务单元选第一项
    _act(page, "select", semantic='业务单元@新建订单页', primary=lambda p: p.get_by_role("combobox", name="业务单元"))
    _log(page, "select", f"业务单元选第一项")

    # step 4: 管理单元选第一项
    _act(page, "select", semantic='管理单元@新建订单页', primary=lambda p: p.get_by_role("combobox", name="管理单元"))
    _log(page, "select", f"管理单元选第一项")

    # step 5: 帐套选第一项
    _act(page, "select", semantic='帐套@新建订单页', primary=lambda p: p.get_by_role("combobox", name="帐套"))
    _log(page, "select", f"帐套选第一项")

    # step 6: 订单类型选第一项
    _act(page, "select", semantic='订单类型@新建订单页', primary=lambda p: p.get_by_role("combobox", name="订单类型"))
    _log(page, "select", f"订单类型选第一项")

    # step 7: 客户选第一个
    _act(page, "select", semantic='客户@新建订单页', primary=lambda p: p.get_by_role("combobox", name="客户"))
    _log(page, "select", f"客户选第一个")

    # step 8: 销售员选第一个
    _act(page, "select", semantic='销售员@新建订单页', primary=lambda p: p.get_by_role("combobox", name="销售员"))
    _log(page, "select", f"销售员选第一个")

    # step 9: 填写订单备注
    _act(page, "fill", semantic='订单备注', primary=lambda p: p.get_by_role("textbox", name="订单备注"), value=_data('fill_1', ctx))
    _log(page, "fill", f"填写订单备注")

    # step 10: 保存新建订单
    _act(page, "click", semantic='保存@新建订单页', primary=lambda p: p.get_by_role("button", name="保存"))
    _log(page, "click", f"保存新建订单")

    # step 11: 进入订单列表页
    _goto(page, 'http://localhost:8000/orders.html')
    _log(page, "goto", f"进入订单列表页")
    _assert_text(page, _data('expect_1', ctx), '确认到达订单列表页')

    # step 12: 在订单名称搜索框输入刚建的订单名称
    _act(page, "fill", semantic='订单名称@订单系统', primary=lambda p: p.get_by_role("textbox", name="订单名称"), value=_data('fill_2', ctx))
    _log(page, "fill", f"在订单名称搜索框输入刚建的订单名称")

    # step 13: 点击搜索
    _act(page, "click", semantic='搜索@订单列表页', primary=lambda p: p.get_by_role("button", name="搜索"))
    _log(page, "click", f"点击搜索")
    _assert_first_row(page, 'orderName', _data('expect_2', ctx), '断言首行就是刚建的订单')

    # step 14: 点该订单的订单名称进入详情页
    _click_row_cell(page, row_text=_data('row_text_3', ctx), cell_field='orderName', tabs=None, op='click')
    _log(page, "click", f"点该订单的订单名称进入详情页")
    _assert_url(page, _data('expect_3', ctx), '确认进入订单详情页')

    # step 15: 进入编辑态
    _act(page, "click", semantic='编辑', primary=lambda p: p.get_by_role("button", name="编辑"))
    _log(page, "click", f"进入编辑态")

    # step 16: 新增第一个订单行
    _act(page, "click", semantic='新增行@订单详情页', primary=lambda p: p.get_by_role("button", name="新增行"))
    _log(page, "click", f"新增第一个订单行")

    # step 17: 填第一行物料编码
    _act_row(page, '物料编码@订单详情页', -1, op='fill', value=_data('fill_4', ctx))
    _log(page, "fill", f"填第一行物料编码")

    # step 18: 填第一行产品编码
    _act_row(page, '产品编码@订单详情页', -1, op='fill', value=_data('fill_5', ctx))
    _log(page, "fill", f"填第一行产品编码")

    # step 19: 填第一行数量
    _act_row(page, '数量@订单详情页', -1, op='fill', value=_data('fill_6', ctx))
    _log(page, "fill", f"填第一行数量")

    # step 20: 选第一行行类型
    _act_row(page, '行类型@订单详情页', -1, op='select')
    _log(page, "select", f"选第一行行类型")

    # step 21: 新增第二个订单行
    _act(page, "click", semantic='新增行@订单详情页', primary=lambda p: p.get_by_role("button", name="新增行"))
    _log(page, "click", f"新增第二个订单行")

    # step 22: 填第二行物料编码
    _act_row(page, '物料编码@订单详情页', -1, op='fill', value=_data('fill_7', ctx))
    _log(page, "fill", f"填第二行物料编码")

    # step 23: 填第二行产品编码
    _act_row(page, '产品编码@订单详情页', -1, op='fill', value=_data('fill_8', ctx))
    _log(page, "fill", f"填第二行产品编码")

    # step 24: 填第二行数量
    _act_row(page, '数量@订单详情页', -1, op='fill', value=_data('fill_9', ctx))
    _log(page, "fill", f"填第二行数量")

    # step 25: 选第二行行类型
    _act_row(page, '行类型@订单详情页', -1, op='select')
    _log(page, "select", f"选第二行行类型")

    # step 26: 点行工具栏保存，先保存订单行
    _act(page, "click", semantic='保存@详细信息', primary=lambda p: p.get_by_role("button", name="保存"))
    _log(page, "click", f"点行工具栏保存，先保存订单行")

    # step 27: 提交整个订单
    _act(page, "click", semantic='提交', primary=lambda p: p.get_by_role("button", name="提交"))
    _log(page, "click", f"提交整个订单")

    # step 28: 点底部返回回到订单列表
    _act(page, "click", semantic='返回', primary=lambda p: p.get_by_role("link", name="返回"))
    _log(page, "click", f"点底部返回回到订单列表")
    _assert_text(page, _data('expect_4', ctx), '确认回到订单列表页')

    # step 29: 再次用订单名称搜索
    _act(page, "fill", semantic='订单名称@订单系统', primary=lambda p: p.get_by_role("textbox", name="订单名称"), value=_data('fill_10', ctx))
    _log(page, "fill", f"再次用订单名称搜索")

    # step 30: 点击搜索
    _act(page, "click", semantic='搜索@订单列表页', primary=lambda p: p.get_by_role("button", name="搜索"))
    _log(page, "click", f"点击搜索")
    _assert_wait_text(page, _data('expect_5', ctx), timeout_ms=150000, refresh='research', desc='有界等待订单状态自动流转到已关闭（提交后最长约150秒按时间自动推进，轮询到状态变化为止）', selector='')

    # step 31: 打开角色切换菜单
    _act(page, "click", semantic='订@订单列表页', primary=lambda p: p.get_by_role("button", name="订"))
    _log(page, "click", f"打开角色切换菜单")

    # step 32: 切换为发票管理员角色
    _act(page, "click", semantic='切换为发票管理员@订单列表页', primary=lambda p: p.get_by_role("button", name="切换为发票管理员"))
    _log(page, "click", f"切换为发票管理员角色")

    # step 33: 勾选该订单行
    _click_row_cell(page, row_text=_data('row_text_11', ctx), cell_field='', tabs=None, op='check', cell_by='index', cell_index=1)
    _log(page, "check", f"勾选该订单行")

    # step 34: 点去开票跳转开票页
    _act(page, "click", semantic='去开票', primary=lambda p: p.get_by_role("button", name="去开票"))
    _log(page, "click", f"点去开票跳转开票页")
    _assert_url(page, _data('expect_6', ctx), '确认进入开票页')
    _assert_text(page, _data('expect_7', ctx), '确认开票页已带入订单信息')

    # step 35: 新增发票行
    _act(page, "click", semantic='新增行@开票页', primary=lambda p: p.get_by_role("button", name="新增行"))
    _log(page, "click", f"新增发票行")

    # step 36: 选发票行类型
    _act(page, "select", semantic='发票行类型@开票页', primary=lambda p: p.get_by_role("combobox", name="发票行类型"))
    _log(page, "select", f"选发票行类型")

    # step 37: 填发票行数量
    _act(page, "fill", semantic='数量@开票页', primary=lambda p: p.get_by_role("textbox", name="数量"), value=_data('fill_12', ctx))
    _log(page, "fill", f"填发票行数量")

    # step 38: 选发票行单位
    _act(page, "select", semantic='单位@开票页', primary=lambda p: p.get_by_role("combobox", name="单位"))
    _log(page, "select", f"选发票行单位")

    # step 39: 保存发票
    _act(page, "click", semantic='保存@应收发票创建@开票页', primary=lambda p: p.get_by_role("button", name="保存"))
    _log(page, "click", f"保存发票")

    # step 40: 进入发票列表页
    _goto(page, 'http://localhost:8000/invoice_list.html')
    _log(page, "goto", f"进入发票列表页")
    _assert_text(page, _data('expect_8', ctx), '确认到达发票列表页')

    # step 41: 在订单名称搜索框输入该订单名称
    _act(page, "fill", semantic='订单名称@发票列表页', primary=lambda p: p.get_by_role("textbox", name="订单名称"), value=_data('fill_13', ctx))
    _log(page, "fill", f"在订单名称搜索框输入该订单名称")

    # step 42: 点击搜索
    _act(page, "click", semantic='搜索@发票列表页', primary=lambda p: p.get_by_role("button", name="搜索"))
    _log(page, "click", f"点击搜索")
    _assert_text(page, _data('expect_9', ctx), '断言能搜到刚创建的发票')

