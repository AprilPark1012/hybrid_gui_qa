"""hybrid_gui_qa 用例模块：ai_在合同列表页面的搜索框输入_合同1_然后点击搜索_074348（场景 manual）—— 由 cases/manual/ai_在合同列表页面的搜索框输入_合同1_然后点击搜索_074348.json 自动生成。

**不要手改本文件**：改用例后重跑 generate 会覆盖它。要改行为 → 改用例 json / 场景 yml。
数据抽离在 scripts/datasets/ai_在合同列表页面的搜索框输入_合同1_然后点击搜索_074348.json（脚本与数据分离）。
一个用例一个文件（P20）：便于按 id 管理、按变化增量重生成。

运行（推荐走 cli：自带资源预检 + run-id 隔离的日志/报告）:
  python -m framework.cli run --workers 2                 # 全量
  python -m framework.cli run --debug --case ai_在合同列表页面的搜索框输入_合同1_然后点击搜索_074348        # 只调试这一条
裸跑 pytest（未设 HYBRID_RUN_ID 时日志落 log/latest/）:
  pytest scripts/generated/manual/ai_在合同列表页面的搜索框输入_合同1_然后点击搜索_074348.py -v
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

def test_ai_在合同列表页面的搜索框输入_合同1_然后点击搜索_074348(page, ctx):
    """在合同列表页面的搜索框输入'合同1'，然后点击搜索按钮查看结果。"""
    _CURRENT_LOG["case_id"] = "ai_在合同列表页面的搜索框输入_合同1_然后点击搜索_074348"
    _goto(page, 'http://localhost:8000')
    _log(page, "场景开始", f"case=ai_在合同列表页面的搜索框输入_合同1_然后点击搜索_074348")

    # step 1: 打开演示系统登录页，出现『演示系统登录』标题与角色账号表格
    _goto(page, 'http://localhost:8000')
    _log(page, "goto", f"打开演示系统登录页，出现『演示系统登录』标题与角色账号表格")

    # step 2: 点击角色账号表格中『合同管理员』一行的『用这个账号填入』按钮，自动填充账号密码
    _act_row(page, '用这个账号填入', 1, op='click')
    _log(page, "click", f"点击角色账号表格中『合同管理员』一行的『用这个账号填入』按钮，自动填充账号密码")

    # step 3: 点击登录按钮，进入系统主界面
    _act(page, "click", semantic='登_录', primary=lambda p: p.locator("#btn-login"))
    _log(page, "click", f"点击登录按钮，进入系统主界面")
    _assert_text(page, _data('expect_0', ctx), '确认登录成功，页面出现合同模块入口')

