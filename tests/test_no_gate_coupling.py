# -*- coding: utf-8 -*-
"""R1 判据固化：敏感词门禁必须与框架代码**解耦**（仓库内零引用）。

项目要求（2026-09-19）：「敏感词门禁和框架代码要解耦，pre_commit 和 pre_push 要扫敏感词跑这个门禁」。

设计口径（为什么是"零引用"）：
- 门禁工具 / 词表 / 规则住在 skill `public-repo-privacy-hygiene`（**仓库外**）⇒ 仓库零痕迹，工具可复用到任何仓库；
- 三个钩子在 `.git/hooks/`（**永不入库**，由 `install_hooks.sh` 按绝对路径安装）
  ⇒ 因此仓库里**任何**对门禁路径的引用都是耦合复发，本测试直接判红。

例外（已声明、按"历史日志不改"口径）：`releases/RELEASE_NOTES_*.md` —— 日志记录当时发生过什么，
不是框架代码，允许出现历史描述。

⚠️ 两个自己踩过的坑（都写清楚，别让下一个人再踩）：
1. **必须豁免本文件自身**：本文件里必然写满那些禁词（它就是判据本身）。老版本漏了这条，
   而当时文件**还没被 git 跟踪** ⇒ `git ls-files` 扫不到它 ⇒ **假绿**；提交后才暴露。
   ⇒ 教训：**用 `git ls-files` 做扫描的判据，在文件入库前会漏扫自己 —— 新增判据要按「提交后」的状态验一次**。
2. 扫描范围是「被跟踪文件」而非工作区：未跟踪的临时文件不在判据内（这是有意的，避免误伤）。
"""

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# 出现即视为耦合（skill 路径 / 门禁工具 / 词表 / 钩子安装器）
FORBIDDEN = (
    "hermes/skills",
    "public-repo-privacy-hygiene",
    "privacy_gate",
    "privacy_words",
    "install_hooks",
)

# 允许的历史日志（非代码）
EXEMPT_PREFIXES = ("releases/RELEASE_NOTES_",)

# 本文件自身：判据里必然含这些禁词 ⇒ 必须豁免（否则提交后必红，见文件头坑 1）
SELF = "tests/test_no_gate_coupling.py"


def _tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files"], cwd=REPO, capture_output=True, encoding="utf-8", errors="replace"
    )
    return [p for p in (out.stdout or "").split("\n") if p.strip()]


def test_repo_has_zero_gate_references():
    """仓库里不得出现门禁/skill 路径引用（R1 判据）。"""
    files = [f for f in _tracked_files()
             if not f.startswith(EXEMPT_PREFIXES) and f != SELF]
    assert files, "git ls-files 返回空 —— 测试前提不成立"

    violations = []
    for rel in files:
        p = REPO / rel
        if not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # 二进制 / 读不了：跳过（门禁的二进制扫描是另一层的事）
        for ln, line in enumerate(text.split("\n"), 1):
            for word in FORBIDDEN:
                if word in line:
                    violations.append(f"{rel}:{ln}  含 «{word}»  →  {line.strip()[:90]}")

    assert not violations, (
        "仓库与门禁耦合了（门禁应住 skill、仓库零痕迹）：\n  " + "\n  ".join(violations[:20])
    )


def test_hooks_are_not_tracked():
    """三个钩子必须只在 .git/hooks/（永不入库）——被跟踪即为耦合 + 泄本机路径。"""
    tracked = _tracked_files()
    leaked = [f for f in tracked if f.startswith(".git/hooks/") or Path(f).name in
              ("pre-commit", "commit-msg", "pre-push") and "/" not in f]
    assert not leaked, f"钩子被跟踪进仓库了：{leaked}"
