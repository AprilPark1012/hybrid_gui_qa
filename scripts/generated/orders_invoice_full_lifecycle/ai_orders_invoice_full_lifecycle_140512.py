"""hybrid_gui_qa 用例模块：ai_orders_invoice_full_lifecycle_140512（场景 orders_invoice_full_lifecycle）—— 由 cases/orders_invoice_full_lifecycle/ai_orders_invoice_full_lifecycle_140512.json 自动生成。

**不要手改本文件**：改用例后重跑 generate 会覆盖它。要改行为 → 改用例 json / 场景 yml。
数据抽离在 scripts/datasets/ai_orders_invoice_full_lifecycle_140512.json（脚本与数据分离）。
一个用例一个文件（P20）：便于按 id 管理、按变化增量重生成。

运行（推荐走 cli：自带资源预检 + run-id 隔离的日志/报告）:
  python -m framework.cli run --workers 2                 # 全量
  python -m framework.cli run --debug --case ai_orders_invoice_full_lifecycle_140512        # 只调试这一条
裸跑 pytest（未设 HYBRID_RUN_ID 时日志落 log/latest/）:
  pytest scripts/generated/orders_invoice_full_lifecycle/ai_orders_invoice_full_lifecycle_140512.py -v
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
                      # V8.5.1：登录步骤化 —— 生成期会把场景 `login:` 的动作序列展开成前导步骤，
                      #   渲染出的 `_login_do` / `_login_wait` 必须在这里同步 import
                      #   （本轮又踩了一次 "模板渲染了但没 import -> 真跑 NameError"）。
                      _login_do, _login_wait,
                      # P22 批 4/5：等待式断言（wait_text；批 5 起支持 selector 限定范围）
                      _assert_wait_text)
# P16 批 5：运行期「锚点 + 容器内相对路径」下钻（col.header 这类列口径只有运行时才算得出列序）
from framework.features.f03_locate.scope_locate import drill as _drill
import pytest
from playwright.sync_api import expect as _pw_expect

def test_ai_orders_invoice_full_lifecycle_140512(page, ctx):
    """【起手状态 · 最重要 · 不要写成步骤】本用例**开局时的页面就是「合同列表页」**，
   且已以**超级管理员**登录、已切换到**订单管理员**角色。
   这两件事由场景级前置 `probe_pre` 自动完成，**用例的第 1 步直接就是\"在合同列表页勾选合同\"**。
    **禁止**在用例里写 `goto 登录页` / `goto login.html`、也不要写\"登录\"\"切换角色\"这类步骤 ——
      框架执行每条用例前**已经**自动做完登录与身份前置，重复执行会把页面**导航回登录页**，
      于是紧接着的\"在合同列表页勾选合同\"必然落空（实测两次：`选择合同_HT_1001` 定位失败，
      报错现场 URL 就是 login.html）。
      [OK] 正确写法：第 1 步 = 在**合同列表页**勾选第一行合同 HT-1001（页面已经在那儿了，不要重新导航）。
3. 进入合同列表页，**选中一条合同**（第一行，HT-1001）。
   [!] 点「新建订单」在 demo 里打开的是 **iframe 弹层**（探测链路暂不覆盖弹层内控件，已单独立项）；
   故本条走**等价直达**：打开新建订单页并把该合同带进去（`order_new.html?contract_no=HT-1001`）。
4. 在新建订单页填写：订单名称用「全链路-{datetime}」、合同已带入、业务单元/管理单元/帐套各选第一行、
   订单类型选第一项、客户与销售员各选第一个、订单备注填「端到端全链路场景」；点「保存」。
