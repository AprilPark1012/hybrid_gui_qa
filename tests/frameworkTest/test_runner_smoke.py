"""二类 runner 的「能起来」冒烟判据（P19 搬迁回归 · 2026-09-23）。

**为什么要有它**（真实事故）：迁移 `tests/` → `tests/frameworkTest/` + `tests/featureTest/` 时，
`run_verifications.py` 里给子导入用的 `sys.path` 只插了 `tests/featureTest/`，
而共享辅助（`demo_freshness.py` 等）住在 `tests/frameworkTest/` ⇒
`import demo_freshness` 抛 `ModuleNotFoundError`，**整个二类 exit 1 起不来**。
一类当时**没抓住**它（一类判据自己把两个目录都插进了 sys.path ⇒ 环境比 runner 宽松），
属于典型「判据比现实宽松 ⇒ 假绿」。本判据用**子进程 + 干净环境**跑 runner 自己的 `--list`，
环境与真实调用一致 ⇒ 这类病当场红。

判据：
  ① `python tests/featureTest/run_verifications.py --list` 必须 **exit 0**（能起来、能列出脚本）
  ② 列出的脚本数 == `tests/featureTest/verify_*.py` 的实际数量（收录口径没漏）
  ③ 负向自证：把一个必然 import 失败的模块名喂进去 ⇒ 检查逻辑必须能报错（防「查什么都说好」）
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FEATURE = REPO / "tests" / "featureTest"
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
    """★核心：runner 用干净子进程**真跑一次**（走 _ensure_demo_fresh 这条真实路径）⇒ 必须 exit 0。

    ⚠️ 用 `--list` 测不出来：那条分支在 demo 检查**之前**就返回了（2026-09-23 实测踩到 ——
    第一版判据就是这么写成假绿的）。所以这里用 `--only <最快脚本>` 真跑一遍。
    """
    assert RUNNER.is_file(), f"缺 {RUNNER}"
    p = _run([str(RUNNER.relative_to(REPO)), "--only", FAST_OFFLINE])
    out = (p.stdout or "") + (p.stderr or "")
    assert p.returncode == 0, (
        f"runner --only {FAST_OFFLINE} 起不来/跑不过（exit {p.returncode}）—— "
        "多半是 sys.path 没把共享辅助目录（tests/frameworkTest/）带上：\n"
        + "\n".join(out.strip().splitlines()[-12:]))


def test_runner_lists_every_verify_script():
    """收录口径：`--list` 必须列出 tests/featureTest/ 下的**每一个** verify_*.py（不许手写清单漏项）。"""
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
    """契约：runner 的 sys.path 必须同时含 tests/featureTest/ 与 tests/frameworkTest/（辅助住后者）。"""
    text = RUNNER.read_text(encoding="utf-8")
    assert re.search(r"sys\.path\.insert\([^)]*frameworkTest", text), (
        "runner 里没有 `sys.path.insert(...frameworkTest...)` —— 共享辅助（demo_freshness 等）住在 "
        "tests/frameworkTest/，不插进 sys.path 就会 ModuleNotFoundError（2026-09-23 实测踩到）。"
        "⚠️ 只断言'文本里出现过 frameworkTest 字样'是不够的：docstring 里就有，会假绿。")
