"""hybrid_gui_qa 用例模块：ai_orders_invoice_full_lifecycle_145948（场景 orders_invoice_full_lifecycle）—— 由 cases/orders_invoice_full_lifecycle/ai_orders_invoice_full_lifecycle_145948.json 自动生成。

**不要手改本文件**：改用例后重跑 generate 会覆盖它。要改行为 → 改用例 json / 场景 yml。
数据抽离在 scripts/datasets/ai_orders_invoice_full_lifecycle_145948.json（脚本与数据分离）。
一个用例一个文件（P20）：便于按 id 管理、按变化增量重生成。

运行（推荐走 cli：自带资源预检 + run-id 隔离的日志/报告）:
  python -m framework.cli run --workers 2                 # 全量
  python -m framework.cli run --debug --case ai_orders_invoice_full_lifecycle_145948        # 只调试这一条
裸跑 pytest（未设 HYBRID_RUN_ID 时日志落 log/latest/）:
  pytest scripts/generated/orders_invoice_full_lifecycle/ai_orders_invoice_full_lifecycle_145948.py -v
"""
from _harness import (_CURRENT_LOG, _log, _data, _act, _goto,
                      _login_flow,
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
                      # L35：登录执行入口是 `_login_flow`（已在上面 import）；by 那套执行器已删除
                      # P22 批 4/5：等待式断言（wait_text；批 5 起支持 selector 限定范围）
                      _assert_wait_text)
# P16 批 5：运行期「锚点 + 容器内相对路径」下钻（col.header 这类列口径只有运行时才算得出列序）
from framework.features.f03_locate.scope_locate import drill as _drill
import pytest
from playwright.sync_api import expect as _pw_expect

def test_ai_orders_invoice_full_lifecycle_145948(page, ctx):
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
   该流转是**按时间自动推进**的：提交订单后**最长约 160 秒**才会变成「已关闭」，所以这一步要
   **有界等待**（轮询到状态变化为止），既不要固定 sleep 硬等，也不要只等几秒就判失败。