5. 回到合同列表页。[!] **这里的顺序写死了，别调换**（页面重载会**清掉**之前的勾选，
   而「查看订单」按钮**必须先勾选合同才会出现**）：
     ① 先**重新勾选第一行合同 HT-1001**；
     ② 再确认「查看订单」按钮出现/可用 —— **不要**在\"勾选之前\"就断言它，那时页面上没有这个按钮
       （实测：断言写在勾选之前 -> `_assert_text(page, \"查看订单\")` 直接失败）；
     ③ 然后才点「查看订单」—— [!] **该按钮是 `window.open` 新开标签页**（demo 源码注释：
       \"新开订单系统页并带上合同编号\"，`#btn-view-orders`），所以**当前标签页仍停在合同列表页**；
       后续断言与操作都必须在**新标签页**上做（框架有跨 tab 支持：清单里该控件的 `opens_new_tab`
       为 true，步骤要用\"点击并切换到新标签页\"的写法），**不要在旧标签页上断言订单系统 URL**
       （实测：在旧页断言 `orders.html` 必然失败，页面快照里还能看到合同列表页的表格）。
     ④ 在**新标签页**的**订单名称**搜索框输入刚填的订单名称，点「搜索」，列表里出现这条订单。
6. 点这条订单的**订单名称**进入订单详情页；点「编辑」进入编辑态（进编辑态后行工具栏的
   「新增行 / 保存 / 取消」才可用，只读态是置灰的）。
   然后**新增 2 个订单行**：每新增一行都要**填满该行的 4 个必填项**（物料编码 / 产品编码 / 数量 / 行类型），
   两行都填好后，**保存要分两步（缺一步整单就存不下来）**：
     ① 先点**行工具栏里的「保存」**把订单行本身**先保存**下来（每新增一行都要保存这一行）；
     ② 再点**页面右下角（底部按钮行最右侧）的「保存」**——这一步才**完成整个订单的保存**。
   [!] 业务前提（必须遵守，否则后面白给）：**页面上有未保存的修改时，点「提交」不会生效**
   —— 它只会提示「请先点保存再提交」，订单不会真的被提交、状态也不会开始流转。
   所以顺序必须是「填行 → 行保存 → 右下角保存 → 再提交」。
   最后点底部的**「提交」**提交整个订单（提交成功后订单进入履行状态，开始按时间自动流转）。
7. 点底部「返回」回到订单列表；用订单名称搜索找到它，**等待**它的状态自动流转到「已关闭」。
   该流转是**按时间自动推进**的：提交订单后**最长约 150 秒**才会变成「已关闭」，所以这一步要
   **有界等待**（轮询到状态变化为止），既不要固定 sleep 硬等，也不要只等几秒就判失败。
