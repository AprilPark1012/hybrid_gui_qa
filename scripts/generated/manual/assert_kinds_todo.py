"""hybrid_gui_qa 用例模块：assert_kinds_todo（场景 manual）—— 由 cases/manual/assert_kinds_todo.json 自动生成。

**不要手改本文件**：改用例后重跑 generate 会覆盖它。要改行为 → 改用例 json / 场景 yml。
数据抽离在 scripts/datasets/assert_kinds_todo.json（脚本与数据分离）。
一个用例一个文件（P20）：便于按 id 管理、按变化增量重生成。

运行（推荐走 cli：自带资源预检 + run-id 隔离的日志/报告）:
  python -m framework.cli run --workers 2                 # 全量
  python -m framework.cli run --debug --case assert_kinds_todo        # 只调试这一条
裸跑 pytest（未设 HYBRID_RUN_ID 时日志落 log/latest/）:
  pytest scripts/generated/manual/assert_kinds_todo.py -v
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

def test_assert_kinds_todo(page, ctx):
    """待办页：断言 checkbox 状态（checked/unchecked）+ 列表行数（count）"""
    _CURRENT_LOG["case_id"] = "assert_kinds_todo"
    _goto(page, 'http://localhost:8000/todo.html')
    _log(page, "场景开始", f"case=assert_kinds_todo")

    # step 1: 打开待办页
    _goto(page, 'http://localhost:8000/todo.html')
    _log(page, "goto", f"打开待办页")

    # ---- 断言（用例末尾）----
    _assert_checked(page, lambda p: p.locator("li:has-text('买牛奶') input[type=checkbox]"), semantic=None, desc='买牛奶 那条已勾选（checked）')
    _assert_unchecked(page, lambda p: p.locator("li:has-text('写周报') input[type=checkbox]"), semantic=None, desc='写周报 那条未勾选（unchecked）')
    _assert_count(page, _data('expect_2', ctx), lambda p: p.locator('#todo-list li'), semantic=None, desc='初始有 2 条待办')
    _assert_text(page, _data('expect_3', ctx), '列表里能看到 买牛奶')

