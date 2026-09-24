"""hybrid_gui_qa 用例模块：search_customer_fuzzy_negative（场景 manual）—— 由 cases/manual/search_customer_fuzzy_negative.json 自动生成。

**不要手改本文件**：改用例后重跑 generate 会覆盖它。要改行为 → 改用例 json / 场景 yml。
数据抽离在 scripts/datasets/search_customer_fuzzy_negative.json（脚本与数据分离）。
一个用例一个文件（P20）：便于按 id 管理、按变化增量重生成。

运行（推荐走 cli：自带资源预检 + run-id 隔离的日志/报告）:
  python -m framework.cli run --workers 2                 # 全量
  python -m framework.cli run --debug --case search_customer_fuzzy_negative        # 只调试这一条
裸跑 pytest（未设 HYBRID_RUN_ID 时日志落 log/latest/）:
  pytest scripts/generated/manual/search_customer_fuzzy_negative.py -v
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

def test_search_customer_fuzzy_negative(page, ctx):
    """客户右模糊（前缀）筛选：非前缀『华信』必须不命中"""
    _CURRENT_LOG["case_id"] = "search_customer_fuzzy_negative"
    _goto(page, 'http://localhost:8000')
    _log(page, "场景开始", f"case=search_customer_fuzzy_negative")

    # step 1: 打开合同列表页
    _goto(page, 'http://localhost:8000')
    _log(page, "goto", f"打开合同列表页")

    # step 2: 客户筛选框输入**非前缀**的『华信』
    _act(page, "fill", semantic='客户名称_右模糊_前缀匹配', primary=lambda p: p.get_by_placeholder("客户名称（右模糊：前缀匹配）"), value=_data('fill_0', ctx))
    _log(page, "fill", f"客户筛选框输入**非前缀**的『华信』")

    # step 3: 点击搜索按钮
    _act(page, "click", semantic='搜索', primary=lambda p: p.get_by_role("button", name="搜索"))
    _log(page, "click", f"点击搜索按钮")

    # ---- 断言（用例末尾）----
    _assert_count(page, _data('expect_0', ctx), lambda p: p.locator("#tbody-contracts tr:has(td[data-field='contractNo'])"), semantic=None, desc='『华信』不是任何客户名的前缀 ⇒ 0 条（若命中就说明实现成了包含匹配，不是右模糊）')
    _assert_text(page, _data('expect_1', ctx), '空结果提示')

