"""scripts 配套 fixture —— 浏览器工厂 / 数据注入 / 变量池 / 动态占位符 / 日志。

数据流：scripts/datasets/<case_id>.json（generate 从 cases/ 抽离）→ _data(key, ctx) 注入。
浏览器生命周期（E 项提速后）：**整个会话共用一个 Chromium**（_pool，session scope），
每条用例只新建 context + page（function scope）——隔离性不变（cookie/存储/trace/录像按 context 走），
但省掉「每条用例重启浏览器」的 ≈0.6s/条（实测 9 用例 setup 由 5.4s → 若干毫秒）。
case.vars 变量池（运行过程数据）+ 动态占位符 {datetime} 解析（一次解析固化，填表名==断言名，重跑不重名）。
"""
# ---- 统一 UTF-8（生成物自带，裸跑 pytest 也不炸；与 framework/text_io.py 同口径）----
# 为什么：Windows 控制台是 cp936 时，本文件里的 ✓/⚠️ 会 UnicodeEncodeError（跑到一半崩）；
# 而 pytest 的 fd 捕获把输出写回真实 fd 时**硬编码 UTF-8**（_pytest/capture.py），
# 只要外层按 locale 解码就 UnicodeDecodeError。这里把本进程 stdio 拉齐到 UTF-8，
# 并把 Windows 控制台代码页设成 65001（否则我们写出的 UTF-8 中文在控制台显示成乱码）。
import os as _os
import sys as _sys
_os.environ.setdefault("PYTHONUTF8", "1")
_os.environ.setdefault("PYTHONIOENCODING", "utf-8")
for _s in (_sys.stdout, _sys.stderr):
    try:
        if _s is None or not hasattr(_s, "reconfigure"):
            continue
        _s.fileno()                      # pytest 捕获替身没有 fileno → 跳过，别去动它
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if _sys.platform == "win32":
    try:
        import ctypes as _ctypes
        _ctypes.windll.kernel32.SetConsoleOutputCP(65001)
    except Exception:
        pass

from pathlib import Path
import pytest
from playwright.sync_api import sync_playwright
from playwright.sync_api import expect as _expect

BASE = Path(__file__).resolve().parent.parent
LOG_DIR = BASE / "log"

# ---- 本次运行的日志目录（run-id 隔离）----
# cli run 会设 HYBRID_RUN_ID=YYYYmmdd_HHMMSS，日志/报告落 log/<run_id>/；
# 裸跑 pytest（未设）则落 log/latest/，并在会话开始时清空 ⇒ 每次运行都干净。
import os
RUN_ID = os.environ.get("HYBRID_RUN_ID", "latest")
RUN_LOG_DIR = LOG_DIR / RUN_ID

# ---- Chromium 启动参数（内联自 framework/browser.py:CHROMIUM_ARGS；生成物自包含）----
CHROMIUM_ARGS = [
    '--disable-dev-shm-usage',
    '--disable-gpu',
    '--disable-extensions',
    '--no-first-run',
    '--no-default-browser-check',
    '--disable-background-networking',
    '--disable-backgrounding-occluded-windows',
    '--disable-renderer-backgrounding',
    '--renderer-process-limit=1',
]


def _launch_opts(headless):
    """headless=True 无头(默认)；False 有头(显示浏览器)。
    支持 HYBRID_SLOWMO=<毫秒> 放慢每个动作，方便肉眼看用例一步步走。"""
    args = list(CHROMIUM_ARGS)
    heap = os.environ.get("HYBRID_JS_HEAP_MB")
    if heap and heap.isdigit():
        args.append(f"--js-flags=--max-old-space-size={int(heap)}")
    opts = {"headless": headless, "args": args}
    slow = os.environ.get("HYBRID_SLOWMO")
    if slow and slow.isdigit() and int(slow) > 0:
        opts["slow_mo"] = int(slow)
    return opts


import sys
sys.path.insert(0, str(BASE))
from framework.data_driven import resolve_dynamic_inputs, format_template  # noqa
from framework.healer import Healer  # noqa: E402

