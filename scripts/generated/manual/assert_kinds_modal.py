"""hybrid_gui_qa 用例模块：assert_kinds_modal（场景 manual）—— 由 cases/manual/assert_kinds_modal.json 自动生成。

**不要手改本文件**：改用例后重跑 generate 会覆盖它。要改行为 → 改用例 json / 场景 yml。
数据抽离在 scripts/datasets/assert_kinds_modal.json（脚本与数据分离）。
一个用例一个文件（P20）：便于按 id 管理、按变化增量重生成。

运行（推荐走 cli：自带资源预检 + run-id 隔离的日志/报告）:
  python -m framework.cli run --workers 2                 # 全量
  python -m framework.cli run --debug --case assert_kinds_modal        # 只调试这一条
裸跑 pytest（未设 HYBRID_RUN_ID 时日志落 log/latest/）:
  pytest scripts/generated/manual/assert_kinds_modal.py -v
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

def test_assert_kinds_modal(page, ctx):
    """点开新建合同弹窗 → 断言弹窗与其字段可见（visible/count，弹窗内容需真页覆盖）"""
    _CURRENT_LOG["case_id"] = "assert_kinds_modal"
    _goto(page, 'http://localhost:8000')
    _log(page, "场景开始", f"case=assert_kinds_modal")

    # step 1: 打开合同列表页
    _goto(page, 'http://localhost:8000')
    _log(page, "goto", f"打开合同列表页")

    # step 2: 点击新建合同按钮打开弹窗
    _act(page, "click", semantic='新建合同', primary=lambda p: p.get_by_role("button", name="+ 新建合同"))
    _log(page, "click", f"点击新建合同按钮打开弹窗")

    # ---- 断言（用例末尾）----
    _assert_visible(page, lambda p: p.locator('#modal-new'), semantic=None, desc='弹窗遮罩可见（visible）')
    _assert_visible(page, lambda p: p.locator('#inp-name'), semantic=None, desc='弹窗里的合同名称输入框可见')
    _assert_count(page, _data('expect_2', ctx), lambda p: p.locator('#modal-new select'), semantic=None, desc='弹窗内 4 个下拉（管理单元/帐套/合同类型/业务单元）—— 客户已改为弹层选择，不再是下拉')
    _assert_enabled(page, lambda p: p.locator('#btn-submit'), semantic=None, desc='提交按钮可用')

