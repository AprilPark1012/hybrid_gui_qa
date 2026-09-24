"""特性验证统一入口（R7 两类验证之②）—— **跨平台 Python 实现（唯一实现）**。

用法（Windows PowerShell / Linux / macOS 完全一致）：
    python tests/featureTest/run_verifications.py                  # 全量（需要 demo：脚本会自动起/停）
    python tests/featureTest/run_verifications.py --only ambiguity # 只跑名字含该子串的
    python tests/featureTest/run_verifications.py --no-demo        # 不起 demo（只跑自包含的验证）
    python tests/featureTest/run_verifications.py --list           # 只列出会跑哪些
    python tests/featureTest/run_verifications.py --stream         # 实时打印每个子进程的输出（默认只打尾部摘要）
    python tests/featureTest/run_verifications.py --min-mem 400    # 覆盖内存阈值（默认 550MB，也可用 VERIFY_MIN_MEM_MB）

退出码：**0** = 全通过（跳过项会如实列出）· **1** = 有失败 · **2** = 环境 / 用法问题 · **3** = 内存不足整体 SKIP。
⭐ 口径：**SKIP 不是绿灯** —— 内存不够时如实报 3，绝不假装通过。

为什么要有这个 Python 版（2026-09-22 使用者现场反馈）：
`bash tests/featureTest/run_verifications.sh` 在 Windows PowerShell 里**根本跑不起来**
（`无法将"bash"项识别为 cmdlet…` —— 机器上没装 Git Bash / WSL）
⇒ 二类验证对团队里的 Windows 用户等于**不存在**，而本框架的现场恰恰是 Windows。
⇒ 口径：**唯一实现 = 本文件**；`tests/featureTest/run_verifications.sh` 退化成薄包装（转发到这里），
   避免「改了一处忘了另一处」的静默不一致（这类漂移在本项目已经踩过）。

跨平台要点（都是实测口径，别改回去）：
- 解释器：优先 `<repo>/.venv/{Scripts,bin}/python*`，找不到退回 `sys.executable`，并在头部**打印用的是谁**；
- 内存：Linux 读 `/proc/meminfo`；Windows 走 `GlobalMemoryStatusEx`（ctypes，纯标准库）；
  **两条都拿不到 ⇒ 如实打印「内存未测」并继续**（不据此 SKIP、也不假装测过）；
- demo 启停：`subprocess.Popen` + 平台各自的后台标志（Windows `DETACHED_PROCESS`，POSIX `start_new_session`）；
  探活用 urllib（与 `tests/frameworkTest/demo_freshness.py` 同一口径）；
- 时间戳按**北京时间**打印（服务器可能在 UTC）；Windows 上没有 `tzset` 时退回本机本地时间。
"""
from __future__ import annotations

import re

import argparse
import os
import subprocess
import sys
import threading
import time
import urllib.request
from collections import deque
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEFAULT_MIN_MEM_MB = 550
# 单脚本预算（AprilPark1012 2026-09-22 拍板 600 → 1200）：用例越来越多，脚本自身规模就会超 600s
# ——`verify_assert_kinds.py` 30+ 子用例 × ~28s ≈ 840s，600s 下**永远跑不完**（exit 124 会被记成失败，
# 可它根本不是断言失败，是预算不够）。超预算就如实记 124，**绝不降级成「通过」**。
PER_SCRIPT_TIMEOUT_S = 1200

# 单个 Chromium 实例要留的内存（与框架其它地方同源的红线：低于它就整套 SKIP）。并行时用它当闸门：
# 能同时起几个浏览器脚本，由**当下真实可用内存**决定，而不是拍脑袋写死并发数。
MEM_PER_BROWSER_MB = 550
TAIL_LINES = 12

# 每个脚本的**完整**日志落盘（2026-09-22 实测逼出来的）：
# 只留尾部 12 行时，一旦出现偶发红项（如 verify_assert_kinds 那次正向 FAIL，
# 单独跑却是 4 passed）就**没有现场可查** ⇒ 只能靠猜。落盘后红项可复诊、可直接贴证据。
LOG_DIR = REPO / "log" / "verify_logs"

