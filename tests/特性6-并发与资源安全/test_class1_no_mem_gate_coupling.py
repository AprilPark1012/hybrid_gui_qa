"""一类自测不许被「二类的资源闸门」支配（L19 · 2026-09-28）。

起因（真实恒定假红，会毁掉一类红灯的可信度）：
  `test_runner_smoke.py::test_runner_runs_a_real_script` 为了「真跑一次二类 runner」，
  调 `tests/_runner/run_verifications.py --only verify_html_sync`；而那个入口**进门先过内存闸门**
  （默认 550MB，`--min-mem` / `VERIFY_MIN_MEM_MB` 可覆盖）⇒ 本机长期多会话共存（网关 + CLI + LSP，
  MemAvailable 常年 280~470MB）时恒 `SKIP exit 3` ⇒ 一类里那条断言 `returncode == 0` **必红**。
  而它点的 `verify_html_sync` 是纯文件比对（零浏览器 / 零内存开销），单跑 `exit 0` 全绿
  ⇒ 闸门拦住的**不是它要防的东西** ⇒ 违反 R7-a「一类秒级、刻意与 demo/浏览器解耦」。

口径（本判据守的规则）：
  一类里**真跑二类 runner** 的调用，必须**显式声明内存闸门策略**（`--min-mem <n>`，或同文件设
  env `VERIFY_MIN_MEM_MB`）。跑的脚本不吃内存就写 `--min-mem 0`（= 明确「这个入口别按内存拦我」）。
  不许继承默认 550MB 阈值 —— 那等于把「这台机器此刻有多少空闲内存」变成一类的红绿条件。

覆盖边界（诚实标注，别以为它已覆盖全部形态）：
  ① 静态检查只覆盖「`--only <脚本>` 真跑」这一形态（含经本文件转发函数 `def xxx(args)` 发出的调用）；
     将来若出现「不带 --only 的全量真跑」等其它执行形态，本条要同步扩。
  ② `--list` 分支在内存闸门**之前**返回（runner 源码 main 里 `if args.list: … return 0` 早于闸门比较）
     ⇒ 只列清单的调用不需要声明，本判据放行。
  ③ 同文件出现 `VERIFY_MIN_MEM_MB` 即视为「已声明」（宁漏不误伤：静态看不出 env 是否真传给了子进程）。

跑法（秒级；只真跑一个纯离线脚本）：
    python -m pytest tests/特性6-并发与资源安全/test_class1_no_mem_gate_coupling.py -q
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
FEATURE = REPO / "tests" / "_runner"
RUNNER = FEATURE / "run_verifications.py"

# 「以列表字面量作实参的子进程调用」：_run([...]) / subprocess.run([...]) / _run_runner([...])
_CALL_ARGS = re.compile(r"\w+\s*\(\s*(\[[^\[\]]*\])", re.S)
_FWD_DEF = re.compile(r"def\s+(\w+)\s*\(\s*args\s*\)")
_ONLY = re.compile(r"['\"]--only['\"]")     # 精确匹配：`"--onlyy"`（故意的错参数负向用例）不算
_LIST = re.compile(r"['\"]--list['\"]")
_RUNNER_REFS = ("RUNNER", "run_verifications")


def _runner_call_args(src: str) -> list[str]:
    """抽出本文件里「真跑二类 runner」的调用实参（含经转发函数发出的那些）。"""
    out = [a for a in _CALL_ARGS.findall(src) if any(r in a for r in _RUNNER_REFS)]
    fwd = [n for n in _FWD_DEF.findall(src)
           if re.search(r"run_verifications", src.split(f"def {n}")[1].split("\ndef ")[0] or "")]
    for name in fwd:
        for m in re.finditer(re.escape(name) + r"\s*\(\s*(\[[^\[\]]*\])", src, re.S):
            out.append(m.group(1))
    return out


def undeclared_gate_calls(src: str) -> list[str]:
    """返回「真跑二类、但没声明内存闸门策略」的调用实参（人话列表，判据与负向自证共用）。"""
    if "VERIFY_MIN_MEM_MB" in src:
        return []
    bad: list[str] = []
    for args in _runner_call_args(src):
        if _LIST.search(args):          # 只列清单 ⇒ 闸门之前就返回了 ⇒ 不要求声明
            continue
        if not _ONLY.search(args):      # 覆盖边界①：只查「--only <脚本>」这种真跑形态
            continue
        if "--min-mem" in args:
            continue
        bad.append(" ".join(args.split()))
    return bad


# ---------- ① 全仓扫描：一类里不许有「没声明闸门策略的真跑」 ----------
def test_no_undeclared_memory_gate_in_framework_tests():
    bad: list[str] = []
    for f in sorted(HERE.glob("test_*.py")):
        for call in undeclared_gate_calls(f.read_text(encoding="utf-8")):
            bad.append(f"{f.name}: {call}")
    assert not bad, (
        "一类里出现了「真跑二类 runner、却没声明内存闸门策略」的调用 —— 这会让一类在本机恒定假红"
        "（MemAvailable 常年 <550MB ⇒ SKIP exit 3），违反 R7-a。改法：给调用加 `--min-mem 0`"
        "（不吃内存的脚本）或在本文件显式设 env `VERIFY_MIN_MEM_MB`。\n  - " + "\n  - ".join(bad))


# ---------- ② 机制：闸门必须「可被 0 关闭」（否则上面的改法会失效） ----------
def test_gate_threshold_is_closable_by_zero():
    src = RUNNER.read_text(encoding="utf-8")
    assert 'os.environ.get("VERIFY_MIN_MEM_MB"' in src, \
        "runner 的 --min-mem 默认值不再取自 env VERIFY_MIN_MEM_MB ⇒ 本判据的声明方式会失效"
    assert "mb < args.min_mem" in src, \
        "找不到「MemAvailable < 阈值」这段比较式 ⇒ 闸门实现变了，请同步本判据与修法口径"


# ---------- ③ 行为：关掉闸门后真跑必须 exit 0（不依赖机器内存多少） ----------
def test_real_run_with_gate_closed_exits_zero():
    """`--min-mem 0 --no-demo` 真跑一个纯离线脚本 ⇒ exit 0。

    这条**不依赖**机器有多少空闲内存（闸门已关），也不起 demo（`--no-demo`）——
    demo 新鲜度那条真实路径由 `test_runner_smoke.py` 自己覆盖，两者分工明确。
    """
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    p = subprocess.run([sys.executable, "tests/_runner/run_verifications.py",
                        "--only", "verify_html_sync", "--min-mem", "0", "--no-demo"],
                       cwd=str(REPO), env=env, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=180)
    out = (p.stdout or "") + (p.stderr or "")
    assert p.returncode == 0, (
        f"关掉闸门后 runner 仍非 0（exit {p.returncode}）：\n" + "\n".join(out.strip().splitlines()[-10:]))


# ---------- ④ 判据自身的负向自证（防恒真 / 防恒红） ----------
_FIXTURE_MISSING = """
def _run(args, timeout=300):
    return subprocess.run([sys.executable, *args], cwd=str(REPO))