8. 切换到**发票管理员**角色；在订单列表里**选中该订单**，点「去开票」。
9. 在开票页确认订单编号/合同编号已带入（发票号是系统生成的），填写发票行后点「保存」，完成发票创建。
10. 进入发票列表页，在**订单名称**搜索框输入该订单名称，点「搜索」-> 能搜到刚创建的那张发票。"""
    _CURRENT_LOG["case_id"] = "ai_orders_invoice_full_lifecycle_145948"
    _t = _Tabs(page)          # 多 tab：点了会开新 tab 的控件后 page 会被重新绑定到新 tab
    _goto(page, 'http://localhost:8000/login.html')
    # ---- 登录（L35：场景自然语言 -> 同一规划器 -> 同一套定位栈；步骤已固化在用例里）----
    _login_flow(page, [{'order': 0, 'op': 'goto', 'element': None, 'value': 'http://localhost:8000/login.html', 'assertion': None, 'desc': '打开 http://localhost:8000/login.html', 'row_text': None, 'cell_field': None, 'cell_by': None, 'cell_index': None, 'row_index': None, 'row_id': None, 'index': None}, {'order': 1, 'op': 'fill', 'element': {'semantic_name': '账号', 'role': 'textbox', 'name': '账号', 'label': None, 'placeholder': '请输入账号', 'test_id': '', 'element_id': None, 'text': '账号', 'page_hint': None, 'container_heading': '演示系统登录', 'nearby_text': '演示系统登录 合同 / 订单 / 发票 三个模块 + 超级管理员 *账号 *密码 角色账号密码 合同管理员contractcontract@123订单管理员or', 'help_text': '账号', 'notes': '', 'anchor': None, 'path': None, 'isValid': True}, 'value': 'super', 'assertion': None, 'desc': '在登录页账号输入框填入账号 super', 'row_text': None, 'cell_field': None, 'cell_by': None, 'cell_index': None, 'row_index': None, 'row_id': None, 'index': None}, {'order': 2, 'op': 'fill', 'element': {'semantic_name': '密码', 'role': 'textbox', 'name': '密码', 'label': None, 'placeholder': '请输入密码', 'test_id': '', 'element_id': None, 'text': '密码', 'page_hint': None, 'container_heading': '演示系统登录', 'nearby_text': '演示系统登录 合同 / 订单 / 发票 三个模块 + 超级管理员 *账号 *密码 角色账号密码 合同管理员contractcontract@123订单管理员or', 'help_text': '密码', 'notes': '', 'anchor': None, 'path': None, 'isValid': True}, 'value': 'super@123', 'assertion': None, 'desc': '在登录页密码输入框填入密码 super@123', 'row_text': None, 'cell_field': None, 'cell_by': None, 'cell_index': None, 'row_index': None, 'row_id': None, 'index': None}, {'order': 3, 'op': 'click', 'element': {'semantic_name': '登_录', 'role': 'button', 'name': '登 录', 'label': None, 'placeholder': '', 'test_id': '', 'element_id': None, 'text': '登 录', 'page_hint': None, 'container_heading': '演示系统登录', 'nearby_text': '演示系统登录 合同 / 订单 / 发票 三个模块 + 超级管理员 *账号 *密码 角色账号密码 合同管理员contractcontract@123订单管理员or', 'help_text': '', 'notes': '', 'anchor': None, 'path': None, 'isValid': True}, 'value': None, 'assertion': None, 'desc': '点击「登录」按钮提交登录', 'row_text': None, 'cell_field': None, 'cell_by': None, 'cell_index': None, 'row_index': None, 'row_id': None, 'index': None}], {'url_not': 'login.html'}, 'http://localhost:8000/login.html')
    # ---- 登录步骤结束 ----
    _log(page, "场景开始", f"case=ai_orders_invoice_full_lifecycle_145948")

    # step 1: 打开 【登录页】http://localhost:8000/login.html
    _goto(page, 'http://localhost:8000/')
    _log(page, "goto", f"打开 【登录页】http://localhost:8000/login.html")

    # step 2: 勾选合同列表第一行合同 HT-1001（起手已在合同列表页且已切订单管理员，不导航不登录）
    _act(page, "check", semantic='选择合同_HT_1001', primary=lambda p: p.get_by_test_id("tbl-contracts").locator("tbody tr").filter(has_text="HT-1001").locator("xpath=.//*[@*[starts-with(name(), 'data-')][.='pick']]").get_by_role("radio"))
    _log(page, "check", f"勾选合同列表第一行合同 HT-1001（起手已在合同列表页且已切订单管理员，不导航不登录）")

    # step 3: 「新建订单」在 demo 是 iframe 弹层（探测未覆盖），走等价直达打开新建订单页并带入合同 HT-1001
    _goto(page, 'http://localhost:8000/order_new.html?contract_no=HT-1001')
    _log(page, "goto", f"「新建订单」在 demo 是 iframe 弹层（探测未覆盖），走等价直达打开新建订单页并带入合同 HT-1001")
    _assert_url(page, _data('expect_0', ctx), '到达证据：order_new 是新建订单页 URL 独有片段')

    # step 4: 填订单名称 全链路-{datetime}（全系统唯一，占位符由数据层展开，保证可重复跑）
    _act(page, "fill", semantic='订单名称@新建订单页', primary=lambda p: p.get_by_test_id("form-order-new").locator("tbody tr").filter(has_text="*订单名称").locator("td").nth(1).get_by_role("textbox"), value=_data('fill_0', ctx))
    _log(page, "fill", f"填订单名称 全链路-{{datetime}}（全系统唯一，占位符由数据层展开，保证可重复跑）")

    # step 5: 业务单元选第一行（页面标*必填）
    _act(page, "select", semantic='业务单元@新建订单页', primary=lambda p: p.get_by_test_id("form-order-new").locator("tbody tr").filter(has_text="*业务单元").locator("td").nth(1).get_by_role("combobox"), index=0)
    _log(page, "select", f"业务单元选第一行（页面标*必填）")

    # step 6: 管理单元选第一行（页面标*必填）
    _act(page, "select", semantic='管理单元@新建订单页', primary=lambda p: p.get_by_test_id("form-order-new").locator("tbody tr").filter(has_text="*管理单元").locator("td").nth(1).get_by_role("combobox"), index=0)
    _log(page, "select", f"管理单元选第一行（页面标*必填）")

    # step 7: 帐套选第一行（页面标*必填）
    _act(page, "select", semantic='帐套@新建订单页', primary=lambda p: p.get_by_test_id("form-order-new").locator("tbody tr").filter(has_text="*帐套").locator("td").nth(1).get_by_role("combobox"), index=0)
    _log(page, "select", f"帐套选第一行（页面标*必填）")

    # step 8: 订单类型选第一项（页面标*必填）
    _act(page, "select", semantic='订单类型@新建订单页', primary=lambda p: p.get_by_test_id("form-order-new").locator("tbody tr").filter(has_text="*订单类型").locator("td").nth(1).get_by_role("combobox"), index=0)
    _log(page, "select", f"订单类型选第一项（页面标*必填）")

    # step 9: 客户选第一个（选择客户弹层首行为北京华信科技有限公司；页面标*必填）
    _act(page, "select", semantic='客户@新建订单页', primary=lambda p: p.get_by_test_id("form-order-new").locator("tbody tr").filter(has_text="*客户").locator("td").nth(1).get_by_role("combobox"), index=0)
    _log(page, "select", f"客户选第一个（选择客户弹层首行为北京华信科技有限公司；页面标*必填）")

    # step 10: 销售员选第一个（选择销售员弹层首行为张伟；页面标*必填）
    _act(page, "select", semantic='销售员@新建订单页', primary=lambda p: p.get_by_test_id("form-order-new").locator("tbody tr").filter(has_text="*销售员").locator("td").nth(1).get_by_role("combobox"), index=0)
    _log(page, "select", f"销售员选第一个（选择销售员弹层首行为张伟；页面标*必填）")

    # step 11: 填订单备注（选填，场景要求填「端到端全链路场景」）
    _act(page, "fill", semantic='订单备注', primary=lambda p: p.get_by_test_id("form-order-new").locator("tbody tr").filter(has_text="订单备注").locator("td").nth(1).get_by_role("textbox"), value=_data('fill_1', ctx))
    _log(page, "fill", f"填订单备注（选填，场景要求填「端到端全链路场景」）")

    # step 12: 保存新建订单（必填项已全部填写，订单管理员角色下可保存）
    _act(page, "click", semantic='保存@新建订单页', primary=lambda p: p.locator("#btn-o-submit"))
    _log(page, "click", f"保存新建订单（必填项已全部填写，订单管理员角色下可保存）")

    # step 13: 回到合同列表页（页面重载会清掉之前的勾选，后面要先重新勾选）
    _goto(page, 'http://localhost:8000/')
    _log(page, "goto", f"回到合同列表页（页面重载会清掉之前的勾选，后面要先重新勾选）")
    _assert_text(page, _data('expect_1', ctx), '到达证据：合同列表页为根路径无独有 URL 片段，改断言该页独有标题「合同管理系统」')

    # step 14: 重新勾选第一行合同 HT-1001（查看订单按钮必须先勾选才出现，顺序写死不可调换）
    _act(page, "check", semantic='选择合同_HT_1001', primary=lambda p: p.get_by_test_id("tbl-contracts").locator("tbody tr").filter(has_text="HT-1001").locator("xpath=.//*[@*[starts-with(name(), 'data-')][.='pick']]").get_by_role("radio"))
    _log(page, "check", f"重新勾选第一行合同 HT-1001（查看订单按钮必须先勾选才出现，顺序写死不可调换）")
    _assert_text(page, _data('expect_2', ctx), '勾选之后才确认「查看订单」按钮出现（勾选前断言会失败）')

    # step 15: 点「查看订单」（window.open 新开标签页），必须用 click_new_tab 切过去，当前标签页仍停在合同列表页
    page = _t.open_new(lambda: _act(page, "click", semantic='查看订单', primary=lambda p: p.locator("#btn-view-orders")))
    _log(page, "click_new_tab", f"点「查看订单」（window.open 新开标签页），必须用 click_new_tab 切过去，当前标签页仍停在合同列表页")
    _assert_url(page, _data('expect_3', ctx), '新标签页到达证据：orders.html 是订单列表页 URL 独有片段（不许在旧标签页断言）')
    _assert_text(page, _data('expect_4', ctx), '补充到达证据：「是否开票」为订单列表页独有的搜索条件/列头文案')

    # step 16: 在新标签页的订单名称搜索框输入刚填的订单名称 全链路-{datetime}
    _act(page, "fill", semantic='订单名称@订单列表页[订单系统]', primary=lambda p: p.locator("#tb-o-name"), value=_data('fill_2', ctx))
    _log(page, "fill", f"在新标签页的订单名称搜索框输入刚填的订单名称 全链路-{{datetime}}")

    # step 17: 点「搜索」过滤出刚建的订单
    _act(page, "click", semantic='搜索@订单列表页', primary=lambda p: p.locator("#btn-search-o"))
    _log(page, "click", f"点「搜索」过滤出刚建的订单")
    _assert_first_row(page, 'orderName', _data('expect_5', ctx), '结构化验证订单已建出来：列表第一行的订单名称列即 全链路-{datetime}', timeout_ms=160000, refresh='research')

    # step 18: 点该行订单名称链接进入订单详情页（当前页跳转；新行探测期不存在，用行内定位）
    _click_row_cell(page, row_text=_data('row_text_3', ctx), cell_field='orderName', tabs=None, op='click')
    _log(page, "click", f"点该行订单名称链接进入订单详情页（当前页跳转；新行探测期不存在，用行内定位）")
    _assert_url(page, _data('expect_6', ctx), '到达证据：order_detail 是订单详情页 URL 独有片段')

    # step 19: 点「编辑」进入编辑态（新增行/行保存只在编辑态可用，只读态置灰）
    _act(page, "click", semantic='编辑', primary=lambda p: p.get_by_role("button", name="编辑"))
    _log(page, "click", f"点「编辑」进入编辑态（新增行/行保存只在编辑态可用，只读态置灰）")

    # step 20: 新增第 1 个订单行（新行为空行，后续用 row_index=-1 定位最后一行）
    _act(page, "click", semantic='新增行@订单详情页', primary=lambda p: p.locator('section[aria-label="详细信息"]').get_by_text("新增行", exact=True))
    _log(page, "click", f"新增第 1 个订单行（新行为空行，后续用 row_index=-1 定位最后一行）")

    # step 21: 填第 1 行物料编码（multi_match 控件，必须 row_index=-1 定位刚新增的空行）
    _act_row(page, '物料编码@订单详情页', -1, op='fill', value=_data('fill_4', ctx))
    _log(page, "fill", f"填第 1 行物料编码（multi_match 控件，必须 row_index=-1 定位刚新增的空行）")

    # step 22: 填第 1 行产品编码（必填项，row_index=-1 定位该空行）
    _act_row(page, '产品编码@订单详情页', -1, op='fill', value=_data('fill_5', ctx))
    _log(page, "fill", f"填第 1 行产品编码（必填项，row_index=-1 定位该空行）")

    # step 23: 填第 1 行数量（必填项，row_index=-1 定位该空行）
    _act_row(page, '数量@订单详情页', -1, op='fill', value=_data('fill_6', ctx))
    _log(page, "fill", f"填第 1 行数量（必填项，row_index=-1 定位该空行）")

    # step 24: 第 1 行行类型选第一项（必填项；multi_match 控件必须 row_index=-1）
    _act_row(page, '行类型@订单详情页', -1, op='select')
    _log(page, "select", f"第 1 行行类型选第一项（必填项；multi_match 控件必须 row_index=-1）")

    # step 25: 先点行工具栏「保存」把第 1 个订单行本身保存（每新增一行都要行保存）
    _act(page, "click", semantic='保存@订单详情页[详细信息]', primary=lambda p: p.locator('section[aria-label="详细信息"]').get_by_text("保存", exact=True))
    _log(page, "click", f"先点行工具栏「保存」把第 1 个订单行本身保存（每新增一行都要行保存）")

    # step 26: 新增第 2 个订单行
    _act(page, "click", semantic='新增行@订单详情页', primary=lambda p: p.locator('section[aria-label="详细信息"]').get_by_text("新增行", exact=True))
    _log(page, "click", f"新增第 2 个订单行")

    # step 27: 填第 2 行物料编码（row_index=-1 定位最后的新空行）
    _act_row(page, '物料编码@订单详情页', -1, op='fill', value=_data('fill_7', ctx))
    _log(page, "fill", f"填第 2 行物料编码（row_index=-1 定位最后的新空行）")

    # step 28: 填第 2 行产品编码（必填项）
    _act_row(page, '产品编码@订单详情页', -1, op='fill', value=_data('fill_8', ctx))
    _log(page, "fill", f"填第 2 行产品编码（必填项）")

    # step 29: 填第 2 行数量（必填项）
    _act_row(page, '数量@订单详情页', -1, op='fill', value=_data('fill_9', ctx))
    _log(page, "fill", f"填第 2 行数量（必填项）")

    # step 30: 第 2 行行类型选第一项（必填项，row_index=-1）
    _act_row(page, '行类型@订单详情页', -1, op='select')
    _log(page, "select", f"第 2 行行类型选第一项（必填项，row_index=-1）")

    # step 31: 行工具栏「保存」保存第 2 个订单行
    _act(page, "click", semantic='保存@订单详情页[详细信息]', primary=lambda p: p.locator('section[aria-label="详细信息"]').get_by_text("保存", exact=True))
    _log(page, "click", f"行工具栏「保存」保存第 2 个订单行")

    # step 32: 再点页面底部「保存」完成整个订单的保存（缺这步点提交不生效）
    _act(page, "click", semantic='保存@订单详情页[订单详情]', primary=lambda p: p.locator("#btn-detail-edit"))
    _log(page, "click", f"再点页面底部「保存」完成整个订单的保存（缺这步点提交不生效）")

    # step 33: 点底部「提交」提交整个订单（提交后订单进入履行状态，开始按时间自动流转）
    _act(page, "click", semantic='提交', primary=lambda p: p.locator("#btn-detail-submit"))
    _log(page, "click", f"点底部「提交」提交整个订单（提交后订单进入履行状态，开始按时间自动流转）")

    # step 34: 点底部「返回」回到订单列表（同一标签页内跳转，不是关 tab）
    _act(page, "click", semantic='返回', primary=lambda p: p.locator("#btn-back"))
    _log(page, "click", f"点底部「返回」回到订单列表（同一标签页内跳转，不是关 tab）")
    _assert_url(page, _data('expect_7', ctx), '到达证据：orders.html 是订单列表页 URL 独有片段')
    _assert_text(page, _data('expect_8', ctx), '补充到达证据：「是否开票」为订单列表页独有文案')

    # step 35: 用订单名称 全链路-{datetime} 搜索找到该订单
    _act(page, "fill", semantic='订单名称@订单列表页[订单系统]', primary=lambda p: p.locator("#tb-o-name"), value=_data('fill_10', ctx))
    _log(page, "fill", f"用订单名称 全链路-{{datetime}} 搜索找到该订单")

    # step 36: 点「搜索」
    _act(page, "click", semantic='搜索@订单列表页', primary=lambda p: p.locator("#btn-search-o"))
    _log(page, "click", f"点「搜索」")
    _assert_first_row(page, 'orderName', _data('expect_9', ctx), '首行即该订单（结构化验证搜索命中）', timeout_ms=160000, refresh='research')
    _assert_first_row(page, 'orderStatus', _data('expect_10', ctx), '有界等待：订单提交后按时间自动流转，最长约160秒变为已关闭，轮询首行状态列到「已关闭」为止（等待时长由框架按场景声明160000ms设置，不固定sleep）', timeout_ms=160000, refresh='research')

    # step 37: 点右上角入口打开角色菜单（切换为发票管理员藏在里面，requires_open）
    _act(page, "click", semantic='订@订单列表页', primary=lambda p: p.locator("#nu-avatar"))
    _log(page, "click", f"点右上角入口打开角色菜单（切换为发票管理员藏在里面，requires_open）")

    # step 38: 切换到发票管理员角色（开票前置权限）
    _act(page, "click", semantic='切换为发票管理员@订单列表页', primary=lambda p: p.get_by_role("button", name="切换为发票管理员"))
    _log(page, "click", f"切换到发票管理员角色（开票前置权限）")

    # step 39: 切角色后页面重载清掉搜索与勾选，重新输入订单名称 全链路-{datetime}
    _act(page, "fill", semantic='订单名称@订单列表页[订单系统]', primary=lambda p: p.locator("#tb-o-name"), value=_data('fill_11', ctx))
    _log(page, "fill", f"切角色后页面重载清掉搜索与勾选，重新输入订单名称 全链路-{{datetime}}")

    # step 40: 点「搜索」重新过滤出该订单
    _act(page, "click", semantic='搜索@订单列表页', primary=lambda p: p.locator("#btn-search-o"))
    _log(page, "click", f"点「搜索」重新过滤出该订单")

    # step 41: 选中该订单行（刚创建的行探测期不存在，用当前行控件+行锚 全链路-{datetime}）
    _click_row_cell(page, row_text=_data('row_text_12', ctx), cell_field='', tabs=None, op='check', cell_by='index', cell_index=1)
    _log(page, "check", f"选中该订单行（刚创建的行探测期不存在，用当前行控件+行锚 全链路-{{datetime}}）")

    # step 42: 带选中的订单点「去开票」，跳到开票页并带入该订单
    _act(page, "click", semantic='去开票', primary=lambda p: p.locator("#btn-to-invoice"))
    _log(page, "click", f"带选中的订单点「去开票」，跳到开票页并带入该订单")
    _assert_url(page, _data('expect_11', ctx), '到达证据：invoice_create 是开票页 URL 独有片段')
    _assert_text(page, _data('expect_12', ctx), '确认合同编号已自动带入（订单来自合同 HT-1001，稳定文本；发票号系统生成不写死）')

    # step 43: 填发票行数量（页面自带单行发票行，无需新增行）
    _act(page, "fill", semantic='数量@开票页', primary=lambda p: p.get_by_test_id("form-inv-lines").get_by_title("数量"), value=_data('fill_13', ctx))
    _log(page, "fill", f"填发票行数量（页面自带单行发票行，无需新增行）")

    # step 44: 发票行单位选第一项
    _act(page, "select", semantic='单位@开票页', primary=lambda p: p.get_by_test_id("form-inv-lines").get_by_title("单位"), index=0)
    _log(page, "select", f"发票行单位选第一项")

    # step 45: 发票行期次号选第一项
    _act(page, "select", semantic='期次号', primary=lambda p: p.get_by_test_id("form-inv-lines").get_by_title("期次号"), index=0)
    _log(page, "select", f"发票行期次号选第一项")

    # step 46: 发票行类型选第一项
    _act(page, "select", semantic='发票行类型', primary=lambda p: p.get_by_test_id("form-inv-lines").get_by_title("发票行类型"), index=0)
    _log(page, "select", f"发票行类型选第一项")

    # step 47: 点底部「保存」完成发票创建（发票管理员角色下可保存）
    _act(page, "click", semantic='保存@开票页[应收发票创建]', primary=lambda p: p.locator("#btn-inv-submit"))
    _log(page, "click", f"点底部「保存」完成发票创建（发票管理员角色下可保存）")

    # step 48: 进入发票列表页
    _goto(page, 'http://localhost:8000/invoice_list.html')
    _log(page, "goto", f"进入发票列表页")
    _assert_url(page, _data('expect_13', ctx), '到达证据：invoice_list 是发票列表页 URL 独有片段')
    _assert_text(page, _data('expect_14', ctx), '补充到达证据：发票列表页独有标题「应收发票列表」')

    # step 49: 在订单名称搜索框输入 全链路-{datetime}（发票号运行时才生成不可写死，用订单名称反查）
    _act(page, "fill", semantic='订单名称@发票列表页', primary=lambda p: p.locator("#tb-i-oname"), value=_data('fill_14', ctx))
    _log(page, "fill", f"在订单名称搜索框输入 全链路-{{datetime}}（发票号运行时才生成不可写死，用订单名称反查）")

    # step 50: 点「搜索」（条件区最下方居中）
    _act(page, "click", semantic='搜索@发票列表页', primary=lambda p: p.locator("#btn-search-inv"))
    _log(page, "click", f"点「搜索」（条件区最下方居中）")
    _assert_first_row(page, 'customer', _data('expect_15', ctx), '订单名称全系统唯一，搜索唯一命中刚创建的那张发票；首行客户列=建单时选的第一个客户 北京华信科技有限公司（结构性验证发票建出来了）', timeout_ms=160000, refresh='research')

