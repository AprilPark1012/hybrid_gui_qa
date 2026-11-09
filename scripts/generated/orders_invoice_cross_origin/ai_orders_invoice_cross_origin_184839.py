"""hybrid_gui_qa 用例模块：ai_orders_invoice_cross_origin_184839（场景 orders_invoice_cross_origin）—— 由 cases/orders_invoice_cross_origin/ai_orders_invoice_cross_origin_184839.json 自动生成。

**不要手改本文件**：改用例后重跑 generate 会覆盖它。要改行为 → 改用例 json / 场景 yml。
数据抽离在 scripts/datasets/ai_orders_invoice_cross_origin_184839.json（脚本与数据分离）。
一个用例一个文件（P20）：便于按 id 管理、按变化增量重生成。

运行（推荐走 cli：自带资源预检 + run-id 隔离的日志/报告）:
  python -m framework.cli run --workers 2                 # 全量
  python -m framework.cli run --debug --case ai_orders_invoice_cross_origin_184839        # 只调试这一条
裸跑 pytest（未设 HYBRID_RUN_ID 时日志落 log/latest/）:
  pytest scripts/generated/orders_invoice_cross_origin/ai_orders_invoice_cross_origin_184839.py -v
"""
from _harness import (_CURRENT_LOG, _log, _data, _act, _goto,
                      _login_flow,
                      # V8.10.0 跨 origin：登录后铺会话（模板里会渲染这个调用，漏 import = NameError）
                      _spread_session,
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

def test_ai_orders_invoice_cross_origin_184839(page, ctx):
    """【跨 origin 演练 · 三个业务系统 + 一套 SSO】
先登录（SSO，只在 8000 上登录一次），然后在订单系统(8001)里按订单名称搜索到一条订单，
再切到发票系统(8002)确认发票列表能打开。"""
    _CURRENT_LOG["case_id"] = "ai_orders_invoice_cross_origin_184839"
    _goto(page, 'http://localhost:8000/')
    # ---- 登录（L35：场景自然语言 -> 同一规划器 -> 同一套定位栈；步骤已固化在用例里）----
    _login_flow(page, [{'order': 0, 'op': 'goto', 'element': None, 'value': 'http://localhost:8000/login.html', 'assertion': None, 'desc': '打开 http://localhost:8000/login.html', 'row_text': None, 'cell_field': None, 'cell_by': None, 'cell_index': None, 'row_index': None, 'row_id': None, 'index': None}, {'order': 1, 'op': 'fill', 'element': {'semantic_name': '账号', 'role': 'textbox', 'name': '账号', 'label': None, 'placeholder': '请输入账号', 'test_id': '', 'element_id': None, 'text': '账号', 'page_hint': None, 'container_heading': '演示系统登录', 'nearby_text': '演示系统登录 合同 / 订单 / 发票 三个模块 + 超级管理员 *账号 *密码 角色账号密码 合同管理员contractcontract@123订单管理员or', 'help_text': '账号', 'notes': '', 'anchor': None, 'path': None, 'isValid': True}, 'value': 'super', 'assertion': None, 'desc': '在登录页账号输入框填入 super', 'row_text': None, 'cell_field': None, 'cell_by': None, 'cell_index': None, 'row_index': None, 'row_id': None, 'index': None}, {'order': 2, 'op': 'fill', 'element': {'semantic_name': '密码', 'role': 'textbox', 'name': '密码', 'label': None, 'placeholder': '请输入密码', 'test_id': '', 'element_id': None, 'text': '密码', 'page_hint': None, 'container_heading': '演示系统登录', 'nearby_text': '演示系统登录 合同 / 订单 / 发票 三个模块 + 超级管理员 *账号 *密码 角色账号密码 合同管理员contractcontract@123订单管理员or', 'help_text': '密码', 'notes': '', 'anchor': None, 'path': None, 'isValid': True}, 'value': 'super@123', 'assertion': None, 'desc': '在登录页密码输入框填入 super@123', 'row_text': None, 'cell_field': None, 'cell_by': None, 'cell_index': None, 'row_index': None, 'row_id': None, 'index': None}, {'order': 3, 'op': 'click', 'element': {'semantic_name': '登_录', 'role': 'button', 'name': '登 录', 'label': None, 'placeholder': '', 'test_id': '', 'element_id': None, 'text': '登 录', 'page_hint': None, 'container_heading': '演示系统登录', 'nearby_text': '演示系统登录 合同 / 订单 / 发票 三个模块 + 超级管理员 *账号 *密码 角色账号密码 合同管理员contractcontract@123订单管理员or', 'help_text': '', 'notes': '', 'anchor': None, 'path': None, 'isValid': True}, 'value': None, 'assertion': None, 'desc': '点击「登录」按钮提交登录', 'row_text': None, 'cell_field': None, 'cell_by': None, 'cell_index': None, 'row_index': None, 'row_id': None, 'index': None}], {'url_not': 'login.html'}, 'http://localhost:8000/login.html')
    # ---- 登录步骤结束 ----
    _spread_session(page.context, {'token_from': 'url_param', 'param': 'token', 'store': 'localStorage', 'key': 'demo_token', 'spread': ['order', 'invoice']}, {'order': 'http://localhost:8001', 'invoice': 'http://localhost:8002'})
    _log(page, "场景开始", f"case=ai_orders_invoice_cross_origin_184839")

    # step 1: 打开 【合同列表页】http://localhost:8000/
    _goto(page, 'http://localhost:8000/')
    _log(page, "goto", f"打开 【合同列表页】http://localhost:8000/")
    _assert_text(page, _data('expect_0', ctx), '确认 SSO 登录后落在合同系统首页（登录由框架前置完成，这里只验登录态与落点）')

    # step 2: 从合同系统(8000)切到订单系统(8001)，复用同一套 SSO 登录态、免再次登录
    _goto(page, 'http://localhost:8001/orders.html', 'order')
    _log(page, "goto", f"从合同系统(8000)切到订单系统(8001)，复用同一套 SSO 登录态、免再次登录")
    _assert_url(page, _data('expect_1', ctx), '到达证据：订单列表页 URL 独有片段 orders.html（仅该页含）')
    _assert_text(page, _data('expect_2', ctx), '到达证据：订单系统页面特征文案出现，证明 SSO 免登录直达成功')

    # step 3: 在订单系统顶部筛选区按订单名称填入搜索关键词
    _act(page, "fill", semantic='订单名称@订单列表页', primary=lambda p: p.locator("#tb-o-name"), value=_data('fill_0', ctx))
    _log(page, "fill", f"在订单系统顶部筛选区按订单名称填入搜索关键词")

    # step 4: 点击搜索按钮，按订单名称过滤订单列表
    _act(page, "click", semantic='搜索@订单列表页', primary=lambda p: p.locator("#btn-search-o"))
    _log(page, "click", f"点击搜索按钮，按订单名称过滤订单列表")
    _assert_first_row(page, 'orderName', _data('expect_3', ctx), '验证按订单名称搜到了该订单：订单列表页首行的订单名称列即该订单', timeout_ms=30000, refresh='none')

    # step 5: 从订单系统(8001)切到发票系统(8002)，继续复用 SSO 登录态
    _goto(page, 'http://localhost:8002/invoice_list.html', 'invoice')
    _log(page, "goto", f"从订单系统(8001)切到发票系统(8002)，继续复用 SSO 登录态")
    _assert_url(page, _data('expect_4', ctx), '到达证据：发票列表页 URL 独有片段 invoice_list.html（仅该页含）')
    _assert_text(page, _data('expect_5', ctx), '确认发票列表能打开：应收发票列表页面特征标题文案出现')

