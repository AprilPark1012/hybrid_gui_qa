"""特性验证统一入口（R7 两类验证之②）—— **跨平台 Python 实现（唯一实现）**。

用法（Windows PowerShell / Linux / macOS 完全一致）：
    python tests/run_verifications.py                  # 全量（需要 demo：脚本会自动起/停）
    python tests/run_verifications.py --only ambiguity # 只跑名字含该子串的
    python tests/run_verifications.py --no-demo        # 不起 demo（只跑自包含的验证）
    python tests/run_verifications.py --list           # 只列出会跑哪些
    python tests/run_verifications.py --stream         # 实时打印每个子进程的输出（默认只打尾部摘要）
    python tests/run_verifications.py --min-mem 400    # 覆盖内存阈值（默认 550MB，也可用 VERIFY_MIN_MEM_MB）

退出码：**0** = 全通过（跳过项会如实列出）· **1** = 有失败 · **2** = 环境 / 用法问题 · **3** = 内存不足整体 SKIP。
⭐ 口径：**SKIP 不是绿灯** —— 内存不够时如实报 3，绝不假装通过。

为什么要有这个 Python 版（2026-09-22 使用者现场反馈）：
`bash tests/run_verifications.sh` 在 Windows PowerShell 里**根本跑不起来**
（`无法将"bash"项识别为 cmdlet…` —— 机器上没装 Git Bash / WSL）
⇒ 二类验证对团队里的 Windows 用户等于**不存在**，而本框架的现场恰恰是 Windows。
⇒ 口径：**唯一实现 = 本文件**；`tests/run_verifications.sh` 退化成薄包装（转发到这里），
   避免「改了一处忘了另一处」的静默不一致（这类漂移在本项目已经踩过）。

跨平台要点（都是实测口径，别改回去）：
- 解释器：优先 `<repo>/.venv/{Scripts,bin}/python*`，找不到退回 `sys.executable`，并在头部**打印用的是谁**；
- 内存：Linux 读 `/proc/meminfo`；Windows 走 `GlobalMemoryStatusEx`（ctypes，纯标准库）；
  **两条都拿不到 ⇒ 如实打印「内存未测」并继续**（不据此 SKIP、也不假装测过）；
- demo 启停：`subprocess.Popen` + 平台各自的后台标志（Windows `DETACHED_PROCESS`，POSIX `start_new_session`）；
  探活用 urllib（与 `tests/demo_freshness.py` 同一口径）；
- 时间戳按**北京时间**打印（服务器可能在 UTC）；Windows 上没有 `tzset` 时退回本机本地时间。
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import threading
import time
import urllib.request
from collections import deque
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_MIN_MEM_MB = 550
PER_SCRIPT_TIMEOUT_S = 600
TAIL_LINES = 12
DEMO_LOG = REPO / "log" / "_run_verifications_demo.log"
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200


# ---------------- 基础工具 ----------------

def _now_cst() -> str:
    """北京时间的时间串（服务器可能在 UTC；Windows 上没有 tzset ⇒ 退回本地时间）。"""
    if hasattr(time, "tzset"):
        saved = os.environ.get("TZ")
        os.environ["TZ"] = "Asia/Shanghai"
        time.tzset()
        try:
            return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        finally:
            if saved is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = saved
            time.tzset()
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())


def _venv_python(repo: Path = REPO) -> str:
    """找 venv 解释器（跨平台）；找不到退回当前解释器。"""
    for c in (repo / ".venv" / "Scripts" / "python.exe",      # Windows
              repo / ".venv" / "bin" / "python3",             # POSIX
              repo / ".venv" / "bin" / "python"):
        if c.exists():
            return str(c)
    return sys.executable or "python3"


def _mem_available_mb_proc() -> int | None:
    try:
        with open("/proc/meminfo", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("MemAvailable"):
                    return int(line.split()[1]) // 1024
    except (OSError, ValueError, IndexError):
        return None
    return None


def _mem_available_mb_windows() -> int | None:
    """Windows：GlobalMemoryStatusEx（纯标准库，不需要 psutil）。"""
    try:
        import ctypes

        class _MemStatus(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

        st = _MemStatus()
        st.dwLength = ctypes.sizeof(_MemStatus)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
            return None
        return int(st.ullAvailPhys // (1024 * 1024))
    except Exception:
        return None


def mem_available_mb() -> int | None:
    """可用内存（MB）；**拿不到返回 None**（调用方不许据此假装测过）。"""
    return _mem_available_mb_windows() if os.name == "nt" else _mem_available_mb_proc()


def demo_up(base: str, timeout: float = 3.0) -> bool:
    try:
        urllib.request.urlopen(base.rstrip("/") + "/api/health", timeout=timeout)
        return True
    except Exception:
        return False


def start_demo(python: str, base: str, log_path: Path = DEMO_LOG) -> subprocess.Popen | None:
    """后台起 demo 并等到就绪；成功返回句柄（本脚本负责收尾杀掉），失败返回 None。"""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(log_path, "ab")
    kw = {"cwd": str(REPO), "stdout": fh, "stderr": subprocess.STDOUT}
    if os.name == "nt":
        kw["creationflags"] = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    else:
        kw["start_new_session"] = True
    try:
        proc = subprocess.Popen([python, "-m", "demo.app"], **kw)
    except OSError as e:
        print(f"  ❌ demo 起不来：{e}（日志 {log_path}）")
        return None
    for _ in range(20):
        if demo_up(base):
            return proc
        time.sleep(1)
    proc.kill()
    print(f"  ❌ demo 起不来或未就绪（见 {log_path}）")
    return None


# ---------------- 收集与执行 ----------------

def list_scripts(repo: Path = REPO, only: str = "") -> list[Path]:
    """自动收录 `tests/verify_*.py`（**不许手写清单**，所以不会漏新脚本）。"""
    items = sorted(repo.glob("tests/verify_*.py"))
    if only:
        items = [p for p in items if only in p.name]
    return items


def classify(rc: int) -> str:
    """退出码 → 归类：0 通过 / 3 跳过（SKIP ≠ 通过）/ 其它失败。"""
    return "ok" if rc == 0 else ("skip" if rc == 3 else "fail")


def run_one(python: str, script: Path, *, stream: bool = False) -> tuple[int, float, list[str]]:
    """跑一个 verify 脚本：返回 (退出码, 秒数, 末 N 行输出)。超时按 124 记（同 `timeout(1)`）。"""
    tail: deque[str] = deque(maxlen=TAIL_LINES)
    started = time.time()
    proc = subprocess.Popen([python, str(script)], cwd=str(REPO),
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace")
    killed = {"v": False}

    def _watchdog() -> None:
        try:
            proc.wait(timeout=PER_SCRIPT_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            killed["v"] = True
            proc.kill()

    threading.Thread(target=_watchdog, daemon=True).start()
    if proc.stdout is not None:
        for line in proc.stdout:
            line = line.rstrip("\n")
            tail.append(line)
            if stream:
                print(f"   {line}", flush=True)
    proc.wait()
    rc = 124 if killed["v"] else (proc.returncode or 0)
    if killed["v"]:
        tail.append(f"⏱️ 超时 {PER_SCRIPT_TIMEOUT_S}s ⇒ 已杀（不计通过）")
    return rc, time.time() - started, list(tail)


# ---------------- 入口 ----------------

def _parse(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        prog="run_verifications.py",
        description="特性验证统一入口（二类）：逐个跑 tests/verify_*.py 并汇总。SKIP 不是通过。",
    )
    ap.add_argument("--only", default="", metavar="子串",
                    help="只跑文件名里含该子串的验证脚本（例：--only ambiguity）")
    ap.add_argument("--no-demo", action="store_true", help="不起 demo，只跑自包含的验证")
    ap.add_argument("--list", action="store_true", help="只列出会跑哪些脚本，不执行")
    ap.add_argument("--stream", action="store_true", help="实时打印子进程输出（默认只在结束时打尾部摘要）")
    ap.add_argument("--min-mem", type=int, default=int(os.environ.get("VERIFY_MIN_MEM_MB", DEFAULT_MIN_MEM_MB)),
                    metavar="MB", help=f"内存阈值（默认 {DEFAULT_MIN_MEM_MB}MB，低于它整体 SKIP 并 exit 3）")
    return ap.parse_args(argv)


def _ensure_demo_fresh(python: str) -> bool:
    """**每轮闸门**（AprilPark1012 2026-09-22 拍）—— 在脚本循环体内调用，不只入口查一次。

    为什么：一轮十几个脚本、期间有人改了 demo ⇒ 后面几个脚本跑在旧页面上（白跑 + 误导结论）。
    口径：内容指纹优先（`demo_freshness.demo_fingerprint`，能抓 `git checkout` 那种"内容变了 mtime 没变"），
    stale ⇒ 真重启；unknown ⇒ **不擅自重启**、但如实喊出来（入口闸门已经拦过一次，这里不阻断整轮）。
    """
    sys.path.insert(0, str(REPO / "tests"))
    sys.path.insert(0, str(REPO))
    import demo_freshness as df
    ok, note = df.ensure_fresh(quiet=True)
    if ok:
        if "重启" in note or "已启动" in note:
            print(f"  ↻ 每轮闸门：{note}")
        return True
    print(f"  ⚠️ 每轮闸门未过：{note}（本轮继续，但该结论需人工复核 demo 新鲜度）")
    return False


def main(argv: list[str]) -> int:
    args = _parse(argv)
    python = _venv_python()
    base = os.environ.get("HYBRID_BASE_URL") or "http://127.0.0.1:8000"
    scripts = list_scripts(REPO, args.only)
    mb = mem_available_mb()

    print("==================================================================")
    print(f" 特性验证统一入口（Python）· {_now_cst()}")
    print(f" 仓库: {REPO}")
    print(f" 解释器: {python}")
    print(f" 内存: " + (f"MemAvailable {mb}MB（阈值 {args.min_mem}MB）" if mb is not None
                      else "⚠️ 未测（该平台拿不到可用内存数字）⇒ 不据此跳过，内存紧请自行腾挪"))
    print(f" 将跑: {len(scripts)} 个 verify 脚本{('（过滤: ' + args.only + '）') if args.only else ''}")
    print("==================================================================")

    if args.list:
        for p in scripts:
            print(f"  {p.name}")
        return 0
    if not scripts:
        print("⚠️ 没有匹配的 verify_*.py ⇒ 什么都不跑（check 你的 --only）")
        return 2
    if mb is not None and mb < args.min_mem:
        print(f"⏭️  SKIP：MemAvailable {mb}MB < {args.min_mem}MB —— 内存不足，跳过全部验证"
              f"（exit 3，**不是通过**）")
        print(f"    腾内存后重跑；或调低阈值（--min-mem <n> / VERIFY_MIN_MEM_MB=<n>）")
        return 3

    # --- demo 新鲜度闸门（R7 前置）----------------------------------------------
    # demo 是常驻进程：改了 demo/app.py 或 demo/*.html 却没重启 ⇒ 后面所有端到端验证都跑在
    # **旧页面**上（用例白跑 + 结论误导）。不新鲜 ⇒ 自动重启；重启后仍不新鲜 ⇒ 停手（exit 2）。
    if not args.no_demo:
        print("· demo 新鲜度闸门（改了 demo 就必须重启，否则验证白跑）…")
        rc = subprocess.run([python, "tests/demo_freshness.py", "--ensure", "--start-if-missing"],
                            cwd=str(REPO)).returncode
        if rc != 0:
            print(f"❌ demo 新鲜度闸门未过（exit {rc}）⇒ 停手：不在旧版本 demo 上跑验证")
            return 2

    started_demo: subprocess.Popen | None = None
    if not args.no_demo:
        if demo_up(base):
            print("· demo 已在跑（复用，跑完不关；新鲜度已由上面的闸门保证）")
        else:
            print(f"· 启动 demo（{base}）…")
            started_demo = start_demo(python, base)
            if started_demo is None:
                return 2
            print(f"· demo 就绪（pid {started_demo.pid}）")

    results: list[tuple[str, int]] = []
    try:
        for i, script in enumerate(scripts, 1):
            if not args.no_demo:
                _ensure_demo_fresh(python)      # 每轮都查（AprilPark1012 2026-09-22）
            print(f"\n———— [{i}/{len(scripts)}] {script.name} ————")
            rc, dur, tail = run_one(python, script, stream=args.stream)
            for line in tail:
                print(f"   {line}")
            results.append((script.name, rc))
            verdict = {"ok": "✅ exit 0", "skip": "⏭️  exit 3 跳过（不是通过）",
                       "fail": f"❌ exit {rc}"}[classify(rc)]
            print(f"  {verdict}（{dur:.0f}s）")
    finally:
        if started_demo is not None:
            started_demo.kill()
            print("\n· 已停自起的 demo")

    ok = sum(1 for _, rc in results if classify(rc) == "ok")
    skip = sum(1 for _, rc in results if classify(rc) == "skip")
    fail = sum(1 for _, rc in results if classify(rc) == "fail")
    print("\n==================================================================")
    print(f" 汇总（通过 {ok} · 跳过 {skip} · 失败 {fail}）")
    for name, rc in results:
        print(f"   {name:<40} exit {rc}")
    print("==================================================================")
    if fail:
        print("❌ 有失败 —— 先修再提交（R7）")
        return 1
    if skip:
        print(f"⚠️ 有跳过项（**不是通过**）：{skip} 个 —— 腾内存后重跑，别当绿灯")
    else:
        print("✅ 特性验证全通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