# ★ R7-d 时长预算（2026-09-23 定）——唯一声明处；一类/二类两个数都在。
#   实测基线：一类 ~24s · 二类 ~33min（--jobs 2）。逼近上限 ⇒ **先清无效用例再加新用例**
#   （目的：不白白增加测试时间、不影响打包/开发效率）。
BUDGET_FRAMEWORK_S = 60
# D6（2026-09-24 项目负责人定）：二类**控制在 40 分钟以内**。手段：并发度 + 用例合并。
# 现状：真 AI 的场景1 已自声明不进日常（`HYBRID_DAILY_SKIP`）⇒ 日常脚本耗时之和 ~34 分钟。
BUDGET_FEATURE_MIN = 40


def _script_log_path(script: Path) -> Path:
    """完整日志路径（log/ 已被 retention 策略管，不入库）。"""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    return LOG_DIR / f"{script.stem}.log"
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

def list_scripts(repo: Path = REPO, only: str = "", include_daily_skip: bool = False) -> list[Path]:
    """自动收录 `tests/featureTest/verify_*.py`（**不许手写清单**，所以不会漏新脚本）。

    例外（D2 · 2026-09-24）：脚本可在**自己文件头部**声明 `# HYBRID_DAILY_SKIP: <原因>`
    ⇒ 日常不收（如真调 LLM 的场景1，单轮 ~8-10 分钟）；`--full` 时照收。
    仍会把它们**列出来**（附原因），免得"看不见 = 忘了"。
    """
    items = sorted(repo.glob("tests/featureTest/verify_*.py"))
    if not include_daily_skip:
        keep = []
        for p in items:
            why = daily_skip_reason(p)
            if why:
                print(f"  ⏭️  {p.name} 不进日常：{why}")
            else:
                keep.append(p)
        items = keep
    if only:
        items = [p for p in items if only in p.name]
    return items


def classify(rc: int) -> str:
    """退出码 → 归类：0 通过 / 3 跳过（SKIP ≠ 通过）/ 其它失败。"""
    return "ok" if rc == 0 else ("skip" if rc == 3 else "fail")


