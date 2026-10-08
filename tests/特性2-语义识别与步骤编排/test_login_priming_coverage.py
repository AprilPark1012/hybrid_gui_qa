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
EXPL = (REPO / "framework" / "tools" / "explore" / "explorer.py").read_text(encoding="utf-8")
GEN = (REPO / "framework" / "tools" / "generate" / "generator.py").read_text(encoding="utf-8")
LOGIN = (REPO / "framework" / "tools" / "run" / "login.py").read_text(encoding="utf-8")

# [!] 判据口径必须跟着实现走：批 5 把 generate 侧的两处调用收成了统一入口 `_ensure_login_for`，
#    这里就要同步（我第一次没改 -> 判据自己变成假红 —— 与 pitfalls 里"判据口径随重构走"同一条）。
_PROBE_CALL_EXPL = "ensure_logged_in(ctx, _base_of"   # explorer 侧：单页 / 跨页
_PROBE_CALL_GEN = "_ensure_login_for(ctx, "           # generate 侧：(1) 单页惯例 (2) 声明页（统一入口）
_EXEC_CALL = "_install_login(context, _AUTH_TABLE"


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
    """判据 1：四处探测路径都要有登录前置调用（explorer 两处 + generate 两处）。"""
    n_expl = _count(EXPL, _PROBE_CALL_EXPL)
    n_gen = _count(GEN, _PROBE_CALL_GEN)
    assert n_expl >= 2, (
        f"explorer 里的登录前置只有 {n_expl} 处（应 ≥2：单页 + 跨页）"
        "—— 漏的那条路径会静默只探到登录页控件")
    assert n_gen >= 2, (
        f"generate 现场探测的登录前置只有 {n_gen} 处（应 ≥2：(1) 单页惯例探测 (2) 声明页探测）"
        "—— 漏的那条 = 缺口补不上，映射质量闸会把 generate 打红（实测踩过）")
    assert "def _ensure_login_for(" in GEN, "generate 侧要有登录前置的唯一入口"


def test_execution_side_installs_login():
    """判据 2：执行侧（生成物 harness 的 page fixture）也要注入，且按 case_id 查表。"""
    assert _count(GEN, _EXEC_CALL) >= 1, (
        "harness 的 page fixture 没有按 `_auth.json` 注入登录态 -> 生成的用例会整条跑在登录页上")
    assert "_auth.json" in GEN, "没有写/读 `_auth.json` 的逻辑 -> 执行侧拿不到 auth 声明"
    assert "登录前置失败" in GEN, "登录失败必须是**大声失败**（静默继续 = 整条用例白跑还报绿）"


def test_login_module_is_the_single_source():
    """判据 3：登录实现在 `framework/tools/run/login.py` 一处（别处不许再写一份）。"""
    assert "def ensure_logged_in(" in LOGIN and "def login_token(" in LOGIN, "登录唯一实现缺函数"
    # 只允许"转发/导入"用，不允许别处再实现登录请求
    assert "urlopen" not in EXPL, "explorer 里不该自己发登录请求（应走 run/login.py）"
    assert "urlopen" not in GEN.split("_install_login", 1)[0] or "login.py" in GEN


def test_negative_missing_a_call_is_caught():
    """判据 4（负向自证）：删掉任一调用点 -> 同一判据必须判红。"""
    broken_expl = EXPL.replace("_lg = ensure_logged_in(ctx, _base_of(url), auth or {})", "")
    assert broken_expl != EXPL, "负向自证前提不成立（找不到单页那行调用）—— 判据需同步更新"
    assert _count(broken_expl, _PROBE_CALL_EXPL) < 2, "删掉单页调用后判据仍通过 -> 判据是恒真的"
    broken_gen = GEN.replace("_ensure_login_for(ctx, TARGET_URL, _decl_auth)", "")
    assert broken_gen != GEN, "负向自证前提不成立（找不到 generate 单页惯例那行）"
    assert _count(broken_gen, _PROBE_CALL_GEN) < 2, "删掉 generate 一条路径后判据仍通过 -> 守门失效"
    broken_gen = GEN.replace("_install_login(context, _AUTH_TABLE.get(_cid)", "_install_login(context, {}")
    assert _count(broken_gen, _EXEC_CALL) < 1, "把执行侧注入改坏后判据仍通过 -> 守门失效"