# ---- 自愈开关（Q1 决策：默认开，可用 HYBRID_SELF_HEAL=0 关）----
# 0 → 确定性 locator 失效即报错，不做语义兜底/自愈（CI 里常要"失败即报"）
_SELF_HEAL = os.environ.get("HYBRID_SELF_HEAL", "1") != "0"
_HEALER = Healer()   # 进程内单例：累积 heal 事件，会话结束统一落盘（可审 diff）

# 用例上下文：数据 + 变量池 + 动态占位符固化
class CaseCtx:
    __slots__ = ("case_id", "data", "vars")
    def __init__(self, case_id, data):
        self.case_id = case_id
        self.data = data
        self.vars = {}          # 用例级变量池：存运行过程数据(编号/抓取值)，function-scope 隔离
        resolve_dynamic_inputs(self.data)   # 动态占位符 {datetime}→实际值(固化)


def _data(key, ctx):
    """从用例数据字典取 key 的值；若含 {占位符} 则动态解析（保留 {datetime} 能力）。"""
    v = ctx.data.get(key, key)
    if isinstance(v, str) and "{" in v:
        return format_template(v, ctx.data)
    return v


def _load_data(case_id):
    import json
    p = Path(__file__).resolve().parent / "datasets" / f"{case_id}.json"
    return json.loads(p.read_text(encoding="utf-8"))


@pytest.fixture(scope="session", autouse=True)
def _prepare_run_log_dir():
    """保证"本次运行"的日志目录干净。

    - 有 HYBRID_RUN_ID（cli run 传入）→ 该目录是全新 run-id，天然干净，不清。
    - 无 HYBRID_RUN_ID（裸跑 pytest）→ 落 log/latest/，会话开始先清空。
    注意 xdist：worker 进程不清理（避免并发删除互相打架），只由主进程清。
    """
    if not os.environ.get("HYBRID_RUN_ID") and "PYTEST_XDIST_WORKER" not in os.environ:
        import shutil
        shutil.rmtree(RUN_LOG_DIR, ignore_errors=True)
    RUN_LOG_DIR.mkdir(parents=True, exist_ok=True)
    yield RUN_LOG_DIR


# ---- 用例级看门狗（2026-09-14）----
# 为什么要：Playwright 驱动**内部崩溃**时（实测 coreBundle.js:463 Assertion error，机器内存吃紧时触发），
# 它的同步 API 会一直等一个永远不来的响应 —— Python 侧 100% CPU 空转、**永不退出**
# （2026-09-14 实测卡了 11 分钟，只能手工 kill）。挂死比失败更糟：CI 一直挂着、也没人知道卡在哪。
# 用 stdlib 的 faulthandler：超时就打印**所有线程的调用栈**（直接看出卡在哪一行）并退出，绝不静默。
# 口径：HYBRID_CASE_TIMEOUT 秒（默认 120）；设为 0/off 关掉。
_CASE_TIMEOUT = os.environ.get("HYBRID_CASE_TIMEOUT", "120")
_WATCHDOG_SINK = None


def _watchdog_sink():
    """看门狗转储目标：run 日志目录里的 watchdog.txt（无缓冲，一定落盘）。

    为什么不用 stderr：pytest 的 fd 捕获会把 **fd 2 也换成临时文件** ⇒ 硬退出时那段调用栈
    随临时文件一起被丢弃（实测：日志里一个字节都没有，看门狗等于没留证据）。
    自己开一个专用文件（fd 3+，不受捕获影响）+ buffering=0 ⇒ 转储一定写进去；
    这也比 stderr 更好找：`log/<run_id>/watchdog.txt`。
    """
    global _WATCHDOG_SINK
    if _WATCHDOG_SINK is None:
        try:
            RUN_LOG_DIR.mkdir(parents=True, exist_ok=True)
            _WATCHDOG_SINK = open(RUN_LOG_DIR / "watchdog.txt", "ab", buffering=0)
        except Exception:
            _WATCHDOG_SINK = _sys.__stderr__
    return _WATCHDOG_SINK


