"""统一 UTF-8 —— 本项目所有「跨进程 / 落盘」文本 IO 的唯一口径。

为什么需要这个模块（2026-09-13 实测复盘）
----------------------------------------
AprilPark1012在 Windows 上跑 `explore --ai`（默认带 --verify），报：

    UnicodeDecodeError: 'gbk' codec can't decode byte 0xbb in position 13:
    illegal multibyte sequence

根因（已在本机用 zh_CN.gbk locale 复现到字节级）：
`cli.py::_verify_cases` 里 `subprocess.run(..., capture_output=True, text=True)`
**没有显式指定 encoding** ⇒ Python 用「系统默认编码」解码子进程输出（中文 Windows = cp936/gbk），
而子进程（`python -m framework.cli generate` / `pytest`）按 **UTF-8** 输出
（常见触发：环境里有 PYTHONUTF8=1 / PYTHONIOENCODING=utf-8、控制台代码页 65001、
或 Python 3.15+ 默认开启 UTF-8 模式）。两端口径不一致 → 只要输出里有中文就可能炸。

  · 复现证据 A（本机）：父进程 GBK + 子进程 UTF-8 →
    `'gbk' codec can't decode byte 0x92 in position 61`（同一 codec / 同一 message）
  · 复现证据 B（精确对位）：子进程第一行 `[generate] 读 cases/ …`，
    `[generate] ` 占 11 字节，`读` = E8 AF BB ⇒ **第 13 字节正是 0xbb**，
    与AprilPark1012报错逐字一致。

还有两处同源坑（一并收口）：
  · **子进程侧**：Windows 控制台是 cp936 时，`✓ / ❌ / ⚠️` 这些字符会
    UnicodeEncodeError（代码跑到一半崩，比报错更伤人）；
  · **pytest 自己的 fd 捕获**把输出写回真实 fd 时**硬编码 UTF-8**：
    `_pytest/capture.py`: `os.write(self.targetfd_save, data.encode("utf-8"))`
    （源码里就写着 `# XXX use encoding of original stream`）⇒ 父进程按 locale 解码必中招。

本项目约定（唯一规则）：
    **凡是跨进程（subprocess）或落盘的文本，一律显式 UTF-8；绝不依赖系统默认编码。**
    · 父进程收子进程输出 → 用本模块的 `run_capture()`（内部 text+encoding="utf-8"+errors="replace"）；
    · 子进程输出中文 → 用本模块的 `utf8_env()` 注入 PYTHONUTF8 / PYTHONIOENCODING；
    · 自己进程的 stdout/stderr → `force_stdio()`（顺带把 Windows 控制台代码页改成 65001）；
    · 生成的测试脚本（scripts/）自带等价的自举代码，裸跑 pytest 也不炸。

为什么 `errors="replace"`：验证闸门（--verify）不应该因为一个编码字节就整条崩掉 ——
看不懂的字节降级成 U+FFFD 并继续，总比 traceback 把「用例到底过没过」这个关键信息盖掉好。
"""
from __future__ import annotations

import os
import subprocess
import sys

# 子进程侧：让 python 子进程按 UTF-8 读 stdin/stdout/stderr（PYTHONIOENCODING）
# 且文件 IO / 文件系统编码也用 UTF-8（PYTHONUTF8=1，即 -X utf8 模式）
UTF8_ENV: dict[str, str] = {
    "PYTHONUTF8": "1",
    "PYTHONIOENCODING": "utf-8",
}


def utf8_env(base: dict | None = None) -> dict:
    """在（可选）给定环境变量上强制叠加 UTF-8 子进程口径，返回新 dict（不改原对象）。"""
    env = dict(os.environ if base is None else base)
    env.update(UTF8_ENV)
    return env


def apply_env() -> None:
    """把 UTF-8 口径写进**本进程**的 os.environ ⇒ 之后所有子进程自动继承（含非 Python 子进程）。"""
    os.environ.update(UTF8_ENV)


def force_stdio(on_windows_console: bool = True) -> None:
    """把本进程的 stdout/stderr 统一到 UTF-8（顺便把 Windows 控制台代码页设为 65001）。

    幂等、永不抛错：任何一步失败都静默跳过（显示层问题不该中断测试链路）。
    """
    apply_env()
    for s in (sys.stdout, sys.stderr):
        try:
            if s is None or not hasattr(s, "reconfigure"):
                continue
            s.fileno()          # 真实文件/控制台才有 fileno；pytest 的捕获替身会抛 → 跳过
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if on_windows_console and sys.platform == "win32":
        # 控制台代码页不改的话：我们按 UTF-8 写出的中文会显示成乱码（cp936 解释 UTF-8 字节）
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        except Exception:
            pass


def fs_encoding_warning(fsenc: str | None = None) -> str | None:
    """文件系统编码不是 UTF-8 时返回一句**大声**的提醒；正常（UTF-8）返回 None。

    为什么：文件名是按「文件系统编码」落地成字节的。中文 Windows / GBK locale 下该编码是
    cp936/gbk ⇒ 生成的中文用例名（`ai_在合同列表页…`）会落成 GBK 字节名，在 UTF-8 的仓库里
    就是乱码甚至非法字节名（2026-09-14 实测踩到：`scripts/datasets/` 留过一个 GBK 名 orphan，
    连工具读文件名都会 surrogate 报错）。
    ⚠️ 运行期**改不了**（解释器启动时已固定）⇒ 只能提醒 + 建议 `PYTHONUTF8=1` 重跑。
    """
    enc_raw = fsenc if fsenc is not None else (sys.getfilesystemencoding() or "")
    norm = str(enc_raw).lower().replace("-", "").replace("_", "")
    if norm in ("utf8", "utf8mb4"):
        return None
    return (f"⚠️ 文件系统编码是 {enc_raw}（不是 UTF-8）：中文文件名会落成 {enc_raw} 字节名，"
            f"在 UTF-8 仓库里就是乱码/非法字节名。请用 `PYTHONUTF8=1` 重新执行本命令。")


def run_capture(cmd: list[str], *, cwd=None, env: dict | None = None,
                timeout: float | None = None, **kw) -> subprocess.CompletedProcess:
    """执行子进程并**按 UTF-8 解码**其输出（替代裸 `subprocess.run(..., text=True)`）。

    关键：显式 `encoding="utf-8"` + `errors="replace"` ⇒ 与子进程（utf8_env 已保证 UTF-8）口径一致，
    且不受父进程 locale 影响（这正是 gbk 事故的根因）。
    """
    kw.pop("text", None)
    kw.pop("encoding", None)
    kw.pop("errors", None)
    kw.pop("universal_newlines", None)
    kw.pop("capture_output", None)
    kw.pop("stdout", None)
    kw.pop("stderr", None)
    return subprocess.run(
        cmd, cwd=cwd, env=utf8_env(env), timeout=timeout,
        capture_output=True, text=True, encoding="utf-8", errors="replace", **kw,
    )