8. 切换到**发票管理员**角色；在订单列表里**选中该订单**，点「去开票」。
9. 在开票页确认订单编号/合同编号已带入（发票号是系统生成的），填写发票行后点「保存」，完成发票创建。
10. 进入发票列表页，在**订单名称**搜索框输入该订单名称，点「搜索」-> 能搜到刚创建的那张发票。"""
    _CURRENT_LOG["case_id"] = "ai_orders_invoice_full_lifecycle_140512"
    _t = _Tabs(page)          # 多 tab：点了会开新 tab 的控件后 page 会被重新绑定到新 tab
    _goto(page, 'http://localhost:8000/login.html')
    # ---- 登录（V8.5.1 步骤化：场景声明 -> 框架展开，不交给 AI）----
    _goto(page, 'http://localhost:8000/login.html')
    # 登录步骤 1: fill ['id']
    _login_do(page, 'fill', {'id': 'login-user'}, value='super')
    # 登录步骤 2: fill ['id']
    _login_do(page, 'fill', {'id': 'login-pwd'}, value='super@123')
    # 登录步骤 3: click ['id']
    _login_do(page, 'click', {'id': 'btn-login'})
    _login_wait(page, {'url_not': 'login.html'})
    # ---- 登录步骤结束 ----
    _log(page, "场景开始", f"case=ai_orders_invoice_full_lifecycle_140512")

    # step 1: 打开 【登录页】http://localhost:8000/login.html
    _goto(page, 'http://localhost:8000/')
    _log(page, "goto", f"打开 【登录页】http://localhost:8000/login.html")

    # step 2: 在合同列表页勾选第一行合同 HT-1001（起手页已是合同列表页，不要重新导航）
    _act(page, "check", semantic='选择合同_HT_1001', primary=lambda p: p.get_by_test_id("tbl-contracts").locator("tbody tr").filter(has_text="HT-1001").locator("td[data-field='pick']").get_by_role("radio"))
    _log(page, "check", f"在合同列表页勾选第一行合同 HT-1001（起手页已是合同列表页，不要重新导航）")

    # step 3: 等价直达：打开新建订单页并带入合同 HT-1001
    _goto(page, 'http://localhost:8000/order_new.html?contract_no=HT-1001')
    _log(page, "goto", f"等价直达：打开新建订单页并带入合同 HT-1001")
    _assert_url(page, _data('expect_0', ctx), '确认已到新建订单页')

    # step 4: 填写唯一订单名称（保留占位符）
    _act(page, "fill", semantic='订单名称@新建订单页', primary=lambda p: p.get_by_test_id("form-order-new").locator("tbody tr").filter(has_text="*订单名称").locator("td").nth(1).get_by_role("textbox"), value=_data('fill_0', ctx))
    _log(page, "fill", f"填写唯一订单名称（保留占位符）")
    _assert_text(page, _data('expect_1', ctx), '确认合同编号已带入（只读回显）')

    # step 5: 业务单元选第一项
    _act(page, "select", semantic='业务单元@新建订单页', primary=lambda p: p.get_by_test_id("form-order-new").locator("tbody tr").filter(has_text="*业务单元").locator("td").nth(1).get_by_role("combobox"))
    _log(page, "select", f"业务单元选第一项")

    # step 6: 管理单元选第一项
    _act(page, "select", semantic='管理单元@新建订单页', primary=lambda p: p.get_by_test_id("form-order-new").locator("tbody tr").filter(has_text="*管理单元").locator("td").nth(1).get_by_role("combobox"))
    _log(page, "select", f"管理单元选第一项")

    # step 7: 帐套选第一项
    _act(page, "select", semantic='帐套@新建订单页', primary=lambda p: p.get_by_test_id("form-order-new").locator("tbody tr").filter(has_text="*帐套").locator("td").nth(1).get_by_role("combobox"))
    _log(page, "select", f"帐套选第一项")

    # step 8: 订单类型选第一项
    _act(page, "select", semantic='订单类型@新建订单页', primary=lambda p: p.get_by_test_id("form-order-new").locator("tbody tr").filter(has_text="*订单类型").locator("td").nth(1).get_by_role("combobox"))
    _log(page, "select", f"订单类型选第一项")

    # step 9: 客户选第一个
    _act(page, "select", semantic='客户@新建订单页', primary=lambda p: p.get_by_test_id("form-order-new").locator("tbody tr").filter(has_text="*客户").locator("td").nth(1).get_by_role("combobox"))
    _log(page, "select", f"客户选第一个")

    # step 10: 销售员选第一个
    _act(page, "select", semantic='销售员@新建订单页', primary=lambda p: p.get_by_test_id("form-order-new").locator("tbody tr").filter(has_text="*销售员").locator("td").nth(1).get_by_role("combobox"))
    _log(page, "select", f"销售员选第一个")

    # step 11: 填写订单备注
    _act(page, "fill", semantic='订单备注', primary=lambda p: p.get_by_test_id("form-order-new").locator("tbody tr").filter(has_text="订单备注").locator("td").nth(1).get_by_role("textbox"), value=_data('fill_1', ctx))
    _log(page, "fill", f"填写订单备注")

    # step 12: 保存订单（当前已是订单管理员角色）
    _act(page, "click", semantic='保存@新建订单页', primary=lambda p: p.locator("#btn-o-submit"))
    _log(page, "click", f"保存订单（当前已是订单管理员角色）")

    # step 13: 回到合同列表页
    _goto(page, 'http://localhost:8000/')
    _log(page, "goto", f"回到合同列表页")
    _assert_text(page, _data('expect_2', ctx), '确认到达合同列表页（根路径无独有 URL 片段，用页头文案）')

    # step 14: 页面重载已清掉勾选，重新勾选第一行合同 HT-1001
    _act(page, "check", semantic='选择合同_HT_1001', primary=lambda p: p.get_by_test_id("tbl-contracts").locator("tbody tr").filter(has_text="HT-1001").locator("td[data-field='pick']").get_by_role("radio"))
    _log(page, "check", f"页面重载已清掉勾选，重新勾选第一行合同 HT-1001")
    _assert_text(page, _data('expect_3', ctx), '勾选之后才断言「查看订单」按钮出现（必须在勾选之后）')

    # step 15: 点查看订单，window.open 新开订单系统标签页并切换过去
    page = _t.open_new(lambda: _act(page, "click", semantic='查看订单', primary=lambda p: p.locator("#btn-view-orders")))
    _log(page, "click_new_tab", f"点查看订单，window.open 新开订单系统标签页并切换过去")
    _assert_url(page, _data('expect_4', ctx), '确认已切到新标签页的订单列表页')

    # step 16: 在新标签页按订单名称搜索（保留占位符）
    _act(page, "fill", semantic='订单名称@订单列表页[订单系统]', primary=lambda p: p.locator("#tb-o-name"), value=_data('fill_2', ctx))
    _log(page, "fill", f"在新标签页按订单名称搜索（保留占位符）")

    # step 17: 点搜索
    _act(page, "click", semantic='搜索@订单列表页', primary=lambda p: p.locator("#btn-search-o"))
    _log(page, "click", f"点搜索")
    _assert_first_row(page, 'orderName', _data('expect_5', ctx), '列表里出现刚创建的这条订单', timeout_ms=150000, refresh='research')

    # step 18: 点这一行的订单名称链接进入订单详情页（新建行只能用行锚定位）
    _click_row_cell(page, row_text=_data('row_text_3', ctx), cell_field='orderName', tabs=None, op='click')
    _log(page, "click", f"点这一行的订单名称链接进入订单详情页（新建行只能用行锚定位）")
    _assert_url(page, _data('expect_6', ctx), '确认到达订单详情页')

    # step 19: 进入编辑态，激活行工具栏
    _act(page, "click", semantic='编辑', primary=lambda p: p.get_by_role("button", name="编辑"))
    _log(page, "click", f"进入编辑态，激活行工具栏")

    # step 20: 新增第 1 个订单行
    _act(page, "click", semantic='新增行@订单详情页', primary=lambda p: p.locator('section[aria-label="详细信息"]').get_by_text("新增行", exact=True))
    _log(page, "click", f"新增第 1 个订单行")

    # step 21: 填第 1 行物料编码（新增的空行，按最后一行定位）
    _act_row(page, '物料编码@订单详情页', -1, op='fill', value=_data('fill_4', ctx))
    _log(page, "fill", f"填第 1 行物料编码（新增的空行，按最后一行定位）")

    # step 22: 填第 1 行产品编码
    _act_row(page, '产品编码@订单详情页', -1, op='fill', value=_data('fill_5', ctx))
    _log(page, "fill", f"填第 1 行产品编码")

    # step 23: 填第 1 行数量
    _act_row(page, '数量@订单详情页', -1, op='fill', value=_data('fill_6', ctx))
    _log(page, "fill", f"填第 1 行数量")

    # step 24: 第 1 行行类型选第一项
    _act_row(page, '行类型@订单详情页', -1, op='select')
    _log(page, "select", f"第 1 行行类型选第一项")

    # step 25: 行工具栏保存，先保存这一订单行
    _act(page, "click", semantic='保存@订单详情页[详细信息]', primary=lambda p: p.locator('section[aria-label="详细信息"]').get_by_text("保存", exact=True))
    _log(page, "click", f"行工具栏保存，先保存这一订单行")

    # step 26: 新增第 2 个订单行
    _act(page, "click", semantic='新增行@订单详情页', primary=lambda p: p.locator('section[aria-label="详细信息"]').get_by_text("新增行", exact=True))
    _log(page, "click", f"新增第 2 个订单行")

    # step 27: 填第 2 行物料编码（新增的空行，按最后一行定位）
    _act_row(page, '物料编码@订单详情页', -1, op='fill', value=_data('fill_7', ctx))
    _log(page, "fill", f"填第 2 行物料编码（新增的空行，按最后一行定位）")

    # step 28: 填第 2 行产品编码
    _act_row(page, '产品编码@订单详情页', -1, op='fill', value=_data('fill_8', ctx))
    _log(page, "fill", f"填第 2 行产品编码")

    # step 29: 填第 2 行数量
    _act_row(page, '数量@订单详情页', -1, op='fill', value=_data('fill_9', ctx))
    _log(page, "fill", f"填第 2 行数量")

    # step 30: 第 2 行行类型选第一项
    _act_row(page, '行类型@订单详情页', -1, op='select')
    _log(page, "select", f"第 2 行行类型选第一项")

    # step 31: 行工具栏保存，保存第 2 个订单行
    _act(page, "click", semantic='保存@订单详情页[详细信息]', primary=lambda p: p.locator('section[aria-label="详细信息"]').get_by_text("保存", exact=True))
    _log(page, "click", f"行工具栏保存，保存第 2 个订单行")

    # step 32: 点底部按钮行右下角的保存，完成整个订单的保存（行保存之后必须有这一步）
    _act(page, "click", semantic='保存@订单详情页[订单详情]', primary=lambda p: p.locator("#btn-detail-edit"))
    _log(page, "click", f"点底部按钮行右下角的保存，完成整个订单的保存（行保存之后必须有这一步）")

    # step 33: 提交整个订单（无未保存修改时才生效），订单开始按时间自动流转
    _act(page, "click", semantic='提交', primary=lambda p: p.locator("#btn-detail-submit"))
    _log(page, "click", f"提交整个订单（无未保存修改时才生效），订单开始按时间自动流转")

    # step 34: 点底部返回回到订单列表
    _act(page, "click", semantic='返回', primary=lambda p: p.locator("#btn-back"))
    _log(page, "click", f"点底部返回回到订单列表")
    _assert_url(page, _data('expect_7', ctx), '确认回到订单列表页')

    # step 35: 用订单名称搜索找到它（保留占位符）
    _act(page, "fill", semantic='订单名称@订单列表页[订单系统]', primary=lambda p: p.locator("#tb-o-name"), value=_data('fill_10', ctx))
    _log(page, "fill", f"用订单名称搜索找到它（保留占位符）")

    # step 36: 点搜索
    _act(page, "click", semantic='搜索@订单列表页', primary=lambda p: p.locator("#btn-search-o"))
    _log(page, "click", f"点搜索")
    _assert_first_row(page, 'orderName', _data('expect_8', ctx), '确认搜到这条订单', timeout_ms=150000, refresh='research')
    _assert_first_row(page, 'orderStatus', _data('expect_9', ctx), '有界等待订单状态自动流转到已关闭（提交后最长约150秒按时间自动推进，轮询到状态变化为止，不固定 sleep）', timeout_ms=150000, refresh='research')

    # step 37: 点开右上角角色菜单入口
    _act(page, "click", semantic='订@订单列表页', primary=lambda p: p.locator("#nu-avatar"))
    _log(page, "click", f"点开右上角角色菜单入口")

    # step 38: 切换到发票管理员角色（开票权限）
    _act(page, "click", semantic='切换为发票管理员@订单列表页', primary=lambda p: p.get_by_role("button", name="切换为发票管理员"))
    _log(page, "click", f"切换到发票管理员角色（开票权限）")

    # step 39: 切角色后重新按订单名称搜索，确保目标行在列表中（保留占位符）
    _act(page, "fill", semantic='订单名称@订单列表页[订单系统]', primary=lambda p: p.locator("#tb-o-name"), value=_data('fill_11', ctx))
    _log(page, "fill", f"切角色后重新按订单名称搜索，确保目标行在列表中（保留占位符）")

    # step 40: 点搜索
    _act(page, "click", semantic='搜索@订单列表页', primary=lambda p: p.locator("#btn-search-o"))
    _log(page, "click", f"点搜索")
    _assert_first_row(page, 'orderName', _data('expect_10', ctx), '确认该订单仍在首行', timeout_ms=150000, refresh='research')
    _assert_text(page, _data('expect_11', ctx), '占位断言（会被下一步替换）')

