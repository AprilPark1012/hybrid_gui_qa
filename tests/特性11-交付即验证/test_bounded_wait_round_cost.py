# -*- coding: utf-8 -*-
"""一类判据：**有界等待的「每轮成本」必须被限住、且慢轮要自己说出来**（2026-11-02）。

## 为什么加这道闸

用户 Windows 实测：一条 60 步用例里 4 处「等订单状态自动流转」的断言声明 160s 预算，
日志却写着 `轮询 3 轮 · 最后读到 '履行中'` —— **160s 只赌了 3 次**，而业务值约 150s 才变，
正好卡在临界：第 1 轮红、第 2 轮才绿（白烧一轮 AI 生成 + 一轮试跑 ~15 分钟）。

两个方向一起治：

1. **每轮成本必须被限住**（`_FAST_WINDOW_MS`）：「重放最近一次搜索」是**每轮都做**的动作，
   慢目标下定位预算会被调到 15000ms，一次重放就可能吃掉几十秒。夹到 2s 后同样 160s
   能轮询几十轮。**只夹等待上限，不改「探到就走」的语义。**
2. **慢轮必须自己说出来**：原来日志只写「轮询 3 轮」，分不清「业务没流转」还是「轮询太慢」。
   慢轮逐条打印 `轮询第 N 轮花了 X.Xs（读到 …）`，快轮不打印（不刷屏）。

判据直接打**运行时产物** `scripts/generated/_harness.py`（生成器模板的落地产物），
而不是只读模板源码 —— 生成器改了但没重新 generate，产物仍是旧的，这道闸必须能发现。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "generated"))

import _harness as H                                                               # noqa: E402


class _FakeFirst:
    def __init__(self, sink):
        self._sink = sink

    def wait_for(self, state=None, timeout=None):
        self._sink["timeout"] = timeout          # 记下真正传进去的等待上限
        return None


class _FakeCand:
    def __init__(self, sink):
        self.first = _FakeFirst(sink)

    def count(self):
        return 1


class _FakePage:
    """够用的 page 替身：记 default_timeout 的设置历史。"""

    def __init__(self, raise_on_click=False):
        self.default_timeout = 30000
        self.set_history = []
        self._raise = raise_on_click
        self.waits = []

    def set_default_timeout(self, ms):
        self.default_timeout = ms
        self.set_history.append(ms)

    def wait_for_timeout(self, ms):
        self.waits.append(ms)


# ------------------------------------------------- ① 每轮成本被夹住

def test_fast_window_clamps_locate_wait():
    """开着快速窗口时，定位等待必须被夹到窗口以内（慢目标 15s 预算不许每轮吃满）。"""
    sink = {}
    cand = _FakeCand(sink)
    old = H._LOCATE_TIMEOUT_MS
    try:
        H._LOCATE_TIMEOUT_MS = 15000                 # 复刻慢目标配置
        H._FAST_WINDOW_MS = 0
        H._count_attached(cand)
        assert sink["timeout"] == 15000, "[NG] 没开窗口时不该改动等待上限: %r" % (sink["timeout"],)

        H._FAST_WINDOW_MS = 2000
        H._count_attached(cand)
        assert sink["timeout"] == 2000, "[NG] 开了窗口仍未夹住定位等待: %r" % (sink["timeout"],)

        # 显式传了更小的 timeout_ms 时，仍然取更小值（不许被窗口放大）
        H._count_attached(cand, 500)
        assert sink["timeout"] == 500, "[NG] 显式更小的等待被窗口放大了: %r" % (sink["timeout"],)
    finally:
        H._LOCATE_TIMEOUT_MS = old
        H._FAST_WINDOW_MS = 0


def test_replay_search_sets_and_restores_fast_window():
    """重放搜索必须**自己开窗口、自己还原** —— 不许把页面默认超时留在小值上（会连带把
    其它正常动作的超时也改掉，那是最难查的一类污染）。"""
    page = _FakePage()
    old_search = H._LAST_SEARCH
    try:
        H._LAST_SEARCH = "任意控件"
        H._replay_last_search(page, budget_ms=2000)      # 点击会抛（替身没有 _act），走 finally
        assert H._FAST_WINDOW_MS == 0, "[NG] 快速窗口没还原: %r" % (H._FAST_WINDOW_MS,)
        assert page.default_timeout == 30000, (
            "[NG] 页面默认超时被留在 %r（应为原值 30000）" % (page.default_timeout,))
    finally:
        H._LAST_SEARCH = old_search


def test_replay_search_returns_false_without_recorded_search():
    """没有搜索记录时如实返回 False（不猜、不假装重放成功）—— 这条是原有契约，别被改坏。"""
    page = _FakePage()
    old_search = H._LAST_SEARCH
    try:
        H._LAST_SEARCH = ""
        assert H._replay_last_search(page) is False
    finally:
        H._LAST_SEARCH = old_search


# ------------------------------------------------- ② 慢轮要自己说出来

def test_first_row_wait_has_bounded_round_logging():
    """慢轮日志必须**两级**：个体（>=5s、最多 3 条）+ 一条汇总。

    反例（2026-11-02 实测）：阈值定 1.0s 时，健康机器每轮 ~1.09s（含 500ms 固定间隔），
    一次 160s 等待打出了 **243 行**「轮询第 N 轮花了 …」，把真正的信号埋掉。
    本项目对「刷屏」的立场是明确的：日志要能一眼看出问题，而不是淹掉问题。
    """
    src = (ROOT / "scripts" / "generated" / "_harness.py").read_text(encoding="utf-8")
    i = src.find("def _assert_first_row")
    j = src.find("\ndef ", i + 10)
    seg = src[i:j if j > 0 else len(src)]

    assert "_round_t0" in seg, "[NG] 没有逐轮计时"
    assert "轮询第" in seg, "[NG] 慢轮个体日志没了"
    assert ">= 5.0" in seg, "[NG] 个体日志阈值必须 >= 5s（1s 会刷屏，实测 243 行）"
    assert "_slow_n <= 3" in seg, "[NG] 个体慢轮日志必须有条数上限"
    assert "_wait_summary(" in seg, "[NG] 缺「一条汇总」（总轮数 / 慢轮数 / 最慢一轮）"
    # 汇总必须**成功与超时两条路都打**（超时那条才是最需要它的）
    assert seg.count("_wait_summary(") >= 2, "[NG] 汇总只在一条路径上打（成功/超时都要）"


def test_wait_summary_reports_rounds_and_slowest():
    """汇总必须把「共几轮 / 几轮慢 / 最慢多久」说清楚 —— 这是分开
    「业务没流转」与「轮询太慢」的唯一依据。"""
    lines = []

    class _P:
        pass

    orig = H._log

    def _fake_log(page, level, msg, *a, **k):
        lines.append((level, msg))

    try:
        H._log = _fake_log
        H._wait_summary(_P(), rounds=3, slow_n=3, slowest=47.2, slowest_at=2, refresh="research")
    finally:
        H._log = orig
    assert lines, "[NG] 汇总什么都没打"
    lvl, msg = lines[0]
    assert "3 轮" in msg and "慢轮 3" in msg and "47.2" in msg, "[NG] 汇总信息不全: %r" % (msg,)
    assert "research" in msg, "[NG] 汇总要带上 refresh 口径"