def run_one(python: str, script: Path, *, stream: bool = False,
            timeout_s: float = PER_SCRIPT_TIMEOUT_S) -> tuple[int, float, list[str]]:
    """跑一个 verify 脚本：返回 (退出码, 秒数, 末 N 行输出)。超时按 124 记（同 `timeout(1)`）。"""
    log_path = _script_log_path(script)
    log_fh = log_path.open("w", encoding="utf-8")
    tail: deque[str] = deque(maxlen=TAIL_LINES)
    started = time.time()
    proc = subprocess.Popen([python, str(script)], cwd=str(REPO),
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace")
    killed = {"v": False}

    def _watchdog() -> None:
        try:
            proc.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            killed["v"] = True
            proc.kill()

    threading.Thread(target=_watchdog, daemon=True).start()
    if proc.stdout is not None:
        for line in proc.stdout:
            log_fh.write(line)
            line = line.rstrip("\n")
            tail.append(line)
            if stream:
                print(f"   {line}", flush=True)
    proc.wait()
    log_fh.close()
    rc = 124 if killed["v"] else (proc.returncode or 0)
    if killed["v"]:
        tail.append(f"⏱️ 超时 {timeout_s:.0f}s ⇒ 已杀（不计通过）")
    try:
        tail.append(f"完整日志: {log_path.relative_to(REPO)}")
    except ValueError:
        tail.append(f"完整日志: {log_path}")
    _dirty = artifacts_are_consistent()
    if _dirty and rc == 0:
        rc = 1
        tail.append(f"❌ 产物被本脚本弄脏（悬空引用）：{_dirty[:3]}{'…' if len(_dirty) > 3 else ''}")
        tail.append("   ⇒ 当场点名报错，不污染后续脚本（修法：删用例后必须重跑 generate 复原产物）")
    return rc, time.time() - started, list(tail)


# ---------------- 入口 ----------------

# 「会跑起 Chromium」的两种形态：
#   ① 直接起：脚本自己调 sync_playwright；
#   ② 间接起：脚本自己不起，但**shell 出去跑生成用例**（真正起浏览器的是子进程）——
#      实测 verify_assert_kinds.py 就是这么漏判成「纯离线」的（当时只认 ①）。
_BROWSER_DIRECT = ("sync_playwright",)
_BROWSER_INDIRECT = ("test_cases.py", "framework.cli")
_SPAWN_HINTS = ("subprocess", "Popen")


# ★「独占」脚本（2026-09-22 实测补）：会写**共享产物**的脚本，彼此之间、以及与任何别的脚本都不能同时跑。
# 实测事故：并发那次 `verify_data_expand.py` 报「generate 失败（exit 2）」，**单独跑**却是 exit 0 全过
# —— generate 会重写 `scripts/`（含 test_cases.py）与 element_map，和并发脚本撞了。
# 这是并发模式**自己引入的假红** ⇒ 自己判掉（宁漏不误伤：宁可少并，绝不误报）。
# ★「不进日常」自声明（D2 · 2026-09-24 他定）：脚本在**自己文件头部**声明被排除，
# 而不是维护一份中心化清单 —— 保持「自动收录、绝不漏新脚本」这个好性质。
# 口径：`# HYBRID_DAILY_SKIP: <原因>`；`--full` 时照跑（发版前 / 手工验真 AI 用）。
_DAILY_SKIP_MARKER = "HYBRID_DAILY_SKIP:"


def daily_skip_reason(path: Path) -> str | None:
    """脚本是否自声明「不在日常跑」⇒ 返回原因（None = 日常要跑）。"""
    try:
        head = "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[:40])
    except OSError:
        return None
    m = re.search(re.escape(_DAILY_SKIP_MARKER) + r"\s*(.+)", head)
    return m.group(1).strip() if m else None


_EXCLUSIVE_MARKERS = (
    "framework.cli",      # generate / run：重写 scripts/ 与 element_map
    "build_tools/",       # 打包、渲染培训页
    "build_html.py",
    "pack_release",
    "record_cassettes",
)



def artifacts_are_consistent() -> list[str]:
    """产物自洽检查：`scripts/test_cases.py` / `conftest.py` 里嵌的 case_id 是否都有数据集。

    为什么放在**每个脚本之间**跑：实测事故 —— 某验证脚本会**临时写用例再删掉**，删时忘了复原
    产物 ⇒ 产物留下**死引用** ⇒ 之后任何跑 `test_cases.py` 的脚本都红，而且报 FileNotFoundError +
    pytest 退出码 2（= 执行环境问题）⇒ 看着像"环境/偶发"。做成脚本间质检后，**弄脏产物的那个脚本
    被当场点名**，不再污染后续脚本。

    返回：死引用列表（空 = 干净）。
    """
    import re as _re
    scripts = REPO / "scripts"
    try:
        tc = (scripts / "test_cases.py").read_text(encoding="utf-8")
        cf = (scripts / "conftest.py").read_text(encoding="utf-8")
    except OSError:
        return []
    used: set[str] = set(_re.findall(r"^def test_([A-Za-z0-9_]+)\(", tc, _re.M))
    used |= set(_re.findall(r"_ds_params\(\s*[\"\']([A-Za-z0-9_]+)[\"\']", cf + tc))
    return sorted(c for c in used if not (scripts / "datasets" / f"{c}.json").exists())


def is_exclusive_script(path: Path) -> bool:
    """会写共享产物 ⇒ 必须独占跑（读不到文件按独占处理：保守优先）。"""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return True
    return any(m in text for m in _EXCLUSIVE_MARKERS)


def is_browser_script(path: Path) -> bool:
    """该验证脚本是否会起 Chromium（决定能不能参与并行、要占多少内存）。

    判据是**脚本自己的源码**里有没有 sync_playwright —— 确定性判据，不靠文件名猜。
    读不到文件 ⇒ 按「会起浏览器」处理（保守：宁可少并一个，也不冒内存风险）。
    """
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return True
    # ⚠️ 只看 sync_playwright **不够**（实测踩到）：像 verify_assert_kinds.py 自己不起浏览器，
    # 但它**shell 出去跑 pytest**，真正起 Chromium 的是那个子进程 ⇒ 会被误判成「纯离线」而绕过内存闸。
    # ⇒ 凡是"会间接跑起浏览器"的痕迹都算浏览器类（保守优先：宁可少并一个，也不冒被 SKIP 的风险）。
    if any(m in text for m in _BROWSER_DIRECT):
        return True
    return (any(m in text for m in _BROWSER_INDIRECT)
            and any(h in text for h in _SPAWN_HINTS))


def mem_available_mb() -> int:
    """当前可用内存（MB）。拿不到 ⇒ 返回 0（触发最保守策略）。"""
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) // 1024
    except OSError:
        pass
    return 0


