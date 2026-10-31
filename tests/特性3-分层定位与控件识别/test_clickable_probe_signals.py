# -*- coding: utf-8 -*-
"""一类判据：**可点击性补探**（A+ 档能力 2，2026-10-31）。

## 守的是什么

默认选择器 `probe.INTERACTIVE_SELECTOR` 只认 button / input / select / textarea / a[href]
以及少量 `[role=...]`；老系统里大量可点元素是裸 `div[onclick]`、无 href 的 `a`、`canvas onclick`、
`img onclick`，这类元素**无障碍树也看不见**（实测非语义页 13 个可点元素里 5 个降级成纯文本、
1 个彻底消失）。于是 AI 以为"这里不能点"，用例漏测，而整条链路全绿 —— 静默错误。

## 判据口径（宁漏不误伤）

* 显式事件处理器（`onclick` 属性 / CDP 查到 click 监听器）=> 直接采信；
* 纯样式类弱信号（`cursor:pointer` / `tabindex` / `contenteditable`）=> **需两条互相印证**才采信；
* 一条弱信号都不许单独放行 —— 现代页面几乎处处 `cursor:pointer`，
  放行它等于给每页加几十条假控件，噪音会把真信号埋掉。

## 这些判据证明什么 / 不证明什么

* 证明：判定口径就是上面写的三条，且**关掉开关一定收空**（负向自证，防判据恒真）；
* 不证明：真实浏览器上补出来的元素一定点得动 —— 那属于二类（需要 demo），不在这里假绿。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from framework.features.f03_locate import clickable_probe as CP                     # noqa: E402


# --------------------------------------------------------------- 纯判定口径

def test_onclick_alone_is_enough():
    """显式 onclick 属性 = 强信号，单独命中就采信（这类元素最典型的写法）。"""
    ok, hits = CP.judge_clickable({"onclick": True})
    assert ok is True
    assert hits == ["onclick"]


def test_listener_alone_is_enough():
    """addEventListener 绑的点击在 DOM 里看不到，但它是显式 handler，同样单独采信。"""
    ok, hits = CP.judge_clickable({"listener": True})
    assert ok is True
    assert hits == ["listener"]


def test_single_weak_signal_is_rejected():
    """单条弱信号一律不采信 —— 这是「不制造假控件」的核心。"""
    for sig in CP.WEAK_SIGNALS:
        ok, hits = CP.judge_clickable({sig: True})
        assert ok is False, "[NG] 弱信号 %s 单独命中时不该放行" % sig
        assert hits == [sig]


def test_two_weak_signals_are_enough():
    """两条弱信号互相印证 => 采信（如 cursor:pointer + tabindex 的可聚焦手型元素）。"""
    ok, hits = CP.judge_clickable({"cursor_pointer": True, "tabindex": True})
    assert ok is True
    assert set(hits) == {"cursor_pointer", "tabindex"}


def test_no_signal_is_rejected():
    ok, hits = CP.judge_clickable({})
    assert ok is False
    assert hits == []


def test_hits_order_is_strong_first():
    """留痕顺序固定「强在前、弱在后」—— 排障时先看强信号。"""
    ok, hits = CP.judge_clickable({"cursor_pointer": True, "tabindex": True, "onclick": True})
    assert ok is True
    assert hits[0] == "onclick", "[NG] 强信号必须排在最前，实际: %r" % (hits,)


def test_signal_sets_are_the_single_source():
    """强/弱信号集合只有一处定义 —— 判据直接引用模块常量，别处另有副本就说明口径分叉了。"""
    assert CP.STRONG_SIGNALS == ("onclick", "listener")
    assert CP.WEAK_SIGNALS == ("cursor_pointer", "tabindex", "contenteditable")


# --------------------------------------------------------------- 开关与清理

def test_switch_off_returns_empty_without_touching_page():
    """负向自证：开关关掉 => 收空，而且**根本不去碰页面**（传 None 也不许崩）。"""
    got = CP.probe_clickable_extras(None, [], enabled=False)
    assert got == []


class _FakePage:
    """最小替身：只回答探测所需的两种 evaluate（扫描 JS / 清理 JS）。"""

    def __init__(self, scan_items=None, locator_raises=True):
        self._scan = scan_items or []
        self._locator_raises = locator_raises
        self.evaluate_calls: list[str] = []

    def evaluate(self, js, arg=None):
        self.evaluate_calls.append(js)
        if "setAttribute" in js:
            return self._scan
        return 0

    @property
    def context(self):
        raise RuntimeError("no cdp in fake page")

    def locator(self, sel):
        if self._locator_raises:
            raise RuntimeError("boom")
        raise AssertionError("本判据不覆盖组装成功路径（那是二类的事）")


def test_marks_are_cleared_even_when_item_build_fails():
    """框架开的必须自己关：组装条目失败时，临时标记也要被清掉（finally 生效）。"""
    fake = _FakePage(scan_items=[{"idx": 0, "tag": "div", "onclick": True,
                                  "cursor_pointer": True, "tabindex": False,
                                  "contenteditable": False, "role_attr": ""}])
    CP.probe_clickable_extras(fake, [], enabled=True)
    cleared = [js for js in fake.evaluate_calls if "removeAttribute" in js]
    assert cleared, "[NG] 没调用清理 JS，框架开的标记没关掉"


def test_scan_is_skipped_when_no_candidates():
    """扫不到候选时不许继续做无意义的 CDP 往返，也不许崩。"""
    fake = _FakePage(scan_items=[])
    assert CP.probe_clickable_extras(fake, [], enabled=True) == []
    assert any("setAttribute" in js for js in fake.evaluate_calls)


# --------------------------------------------------------------- 解耦：框架层零业务词

def test_module_has_no_business_literals():
    """框架层不许写死业务词（订单/合同/发票/账号/登录/密码）—— 业务细节归场景 yml。

    只扫**字符串字面量与注释之外**的可执行部分做不到可靠剥离，所以这里扫全文；
    模块 docstring 里若真要举例，请用「某按钮」这类中性说法。
    """
    src = (ROOT / "framework/features/f03_locate/clickable_probe.py").read_text(encoding="utf-8")
    banned = ["订单", "合同", "发票", "账号", "登录", "密码"]
    hit = [w for w in banned if w in src]
    assert not hit, "[NG] 框架层出现业务词: %r" % (hit,)
