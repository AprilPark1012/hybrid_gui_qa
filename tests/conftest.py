"""pytest 全局夹具：把 `tests/_helpers` 补进 sys.path。

为什么需要它（2026-10-07）：
  按「9 个框架特性」重组 tests/ 后，公共模块（artifacts / repo_files / demo_freshness /
  testid_policy）从 tests/_helpers/ 移到了 tests/_helpers/，而各特性夹下的判据用的是
  平铺导入（`import repo_files`）—— 在这里统一补一次路径，避免每个判据各写一份 sys.path。

注意：本文件只对 **pytest 收集** 生效；`tests/**/verify_*.py` 是独立脚本（直接 python 执行），
不经过 conftest，它们自己的 sys.path 处理见各自文件头部。
"""
import sys
from pathlib import Path

# 用显式常量命名（`_TESTS_DIR` 含 "TESTS_DIR" 字样 ⇒ test_path_join_contract 能识别左侧已带容器层）
_TESTS_DIR = Path(__file__).resolve().parent        # = tests/
_HELPERS = _TESTS_DIR / "_helpers"
if str(_HELPERS) not in sys.path:
    sys.path.insert(0, str(_HELPERS))