@pytest.fixture(autouse=True)
def _case_watchdog():
    """每条用例一个硬超时：超时把**所有线程的调用栈**写进 log/<run>/watchdog.txt 并退出。

    防的是「Playwright 驱动崩溃 → 同步 API 空转不返回」那种永久挂死（比失败更糟）。
    口径：HYBRID_CASE_TIMEOUT 秒（默认 120）；设 0/off 关掉。
    """
    import faulthandler
    secs = (_CASE_TIMEOUT or "").strip().lower()
    if secs in ("", "0", "off", "none", "false"):
        yield None
        return
    try:
        faulthandler.dump_traceback_later(int(float(secs)), exit=True, file=_watchdog_sink())
    except Exception as e:
        print(f"[setup] ⚠️ 用例看门狗没装上（HYBRID_CASE_TIMEOUT={_CASE_TIMEOUT!r}）：{e}", flush=True)
        yield None
        return
    try:
        yield None
    finally:
        faulthandler.cancel_dump_traceback_later()


# ---- 用例间数据复位（2026-09-14）----
# 为什么需要：被测应用（demo）现在把合同数据放在**服务端**（详情页要读同一条真实记录），
# 新建用例会真的写进去 ⇒ 不复位的话「列表恢复 20 行」这类断言会被上一条用例的残留数据打乱，
# 而且失败原因会指向错误的地方（用例互相污染比用例失败更难查）。
# 口径：HYBRID_RESET_URL 可覆盖默认值；设为 off/0/none/空 则完全不复位（被测应用没有复位接口时）。
# 复位失败**大声告警但不中断**：那是「用例可能互相污染」的信号，绝不该被静默吞掉。
_RESET_URL = os.environ.get("HYBRID_RESET_URL", "http://localhost:8000/api/reset")
_RESET_OFF = ("", "off", "0", "none", "no", "false")


@pytest.fixture(autouse=True)
def _reset_target_data():
    """每条用例开始前把被测应用的数据复位（默认 POST http://localhost:8000/api/reset）。"""
    url = (_RESET_URL or "").strip()
    if url.lower() in _RESET_OFF:
        yield None
        return
    import urllib.request
    try:
        req = urllib.request.Request(url, data=b"", method="POST")
        with urllib.request.urlopen(req, timeout=5) as r:
            print(f"[setup] 数据复位 {url} → HTTP {r.status}", flush=True)
    except Exception as e:
        print(f"[setup] ⚠️ 数据复位失败（{url}）：{type(e).__name__}: {e}"
              f" —— 用例之间可能互相污染（要关掉这条提示：HYBRID_RESET_URL=off）", flush=True)
    yield None


@pytest.fixture(scope="session", autouse=True)
def _dump_heals_at_session_end():
    """会话结束把自愈记录落盘（可审 diff）；带 worker 后缀，避免并发同秒同名相撞。"""
    yield
    if _HEALER.events:
        worker = os.environ.get("PYTEST_XDIST_WORKER", "main")
        paths = _HEALER.dump(suffix=f"_{worker}")
        print(f"[heal] 本次运行自愈 {len(_HEALER.events)} 条 -> {paths}")


