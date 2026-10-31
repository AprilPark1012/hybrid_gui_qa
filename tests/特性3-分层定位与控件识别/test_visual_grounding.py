# -*- coding: utf-8 -*-
"""一类判据：**视觉 grounding 兜底**（A+ 档能力 3，2026-10-31）。

## 守的是什么

确定性定位（语义 + a11y + 可点击性补探）**全都失败**时，最后还剩客观信息：像素。
把截图交给多模态模型要一个 0-1000 归一化坐标，换算成像素点下去，然后**校验点完有没有变化**。

必须守住的五条：

1. **坐标换算按截图实际尺寸**，越界一律夹紧（绝不产生越界点击）；
2. **模型回复解析要宽容、但绝不猜** —— 抠不出两个数就返回 None，不许拿默认值硬凑；
3. **空回复要做一次收紧重试**（国产模型思考模式会把 token 预算烧在 reasoning 上、
   返回空 content 且 HTTP 200 —— 实测静默失败）；
4. **点了必须校验**：签名没变 => `no-effect`，绝不报成功（铁律 18）；
5. **失败只报原因、不抛**：决定权交回调用方。

## 这些判据证明什么 / 不证明什么

* 证明：换算、解析、降级、重试、后置校验五条行为，且**负向自证过**；
* 不证明：真实模型在这台机器上一定给得准坐标 —— 那需要真网络，属于二类；
  真机实测的偏差数字（0.8 px / 8.7 px）记录在模块 docstring 里，不在判据里假装。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from framework.features.f03_locate import visual_grounding as VG                        # noqa: E402


# --------------------------------------------------------------- 替身

class _FakeMouse:
    def __init__(self):
        self.clicks: list[tuple[int, int]] = []

    def click(self, x, y):
        self.clicks.append((x, y))


class _FakePage:
    """最小替身：截图 / 视口 / 签名 / 鼠标都只回固定值。"""

    def __init__(self, sigs=None, viewport=(1280, 800)):
        self.url = "http://example.invalid/"
        self.viewport_size = {"width": viewport[0], "height": viewport[1]}
        self.mouse = _FakeMouse()
        self._sigs = list(sigs or [(1, 1)])
        self.signature_reads = 0

    def screenshot(self, type="png"):
        return b"\x89PNG-fake"

    def evaluate(self, js):
        idx = min(self.signature_reads, len(self._sigs) - 1)
        self.signature_reads += 1
        return list(self._sigs[idx])

    def wait_for_timeout(self, ms):
        return None


class _FakeLlm:
    """假 LLM：记录收到的提示词，返回固定文本。"""

    def __init__(self, text):
        self._text = text
        self.calls: list[str] = []

    def __call__(self, png, prompt):
        self.calls.append(prompt)
        return self._text


def _llm(text):
    return _FakeLlm(text)


# --------------------------------------------------------------- 坐标换算

def test_norm_to_px_corners_and_middle():
    assert VG.norm_to_px(0, 0, 1280, 800) == (0, 0)
    assert VG.norm_to_px(1000, 1000, 1280, 800) == (1279, 799)
    assert VG.norm_to_px(500, 500, 1280, 800) == (640, 400)


def test_norm_to_px_clamps_out_of_range():
    """模型偶尔给 1200 / 负数 —— 一律夹进有效范围，绝不越界点击。"""
    assert VG.norm_to_px(1200, -50, 100, 50) == (99, 0)


def test_norm_to_px_rejects_bad_size():
    try:
        VG.norm_to_px(1, 1, 0, 0)
    except ValueError:
        return
    raise AssertionError("[NG] 零尺寸应当报错，不许返回坐标")


# --------------------------------------------------------------- 回复解析

def test_parse_plain_json():
    assert VG.parse_point('{"x": 500, "y": 351}') == (500.0, 351.0)


def test_parse_fenced_json():
    assert VG.parse_point('```json\n{"x": 12, "y": 34}\n```') == (12.0, 34.0)


def test_parse_tool_call_wrapper():
    assert VG.parse_point('<tool_call>{"y": 7, "x": 9}</tool_call>') == (9.0, 7.0)


def test_parse_prose_with_numbers():
    assert VG.parse_point("坐标是 (640, 280)") == (640.0, 280.0)


def test_parse_garbage_returns_none_not_guess():
    """绝不猜：抠不出来就是 None，调用方据此报 parse-failed。"""
    assert VG.parse_point("我找不到这个控件") is None
    assert VG.parse_point("") is None
    assert VG.parse_point(None) is None


# --------------------------------------------------------------- 开关与降级

def test_disabled_does_not_call_llm():
    llm = _llm('{"x":1,"y":2}')
    vg = VG.VisionGrounding(_FakePage(), llm_call=llm, enabled=False)
    got = vg.locate("某个按钮")
    assert got["ok"] is False and got["reason"] == "disabled"
    assert llm.calls == [], "[NG] 关掉开关还去调模型"


def test_empty_description_is_rejected():
    vg = VG.VisionGrounding(_FakePage(), llm_call=_llm("x"), enabled=True)
    assert vg.locate("  ")["reason"] == "empty-description"


def test_empty_content_triggers_one_strict_retry():
    """国产模型思考模式会把预算烧在 reasoning 上、content 返回空 —— 要收紧提示词再问一次。"""
    llm = _llm("")
    vg = VG.VisionGrounding(_FakePage(), llm_call=llm, enabled=True)
    got = vg.locate("某个按钮")
    assert got["reason"] == "empty-content"
    assert len(llm.calls) == 2, "[NG] 空回复应当重试一次，实际调用 %d 次" % len(llm.calls)
    assert "不要任何其它文字" in llm.calls[1], "[NG] 第二次用的不是收紧提示词"


def test_unparsable_reply_reports_parse_failed():
    vg = VG.VisionGrounding(_FakePage(), llm_call=_llm("看不到"), enabled=True)
    got = vg.locate("某个按钮")
    assert got["reason"] == "parse-failed"
    assert "raw" in got


def test_llm_exception_is_reported_not_raised():
    def boom(png, prompt):
        raise RuntimeError("网络断了")

    vg = VG.VisionGrounding(_FakePage(), llm_call=boom, enabled=True)
    got = vg.locate("某个按钮")
    assert got["ok"] is False
    assert got["reason"].startswith("llm-error")


def test_locate_returns_pixel_and_norm():
    vg = VG.VisionGrounding(_FakePage(), llm_call=_llm('{"x": 500, "y": 351}'), enabled=True)
    got = vg.locate("某个按钮")
    assert got["ok"] is True
    # 真值口径：round(500/1000*1279)=640；round(351/1000*799)=280（用 width-1/height-1 换算）
    assert got["px"] == [640, 280]
    assert got["size"] == [1280, 800]


# --------------------------------------------------------------- 后置校验

def test_click_reports_no_effect_when_page_unchanged():
    """点了没变化 => 必须报 no-effect。这条是「做了 != 生效了」的红线。"""
    vg = VG.VisionGrounding(_FakePage(sigs=[(1, 1), (1, 1)]),
                            llm_call=_llm('{"x": 10, "y": 10}'), enabled=True)
    got = vg.click("某个按钮")
    assert got["clicked"] is True
    assert got["ok"] is False
    assert got["reason"] == "no-effect"


def test_click_ok_when_signature_changes():
    page = _FakePage(sigs=[(1, 1), (9, 9)])
    vg = VG.VisionGrounding(page, llm_call=_llm('{"x": 10, "y": 10}'), enabled=True)
    got = vg.click("某个按钮")
    assert got["ok"] is True
    assert got["signature_changed"] is True
    assert page.mouse.clicks, "[NG] 没真的点"


def test_click_can_be_disabled_for_dry_run():
    page = _FakePage(sigs=[(1, 1)])
    vg = VG.VisionGrounding(page, llm_call=_llm('{"x": 10, "y": 10}'),
                            enabled=True, click=False)
    got = vg.click("某个按钮")
    assert got["clicked"] is False
    assert page.mouse.clicks == []


# --------------------------------------------------------------- 解耦

def test_module_has_no_business_literals():
    src = (ROOT / "framework/features/f03_locate/visual_grounding.py").read_text(encoding="utf-8")
    banned = ["订单", "合同", "发票", "账号", "登录", "密码"]
    hit = [w for w in banned if w in src]
    assert not hit, "[NG] 框架层出现业务词: %r" % (hit,)
