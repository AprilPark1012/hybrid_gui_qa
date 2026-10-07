"""「点击后等页面就绪」契约（P22 批 1/3 · J2）—— 秒级源码守门，不需 demo/浏览器。

起因（真值 · P22 §二 缺口 1b）：
  · demo 的「切换为订单管理员」实现是 `location.reload()`（`demo/auth.js:130`）-> 页面换新文档；
  · 而生成物的 `_act` 以前只有 `loc.click()`（`generator.py:1909-1910`），**之后不等任何状态**
    -> 紧接着的步骤落在旧文档上 / 新页面还没渲染完 -> 竞态（假红，或更糟的假绿）；
  · 只有 `_goto()` 才等 `body[data-hybrid-ready]`（`generator.py:1399+`）。
AprilPark1012 2026-09-29 拍：**补能力**（不绕过、不用 `?demo_role=` 回避）。

判据口径（J2）：
  1. 生成物模板的 `_act` 里，`click` 分支**必须**在 `loc.click(...)` 之后调用 `_wait_after_action(page)`
  2. `_wait_after_action` 必须用**导航事件**判定（`framenavigated`），**不许**用固定 sleep 顶替
     （"固定 sleep 是把环境噪声变成业务结论的经典途径" —— 本项目既有红线）
  3. 等就绪用的契约必须与 `_goto` **同源**（`body[data-hybrid-ready='1']`），不另立一套就绪标准
  4. **负向自证**：把调用删掉的源码喂给同一判据函数 -> 必须判红（防判据写成恒真）

跑法（秒级）：
    python -m pytest tests/特性8-质量闸门体系/test_click_then_ready_contract.py -q
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = (REPO / "framework" / "tools" / "generate" / "generator.py").read_text(encoding="utf-8")
# P22 批 3：等待逻辑的**唯一实现**在框架侧（生成物模板只转发）-> 判据钉在这里
WAITS = (REPO / "framework" / "tools" / "run" / "waits.py").read_text(encoding="utf-8")
READY_TOKEN = "body[data-hybrid-ready='1']"


def _click_branch_waits(src: str) -> bool:
    """判据本体（抽成函数 -> 可以被负向自证喂"坏源码"）：click 分支点完必须等。"""
    if "if action == \"click\":" not in src:
        return False
    # 取 click 分支到下一个分支之间的片段
    seg = src.split('if action == "click":', 1)[1]
    seg = seg.split('elif action ==', 1)[0]
    return "loc.click(" in seg and "_wait_after_action(page)" in seg


def _has_nav_event_wait(waits_src: str) -> bool:
    """判据本体：等待用导航事件 + 同源 ready 契约，而不是固定 sleep（检查唯一实现那份）。"""
    return ('"framenavigated"' in waits_src) and ("hybrid-ready" in waits_src)


def _template_has_second_impl(src: str) -> bool:
    """负向判据本体：生成物模板里**不许**再出现第二份事件等待实现（只许转发）。"""
    return '"framenavigated"' in src


def test_act_click_waits_after_action():
    """判据 1（正向）：click 之后必须等页面就绪。"""
    assert _click_branch_waits(SRC), (
        "`_act` 的 click 分支点完没有等页面就绪 -> 「切换角色」这类 location.reload() 的动作"
        "会让后续步骤撞重载竞态（缺口 1b 复发）")


def test_wait_uses_navigation_event_not_sleep():
    """判据 2/3（正向）：唯一实现用导航事件判定 + 就绪契约与 `_goto` 同源。"""
    assert _has_nav_event_wait(WAITS), (
        "框架侧 `framework/tools/run/waits.py` 必须用 framenavigated 事件判定导航、并等 "
        f"{READY_TOKEN}（与 _goto 同源）；用固定 sleep 顶替是不允许的")


def test_template_forwards_instead_of_reimplementing():
    """判据 3b：模板里**不许有第二份实现**（只许转发到框架唯一实现）。"""
    assert "from framework.tools.run.waits import wait_after_action" in SRC, (
        "生成物模板没有转发到框架唯一实现 -> 又变成两份实现，迟早漂移")
    assert not _template_has_second_impl(SRC), (
        "生成物模板里出现了 framenavigated 等待实现 -> 第二份实现，违反单一来源")


def test_negative_missing_call_is_caught():
    """判据 4（负向自证）：删掉调用后，同一判据必须判红（证明它不是在检查"文件里有这个词"）。"""
    broken = SRC.replace("        _wait_after_action(page)\n", "")
    assert broken != SRC, "负向自证的前提（能找到那行调用）不成立 —— 判据需要同步更新"
    assert not _click_branch_waits(broken), "删掉 `_wait_after_action(page)` 后判据仍通过 -> 判据是恒真的"


def test_negative_sleep_instead_of_event_is_caught():
    """判据 4b（负向自证）：把唯一实现里的事件等待换掉，判据必须判红。"""
    broken = WAITS.replace('"framenavigated"', '"__no_such_event__"')
    assert broken != WAITS, "负向自证的前提不成立 —— 判据需要同步更新"
    assert not _has_nav_event_wait(broken), "换成非导航事件后判据仍通过 -> 判据没在真正检查机制"


def test_negative_second_impl_is_caught():
    """判据 4c（负向自证）：模板里塞回一份实现 -> 必须判红。"""
    broken = SRC + '\n_wait_after_action = lambda p: p.on("framenavigated", None)\n'
    assert _template_has_second_impl(broken), "塞回第二份实现后判据没抓到 -> 单一来源守门失效"


def test_ready_contract_still_single_source():
    """回归：就绪契约仍是那一份 + 超时仍来自可配置常量（不许出现第二套 ready 标记写法）。

    [!] `_READY_TIMEOUT_MS` / `_LOCATE_TIMEOUT_MS` 住在 **`_CONFTEST_TEMPLATE` 字符串里**
    （生成物的模块级常量），**不是** `generator` 模块的属性 -> 判据只能查源码文本，不能 `G._READY_TIMEOUT_MS`
    （写错过一次：那样会 AttributeError）。
    """
    # [!] 实现移到框架侧之后，generator 里只剩 `_goto` 那一份调用 -> 断言从 >=2 改回 >=1
    #    （判据口径要跟着结构性重构走，否则就会像这次一样"自己变成假红"）
    assert SRC.count(READY_TOKEN) >= 1, "生成物侧的等就绪调用丢了 -> 生成物不再等页面就绪"
    assert "hybrid-ready" in WAITS, "框架唯一实现里没有 ready 契约 -> 等待口径与 _goto 分叉了"
    assert "_READY_TIMEOUT_MS = int(os.environ.get(" in SRC, (
        "就绪超时不再来自可配置常量（HYBRID_READY_TIMEOUT）-> 慢机器/慢页面上无法放宽")