def may_start(*, is_browser: bool, running: int, running_browsers: int, jobs: int,
              mem_mb: int, exclusive: bool = False,
              running_exclusive: bool = False) -> tuple[bool, str]:
    """并行调度的准入判据（纯函数，便于单测；调用方负责真正起进程）。

    四条红线，任一不满足就「先别起」：
      ⓪ **独占屏障**：会写共享产物的脚本跑着时谁也别起；它要起时别人必须都跑完；
      ① 并发数没到上限；
      ② 浏览器脚本额外过内存闸 —— 可用内存 ≥ 550MB × (已跑的浏览器脚本数 + 1)；
         **差几 MB 也不硬闯**（硬闯的下场是浏览器起不来 ⇒ 整套验证被跳过，比慢更糟）；
      ③ jobs <= 1 ⇒ 永远串行（与改造前行为**完全一致**）。
    返回 (能不能起, 原因)：原因会打进日志，方便事后看懂当时为什么没并。
    """
    if jobs <= 1:
        return (running == 0), "串行模式：一次只跑一个"
    if running >= jobs:
        return False, f"并发已满（{running}/{jobs}）"
    if running_exclusive:
        return False, "已有独占脚本在跑（它会重写共享产物，等它）"
    if exclusive and running:
        return False, "本脚本要独占（会重写共享产物），等当前任务跑完"
    if is_browser:
        need = MEM_PER_BROWSER_MB * (running_browsers + 1)
        if mem_mb < need:
            return False, f"内存闸未过：可用 {mem_mb}MB < 需要 {need}MB（不硬闯，先腾内存）"
    return True, "准行"

def _parse(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        prog="run_verifications.py",
        description="特性验证统一入口（二类）：逐个跑 tests/featureTest/verify_*.py 并汇总。SKIP 不是通过。",
    )
    ap.add_argument("--only", default="", metavar="子串",
                    help="只跑文件名里含该子串的验证脚本（例：--only ambiguity）")
    ap.add_argument("--no-demo", action="store_true", help="不起 demo，只跑自包含的验证")
    ap.add_argument("--list", action="store_true", help="只列出会跑哪些脚本，不执行")
    ap.add_argument("--full", action="store_true",
                    help="连自声明「不进日常」的脚本一起跑（如真调 LLM 的场景1；发版前或手工验真 AI 时用）")
    ap.add_argument("--stream", action="store_true", help="实时打印子进程输出（默认只在结束时打尾部摘要）")
    ap.add_argument("--min-mem", type=int, default=int(os.environ.get("VERIFY_MIN_MEM_MB", DEFAULT_MIN_MEM_MB)),
                    metavar="MB", help=f"内存阈值（默认 {DEFAULT_MIN_MEM_MB}MB，低于它整体 SKIP 并 exit 3）")
    ap.add_argument("--timeout-s", type=float, default=PER_SCRIPT_TIMEOUT_S,
                    help=f"单个脚本的预算秒数（默认 {PER_SCRIPT_TIMEOUT_S:.0f}）")
    ap.add_argument("--jobs", type=int, default=1,
                    help="并发脚本数（默认 1 = 串行，行为与改造前完全一致）。"
                         "浏览器脚本会各自过内存闸，内存不够时自动退回串行")
    return ap.parse_args(argv)


