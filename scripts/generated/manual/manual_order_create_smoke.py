"""hybrid_gui_qa 用例模块：manual_order_create_smoke（场景 manual）—— 由 cases/manual/manual_order_create_smoke.json 自动生成。

**不要手改本文件**：改用例后重跑 generate 会覆盖它。要改行为 → 改用例 json / 场景 yml。
数据抽离在 scripts/datasets/manual_order_create_smoke.json（脚本与数据分离）。
一个用例一个文件（P20）：便于按 id 管理、按变化增量重生成。

运行（推荐走 cli：自带资源预检 + run-id 隔离的日志/报告）:
  python -m framework.cli run --workers 2                 # 全量
  python -m framework.cli run --debug --case manual_order_create_smoke        # 只调试这一条
裸跑 pytest（未设 HYBRID_RUN_ID 时日志落 log/latest/）:
  pytest scripts/generated/manual/manual_order_create_smoke.py -v
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
                      _Tabs, _click_row_cell, _assert_first_row,
                      # P22 批 4/5：等待式断言（wait_text；批 5 起支持 selector 限定范围）
                      _assert_wait_text)
# P16 批 5：运行期「锚点 + 容器内相对路径」下钻（col.header 这类列口径只有运行时才算得出列序）
from framework.tools.probe.scope_locate import drill as _drill
import pytest
from playwright.sync_api import expect as _pw_expect

def test_manual_order_create_smoke(page, ctx):
    """手搓最小闭环（场景 2 常驻样例）：
1. 打开合同列表页（登录由场景级前置完成）。
2. 切换为**订单管理员**角色（不切则保存按钮置灰）。
3. 等价直达新建订单页并带入合同 HT-1001（点「新建订单」在 demo 里是 iframe 弹层，探测链路暂不覆盖）。
4. 填写订单名称「手搓-{datetime}」，业务单元/管理单元/帐套/订单类型/客户/销售员各选第一行，保存。
5. 进订单列表页，按订单名称搜索 ⇒ 列表首行必须出现这条订单。"""
    _CURRENT_LOG["case_id"] = "manual_order_create_smoke"
    _goto(page, 'http://localhost:8000/login.html')
    _log(page, "场景开始", f"case=manual_order_create_smoke")

    # step 1: 打开合同列表页（登录由场景级登录前置完成，无需手工登录）
    _goto(page, 'http://localhost:8000/')
    _log(page, "goto", f"打开合同列表页（登录由场景级登录前置完成，无需手工登录）")

    # step 2: 展开右上角角色切换入口
    _act(page, "click", semantic='超@合同列表页', primary=lambda p: p.get_by_title("点击切换角色 / 退出登录"))
    _log(page, "click", f"展开右上角角色切换入口")

    # step 3: 切换为订单管理员角色
    _act(page, "click", semantic='切换为订单管理员@合同列表页', primary=lambda p: p.get_by_role("button", name="切换为订单管理员"))
    _log(page, "click", f"切换为订单管理员角色")

    # step 4: 等价直达新建订单页并带入合同 HT-1001
    _goto(page, 'http://localhost:8000/order_new.html?contract_no=HT-1001')
    _log(page, "goto", f"等价直达新建订单页并带入合同 HT-1001")

    # step 5: 填写订单名称
    _act(page, "fill", semantic='订单名称@新建订单页', primary=lambda p: p.get_by_role("textbox", name="订单名称"), value=_data('fill_0', ctx))
    _log(page, "fill", f"填写订单名称")

    # step 6: 业务单元选第一行
    _act(page, "select", semantic='业务单元@新建订单页', primary=lambda p: p.get_by_role("combobox", name="业务单元"), index=0)
    _log(page, "select", f"业务单元选第一行")

    # step 7: 管理单元选第一行
    _act(page, "select", semantic='管理单元@新建订单页', primary=lambda p: p.get_by_role("combobox", name="管理单元"), index=0)
    _log(page, "select", f"管理单元选第一行")

    # step 8: 帐套选第一行
    _act(page, "select", semantic='帐套@新建订单页', primary=lambda p: p.get_by_role("combobox", name="帐套"), index=0)
    _log(page, "select", f"帐套选第一行")

    # step 9: 订单类型选第一项
    _act(page, "select", semantic='订单类型@新建订单页', primary=lambda p: p.get_by_role("combobox", name="订单类型"), index=0)
    _log(page, "select", f"订单类型选第一项")

    # step 10: 客户选第一个
    _act(page, "select", semantic='客户@新建订单页', primary=lambda p: p.get_by_role("combobox", name="客户"), index=0)
    _log(page, "select", f"客户选第一个")

    # step 11: 销售员选第一个
    _act(page, "select", semantic='销售员@新建订单页', primary=lambda p: p.get_by_role("combobox", name="销售员"), index=0)
    _log(page, "select", f"销售员选第一个")

    # step 12: 保存新建订单（id=btn-o-submit）
    _act(page, "click", semantic=None, primary=lambda p: p.locator("#btn-o-submit"))
    _log(page, "click", f"保存新建订单（id=btn-o-submit）")

    # step 13: 进入订单列表页（带合同号查询条件，reload 后条件不丢）
    _goto(page, 'http://localhost:8000/orders.html?contract_no=HT-1001')
    _log(page, "goto", f"进入订单列表页（带合同号查询条件，reload 后条件不丢）")
    _assert_text(page, _data('expect_0', ctx), '确认进入订单列表页')

    # step 14: 在订单名称搜索框输入刚填的订单名称
    _act(page, "fill", semantic='订单名称@订单列表页', primary=lambda p: p.get_by_role("textbox", name="订单名称"), value=_data('fill_1', ctx))
    _log(page, "fill", f"在订单名称搜索框输入刚填的订单名称")

    # step 15: 搜索该订单
    _act(page, "click", semantic='搜索@订单列表页', primary=lambda p: p.get_by_role("button", name="搜索"))
    _log(page, "click", f"搜索该订单")
    _assert_first_row(page, 'orderName', _data('expect_1', ctx), '列表首行出现刚创建的订单')