class _BrowserPool:
    """**会话级**浏览器持有者（2026-09-13 E 项提速）。

    改造前：每条用例各起一次 Chromium（实测 setup ≈0.6s/条 ×9 条 ≈5.4s，占总时长一半）。
    现在：整场（一个 worker 进程）共用一个浏览器，每条用例只新建 context + page（隔离不变：
    每个 context 有自己的 cookie/存储/trace/录像）。
    崩溃兜底：若浏览器被内核 OOM 杀掉或自身崩了 → **大声告警 + 重启**（绝不静默拿坏句柄继续跑，
    那会让后面所有用例连锁失败且原因不明）。
    """

    def __init__(self, opts):
        self._opts = opts
        self._p = None
        self.browser = None
        self.restarts = 0

    def get(self):
        from playwright.sync_api import sync_playwright
        if self._p is None:
            self._p = sync_playwright().start()
        if self.browser is None or not self.browser.is_connected():
            if self.browser is not None:
                self.restarts += 1
                print(f"[browser] ⚠️ 会话级浏览器已断开（第 {self.restarts} 次）→ 重启。"
                      f"若 dmesg 有 OOM 记录，说明内存不够（见 framework/limits.py 的并发降级）",
                      flush=True)
            self.browser = self._p.chromium.launch(**self._opts)
        return self.browser

    def close(self):
        for fn in (lambda: self.browser and self.browser.close(),
                   lambda: self._p and self._p.stop()):
            try:
                fn()
            except Exception:
                pass


def _is_headed():
    """调试·有头判定：HYBRID_HEADED=1 且不在 xdist worker 里（worker 一律无头，见 cli.py 注释）。"""
    import os as _os
    return _os.environ.get("HYBRID_HEADED", "") == "1" and "PYTEST_XDIST_WORKER" not in _os.environ


@pytest.fixture(scope="session")
def _pool():
    """会话级浏览器池（每场一个 Chromium；kill 掉也不用管，下一场重新起）。"""
    pool = _BrowserPool(_launch_opts(not _is_headed()))
    yield pool
    pool.close()


@pytest.fixture
def page(request, _pool):
    global _SHOT_N
    _SHOT_N = 0                                # 每条用例从 01 重新编号
    import re as _re
    # trace 文件名带 case_id：多用例并发/多次运行**不再互相覆盖**（原先都写 latest_trace.zip）
    _m = _re.search(r"test_(.+)", request.node.name)
    _cid = _m.group(1) if _m else request.node.name
    browser = _pool.get()                      # 会话级浏览器（崩了由 pool 重启 + 告警）
    _ctx_kw = {}
    if _DEBUG_VIDEO:                           # 调试·录制：整条用例录成 webm
        _ctx_kw = {"record_video_dir": str(RUN_LOG_DIR / "videos"),
                   "record_video_size": {"width": 1280, "height": 720}}
    context = browser.new_context(**_ctx_kw)
    context.tracing.start(screenshots=True, snapshots=True)
    pg = context.new_page()
    try:
        yield pg
    finally:
        trace_dir = RUN_LOG_DIR / "traces"
        trace_dir.mkdir(parents=True, exist_ok=True)
        context.tracing.stop(path=str(trace_dir / f"{_cid}_trace.zip"))
        _vid = pg.video if _DEBUG_VIDEO else None   # 必须在关闭前拿到 video 句柄
        context.close()                             # ⚠️ 关上下文才会把 webm 真正写盘（否则只有几 KB）
        if _vid:
            try:
                _t = RUN_LOG_DIR / "videos" / f"{_cid}.webm"
                _t.parent.mkdir(parents=True, exist_ok=True)
                _vid.save_as(str(_t))               # 改名成 <case_id>.webm（默认是随机名）
            except Exception:
                pass
        try:                                        # 清掉 Playwright 留下的随机名空壳
            for _f in (RUN_LOG_DIR / "videos").glob("page@*.webm"):
                _f.unlink()
        except Exception:
            pass
        # 注意：这里**不关浏览器**——会话级复用，由 _pool 在整场结束时关闭


@pytest.fixture
def ctx(request):
    import re
    node = request.node.name          # test_<case_id>
    m = re.search(r"test_(.+)", node)
    case_id = m.group(1) if m else "run"
    return CaseCtx(case_id, _load_data(case_id))


# ---- 操作辅助（生成用例脚本引用）----
_CURRENT_LOG: dict = {}

def _log(page, step, detail=""):
    cid = _CURRENT_LOG.get("case_id", "run")
    line = f"[TEST] {step}: {detail}"
    print(line, flush=True)
    _append_log(cid, line)