def _ensure_demo_fresh(python: str) -> bool:
    """**每轮闸门**（AprilPark1012 2026-09-22 拍）—— 在脚本循环体内调用，不只入口查一次。

    为什么：一轮十几个脚本、期间有人改了 demo ⇒ 后面几个脚本跑在旧页面上（白跑 + 误导结论）。
    口径：内容指纹优先（`demo_freshness.demo_fingerprint`，能抓 `git checkout` 那种"内容变了 mtime 没变"），
    stale ⇒ 真重启；unknown ⇒ **不擅自重启**、但如实喊出来（入口闸门已经拦过一次，这里不阻断整轮）。
    """
    sys.path.insert(0, str(REPO / "tests" / "featureTest"))     # 二类脚本自身
    sys.path.insert(0, str(REPO / "tests" / "frameworkTest"))   # ★ 共享辅助（demo_freshness / artifacts 等）住这里
    sys.path.insert(0, str(REPO))
    import demo_freshness as df
    ok, note = df.ensure_fresh(quiet=True)
    if ok:
        if "重启" in note or "已启动" in note:
            print(f"  ↻ 每轮闸门：{note}")
        return True
    print(f"  ⚠️ 每轮闸门未过：{note}（本轮继续，但该结论需人工复核 demo 新鲜度）")
    return False



def run_parallel(python: str, scripts: list[Path], *, jobs: int, timeout_s: float,
                 verbose: bool = True) -> list[tuple[str, int]]:
    """并发跑多个验证脚本（**只在不满足准入时空转等待，绝不硬闯内存**）。

    与串行版的差别只在"什么时候起下一个"：串行版是"跑完一个起一个"，
    这里在**准入判据**（并发数 + 浏览器内存闸）允许时就起下一个，并把结果按**完成顺序**打出来。
    输出会整体贴上脚本名，避免并发日志串台看不出是谁的。
    """
    pending = list(scripts)
    # 预先算好分类（轮询 0.3s 一次，别每轮都去读 16 个文件）
    _excl = {s: is_exclusive_script(s) for s in scripts}
    running: dict[subprocess.Popen, tuple[Path, bool, float]] = {}
    results: list[tuple[str, int]] = []
    durations: list[float] = []
    state: dict[str, str] = {"last_hold": ""}        # 供"同一原因不重复刷屏"用
    while pending or running:
        started = False
        while pending:
            script = pending[0]
            is_b = is_browser_script(script)
            is_x = _excl.get(script, True)                    # 读不到 ⇒ 按独占（保守）
            rb = sum(1 for _s, _b, _t in running.values() if _b)
            rx = any(_excl.get(_s, True) for _s, _b, _t in running.values())
            ok, why = may_start(is_browser=is_b, running=len(running), running_browsers=rb,
                                jobs=jobs, mem_mb=mem_available_mb(),
                                exclusive=is_x, running_exclusive=rx)
            if not ok:
                # 只在**原因变化**时打一行：内存闸未过是常态（本机 2 个浏览器要 1100MB），
                # 每 0.3s 重复同一行会把日志刷爆（实测单次跑刷出几百行，真正有用的信息全被埋了）。
                if verbose and running and why != state.get("last_hold"):
                    state["last_hold"] = why
                    print(f"   ⏸ {script.name} 暂不起：{why}")
                break
            pending.pop(0)
            proc = subprocess.Popen([python, str(script)], cwd=str(REPO),
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, encoding="utf-8", errors="replace")
            running[proc] = (script, is_b, time.monotonic())
            state["last_hold"] = ""
            print(f"▶ 起 {script.name}（并发 {len(running)}/{jobs}{'，含浏览器' if is_b else ''}）")
            started = True
        if not running:
            if pending:
                continue                      # 等内存腾出来（外层没有死循环：pending 只在准行时减少）
            break
        time.sleep(0.3)          # 轮询间隔：真脚本动辄几百秒，这 0.3s 可忽略；短脚本也别为它多等
        for proc in list(running):
            rc = proc.poll()
            if rc is None:
                script, _b, t0 = running[proc]
                if time.monotonic() - t0 > timeout_s:
                    proc.kill()
                    running.pop(proc)
                    print(f"\n———— {script.name} ————\n   ⏱️ 超时 {timeout_s:.0f}s ⇒ 已杀（不计通过）")
                    results.append((script.name, 124))
                    durations.append(float(timeout_s))
                continue
            script, _b, t0 = running.pop(proc)
            dur = time.monotonic() - t0
            out = proc.stdout.read() if proc.stdout else ""
            _dirty = artifacts_are_consistent()
            if _dirty and proc.returncode == 0:
                proc.returncode = 1
                print(f"  ❌ 产物被本脚本弄脏（悬空引用）：{_dirty[:3]}"
                      f"{'…' if len(_dirty) > 3 else ''} ⇒ 删用例后必须重跑 generate 复原")
            # 完整日志落盘（并发路径同样要落 —— 偶发红项没现场就只能靠猜）
            try:
                _script_log_path(script).write_text(out, encoding="utf-8")
                log_note = f"（完整日志: log/verify_logs/{script.stem}.log）"
            except OSError as e:
                log_note = f"（⚠️ 完整日志落盘失败: {type(e).__name__}）"
            print(f"\n———— {script.name} ————")
            for line in out.strip().splitlines()[-12:]:
                print(f"   {line}")
            print(f"   {log_note}")
            verdict = {"ok": "✅ exit 0", "skip": "⏭️  exit 3 跳过（不是通过）",
                       "fail": f"❌ exit {rc}"}[classify(rc)]
            print(f"  {verdict}（{dur:.0f}s）")
            results.append((script.name, rc))
        if not started and not any(p.poll() is None for p in running) and pending:
            time.sleep(0.2)
    return results

