"""仓库内的路径 / 解释器定位 —— **唯一入口**。

[!] 为什么需要这个模块（2026-10-29 AprilPark1012 Windows 实测）：
    「找本仓库 venv 的解释器」这件事在仓库里被写了 **3 份**，而且都只认 POSIX：

        tests/_runner/run_verifications.py:112   -> 认得 Windows（对的，唯一正确的一份）
        tests/特性1-混合链路/test_offline_chain_python.py:125  -> 只认 .venv/bin/python
        tests/特性7-并发与资源安全/verify_slow_target.py:44    -> 只认 .venv/bin/python
        tests/特性8-离线回放/verify_offline_chain_deps.py:99   -> 只认 .venv/bin/python

    Windows 的 venv 布局是 `.venv\\Scripts\\python.exe`（**没有 bin/ 目录**），
    于是：
      * 判据 `test_probe_deps_on_repo_venv_if_present` 在 Windows 上**永远 skip**
        （实测：用户机器 6 skipped，本机 3 skipped，多出来的第 1 条就是它）；
      * 两个 `verify_*.py` 在现场会拿不到解释器（一个退回系统 python -> 依赖缺失；
        一个直接拿到不存在的路径 -> 跑不起来）。

    口径：**一处实现，四处引用**。以后要支持别的平台（conda / uv / 嵌入式），只改这里。
"""
from __future__ import annotations

import sys
from pathlib import Path

__all__ = ["venv_python_or_none", "venv_python"]

#: venv 解释器的候选相对路径，**按优先级**排列。
#:   Windows:  .venv/Scripts/python.exe
#:   POSIX:    .venv/bin/python3  然后  .venv/bin/python
_VENV_CANDIDATES: tuple[tuple[str, ...], ...] = (
    (".venv", "Scripts", "python.exe"),
    (".venv", "bin", "python3"),
    (".venv", "bin", "python"),
)


def venv_python_or_none(repo: str | Path) -> Path | None:
    """仓库 venv 的解释器路径；**没有 venv 就返回 None**（不退回 sys.executable）。

    需要区分「没有 venv」和「有 venv」时用这个 —— 例如判据要如实 SKIP。
    这是本项目「拿不到就降级为等效可用，或如实 SKIP，绝不把读不到当成通过」的落地。
    """
    root = Path(repo)
    for parts in _VENV_CANDIDATES:
        cand = root.joinpath(*parts)
        if cand.is_file():          # is_file 而不是 exists：目录同名不算找到了解释器
            return cand
    return None


def venv_python(repo: str | Path) -> str:
    """仓库 venv 的解释器路径；**找不到就退回当前解释器**（不让脚本直接崩）。

    需要「尽力跑起来」的场合用它（脚本 / 工具入口）。
    [!] 退回 sys.executable 意味着**可能不在 venv 里**（依赖可能缺失）——
        调用方若对此敏感，改用 `venv_python_or_none()` 并自己决定 skip / 报错。
    """
    found = venv_python_or_none(repo)
    if found is not None:
        return str(found)
    return sys.executable or "python3"
