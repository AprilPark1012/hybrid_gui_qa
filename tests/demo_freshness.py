"""demo 新鲜度闸门 —— 防止「改了 demo、验证却跑在旧版本上」（2026-09-21 反馈）。

**问题形态**：`python -m demo.app` 是**常驻进程**。改完 `demo/app.py` 或 `demo/*.html` 之后如果不重启，
浏览器里拿到的仍是**旧页面** ⇒ 端到端验证（R7 二类）跑在旧版本上：**测试用例白跑**，
而且比白跑更糟 —— 它会给出一个「看起来通过/看起来失败」的结论，把人引向错误的判断。

**判据（本模块）**：`demo/` 下源码（.py / .html，排除 __pycache__）的**最新 mtime** 必须 **早于**
demo 进程的**启动时刻**（从 /proc/<pid>/stat 的 starttime + /proc/stat 的 btime 精确取，不靠 ps 文本解析）。
不满足 ⇒ 「不新鲜」，二类验证前必须重启。

**三种状态**（都不许含糊）：
  fresh       : 进程比源码新 ⇒ 可以跑验证
  stale       : 进程比源码旧 ⇒ 必须重启（`--ensure` 会重启并等到就绪，然后复检）
  no_process  : 没在跑 ⇒ 由调用方决定：`--ensure` 默认**不擅自起**（脚本可能自己起 demo），
                `--start-if-missing` 才起；验证脚本自起 demo 的不受影响。

用法（验证入口 / 手工排查都用它）：
    python tests/demo_freshness.py --check              # 只查，退出码 0=fresh / 3=stale / 4=no_process
    python tests/demo_freshness.py --ensure             # 查 + 不新鲜就重启 + 等到就绪 + 复检
    python tests/demo_freshness.py --start-if-missing    # 没起才起
    python tests/demo_freshness.py --json                # 机器可读（给脚本调用）
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEMO_DIR = REPO / "demo"
BASE_URL = os.environ.get("HYBRID_BASE_URL") or "http://localhost:8000"
SUFFIXES = (".py", ".html", ".js", ".css")     # 页面与后端都在 demo/ 下，任一变了都要重启
CLOCK_TOLERANCE_S = 1.0                        # 同秒级容差（避免 mtime 与启动时刻同秒时误报）
READY_TIMEOUT_S = 20.0


# ---------------- 纯判定（可离线测）----------------

def newest_src_mtime(demo_dir: Path = DEMO_DIR) -> tuple[float, str]:
    """demo/ 下源码的最新 mtime 与它的文件名（排除 __pycache__）。"""
    newest, who = 0.0, ""
    for p in demo_dir.rglob("*"):
        if not p.is_file() or "__pycache__" in p.parts:
            continue
        if p.suffix.lower() not in SUFFIXES:
            continue
        m = p.stat().st_mtime
        if m > newest:
            newest, who = m, str(p.relative_to(demo_dir))
    return newest, who


def verdict(started_epoch: float | None, newest_mtime: float,
            tolerance: float = CLOCK_TOLERANCE_S) -> tuple[str, str]:
    """纯判定：进程启动时刻 vs 源码最新 mtime ⇒ fresh / stale / no_process。

    ⚠️ 这是**保守**判定：mtime 与启动时刻同秒（容差内）算 fresh —— 宁可不重启（多一次重启的代价是几秒，
    误判成 stale 会影响「验证结论可追溯」这件事本身）……但反过来，**源码比进程新就必须 stale**：
    那是「改了没重启」的确切信号，放过它等于让整个二类验证失去意义。
    """
    if started_epoch is None:
        return "no_process", "demo 未在运行"
    if newest_mtime > started_epoch + tolerance:
        return "stale", (f"demo 源码比进程新：源码最新 {time.strftime('%H:%M:%S', time.localtime(newest_mtime))} "
                         f"> 进程启动 {time.strftime('%H:%M:%S', time.localtime(started_epoch))}")
    return "fresh", "demo 进程比源码新（页面与后端都是当前版本）"


# ---------------- 进程探测（Linux /proc，精确）----------------

def demo_pids() -> list[int]:
    """当前在跑的 demo.app 进程（主进程 + 其 fork 的子进程都收）。"""
    out = []
    for d in Path("/proc").iterdir():
        if not d.name.isdigit():
            continue
        try:
            cmd = (d / "cmdline").read_bytes().decode("utf-8", errors="replace")
        except OSError:
            continue
        if "demo.app" in cmd and "python" in cmd:
            out.append(int(d.name))
    return out


def proc_start_epoch(pid: int) -> float | None:
    """进程启动时刻（epoch 秒）—— 取 /proc/<pid>/stat 的 starttime 字段 + /proc/stat 的 btime。

    不解析 ps 的输出文本（格式随 locale/版本漂移，且要按列切字符串）。
    """
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8", errors="replace")
        after = stat[stat.rindex(")") + 2:].split()     # 跳过 pid 与 comm（comm 可能含空格/括号）
        starttime_ticks = int(after[19])                # 字段 22 ⇒ 切掉前两个字段后 index 19
        btime = None
        for line in Path("/proc/stat").read_text(encoding="utf-8").splitlines():
            if line.startswith("btime"):
                btime = float(line.split()[1])
                break
        if btime is None:
            return None
        return btime + starttime_ticks / os.sysconf("SC_CLK_TCK")
    except (OSError, ValueError, IndexError):
        return None


def check() -> dict:
    newest_mtime, who = newest_src_mtime()
    pids = demo_pids()
    if not pids:
        state, detail, pid, started = "no_process", "demo 未在运行", None, None
    else:
        pid = min(pids, key=lambda p: proc_start_epoch(p) or float("inf"))   # 主进程 = 起得最早那个
        started = proc_start_epoch(pid)
        state, detail = verdict(started, newest_mtime)
    return {"state": state, "detail": detail, "pid": pid, "started_epoch": started,
            "newest_mtime": newest_mtime, "newest_file": who, "base_url": BASE_URL}


# ---------------- 动作 ----------------

def _wait_ready(timeout: float = READY_TIMEOUT_S) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(BASE_URL.rstrip("/") + "/api/health", timeout=2)
            return True
        except (urllib.error.URLError, OSError):
            time.sleep(0.4)
    return False


def restart(quiet: bool = False) -> bool:
    """重启 demo（先停旧的，再以与日常相同的方式起新的），并等到 /api/health 就绪。"""
    pids = demo_pids()
    for p in pids:
        try:
            os.kill(p, 15)
        except OSError:
            pass
    for _ in range(20):                       # 等旧进程退出，最多 ~4s
        if not demo_pids():
            break
        time.sleep(0.2)
    if not quiet:
        print(f"  [demo] 已停旧进程 {pids}")
    log = REPO / "log" / "_demo_restart.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "ab") as fh:
        subprocess.Popen([sys.executable, "-m", "demo.app"], cwd=str(REPO),
                         stdout=fh, stderr=fh, start_new_session=True)
    ok = _wait_ready()
    if not quiet:
        print(f"  [demo] {'✅ 已重启并就绪' if ok else '❌ 重启后未就绪（看 ' + str(log) + '）'}")
    return ok


def main(argv: list[str]) -> int:
    want_json = "--json" in argv
    ensure = "--ensure" in argv
    start_missing = "--start-if-missing" in argv
    r = check()
    if want_json:
        print(json.dumps(r, ensure_ascii=False, indent=2))

    if r["state"] == "fresh":
        if not want_json:
            print(f"  ✅ demo 新鲜（pid {r['pid']}）：{r['detail']}")
        return 0
    if r["state"] == "no_process":
        if ensure and start_missing:
            if not want_json:
                print("  ⚠️ demo 未在运行 ⇒ 按 --start-if-missing 起一个")
            return 0 if restart(quiet=want_json) else 4
        if not want_json:
            print("  ⚠️ demo 未在运行（如需起：--start-if-missing）")
        return 4
    # stale
    if not want_json:
        print(f"  ❌ demo 不新鲜 ⇒ 验证会跑在**旧页面/旧后端**上，结论无效\n     {r['detail']}")
    if not ensure:
        return 3
    if not want_json:
        print("  → 自动重启（--ensure）")
    if not restart(quiet=want_json):
        return 4
    again = check()
    if want_json:
        print(json.dumps(again, ensure_ascii=False, indent=2))
    if again["state"] == "fresh":
        if not want_json:
            print(f"  ✅ 重启后复检：新鲜（pid {again['pid']}）")
        return 0
    if not want_json:
        print(f"  ❌ 重启后复检仍不新鲜：{again['detail']}")
    return 3


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
