"""取「仓库文件清单」的唯一入口 —— git 优先，非 git 环境**等效降级**（2026-09-22）。

为什么需要它（AprilPark1012 2026-09-22 本地 Windows 验收实测出来的真 bug）：
R1 判据（`tests/frameworkTest/test_no_gate_coupling.py`）与 R9 判据（`tests/frameworkTest/test_no_stale_paths.py`）
原先各自直接调 `git ls-files`。而**交付包解压目录不是 git 仓库** ⇒ 在那里
`git ls-files` 要么 exit 128（`check=True` 直接 CalledProcessError），要么返回空清单
（判据自报「测试前提不成立」）⇒ 两条判据必红。
可它们要判的事（「仓库里有没有指向旧位置 / 门禁路径的引用」）**与有没有 .git 毫无关系** ——
团队用户按 README 一路跑下来，看到的是「框架自己的测试红了」，归因完全错位。

口径（MEMORY「开关开了就要好用」：受限环境降级为**等效可用**，不报错退出）：
- git 可用 ⇒ 沿用 git 口径 `ls-files --cached --others --exclude-standard`
  （**必须含未跟踪但未被忽略**：V8.0 实测过只扫已跟踪 ⇒「提交前全绿、刚提交就红」的假绿）；
- git 不可用（非仓库 / 没装 git）⇒ **等效降级**为文件树扫描：同一套排除规则（对齐 `.gitignore`）
  + 二进制粗判，判据照常执行；
- 无论走哪条路，都把**清单来源**写进断言消息 —— 免得下次有人对着「空清单」猜原因。

维护：排除清单与 `.gitignore` 保持同步；改 `.gitignore` 时顺手看一眼这里。
"""
from __future__ import annotations

import subprocess
from pathlib import Path

GIT_TIMEOUT_S = 30

# 与 .gitignore 对齐的排除目录（降级扫描时用；git 路径由 git 自己按 .gitignore 处理）
EXCLUDE_DIRS = frozenset({
    ".git", ".hg", ".svn", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".venv", "venv", "env", ".env", "virtualenv", ".virtualenv", "site-packages",
    ".tox", ".nox", ".eggs", "dist", "build", "node_modules",
    "log", "logs", "output", "tmp", ".cache", ".idea", ".vscode",
})

# 二进制 / 打包产物（判据只看文本，扫进来纯属浪费）
EXCLUDE_SUFFIXES = frozenset({
    ".pyc", ".pyo", ".pyd", ".so", ".dll", ".dylib", ".exe", ".bin",
    ".zip", ".tar", ".gz", ".tgz", ".whl", ".egg", ".7z", ".rar",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg", ".pdf",
    ".webm", ".mp4", ".mov", ".mp3", ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".db", ".sqlite", ".sqlite3", ".pkl", ".npy", ".parquet",
})

EXCLUDE_FILES = frozenset({".DS_Store", "Thumbs.db", ".gitignore"})


def _git_file_list(repo: Path) -> list[str] | None:
    """git 口径的文件清单；**任何形态的失败都返回 None**（由调用方降级，绝不抛）。"""
    try:
        r = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=str(repo), capture_output=True, timeout=GIT_TIMEOUT_S,
            text=True, encoding="utf-8", errors="replace",
        )
    except (OSError, subprocess.SubprocessError):
        return None                      # 没装 git / 进程起不来
    if r.returncode != 0:
        return None                      # 不是 git 仓库（exit 128）等
    return [p for p in r.stdout.splitlines() if p.strip()]


def _walk_file_list(repo: Path) -> list[str]:
    """降级口径：文件树扫描（排除第三方树 / 缓存 / 运行时证据 / 二进制）。"""
    out: list[str] = []
    for p in sorted(repo.rglob("*")):
        rel = p.relative_to(repo)
        if any(part in EXCLUDE_DIRS for part in rel.parts):
            continue
        if rel.name in EXCLUDE_FILES:
            continue
        if not p.is_file():
            continue
        if p.suffix.lower() in EXCLUDE_SUFFIXES:
            continue
        out.append(rel.as_posix())
    return out


def file_list(repo: Path) -> tuple[list[str], str]:
    """返回 (相对路径清单, 清单来源)。来源会进断言消息，便于一眼归因。"""
    listed = _git_file_list(repo)
    if listed is not None:
        return listed, "git ls-files --cached --others --exclude-standard（含未跟踪但不被忽略）"
    return _walk_file_list(repo), "文件树扫描（本目录不是 git 仓库或没装 git ⇒ 等效降级）"


def read_text_file(path: Path) -> str | None:
    """读文本；读不了 / 二进制 ⇒ None（由调用方决定跳过还是报错）。

    ⚠️ 名字故意不叫 `read_text`：仓内有一条 AST 判据（`test_utf8_io.py`）要求**所有** `.read_text()` 调用
    显式带 `encoding="utf-8"`；本函数把编码口径封在内部，用同名属性会让那条判据误报（实测踩过）。
    """
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if b"\0" in raw[:4096]:
        return None
    return raw.decode("utf-8", errors="replace")
