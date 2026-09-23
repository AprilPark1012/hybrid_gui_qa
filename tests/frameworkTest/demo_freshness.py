"""demo 新鲜度闸门 —— 防止「改了 demo、验证却跑在旧版本上」（2026-09-21 反馈）。

**问题形态**：`python -m demo.app` 是**常驻进程**。改完 `demo/app.py` 或 `demo/*.html` 之后如果不重启，
浏览器里拿到的仍是**旧页面** ⇒ 端到端验证（R7 二类）跑在旧版本上：**测试用例白跑**，
而且比白跑更糟 —— 它会给出一个「看起来通过/看起来失败」的结论，把人引向错误的判断。

**判据（本模块）· 双口径（2026-09-22 升级，AprilPark1012 拍 A 档）**：

  ① **内容指纹（主口径）**：`demo/` 下源码（.py/.html/.js/.css，排除 __pycache__）的 sha256 指纹，
     与「demo 进程**启动那一刻**的指纹快照」（`log/_demo_fingerprint.json`，由起/重启方落盘）比对。
     指纹不一致 ⇒ **stale**（内容变过）。
  ② **mtime（降级口径）**：没有可用快照时（demo 不是你起的 / 快照进程号对不上），退回原口径 ——
     源码最新 mtime 必须早于进程启动时刻。

  ⚠️ **为什么必须加指纹**（实测漏判口）：`git checkout` / 解压覆盖 / `cp -p` 会**保留旧 mtime** ⇒
  内容变了却判 fresh ⇒ 二类验证跑在旧页面上 = 假绿。系统时钟回拨同理。
  ⚠️ **快照只在进程号吻合时才采信**：别人的快照（别的会话/上一轮）不能证明"当前进程加载的是这份内容"。

**每轮都查（同批落地）**：一轮二类验证十几个脚本，期间有人改 demo ⇒ 后面几个脚本白跑。
⇒ `run_verifications.py` 在**脚本循环体内**每轮调 `ensure_fresh()`；只在入口查一次挡不住中途污染。

**四种状态**（都不许含糊）：

  fresh       : 内容与进程启动时一致 ⇒ 可以跑验证
  stale       : 内容变了（指纹不符）或进程比源码旧 ⇒ 必须重启（`--ensure` 会重启并等到就绪，然后复检）
  no_process  : 没在跑 ⇒ 由调用方决定：`--ensure` 默认**不擅自起**（脚本可能自己起 demo），
                `--start-if-missing` 才起；验证脚本自起 demo 的不受影响。
  unknown     : **探测到 demo 进程、但读不到它的启动时刻**（平台能力缺失）⇒ 新鲜度无法判定。
                ⚠️ 既不许当 fresh（假绿），也不许当 no_process（那会诱导重启一个其实在跑的 demo）；
                `--ensure` 同样**不擅自重启**，退出码 **5**，交人工确认。

**跨平台（2026-09-22 修）**：进程与启动时刻按平台取 ——

  linux   : `/proc/<pid>/stat` 的 starttime + `/proc/stat` 的 btime（精确，不依赖外部命令）
  windows : PowerShell（`Get-CimInstance` 找进程、`Get-Process.StartTime` 取时刻；wmic 已弃用，不用）
  posix   : `ps -eo pid=,args=` 找进程 / `ps -p <pid> -o lstart=` 取时刻

  任何一环拿不到 ⇒ 返回 None ⇒ 上层判 `unknown`（见上，绝不猜）。
  ⚠️ 历史（2026-09-22 AprilPark1012 本地 Windows 验收）：老实现只认 `/proc` ⇒ Windows 上
  `Path("/proc").iterdir()` 直接 `FileNotFoundError: [WinError 3] '\\proc'`、`os.sysconf` 也不存在
  ⇒ 整条闸门在 Windows 上不可用（一类判据 5 条全红，而它只是开发期守门人）。

用法（验证入口 / 手工排查都用它）：
    python tests/frameworkTest/demo_freshness.py --check               # 只查：0=fresh / 3=stale / 4=no_process / 5=unknown
    python tests/frameworkTest/demo_freshness.py --ensure              # 查 + 不新鲜就重启 + 等到就绪 + 复检
    python tests/frameworkTest/demo_freshness.py --start-if-missing     # 没起才起
    python tests/frameworkTest/demo_freshness.py --json                 # 机器可读（给脚本调用）
    python tests/frameworkTest/demo_freshness.py --fingerprint          # 只打印当前 demo 源码的内容指纹（排查用）
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEMO_DIR = REPO / "demo"
BASE_URL = os.environ.get("HYBRID_BASE_URL") or "http://localhost:8000"
SUFFIXES = (".py", ".html", ".js", ".css")     # 页面与后端都在 demo/ 下，任一变了都要重启
CLOCK_TOLERANCE_S = 1.0                        # 同秒级容差（避免 mtime 与启动时刻同秒时误报）
READY_TIMEOUT_S = 20.0
SNAPSHOT_PATH = REPO / "log" / "_demo_fingerprint.json"   # 启动那一刻的「指纹 + 进程号」快照


# ---------------- 纯判定（可离线测）----------------

def _src_files(demo_dir: Path) -> list[Path]:
    """demo/ 下的源码文件（排除 __pycache__ / 非源码后缀），按相对路径排序 ⇒ 指纹与顺序无关但可复现。"""
    out: list[Path] = []
    for p in demo_dir.rglob("*"):
        try:
            if not p.is_file() or "__pycache__" in p.parts:
                continue
            if p.suffix.lower() not in SUFFIXES:
                continue
        except OSError:
            continue
        out.append(p)
    return sorted(out, key=lambda p: str(p.relative_to(demo_dir)).replace(os.sep, "/"))


def demo_fingerprint(demo_dir: Path = DEMO_DIR) -> dict:
    """demo 源码的**内容指纹**（sha256 前 16 位）+ 文件数 + 最新 mtime。

    指纹只吃「相对路径 + 文件内容」⇒ 与 mtime / 系统时钟无关（`touch` 不改变指纹，
    `git checkout` 保留旧时间戳也躲不过）。读不到的文件**跳过**（不猜、不编造空内容）。
    """
    h = hashlib.sha256()
    files, newest, who = 0, 0.0, ""
    for p in _src_files(demo_dir):
        try:
            data = p.read_bytes()
            m = p.stat().st_mtime
        except OSError:
            continue
        rel = str(p.relative_to(demo_dir)).replace(os.sep, "/")
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(data)
        h.update(b"\0")
        files += 1
        if m > newest:
            newest, who = m, rel
    return {"fingerprint": h.hexdigest()[:16], "files": files,
            "newest_mtime": newest, "newest_file": who}


def read_snapshot() -> dict | None:
    """读「启动那一刻」的快照；读不到 / 损坏 ⇒ None（调用方退回 mtime 口径，不猜）。"""
    try:
        d = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(d, dict) or not d.get("fingerprint"):
        return None
    return d


def write_snapshot(fingerprint: str, pid: int | None, files: int = 0) -> None:
    """落盘快照（起/重启 demo 后立即调用）。写不进去**不抛**（闸门是守门人，不该阻断流程）。"""
    try:
        SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT_PATH.write_text(json.dumps(
            {"fingerprint": fingerprint, "pid": pid, "files": files, "recorded_at": time.time()},
            ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def newest_src_mtime(demo_dir: Path = DEMO_DIR) -> tuple[float, str]:
    """demo/ 下源码的最新 mtime 与它的文件名（排除 __pycache__）。—— mtime 降级口径用。"""
    fp = demo_fingerprint(demo_dir)
    return fp["newest_mtime"], fp["newest_file"]


def verdict(started_epoch: float | None, newest_mtime: float,
            tolerance: float = CLOCK_TOLERANCE_S, *,
            snapshot: dict | None = None, fingerprint: str | None = None) -> tuple[str, str]:
    """纯判定 ⇒ fresh / stale / no_process。

    主口径（给了 snapshot + fingerprint）：**内容指纹**比对 —— 不一致就是 stale，
    哪怕 mtime 看着比进程旧（`git checkout` / 解压覆盖会保留旧时间戳，正是要堵的漏判口）。
    降级口径（无 snapshot）：原 mtime 比对 —— 保守：同秒算 fresh，源码比进程新必须 stale。
    """
    if started_epoch is None:
        return "no_process", "demo 未在运行"
    if snapshot and fingerprint:
        snap_fp = str(snapshot.get("fingerprint") or "")
        if snap_fp:
            if snap_fp == fingerprint:
                return "fresh", "demo 源码内容与进程启动时一致（内容指纹相同）"
            return "stale", (f"demo 源码**内容**已变（内容指纹 {snap_fp} → {fingerprint}）"
                             f"⇒ 进程还跑着旧内容（mtime 可能没前进：checkout/解压会保留旧时间戳）")
    if newest_mtime > started_epoch + tolerance:
        return "stale", (f"demo 源码比进程新：源码最新 {time.strftime('%H:%M:%S', time.localtime(newest_mtime))} "
                         f"> 进程启动 {time.strftime('%H:%M:%S', time.localtime(started_epoch))}")
    return "fresh", "demo 进程比源码新（页面与后端都是当前版本）"


# ---------------- 进程探测（跨平台：Linux /proc · Windows PowerShell · POSIX ps）----------------

def _platform_kind() -> str:
    """运行平台口径：`linux`（有 /proc）/ `windows` / `posix`（其余 Unix）。

    单独抽出来是为了**可测**：判据里 monkeypatch 成 `"windows"` 就能在本机验 Windows 分支的
    解析逻辑（不需要真有一台 Windows —— 真机验收仍必须由人在 Windows 上跑，见 P14 方案）。
    """
    if os.name == "nt":
        return "windows"
    if sys.platform.startswith("linux") and Path("/proc/self/stat").exists():
        return "linux"
    return "posix"


def _run(cmd: list[str], timeout: float = 15.0) -> str | None:
    """跑一条外部命令并返回 stdout（**显式 UTF-8**，跨平台文本口径同框架）；失败/超时 ⇒ None。"""
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout,
                           text=True, encoding="utf-8", errors="replace")
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


# PowerShell：找 demo 进程 / 取某个进程的启动时刻（换算成 epoch 秒，纯数字输出好解析）
_PS_LIST = ("Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | "
            "Where-Object { $_.CommandLine -like '*demo.app*' } | "
            "Select-Object -ExpandProperty ProcessId")
_PS_START = ("$p = Get-Process -Id {pid} -ErrorAction Stop; "
             "[int64]($p.StartTime.ToUniversalTime() - "
             "[datetime]'1970-01-01T00:00:00Z').TotalSeconds")


def demo_pids() -> list[int]:
    """当前在跑的 demo.app 进程（主进程 + 其 fork 的子进程都收）；**任何异常都不抛**。"""
    kind = _platform_kind()

    if kind == "windows":
        out = _run(["powershell", "-NoProfile", "-NonInteractive", "-Command", _PS_LIST])
        return [int(x) for x in (out or "").split() if x.strip().isdigit()]

    if kind == "posix":
        out = _run(["ps", "-eo", "pid=,args="])
        pids: list[int] = []
        for line in (out or "").splitlines():
            parts = line.strip().split(None, 1)
            if len(parts) == 2 and "demo.app" in parts[1] and "python" in parts[1]:
                try:
                    pids.append(int(parts[0]))
                except ValueError:
                    continue
        return pids

    # linux：扫 /proc（精确，不依赖外部命令）
    out_pids: list[int] = []
    try:
        for d in Path("/proc").iterdir():
            if not d.name.isdigit():
                continue
            try:
                cmd = (d / "cmdline").read_bytes().decode("utf-8", errors="replace")
            except OSError:
                continue
            if "demo.app" in cmd and "python" in cmd:
                out_pids.append(int(d.name))
    except OSError:
        return []
    return out_pids


def proc_start_epoch(pid: int) -> float | None:
    """进程启动时刻（epoch 秒）；**拿不到一律 None**（调用方据此判 unknown，不猜）。

    - linux  ：`/proc/<pid>/stat` 的 starttime 字段 + `/proc/stat` 的 btime
               （不解析 ps 输出文本：格式随 locale/版本漂移，且要按列切字符串）
    - windows：PowerShell 读 `Get-Process.StartTime` 换算成 epoch
    - posix  ：`ps -p <pid> -o lstart=`（BSD/macOS 与 Linux 都支持）
    """
    kind = _platform_kind()

    if kind == "windows":
        out = _run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                    _PS_START.format(pid=pid)])
        lines = [x for x in (out or "").strip().splitlines() if x.strip()]
        try:
            return float(lines[-1].strip())
        except (ValueError, IndexError):
            return None

    if kind == "posix":
        out = _run(["ps", "-p", str(pid), "-o", "lstart="])
        txt = " ".join((out or "").split())
        if not txt:
            return None
        try:
            return time.mktime(time.strptime(txt, "%a %b %d %H:%M:%S %Y"))
        except ValueError:
            return None

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
    except (OSError, ValueError, IndexError, AttributeError):
        return None


def check() -> dict:
    fp = demo_fingerprint()
    newest_mtime, who = fp["newest_mtime"], fp["newest_file"]
    pids = demo_pids()
    snap: dict | None = None
    if not pids:
        state, detail, pid, started = "no_process", "demo 未在运行", None, None
    else:
        pid = min(pids, key=lambda p: proc_start_epoch(p) or float("inf"))   # 主进程 = 起得最早那个
        started = proc_start_epoch(pid)
        snap = read_snapshot()
        if snap and snap.get("pid") != pid:
            # ⚠️ 快照不属于当前在跑的进程（别的会话 / 上一轮）⇒ 不采信，退回 mtime 口径
            snap = None
        if started is None:
            # ⚠️「读不到」≠「没在跑」：既不许报 fresh（假绿），也不许报 no_process（会诱导重启在跑的 demo）
            state, detail = "unknown", (f"探测到 demo 进程（pid {pid}）但读不到它的启动时刻"
                                        f"（平台 {_platform_kind()}）⇒ 新鲜度无法判定，请人工确认")
        else:
            state, detail = verdict(started, newest_mtime, snapshot=snap, fingerprint=fp["fingerprint"])
    return {"state": state, "detail": detail, "pid": pid, "started_epoch": started,
            "newest_mtime": newest_mtime, "newest_file": who, "base_url": BASE_URL,
            "fingerprint": fp["fingerprint"], "files": fp["files"],
            "snapshot_used": bool(snap), "snapshot": snap}


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
    """重启 demo（先停旧的，再以与日常相同的方式起新的），并等到 /api/health 就绪。

    重启成功后**落一份指纹快照**（指纹取「启动前那一刻」的 demo 源码 ⇒ 就是新进程即将加载的内容），
    这样下次 check() 就能用内容指纹判定新鲜度，而不是退回 mtime。
    """
    fp = demo_fingerprint()               # 起之前取：即将被加载的那份内容
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
    if ok:
        after = demo_pids()
        new_pid = (min(after, key=lambda p: proc_start_epoch(p) or float("inf")) if after else None)
        write_snapshot(fingerprint=fp["fingerprint"], pid=new_pid, files=fp["files"])
        if not quiet:
            print(f"  [demo] 快照已落盘（指纹 {fp['fingerprint']} · pid {new_pid}）")
    if not quiet:
        print(f"  [demo] {'✅ 已重启并就绪' if ok else '❌ 重启后未就绪（看 ' + str(log) + '）'}")
    return ok


def ensure_fresh(quiet: bool = False) -> tuple[bool, str]:
    """**每轮闸门**（AprilPark1012 2026-09-22 拍：不只入口查一次，每轮都查）⇒ `(是否可用, 说明)`。

    与 CLI `--ensure --start-if-missing` 同口径，区别是**返回布尔而不退出进程**，供
    `run_verifications.py` 在脚本循环体里逐轮调用：
      · fresh              ⇒ (True, 说明)
      · stale              ⇒ 重启 + 复检 ⇒ (复检是否 fresh, 说明)
      · no_process         ⇒ 起一个（验证脚本需要 demo）⇒ (是否就绪, 说明)
      · unknown            ⇒ **(False, 说明) 且绝不擅自重启**（重启是破坏性动作，交人工判断）
    """
    r = check()
    state = r.get("state")
    if state == "fresh":
        return True, r.get("detail", "")
    if state == "no_process":
        if not quiet:
            print(f"  [demo] 未在运行 ⇒ 按每轮闸门起一个")
        ok = restart(quiet=quiet)
        return ok, ("每轮闸门：demo 未在运行 ⇒ 已启动" if ok else "每轮闸门：demo 启动失败")
    if state == "unknown":
        if not quiet:
            print(f"  ⚠️ [demo] 新鲜度**无法判定**：{r.get('detail')}")
        return False, f"{r.get('detail', '')}（无法判定 ⇒ 不擅自重启）"
    # stale
    if not quiet:
        print(f"  ❌ [demo] 不新鲜已拦截：{r.get('detail')}\n  → 自动重启（改过 demo 就必须重启，否则本轮验证白跑）")
    if not restart(quiet=quiet):
        return False, "每轮闸门：demo 重启后未就绪"
    again = check()
    ok = again.get("state") == "fresh"
    return ok, ("每轮闸门：内容变过 ⇒ 已重启并复检为新鲜" if ok else f"每轮闸门：重启后仍不新鲜（{again.get('detail')}）")


def main(argv: list[str]) -> int:
    want_json = "--json" in argv
    ensure = "--ensure" in argv
    start_missing = "--start-if-missing" in argv
    if "--fingerprint" in argv:
        fp = demo_fingerprint()
        if want_json:
            print(json.dumps(fp, ensure_ascii=False, indent=2))
        else:
            print(f"  demo 源码内容指纹：{fp['fingerprint']}"
                  f"（{fp['files']} 个文件 · 最新 {fp['newest_file'] or '—'}）")
        return 0
    r = check()
    if want_json:
        print(json.dumps(r, ensure_ascii=False, indent=2))

    if r["state"] == "fresh":
        if not want_json:
            print(f"  ✅ demo 新鲜（pid {r['pid']} · 指纹 {r['fingerprint']}）：{r['detail']}")
        return 0
    if r["state"] == "no_process":
        if ensure and start_missing:
            if not want_json:
                print("  ⚠️ demo 未在运行 ⇒ 按 --start-if-missing 起一个")
            return 0 if restart(quiet=want_json) else 4
        if not want_json:
            print("  ⚠️ demo 未在运行（如需起：--start-if-missing）")
        return 4
    if r["state"] == "unknown":
        # ⚠️ 不擅自重启：进程在跑，只是读不到启动时刻；重启是破坏性动作，交人工判断
        if not want_json:
            print(f"  ⚠️ demo 新鲜度**无法判定**：{r['detail']}\n"
                  f"     保守做法：改过 demo 就手工重启一次（`python -m demo.app`），再跑验证。")
        return 5
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
