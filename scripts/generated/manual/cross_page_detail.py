"""hybrid_gui_qa 用例模块：cross_page_detail（场景 manual）—— 由 cases/manual/cross_page_detail.json 自动生成。

**不要手改本文件**：改用例后重跑 generate 会覆盖它。要改行为 → 改用例 json / 场景 yml。
数据抽离在 scripts/datasets/cross_page_detail.json（脚本与数据分离）。
一个用例一个文件（P20）：便于按 id 管理、按变化增量重生成。

运行（推荐走 cli：自带资源预检 + run-id 隔离的日志/报告）:
  python -m framework.cli run --workers 2                 # 全量
  python -m framework.cli run --debug --case cross_page_detail        # 只调试这一条
裸跑 pytest（未设 HYBRID_RUN_ID 时日志落 log/latest/）:
  pytest scripts/generated/manual/cross_page_detail.py -v
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

def test_cross_page_detail(page, ctx):
    """跨页：列表搜索 → 点编号进详情页（换页有 url 断言）→ 返回列表再搜索核验"""
    _CURRENT_LOG["case_id"] = "cross_page_detail"
    _goto(page, 'http://localhost:8000')
    _log(page, "场景开始", f"case=cross_page_detail")

    # step 1: 打开合同列表页
    _goto(page, 'http://localhost:8000/')
    _log(page, "goto", f"打开合同列表页")

    # step 2: 关键字输入 1005
    _act(page, "fill", semantic='合同编号_名称_管理单元_合同类型_帐套', primary=lambda p: p.get_by_placeholder("合同编号/名称/管理单元/合同类型/帐套"), value=_data('fill_0', ctx))
    _log(page, "fill", f"关键字输入 1005")

    # step 3: 点击列表页的搜索按钮
    _act(page, "click", semantic='搜索@列表页', primary=lambda p: p.get_by_role("button", name="搜索"))
    _log(page, "click", f"点击列表页的搜索按钮")
    _assert_count(page, _data('expect_0', ctx), lambda p: p.locator('#tbody-contracts tr'), semantic=None, desc='【列表页·搜索后】结果恰好 1 行')
    _assert_attr(page, 'data-cust', _data('expect_1', ctx), lambda p: p.locator("#tbody-contracts tr:has-text('HT-1005') td[data-field='customer']"), semantic=None, desc='【列表页】HT-1005 的客户编号 = c5（客户按序号确定：HT-1001→c1、HT-1005→c5、HT-1007→c1…）')

    # step 4: 点击结果里的编号链接 HT-1005 进入详情页
    _act(page, "click", semantic='HT_1005', primary=lambda p: p.get_by_test_id("tbl-contracts").locator("tbody tr").filter(has_text="HT-1005 合同5 0021 002 合同 北京中科智慧科技有限公司 bu_b").locator("td[data-field='contractNo']").get_by_role("link"))
    _log(page, "click", f"点击结果里的编号链接 HT-1005 进入详情页")
    _assert_url(page, _data('expect_2', ctx), '【换页证据】点击编号后 URL 已变为详情页')
    _assert_count(page, _data('expect_3', ctx), lambda p: p.locator("table[aria-label='合同详情'] tr:has-text('合同编号') td"), semantic=None, desc='【详情页】编号单元格存在（确认换的是详情页而不是别的页）')
    _assert_text(page, _data('expect_4', ctx), '【详情页】显示名称 合同5（与列表页 HT-1005 一致）')
    _assert_attr(page, 'data-cust', _data('expect_5', ctx), lambda p: p.locator("table[aria-label='合同详情'] tr:has-text('客户') td"), semantic=None, desc='【详情页·客户跨页一致】HT-1005 的客户编号也是 c5 —— 2026-09-14 起两页读服务端的同一条记录，客户不再各自推导')

    # step 5: 点击详情页的「返回列表」回到列表页
    _act(page, "click", semantic='返回列表', primary=lambda p: p.get_by_role("link", name="返回列表"))
    _log(page, "click", f"点击详情页的「返回列表」回到列表页")
    _assert_visible(page, lambda p: p.locator('#btn-new'), semantic=None, desc='【回到列表页】「+ 新建合同」按钮可见（列表页特征）')
    _assert_count(page, _data('expect_7', ctx), lambda p: p.locator("#tbody-contracts tr:has-text('HT-1001')"), semantic=None, desc='【回到列表页·基线】预置首行 HT-1001 在列表里（F5 稳健化：不再用「全量 20 行」——那条会被本次运行新建的数据顶掉，与「回到列表页」要验的事无关）')

    # step 6: 回到列表页后再输入关键字 1005
    _act(page, "fill", semantic='合同编号_名称_管理单元_合同类型_帐套', primary=lambda p: p.get_by_placeholder("合同编号/名称/管理单元/合同类型/帐套"), value=_data('fill_1', ctx))
    _log(page, "fill", f"回到列表页后再输入关键字 1005")

    # step 7: 再次点击搜索
    _act(page, "click", semantic='搜索@列表页', primary=lambda p: p.get_by_role("button", name="搜索"))
    _log(page, "click", f"再次点击搜索")
    _assert_count(page, _data('expect_8', ctx), lambda p: p.locator("#tbody-contracts tr:has-text('HT-1005')"), semantic=None, desc='【末尾】再搜索 1005 仍能命中 HT-1005')
    _assert_text(page, _data('expect_9', ctx), '【末尾】列表里出现编号 HT-1005')

