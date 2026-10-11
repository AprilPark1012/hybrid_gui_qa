"""hybrid_gui_qa 用例模块：ai_orders_invoice_full_lifecycle_044342（场景 orders_invoice_full_lifecycle）—— 由 cases/orders_invoice_full_lifecycle/ai_orders_invoice_full_lifecycle_044342.json 自动生成。

**不要手改本文件**：改用例后重跑 generate 会覆盖它。要改行为 → 改用例 json / 场景 yml。
数据抽离在 scripts/datasets/ai_orders_invoice_full_lifecycle_044342.json（脚本与数据分离）。
一个用例一个文件（P20）：便于按 id 管理、按变化增量重生成。

运行（推荐走 cli：自带资源预检 + run-id 隔离的日志/报告）:
  python -m framework.cli run --workers 2                 # 全量
  python -m framework.cli run --debug --case ai_orders_invoice_full_lifecycle_044342        # 只调试这一条
裸跑 pytest（未设 HYBRID_RUN_ID 时日志落 log/latest/）:
  pytest scripts/generated/orders_invoice_full_lifecycle/ai_orders_invoice_full_lifecycle_044342.py -v
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

def test_ai_orders_invoice_full_lifecycle_044342(page, ctx):
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
    _CURRENT_LOG["case_id"] = "ai_orders_invoice_full_lifecycle_044342"
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
    _log(page, "场景开始", f"case=ai_orders_invoice_full_lifecycle_044342")

    # step 1: 打开 【登录页】http://localhost:8000/login.html
    _goto(page, 'http://localhost:8000/')
    _log(page, "goto", f"打开 【登录页】http://localhost:8000/login.html")

    # step 2: 在合同列表页勾选第一行合同 HT-1001（页面已由前置就绪，不再重新导航/登录）
    _act(page, "check", semantic='选择合同_HT_1001', primary=lambda p: p.get_by_test_id("tbl-contracts").locator("tbody tr").filter(has_text="HT-1001").locator("td[data-field='pick']").get_by_role("radio"))
    _log(page, "check", f"在合同列表页勾选第一行合同 HT-1001（页面已由前置就绪，不再重新导航/登录）")

    # step 3: 等价直达：打开新建订单页并带上 HT-1001 合同（demo 里点「新建订单」是 iframe 弹层，探测链路不覆盖弹层内控件）
    _goto(page, 'http://localhost:8000/order_new.html?contract_no=HT-1001')
    _log(page, "goto", f"等价直达：打开新建订单页并带上 HT-1001 合同（demo 里点「新建订单」是 iframe 弹层，探测链路不覆盖弹层内控件）")
    _assert_url(page, _data('expect_0', ctx), '确认确实到达新建订单页')

    # step 4: 填写订单名称（全系统唯一，用 {datetime} 保证可重复跑）
    _act(page, "fill", semantic='订单名称@新建订单页', primary=lambda p: p.get_by_test_id("form-order-new").locator("tbody tr").filter(has_text="*订单名称").locator("td").nth(1).get_by_role("textbox"), value=_data('fill_0', ctx))
    _log(page, "fill", f"填写订单名称（全系统唯一，用 {{datetime}} 保证可重复跑）")

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

    # step 11: 填写订单备注（选填）
    _act(page, "fill", semantic='订单备注', primary=lambda p: p.get_by_test_id("form-order-new").locator("tbody tr").filter(has_text="订单备注").locator("td").nth(1).get_by_role("textbox"), value=_data('fill_1', ctx))
    _log(page, "fill", f"填写订单备注（选填）")

    # step 12: 点保存完成新建订单（当前身份为订单管理员，保存按钮可用）
    _act(page, "click", semantic='保存@新建订单页', primary=lambda p: p.locator("#btn-o-submit"))
    _log(page, "click", f"点保存完成新建订单（当前身份为订单管理员，保存按钮可用）")

    # step 13: 回到合同列表页
    _goto(page, 'http://localhost:8000/')
    _log(page, "goto", f"回到合同列表页")
    _assert_text(page, _data('expect_1', ctx), '确认已回到合同列表页（页面上存在「新建订单」按钮）')

    # step 14: 页面重载会清掉之前的勾选，这里必须重新勾选第一行合同 HT-1001
    _act(page, "check", semantic='选择合同_HT_1001', primary=lambda p: p.get_by_test_id("tbl-contracts").locator("tbody tr").filter(has_text="HT-1001").locator("td[data-field='pick']").get_by_role("radio"))
    _log(page, "check", f"页面重载会清掉之前的勾选，这里必须重新勾选第一行合同 HT-1001")
    _assert_text(page, _data('expect_2', ctx), '勾选之后才断言「查看订单」按钮出现/可用（勾选前页面上没有这个按钮）')

    # step 15: 点「查看订单」——该按钮是 window.open 新开标签页，当前标签页仍停在合同列表页，必须用 click_new_tab 并切到新标签页
    page = _t.open_new(lambda: _act(page, "click", semantic='查看订单', primary=lambda p: p.locator("#btn-view-orders")))
    _log(page, "click_new_tab", f"点「查看订单」——该按钮是 window.open 新开标签页，当前标签页仍停在合同列表页，必须用 click_new_tab 并切到新标签页")
    _assert_url(page, _data('expect_3', ctx), '在新标签页确认到达订单系统列表页（orders.html）')

    # step 16: 在新标签页用刚填的订单名称搜索
    _act(page, "fill", semantic='订单名称@订单系统', primary=lambda p: p.locator("#tb-o-name"), value=_data('fill_2', ctx))
    _log(page, "fill", f"在新标签页用刚填的订单名称搜索")

    # step 17: 点搜索
    _act(page, "click", semantic='搜索@订单列表页', primary=lambda p: p.locator("#btn-search-o"))
    _log(page, "click", f"点搜索")
    _assert_first_row(page, 'orderName', _data('expect_4', ctx), '确认新建的订单确实落在列表第一行（订单编号由服务端分配，不写进断言）')

    # step 18: 点这一行的订单名称进入订单详情页（运行时新建行，用行锚+列定位）
    _click_row_cell(page, row_text=_data('row_text_3', ctx), cell_field='orderName', tabs=None, op='click')
    _log(page, "click", f"点这一行的订单名称进入订单详情页（运行时新建行，用行锚+列定位）")
    _assert_url(page, _data('expect_5', ctx), '确认到达订单详情页')

    # step 19: 点「编辑」进入编辑态（否则行工具栏的新增行/保存置灰不可用）
    _act(page, "click", semantic='编辑', primary=lambda p: p.locator("#btn-detail-edit"))
    _log(page, "click", f"点「编辑」进入编辑态（否则行工具栏的新增行/保存置灰不可用）")

    # step 20: 新增第 1 个订单行
    _act(page, "click", semantic='新增行@订单详情页', primary=lambda p: p.locator('section[aria-label="详细信息"]').get_by_text("新增行", exact=True))
    _log(page, "click", f"新增第 1 个订单行")

    # step 21: 填新增行（最后一行）的物料编码
    _act_row(page, '物料编码@订单详情页', -1, op='fill', value=_data('fill_4', ctx))
    _log(page, "fill", f"填新增行（最后一行）的物料编码")

    # step 22: 填新增行的产品编码
    _act_row(page, '产品编码@订单详情页', -1, op='fill', value=_data('fill_5', ctx))
    _log(page, "fill", f"填新增行的产品编码")

    # step 23: 填新增行的数量
    _act_row(page, '数量@订单详情页', -1, op='fill', value=_data('fill_6', ctx))
    _log(page, "fill", f"填新增行的数量")

    # step 24: 选新增行的行类型（必填项）
    _act_row(page, '行类型@订单详情页', -1, op='select', value=_data('select_7', ctx))
    _log(page, "select", f"选新增行的行类型（必填项）")

    # step 25: 点行工具栏里的「保存」，先把这一行订单行本身保存下来
    _log(page, "multi_match", '缺行定位: 保存@详细信息')
    pytest.fail("控件 '保存@详细信息' 在页面上**重复出现 2 个**（同一容器内每行/每条一个）-> 只给语义名会同时命中多个，运行期必红。请补行定位：`row_index`（第 N 行，从 1 起；`-1` = 最后一行）或 `row_text` + 列字段；**刚新增的空行只能用 `row_index`**。", pytrace=False)
    # step 26: 新增第 2 个订单行
    _act(page, "click", semantic='新增行@订单详情页', primary=lambda p: p.locator('section[aria-label="详细信息"]').get_by_text("新增行", exact=True))
    _log(page, "click", f"新增第 2 个订单行")

    # step 27: 填第 2 个新增行（最后一行）的物料编码
    _act_row(page, '物料编码@订单详情页', -1, op='fill', value=_data('fill_8', ctx))
    _log(page, "fill", f"填第 2 个新增行（最后一行）的物料编码")

    # step 28: 填第 2 个新增行的产品编码
    _act_row(page, '产品编码@订单详情页', -1, op='fill', value=_data('fill_9', ctx))
    _log(page, "fill", f"填第 2 个新增行的产品编码")

    # step 29: 填第 2 个新增行的数量
    _act_row(page, '数量@订单详情页', -1, op='fill', value=_data('fill_10', ctx))
    _log(page, "fill", f"填第 2 个新增行的数量")

    # step 30: 选第 2 个新增行的行类型（必填项）
    _act_row(page, '行类型@订单详情页', -1, op='select', value=_data('select_11', ctx))
    _log(page, "select", f"选第 2 个新增行的行类型（必填项）")

    # step 31: 点行工具栏里的「保存」，把第 2 行订单行也保存下来
    _log(page, "multi_match", '缺行定位: 保存@详细信息')
    pytest.fail("控件 '保存@详细信息' 在页面上**重复出现 2 个**（同一容器内每行/每条一个）-> 只给语义名会同时命中多个，运行期必红。请补行定位：`row_index`（第 N 行，从 1 起；`-1` = 最后一行）或 `row_text` + 列字段；**刚新增的空行只能用 `row_index`**。", pytrace=False)
    # step 32: 点页面右下角（底部按钮行最右侧）的「保存」，这一步才完成整个订单的保存
    _act(page, "click", semantic='保存@订单详情', primary=lambda p: p.locator("#btn-detail-edit"))
    _log(page, "click", f"点页面右下角（底部按钮行最右侧）的「保存」，这一步才完成整个订单的保存")

    # step 33: 点底部「提交」提交整个订单（若之前有未保存修改，提交不会生效，所以必须先保存）
    _act(page, "click", semantic='提交', primary=lambda p: p.locator("#btn-detail-submit"))
    _log(page, "click", f"点底部「提交」提交整个订单（若之前有未保存修改，提交不会生效，所以必须先保存）")

    # step 34: 点底部「返回」回到订单列表页
    _act(page, "click", semantic='返回', primary=lambda p: p.locator("#btn-back"))
    _log(page, "click", f"点底部「返回」回到订单列表页")
    _assert_url(page, _data('expect_6', ctx), '确认返回到订单系统列表页')

    # step 35: 用订单名称搜索该订单以观察状态流转
    _act(page, "fill", semantic='订单名称@订单系统', primary=lambda p: p.locator("#tb-o-name"), value=_data('fill_12', ctx))
    _log(page, "fill", f"用订单名称搜索该订单以观察状态流转")

    # step 36: 点搜索
    _act(page, "click", semantic='搜索@订单列表页', primary=lambda p: p.locator("#btn-search-o"))
    _log(page, "click", f"点搜索")
    _assert_wait_text(page, _data('expect_7', ctx), timeout_ms=150000, refresh='research', desc='有界等待：提交后订单按时间自动流转（最长约150秒）到「已关闭」，轮询到状态变化为止，等待时长由场景声明的150000ms自动设置，不写固定 sleep', selector='')

    # step 37: 点右上角头像/角色入口展开角色切换菜单
    _act(page, "click", semantic='订@订单列表页', primary=lambda p: p.locator("#nu-avatar"))
    _log(page, "click", f"点右上角头像/角色入口展开角色切换菜单")

    # step 38: 切换为发票管理员角色（开票需发票管理员权限）
    _act(page, "click", semantic='切换为发票管理员@订单列表页', primary=lambda p: p.get_by_role("button", name="切换为发票管理员"))
    _log(page, "click", f"切换为发票管理员角色（开票需发票管理员权限）")

    # step 39: 切角色后重新按订单名称搜索，确保目标订单在列表中可选
    _act(page, "fill", semantic='订单名称@订单系统', primary=lambda p: p.locator("#tb-o-name"), value=_data('fill_13', ctx))
    _log(page, "fill", f"切角色后重新按订单名称搜索，确保目标订单在列表中可选")

    # step 40: 点搜索
    _act(page, "click", semantic='搜索@订单列表页', primary=lambda p: p.locator("#btn-search-o"))
    _log(page, "click", f"点搜索")

    # step 41: 勾选刚创建的那条订单（行锚=订单名称，勾选列无 data-field，用列下标 1）
    _click_row_cell(page, row_text=_data('row_text_14', ctx), cell_field='', tabs=None, op='check', cell_by='index', cell_index=1)
    _log(page, "check", f"勾选刚创建的那条订单（行锚=订单名称，勾选列无 data-field，用列下标 1）")

    # step 42: 点「去开票」，跳转开票页并带入该订单
    _act(page, "click", semantic='去开票', primary=lambda p: p.locator("#btn-to-invoice"))
    _log(page, "click", f"点「去开票」，跳转开票页并带入该订单")
    _assert_url(page, _data('expect_8', ctx), '确认到达新建应收发票页（订单编号/合同编号已自动带入）')

    # step 43: 选发票行的期次号
    _act_row(page, '期次号@开票页', 1, op='select')
    _log(page, "select", f"选发票行的期次号")

    # step 44: 选发票行的发票行类型
    _act_row(page, '发票行类型@开票页', 1, op='select', value=_data('select_15', ctx))
    _log(page, "select", f"选发票行的发票行类型")

    # step 45: 填发票行数量
    _act_row(page, '数量@开票页', 1, op='fill', value=_data('fill_16', ctx))
    _log(page, "fill", f"填发票行数量")

    # step 46: 选发票行单位
    _act_row(page, '单位@开票页', 1, op='select', value=_data('select_17', ctx))
    _log(page, "select", f"选发票行单位")

    # step 47: 点保存完成发票创建（发票号由系统自动生成，不写进断言）
    _act(page, "click", semantic='保存@应收发票创建@开票页', primary=lambda p: p.locator("#btn-inv-submit"))
    _log(page, "click", f"点保存完成发票创建（发票号由系统自动生成，不写进断言）")

    # step 48: 进入应收发票列表页
    _goto(page, 'http://localhost:8000/invoice_list.html')
    _log(page, "goto", f"进入应收发票列表页")
    _assert_url(page, _data('expect_9', ctx), '确认到达应收发票列表页')

    # step 49: 在发票列表页用订单名称搜索刚创建的发票
    _act(page, "fill", semantic='订单名称@发票列表页', primary=lambda p: p.locator("#tb-i-oname"), value=_data('fill_18', ctx))
    _log(page, "fill", f"在发票列表页用订单名称搜索刚创建的发票")

    # step 50: 点搜索
    _act(page, "click", semantic='搜索@发票列表页', primary=lambda p: p.locator("#btn-search-inv"))
    _log(page, "click", f"点搜索")
    _assert_text(page, _data('expect_10', ctx), '按订单名称检索后发票列表渲染出结果，页面含发票的「订单编号」列（发票号系统生成，不做硬编码断言）')

