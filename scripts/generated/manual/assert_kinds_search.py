"""hybrid_gui_qa 用例模块：assert_kinds_search（场景 manual）—— 由 cases/manual/assert_kinds_search.json 自动生成。

**不要手改本文件**：改用例后重跑 generate 会覆盖它。要改行为 → 改用例 json / 场景 yml。
数据抽离在 scripts/datasets/assert_kinds_search.json（脚本与数据分离）。
一个用例一个文件（P20）：便于按 id 管理、按变化增量重生成。

运行（推荐走 cli：自带资源预检 + run-id 隔离的日志/报告）:
  python -m framework.cli run --workers 2                 # 全量
  python -m framework.cli run --debug --case assert_kinds_search        # 只调试这一条
裸跑 pytest（未设 HYBRID_RUN_ID 时日志落 log/latest/）:
  pytest scripts/generated/manual/assert_kinds_search.py -v
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

def test_assert_kinds_search(page, ctx):
    """搜索 1005：覆盖 url/count/attr/text/hidden/enabled/disabled 断言类型（真页）"""
    _CURRENT_LOG["case_id"] = "assert_kinds_search"
    _goto(page, 'http://localhost:8000')
    _log(page, "场景开始", f"case=assert_kinds_search")

    # step 1: 打开合同列表页
    _goto(page, 'http://localhost:8000')
    _log(page, "goto", f"打开合同列表页")

    # step 2: 关键字输入 1005
    _act(page, "fill", semantic='合同编号_名称_管理单元_合同类型_帐套', primary=lambda p: p.get_by_placeholder("合同编号/名称/管理单元/合同类型/帐套"), value=_data('fill_0', ctx))
    _log(page, "fill", f"关键字输入 1005")

    # step 3: 点击搜索按钮
    _act(page, "click", semantic='搜索', primary=lambda p: p.get_by_role("button", name="搜索"))
    _log(page, "click", f"点击搜索按钮")

    # ---- 断言（用例末尾）----
    _assert_url(page, _data('expect_0', ctx), 'URL 仍在合同列表页（url 断言：子串匹配）')
    _assert_count(page, _data('expect_1', ctx), lambda p: p.locator('#tbody-contracts tr'), semantic=None, desc='搜索结果恰好 1 行（count：结果行数）')
    _assert_count(page, _data('expect_2', ctx), lambda p: p.locator("#tbody-contracts tr:has-text('HT-1005')"), semantic=None, desc='命中的正是 HT-1005 那一行')
    _assert_attr(page, 'data-field', _data('expect_3', ctx), lambda p: p.locator("#tbody-contracts tr:first-child td[data-field='contractNo']"), semantic=None, desc='首单元格是合同编号列（attr：data-field）')
    _assert_text(page, _data('expect_4', ctx), '列表里出现编号 HT-1005（text，原有类型）')
    _assert_text(page, _data('expect_5', ctx), '状态行提示搜索完成')
    _assert_hidden(page, lambda p: p.locator('#modal-new'), semantic=None, desc='新建弹窗保持关闭（hidden）')
    _assert_enabled(page, lambda p: p.get_by_role("button", name="搜索"), semantic='搜索', desc='搜索按钮可用（enabled，走 element→语义映射的 locator）')
    _assert_disabled(page, lambda p: p.locator('#btn-export'), semantic=None, desc='导出按钮未接入 → 禁用（disabled）')

