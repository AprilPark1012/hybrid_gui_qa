"""登录前置的**覆盖面**守门（P22 批 5 · J7）—— 秒级源码判据，不需 demo/浏览器。

为什么单独立一条：登录前置有**三处探测路径 + 一处执行路径**，漏任何一处的表现都是
"看着跑通了、其实那一处只拿到登录页控件"（静默失效，最难发现）。实测过的教训形态：
`explorer` 单页/跨页都接了、但 `generate` 的现场探测没接 -> 手写用例集体报「元素未映射」。

四处（缺一不可）：
  (1) `explorer._collect_page_context`（单页探测）
  (2) `explorer._collect_pages_context`（跨页探测）
  (3) `generator._probe_declared_pages`（generate 现场探测声明页）
  (4) 生成物 harness 的 `page` fixture（执行侧，按 case_id 查 `_auth.json` 注入）

判据口径：**数调用点**（`ensure_logged_in(ctx, _base_of...` / `_install_login(context, ...`），
import 行不算；并附**负向自证**（删掉任一处 -> 必须判红）。

跑法（秒级）：python -m pytest tests/特性2-语义识别与步骤编排/test_login_priming_coverage.py -q
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCAN_PAGES = (REPO / "framework" / "features" / "f03_locate" / "scan_pages_probe.py").read_text(encoding="utf-8")
                 # 片 3c（2026-10-12）：跨页探测骨架的唯一入口，登录/前置/行内列都在它里面
EXPL = (REPO / "framework" / "features" / "f02_semantic" / "explorer_explore.py").read_text(encoding="utf-8")
GEN = (REPO / "framework" / "features" / "f02_semantic" / "generator_generate.py").read_text(encoding="utf-8")
LOGIN = (REPO / "framework" / "shared" / "login.py").read_text(encoding="utf-8")

# [!] 判据口径必须跟着实现走：批 5 把 generate 侧的两处调用收成了统一入口 `_ensure_login_for`，
#    这里就要同步（我第一次没改 -> 判据自己变成假红 —— 与 pitfalls 里"判据口径随重构走"同一条）。
_PROBE_CALL_EXPL = "ensure_logged_in(ctx, _base_of"   # explorer 侧：单页 / 跨页
_PROBE_CALL_GEN = "_ensure_login_for(ctx, "           # generate 侧：(1) 单页惯例 (2) 声明页（统一入口）
_EXEC_CALL = "_login_do(page,"          # 执行侧（V8.5.1 登录步骤化后）


def _count(src: str, needle: str) -> int:
    """数**调用点** —— 跳过 import 行（"只 import 没调用"不算接线）**和 def 行**
    （`def _ensure_login_for(ctx, ...)` 这种定义行会被子串匹配误算成一次调用，实测踩过）。"""
    n = 0
    for line in src.splitlines():
        s = line.strip()
        if s.startswith(("from ", "import ", "def ")):
            continue
        if needle in s:
            n += 1
    return n


def test_three_probe_paths_install_login():
    """判据 1：每条探测路径都要有登录前置调用。

    [!] 片 3c（2026-10-12，B1 三合一）后口径更新：**跨页**路径的登录前置跟着骨架搬到了
    `probe/scan_pages.py`；explorer 只剩**单页**那处。判据改为：
      explorer ≥1（单页）+ scan_pages ≥1（跨页骨架）+ generate ≥2（单页惯例 + 声明页）。
    """
    n_expl = _count(EXPL, _PROBE_CALL_EXPL)
    n_sp = _count(SCAN_PAGES, _PROBE_CALL_EXPL)
    n_gen = _count(GEN, _PROBE_CALL_GEN)
    assert n_expl >= 1, (
        f"explorer 里的登录前置只有 {n_expl} 处（单页路径那处必须还在）"
        "—— 漏的那条路径会静默只探到登录页控件")
    assert n_sp >= 1, (
        f"scan_pages（跨页骨架）里的登录前置只有 {n_sp} 处"
        "—— 骨架收敛后跨页的登录前置只可能在这里，漏了整条跨页链路都会落到登录页")
    # [!] 片 3c（2026-10-12）：generate 侧**声明页**那处跟着骨架搬到了 scan_pages，
    #   所以 generator 里现在只剩「单页惯例探测」1 处；声明页那处改在 scan_pages 里数。
    #   两条路径仍缺一不可（漏一条 = 缺口补不上，映射质量闸会打红 —— 实测踩过）。
    assert n_gen >= 1, (
        f"generate 单页惯例探测的登录前置只有 {n_gen} 处（应 ≥1）—— 漏了会静默只探到登录页控件")
    assert n_sp >= 1, (
        f"scan_pages（跨页骨架）里的登录前置只有 {n_sp} 处"
        "—— generate 的声明页探测 + explore 的跨页探测都走它，漏了整条跨页链路都会落到登录页")
    assert "def _ensure_login_for(" in GEN, "generate 侧要有登录前置的唯一入口"


def test_execution_side_installs_login():
    """判据 2：执行侧登录必须**可见地执行**（V8.5.1 登录步骤化后口径已变）。

    [!] 这条判据**随重构改口径**（2026-10-12 V8.5.1）：执行侧原来靠 harness 读 `_auth.json`
    注入 token —— 那文件由生成期写出却被 .gitignore 忽略、**不进交付包**，收包方 run 时
    登录前置会**静默失效**（报「元素语义未找到」而真因是"整条用例跑在登录页上"）。
    现在改为：场景 `login:` 声明 -> 生成期展开成用例**前导步骤**（`_login_do`/`_login_wait`）。
    所以"执行侧有没有登录"要盯的是**展开出来的调用**，而不是那个 json。
    """
    assert _count(GEN, _EXEC_CALL) >= 1, (
        "生成物模板里没有 `_login_do(page, ...)` -> 登录步骤不会真的执行，"
        "用例会整条跑在登录页上（这正是 V8.3 的静默失效形态）")
    assert "def _login_wait(" in GEN, "缺 `_login_wait` -> 登录成功判定会退化成固定 sleep"
    # [!] 只查**代码行**：GEN 里"已删除 `_auth.json`"这类**注释**不该算残留
    #   （第一版直接 `"_auth.json" not in GEN` -> 被自己的说明注释判红）。
    _gen_code = "\n".join(l.split("#", 1)[0] for l in GEN.splitlines())
    assert '"_auth.json"' not in _gen_code and "'_auth.json'" not in _gen_code, (
        "`_auth.json` 那套必须已删除（它不进交付包 -> 收包方拿不到登录态）")
    assert "def _login_do(" in GEN, "登录动作执行函数不见了"


def test_login_module_is_the_single_source():
    """判据 3：登录实现在 `framework/shared/login.py` 一处（别处不许再写一份）。"""
    assert "def ensure_logged_in(" in LOGIN and "def login_token(" in LOGIN, "登录唯一实现缺函数"
    # 只允许"转发/导入"用，不允许别处再实现登录请求
    assert "urlopen" not in EXPL, "explorer 里不该自己发登录请求（应走 run/login.py）"
    # [!] 2026-10-12 改口径：原来这条用 `GEN.split("_install_login",1)[0]` 判断"generator 前段没有
    #   urlopen" —— **太脆**：generator 里还有「setup 数据复位」的 urlopen（与登录无关），
    #   只要 `_install_login`（生成脚本模板里的片段）在前面就误报。改成**直接盯意图**：
    #   generate 侧的登录前置必须走 `run/login.py`（`_ensure_login_for` 是它的统一入口），
    #   不许自实现一套登录请求。
    assert "def _ensure_login_for(" in GEN, "generate 侧登录前置的统一入口 `_ensure_login_for` 不见了"
    assert ("from framework.shared.login import" in GEN) or ("run.login" in GEN), \
        "generate 侧登录前置没走 run/login.py（会漂成第二份实现）"


def test_negative_missing_a_call_is_caught():
    """判据 4（负向自证）：删掉任一调用点 -> 同一判据必须判红。"""
    broken_expl = EXPL.replace("_lg = ensure_logged_in(ctx, _base_of(url), auth or {})", "")
    assert broken_expl != EXPL, "负向自证前提不成立（找不到单页那行调用）—— 判据需同步更新"
    assert _count(broken_expl, _PROBE_CALL_EXPL) < 2, "删掉单页调用后判据仍通过 -> 判据是恒真的"
    # P25 片 4：目标地址改成**运行期**读取（`TARGET_URL` 常量 -> `target_url()`），
    # 判据里这行源码串必须同步，否则负向自证的**前提**不成立（找不到那行 = 自证恒真）。
    broken_gen = GEN.replace("_ensure_login_for(ctx, target_url(), _decl_auth)", "")
    assert broken_gen != GEN, "负向自证前提不成立（找不到 generate 单页惯例那行）"
    assert _count(broken_gen, _PROBE_CALL_GEN) < 2, "删掉 generate 一条路径后判据仍通过 -> 守门失效"
    # [!] V8.5.1：执行侧改口径后，负向自证也要跟着改 —— 原来打坏的是 `_install_login` 调用，
    #   现在执行侧靠 `_login_do` 展开，所以要打坏**那个**（否则自证恒真 = 判据形同虚设）。
    # [!] 要打坏**渲染处**（`_login_do(page,` 出现在渲染模板里），
    #   只改 `def _login_do(` 定义是没用的 —— 计数仍 >=1，自证就成了永真断言。
    broken_gen = GEN.replace("_login_do(page, ", "_login_do_RENAMED(page, ")
    assert broken_gen != GEN, "负向自证前提不成立（找不到渲染处的 `_login_do(page,`）"
    assert _count(broken_gen, _EXEC_CALL) < 1, "把执行侧登录调用打坏后判据仍通过 -> 守门失效"