def _append_log(case_id, line):
    try:
        RUN_LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(RUN_LOG_DIR / f"{case_id}.log", "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

_INDEX: dict = {}


def _item_for(hint, page):
    """semantic_name → probe 控件项。缓存优先；未命中才重探一次（兼容弹窗后出现的控件）。

    改造前每个动作都全页 probe（并发下页面时序不稳会超时）；现在只在首次/未命中时探。
    """
    from framework.probe import probe_page
    it = _INDEX.get(hint)
    if it is None:
        for x in probe_page(page):
            _INDEX.setdefault(x.get("semantic_name"), x)
        it = _INDEX.get(hint)
    if it is None:                      # 模糊兜底（包含关系），与改造前一致
        for k, v in _INDEX.items():
            if k and (hint in k or k in hint):
                return v
    return it


def _to_ref(it):
    from framework.element_map import ElementRef
    return ElementRef(
        semantic_name=it["semantic_name"],
        test_id=it.get("test_id"),
        role=it.get("role"),
        name=it.get("name"),
        placeholder=it.get("placeholder"),
        text=it.get("text"),
        label=it.get("label"),
        nearby_text=it.get("nearby_text"),
    )


def _loc(hint, page):
    """semantic_name → 真实 locator：分层定位（Tier1/Tier2/意图复验），失败走 Healer 自愈。

    HYBRID_SELF_HEAL=0 → 关闭自愈（CI 语义：失败即报，不做任何猜测性定位）。
    """
    from framework.locator_bridge import resolve_locator
    from framework.element_map import TestStep
    it = _item_for(hint, page)
    if it is None:
        raise RuntimeError(f"元素语义未找到: {hint}")
    el = _to_ref(it)
    r = resolve_locator(page, el)
    if r["ok"]:
        if r.get("healed"):
            _HEALER.record_heal(TestStep(0, "locate", element=el, description=hint), r)
            _log(page, "heal", f"{hint} 指纹自愈 -> {r['strategy']} conf={r['confidence']}")
        return r["locator_obj"]
    if _SELF_HEAL:
        h = _HEALER.try_heal(page, TestStep(0, "locate", element=el, description=hint))
        if h.get("recovered"):
            _log(page, "heal", f"{hint} 自愈 -> {h['strategy']} conf={h['confidence']}")
            return h["locator_obj"]
        raise RuntimeError(f"元素定位失败且自愈未成功: {hint}（{h.get('reason') or '未知'}）")
    raise RuntimeError(f"元素定位失败: {hint}（{r.get('reason')}）")


# ---- 调试模式（cli run --debug）产物：逐步截图 + 录像 ----
# HYBRID_SHOTS=1 → 每步存一张 PNG（直接打开就能看"这一步长什么样"，序号即执行顺序）
# HYBRID_VIDEO=1 → 整个用例录成 webm（本机没有图形显示时的"看得见"方案）
_DEBUG_SHOTS = os.environ.get("HYBRID_SHOTS", "") == "1"
_DEBUG_VIDEO = os.environ.get("HYBRID_VIDEO", "") == "1"
_SHOT_N = 0


def _shot(page, tag):
    """调试模式：把当前页面存成 PNG（失败不影响用例执行）。"""
    global _SHOT_N
    if not _DEBUG_SHOTS:
        return
    try:
        import re as _re2
        _SHOT_N += 1
        d = RUN_LOG_DIR / "shots" / _CURRENT_LOG.get("case_id", "run")
        d.mkdir(parents=True, exist_ok=True)
        safe = _re2.sub(r"[^0-9A-Za-z一-鿿]+", "_", str(tag))[:40].strip("_") or "step"
        page.screenshot(path=str(d / f"{_SHOT_N:02d}_{safe}.png"))
    except Exception:
        pass


def _act(page, action, semantic=None, primary=None, value=None):
    """执行动作：主用【确定性 locator】(零探测)；主失效才走语义定位/自愈兜底。

    健康页面 → 与改造前完全一致（零额外开销）；页面漂移 → 自动降级/自愈而非硬失败。
    HYBRID_SELF_HEAL=0 → 不做语义兜底（要"失败即报"时用）。
    """
    loc = None
    if primary is not None:
        try:
            cand = primary(page)
            n = cand.count()
            if n == 1:
                loc = cand
            elif n == 0:
                _log(page, "warn", f"primary 未命中 → 语义兜底 {semantic}")
            else:
                _log(page, "warn", f"primary 命中 {n} 个(非唯一) → 语义兜底 {semantic}")
        except Exception as e:
            _log(page, "warn", f"primary 失效 → 语义兜底 {semantic} ({type(e).__name__})")
    if loc is None:
        if not _SELF_HEAL:
            raise RuntimeError(f"确定性 locator 失效且 HYBRID_SELF_HEAL=0（不做推测性定位）: {semantic or action}")
        if not semantic:
            raise RuntimeError(f"确定性 locator 失效且无语义兜底: {action}")
        loc = _loc(semantic, page)
    if action == "click":
        loc.click()
    elif action == "fill":
        loc.fill(value if value is not None else "")
    elif action == "select":
        loc.select_option(value if value is not None else "")
    elif action == "check":
        loc.check()
    elif action == "press_enter":
        loc.press("Enter")
    else:
        raise NotImplementedError(f"未知动作: {action}")
    _shot(page, f"{action}_{semantic or ''}")      # 调试模式：动作执行后存一张图


def _click(page, hint):
    return _act(page, "click", semantic=hint)


def _fill(page, hint, value):
    return _act(page, "fill", semantic=hint, value=value)


def _select(page, hint, value):
    return _act(page, "select", semantic=hint, value=value)


def _check(page, hint):
    return _act(page, "check", semantic=hint)


def _press_enter(page, hint):
    return _act(page, "press_enter", semantic=hint)

def _assert_text(page, text, desc=""):
    loc = page.get_by_text(text)
    loc.first.wait_for(timeout=5000)
    from playwright.sync_api import expect
    expect(loc.first).to_be_visible()
    line = f"[CHECK] ✓ 断言: {desc or text}"
    print(line, flush=True)
    _append_log(_CURRENT_LOG.get("case_id", "run"), line)
    _shot(page, f"assert_{text}")                  # 调试模式：断言通过后也存一张


# ---- 断言辅助（2026-09-13 D 项：断言类型从「只有文本」扩展到 11 种）----
# 约定：全部 web-first（playwright expect 自动重试）；成功统一打印 [CHECK] ✓ 断言: …
#       并写逐用例日志（调试模式另存一张截图）。
#       ❗ 缺字段 / 定位不到时，由**生成的脚本** pytest.fail（绝不静默少验一步 = 假绿）。


def _ok(page, desc, tag, detail=""):
    line = f"[CHECK] ✓ 断言: {desc}" + (f"（{detail}）" if detail else "")
    print(line, flush=True)
    _append_log(_CURRENT_LOG.get("case_id", "run"), line)
    _shot(page, f"assert_{tag}")


def _resolve(page, primary, semantic=None, *, unique=True):
    """断言定位：主用确定性 locator；失效才走语义兜底/自愈（与 _act 同策略）。

    unique=False 用于「复数元素」断言（count）——命中的 locator 本来就允许多个/零个，
    不能按「必须唯一」判定。
    """
    loc = None
    if primary is not None:
        try:
            cand = primary(page)
            n = cand.count()
            if n == 1 or not unique:
                loc = cand
            elif n == 0:
                _log(page, "warn", f"断言 primary 未命中 → 语义兜底 {semantic}")
            else:
                _log(page, "warn", f"断言 primary 命中 {n} 个(非唯一) → 语义兜底 {semantic}")
        except Exception as e:
            _log(page, "warn", f"断言 primary 失效 → 语义兜底 {semantic} ({type(e).__name__})")
    if loc is None:
        if not unique:
            raise RuntimeError(f"复数元素断言必须有确定性 locator（selector / 已映射 element）: {semantic}")
        if not _SELF_HEAL:
            raise RuntimeError(f"断言 locator 失效且 HYBRID_SELF_HEAL=0（不做推测性定位）: {semantic}")
        if not semantic:
            raise RuntimeError("断言 locator 失效且无语义兜底（该断言既没 selector 也没 element）")
        loc = _loc(semantic, page)
    return loc


def _assert_visible(page, primary, semantic=None, desc=""):
    """元素可见（如弹窗打开、提示出现）。"""
    loc = _resolve(page, primary, semantic)
    _expect(loc.first).to_be_visible()
    _ok(page, desc or f"{semantic or '该元素'} 可见", f"visible_{semantic or 'selector'}", "visible")


def _assert_hidden(page, primary, semantic=None, desc=""):
    """元素不可见/不存在（如弹窗关闭）。"""
    loc = _resolve(page, primary, semantic)
    _expect(loc.first).to_be_hidden()
    _ok(page, desc or f"{semantic or '该元素'} 不可见", f"hidden_{semantic or 'selector'}", "hidden")


def _assert_count(page, n, primary, semantic=None, desc=""):
    """元素数量（如结果行数）——注意 expect 必须是**操作前可确定**的值，别拿运行时计数硬凑。"""
    loc = _resolve(page, primary, semantic, unique=False)
    _expect(loc).to_have_count(int(n))
    _ok(page, desc or f"{semantic or '该元素'} 数量 = {n}", f"count_{semantic or 'selector'}", f"count={n}")


def _assert_attr(page, name, value, primary, semantic=None, desc=""):
    """元素属性值（如 data-field / class / href）。"""
    loc = _resolve(page, primary, semantic)
    _expect(loc.first).to_have_attribute(name, str(value))
    _ok(page, desc or f"{semantic or '该元素'} 属性 {name}={value}", f"attr_{name}", f"{name}={value}")


def _assert_value(page, value, primary, semantic=None, desc=""):
    """输入框当前值（注意：断言「刚填进去的值」= 输入回显，属假绿；要验「被清空/被改写」）。"""
    loc = _resolve(page, primary, semantic)
    _expect(loc.first).to_have_value(str(value))
    _ok(page, desc or f"{semantic or '该元素'} 输入值 = {value!r}", f"value_{semantic or 'selector'}", f"value={value!r}")


def _assert_checked(page, primary, semantic=None, desc=""):
    loc = _resolve(page, primary, semantic)
    _expect(loc.first).to_be_checked()
    _ok(page, desc or f"{semantic or '该元素'} 已勾选", f"checked_{semantic or 'selector'}", "checked")


def _assert_unchecked(page, primary, semantic=None, desc=""):
    loc = _resolve(page, primary, semantic)
    _expect(loc.first).not_to_be_checked()
    _ok(page, desc or f"{semantic or '该元素'} 未勾选", f"unchecked_{semantic or 'selector'}", "unchecked")


def _assert_enabled(page, primary, semantic=None, desc=""):
    loc = _resolve(page, primary, semantic)
    _expect(loc.first).to_be_enabled()
    _ok(page, desc or f"{semantic or '该元素'} 可用", f"enabled_{semantic or 'selector'}", "enabled")


def _assert_disabled(page, primary, semantic=None, desc=""):
    loc = _resolve(page, primary, semantic)
    _expect(loc.first).to_be_disabled()
    _ok(page, desc or f"{semantic or '该元素'} 不可用", f"disabled_{semantic or 'selector'}", "disabled")


def _assert_url(page, expected, desc=""):
    """页面 URL：以 http 开头 = 精确匹配；否则按「包含」匹配（跨页面跳转常用）。"""
    import re as _re
    exp = str(expected)
    if exp.startswith("http"):
        _expect(page).to_have_url(exp)
    else:
        _expect(page).to_have_url(_re.compile(_re.escape(exp)))
    _ok(page, desc or f"URL 含 {exp}", f"url_{exp[:24]}", "url")
