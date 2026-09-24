"""scripts/generated 的 conftest —— 只做转发（P20：消除两个 conftest 的 import 歧义）。

辅助函数都在同目录的 _harness.py 里；这里只负责把夹具暴露给 pytest。
"""
import sys as _sys
from pathlib import Path as _Path

# 让同目录的 _harness 可被各用例模块显式 import（不依赖 pytest 的路径插入策略）
_sys.path.insert(0, str(_Path(__file__).resolve().parent))

from _harness import *  # noqa: F401,F403  —— 夹具靠它暴露
from _harness import (  # noqa: F401  —— 显式列名，防止 import * 漏掉下划线名
    _case_watchdog,
    _reset_target_data,
    _dump_heals_at_session_end,
    _pool,
    page,
    ctx,
)


# P20：用例模块按 **case_id 命名**（ai_xxx_160019.py / assert_kinds_todo.py），
# 不匹配 pytest 默认的 test_*.py ⇒ 必须有这个钩子，否则「一条都收集不到」✗
# （这正是 P20 判据 test_generated_pytest_discovery 当场抓出来的问题）
def pytest_collect_file(file_path, parent):
    import pytest as _pt
    if file_path.suffix == ".py" and file_path.name not in ("conftest.py", "_harness.py"):
        return _pt.Module.from_parent(parent, path=file_path)
    return None