RUNNER = FEATURE / "run_verifications.py"

def test_x():
    p = _run([str(RUNNER.relative_to(REPO)), "--only", FAST_OFFLINE])
"""

_FIXTURE_DECLARED = """
def _run(args, timeout=300):
    return subprocess.run([sys.executable, *args], cwd=str(REPO))

RUNNER = FEATURE / "run_verifications.py"

def test_x():
    p = _run([str(RUNNER.relative_to(REPO)), "--only", FAST_OFFLINE, "--min-mem", "0"])
"""

_FIXTURE_LIST_ONLY = """
RUNNER = FEATURE / "run_verifications.py"

def test_x():
    p = subprocess.run([sys.executable, str(RUNNER.relative_to(REPO)), "--list"])
"""


def test_negative_undeclared_call_is_flagged():
    """少一个 `--min-mem` 就必须被抓（否则这条判据等于没写）。"""
    bad = undeclared_gate_calls(_FIXTURE_MISSING)
    assert bad, "没声明闸门策略的调用没被抓出来 ⇒ 判据恒真（假绿）"


def test_negative_declared_call_passes():
    """写了 `--min-mem 0` 就必须放行（防判据写成恒红、逼人绕过）。"""
    assert undeclared_gate_calls(_FIXTURE_DECLARED) == []


def test_negative_list_only_call_is_allowed():
    """只 `--list`（闸门之前返回）不该被要求声明 —— 否则会误伤。"""
    assert undeclared_gate_calls(_FIXTURE_LIST_ONLY) == []
