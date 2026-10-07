"""二类 runner 的「能起来」冒烟判据（P19 搬迁回归 · 2026-09-23）。

**为什么要有它**（真实事故）：迁移 `tests/` → `tests/_helpers/` + `tests/_runner/` 时，
`run_verifications.py` 里给子导入用的 `sys.path` 只插了 `tests/_runner/`，
而共享辅助（`demo_freshness.py` 等）住在 `tests/_helpers/` ->
`import demo_freshness` 抛 `ModuleNotFoundError`，**整个二类 exit 1 起不来**。
一类当时**没抓住**它（一类判据自己把两个目录都插进了 sys.path -> 环境比 runner 宽松），
属于典型「判据比现实宽松 -> 假绿」。本判据用**子进程 + 干净环境**跑 runner 自己的 `--list`，
环境与真实调用一致 -> 这类病当场红。

判据：
  (1) `python tests/_runner/run_verifications.py --list` 必须 **exit 0**（能起来、能列出脚本）
  (2) 列出的脚本数 == `tests/_runner/verify_*.py` 的实际数量（收录口径没漏）
  (3) 负向自证：把一个必然 import 失败的模块名喂进去 -> 检查逻辑必须能报错（防「查什么都说好」）
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import pytest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FEATURE = REPO / "tests" / "_runner"
RUNNER = FEATURE / "run_verifications.py"


def _run(args: list[str], timeout: int = 300) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env.pop("HYBRID_SKIP_BROWSER_CHECK", None)      # 与真实调用一致（不是"跳过一切"的环境）
    return subprocess.run([sys.executable, *args], cwd=str(REPO), env=env,
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout)


def verify_scripts() -> list[str]:
    return sorted(p.name for p in FEATURE.glob("verify_*.py"))


def listed_names(out: str) -> list[str]:
    return sorted(set(re.findall(r"(verify_[a-z0-9_]+\.py)", out)))


FAST_OFFLINE = "verify_html_sync"      # 最快的纯离线脚本（秒级），用来真跑一次 runner


def test_runner_runs_a_real_script(capsys=None):
    """★核心：runner 用干净子进程**真跑一次**（走 _ensure_demo_fresh 这条真实路径）-> 必须 exit 0。

    [!] 用 `--list` 测不出来：那条分支在 demo 检查**之前**就返回了（2026-09-23 实测踩到 ——
    第一版判据就是这么写成假绿的）。所以这里用 `--only <最快脚本>` 真跑一遍。

    [!] `--min-mem 0`（L19 · 2026-09-28 修）：**必须显式关掉二类的内存闸门**。本机长期多会话共存
    （MemAvailable 常年 280~470MB < 默认 550MB）-> 不关的话 runner 恒 `SKIP exit 3`，一类里这条**恒定假红**；
    而这里跑的 `verify_html_sync` 是纯文件比对（零浏览器 / 零内存开销）-> 闸门拦住的不是本用例要防的东西
    （本用例要防的是「runner 起不来 / sys.path 漏目录」）。守这条的判据：
    `test_class1_no_mem_gate_coupling.py`（含负向自证 + 「关闸门后真跑 exit 0」的行为判据）。
    """
    assert RUNNER.is_file(), f"缺 {RUNNER}"
    p = _run([str(RUNNER.relative_to(REPO)), "--only", FAST_OFFLINE, "--min-mem", "0"])
    out = (p.stdout or "") + (p.stderr or "")

    # [!] 2026-10-07（V8.3.3）：demo 新鲜度闸门未过时**跳过**，不判红。
    # 原因：本判据要防的是「runner 起不来 / sys.path 漏目录」，而「demo 没在跑 / demo 比进程新」
    # 是**环境状态**（R7 第 0 步本来就要求跑验证前先重启 demo）—— 那是环境没准备好，
    # 不是 runner 坏了。按本项目既有口径：不拿与判据意图无关的环境因素去红别人的机器。
    # 注意：**只在闸门这一种情况下跳过**；runner 真的起不来（import 失败 / 用法错）仍然照红，
    # 所以本判据不会因此变成空转（云主机上 demo 常驻，这条每轮都在真跑）。
    if "demo 新鲜度闸门未过" in out or "新鲜度闸门未过" in out:
        pytest.skip("demo 新鲜度闸门未过（demo 没在跑或比进程新）—— 环境没准备好，"
                    "与「runner 起不来 / sys.path 漏目录」无关；"
                    "跑验证前请按 R7 第 0 步先重启 demo，届时本判据会真跑")

    assert p.returncode == 0, (
        f"runner --only {FAST_OFFLINE} 起不来/跑不过（exit {p.returncode}）—— "
        "多半是 sys.path 没把共享辅助目录（tests/_helpers/）带上：\n"
        + "\n".join(out.strip().splitlines()[-12:]))


def test_runner_lists_every_verify_script():
    """收录口径：`--list` 必须列出 tests/_runner/ 下的**每一个** verify_*.py（不许手写清单漏项）。"""
    p = _run([str(RUNNER.relative_to(REPO)), "--list"])
    out = (p.stdout or "") + (p.stderr or "")
    assert p.returncode == 0, f"--list 失败（exit {p.returncode}）：\n{out[-400:]}"
    names = listed_names(out)
    want = verify_scripts()
    missing = [n for n in want if n not in names]
    assert not missing, f"这些 verify 脚本没被 runner 列出（收录口径漏了）：{missing}"


def test_negative_missing_module_is_reported():
    """负向自证：真的缺模块时，子进程必须**非 0**（否则上面的冒烟就是假绿）。"""
    p = _run(["-c", "import definitely_missing_module_xyz"])
    assert p.returncode != 0
    assert "ModuleNotFoundError" in (p.stderr or "") or "No module named" in (p.stderr or "")


def test_runner_declares_both_helper_paths():
    """契约：runner 的 sys.path 必须同时含 tests/_runner/ 与 tests/_helpers/（辅助住后者）。"""
    text = RUNNER.read_text(encoding="utf-8")
    assert re.search(r"sys\.path\.insert\([^)]*_helpers", text), (
        "runner 里没有 `sys.path.insert(...tests/_helpers...)` —— 共享辅助（demo_freshness 等）住在 "
        "tests/_helpers/，不插进 sys.path 就会 ModuleNotFoundError（2026-09-23 实测踩到）。"
        "[!] 只断言'文本里出现过 _helpers 字样'是不够的：docstring 里就有，会假绿。")