def main(argv: list[str]) -> int:
    args = _parse(argv)
    python = _venv_python()
    base = os.environ.get("HYBRID_BASE_URL") or "http://127.0.0.1:8000"
    scripts = list_scripts(REPO, args.only, args.full)
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
        rc = subprocess.run([python, "tests/frameworkTest/demo_freshness.py", "--ensure", "--start-if-missing"],
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
    durations: list[float] = []      # 每脚本耗时（D6 的 40 分钟预算对账用）
    try:
        if args.jobs > 1 and len(scripts) > 1:
            print(f"· 并发模式 jobs={args.jobs}（浏览器脚本各自过内存闸，内存不够自动退回串行；"
                  f"单脚本预算 {args.timeout_s:.0f}s）")
            if not args.no_demo:
                _ensure_demo_fresh(python)
            results = run_parallel(python, scripts, jobs=args.jobs, timeout_s=args.timeout_s)
            durations = []
        else:
            for i, script in enumerate(scripts, 1):
                if not args.no_demo:
                    _ensure_demo_fresh(python)      # 每轮都查（AprilPark1012 2026-09-22）
                print(f"\n———— [{i}/{len(scripts)}] {script.name} ————")
                rc, dur, tail = run_one(python, script, stream=args.stream, timeout_s=args.timeout_s)
                for line in tail:
                    print(f"   {line}")
                results.append((script.name, rc))
                durations.append(dur)
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
    _elapsed_min = sum(durations) / 60.0
    print(f" 汇总（通过 {ok} · 跳过 {skip} · 失败 {fail}）· 脚本耗时 {_elapsed_min:.1f} 分钟"
          f"（预算 {BUDGET_FEATURE_MIN} 分钟 · D6）")
    if _elapsed_min > BUDGET_FEATURE_MIN:
        print(f"⚠️ 超出 R7-d / D6 预算：{_elapsed_min:.1f} > {BUDGET_FEATURE_MIN} 分钟 ⇒ "
              "按「先清后加」处理（合并用例 / 提并发 / 把重活移出日常）")
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
