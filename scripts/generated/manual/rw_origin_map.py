"""hybrid_gui_qa 用例模块：rw_origin_map（场景 manual）—— 由 cases/manual/rw_origin_map.json 自动生成。

**不要手改本文件**：改用例后重跑 generate 会覆盖它。要改行为 → 改用例 json / 场景 yml。
数据抽离在 scripts/datasets/rw_origin_map.json（脚本与数据分离）。
一个用例一个文件（P20）：便于按 id 管理、按变化增量重生成。

运行（推荐走 cli：自带资源预检 + run-id 隔离的日志/报告）:
  python -m framework.cli run --workers 2                 # 全量
  python -m framework.cli run --debug --case rw_origin_map        # 只调试这一条
裸跑 pytest（未设 HYBRID_RUN_ID 时日志落 log/latest/）:
  pytest scripts/generated/manual/rw_origin_map.py -v
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

def test_rw_origin_map(page, ctx):
    """跨 origin：HYBRID_ORIGIN_MAP 把 order 指到 8002（换环境只改一处）"""
    _CURRENT_LOG["case_id"] = "rw_origin_map"
    _goto(page, 'http://localhost:8000')
    _log(page, "场景开始", f"case=rw_origin_map")

    # step 1: 打开订单系统（生成期是 8001）
    _goto(page, _data('goto_0', ctx), 'order')
    _log(page, "goto", f"打开订单系统（生成期是 8001）")
    _assert_url(page, _data('expect_0', ctx), '按映射落到 8002（模拟「订单系统换到另一台机器」）')

