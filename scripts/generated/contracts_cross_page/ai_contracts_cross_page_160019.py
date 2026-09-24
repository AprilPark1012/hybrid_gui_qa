"""hybrid_gui_qa 用例模块：ai_contracts_cross_page_160019（场景 contracts_cross_page）—— 由 cases/contracts_cross_page/ai_contracts_cross_page_160019.json 自动生成。

**不要手改本文件**：改用例后重跑 generate 会覆盖它。要改行为 → 改用例 json / 场景 yml。
数据抽离在 scripts/datasets/ai_contracts_cross_page_160019.json（脚本与数据分离）。
一个用例一个文件（P20）：便于按 id 管理、按变化增量重生成。

运行（推荐走 cli：自带资源预检 + run-id 隔离的日志/报告）:
  python -m framework.cli run --workers 2                 # 全量
  python -m framework.cli run --debug --case ai_contracts_cross_page_160019        # 只调试这一条
裸跑 pytest（未设 HYBRID_RUN_ID 时日志落 log/latest/）:
  pytest scripts/generated/contracts_cross_page/ai_contracts_cross_page_160019.py -v
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

def test_ai_contracts_cross_page_160019(page, ctx):
    """打开合同列表页，在关键字搜索框输入 1005 并点击搜索；
点击结果行里的编号链接 HT-1005 进入合同详情页，确认已经换页（URL 含 contract_detail）
且详情页显示了编号 HT-1005 与名称 合同5；
然后点击「返回列表」回到列表页，再在关键字搜索框输入 1005 并点击搜索，确认列表里仍有 HT-1005。"""
    _CURRENT_LOG["case_id"] = "ai_contracts_cross_page_160019"
    _goto(page, 'http://localhost:8000/')
    _log(page, "场景开始", f"case=ai_contracts_cross_page_160019")

    # step 1: 打开合同列表页
    _goto(page, 'http://localhost:8000/')
    _log(page, "goto", f"打开合同列表页")

    # step 2: 在关键字搜索框输入 1005
    _act(page, "fill", semantic='合同编号_名称_管理单元_合同类型_帐套', primary=lambda p: p.get_by_placeholder("合同编号/名称/管理单元/合同类型/帐套"), value=_data('fill_0', ctx))
    _log(page, "fill", f"在关键字搜索框输入 1005")

    # step 3: 点击列表页搜索按钮
    _act(page, "click", semantic='搜索@列表页', primary=lambda p: p.get_by_role("button", name="搜索"))
    _log(page, "click", f"点击列表页搜索按钮")
    _assert_text(page, _data('expect_0', ctx), '确认搜索结果里出现 HT-1005')

    # step 4: 点击结果行里的编号链接 HT-1005 进入详情页
    _act(page, "click", semantic='HT_1005', primary=lambda p: p.get_by_test_id("tbl-contracts").locator("tbody tr").filter(has_text="HT-1005 合同5 0021 002 合同 北京中科智慧科技有限公司 bu_b").locator("td[data-field='contractNo']").get_by_role("link"))
    _log(page, "click", f"点击结果行里的编号链接 HT-1005 进入详情页")
    _assert_url(page, _data('expect_1', ctx), '确认已换页到合同详情页')
    _assert_text(page, _data('expect_2', ctx), '确认详情页显示编号 HT-1005')
    _assert_text(page, _data('expect_3', ctx), '确认详情页显示名称 合同5')

    # step 5: 点击返回列表回到列表页
    _act(page, "click", semantic='返回列表', primary=lambda p: p.get_by_role("link", name="返回列表"))
    _log(page, "click", f"点击返回列表回到列表页")
    _assert_text(page, _data('expect_4', ctx), '确认已回到列表页（表头出现）')

    # step 6: 再次在关键字搜索框输入 1005
    _act(page, "fill", semantic='合同编号_名称_管理单元_合同类型_帐套', primary=lambda p: p.get_by_placeholder("合同编号/名称/管理单元/合同类型/帐套"), value=_data('fill_1', ctx))
    _log(page, "fill", f"再次在关键字搜索框输入 1005")

    # step 7: 再次点击列表页搜索按钮
    _act(page, "click", semantic='搜索@列表页', primary=lambda p: p.get_by_role("button", name="搜索"))
    _log(page, "click", f"再次点击列表页搜索按钮")
    _assert_text(page, _data('expect_5', ctx), '确认列表里仍有 HT-1005')

