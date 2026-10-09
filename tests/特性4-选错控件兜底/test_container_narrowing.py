# -*- coding: utf-8 -*-
"""特性4 · 「容器收窄」消歧：多个同名候选 -> 按容器**排除**到唯一（V8.4.3+）。

## 事故（Windows 干净环境实测）

demo 订单详情页**两个按钮文案都叫「保存」**：

| 候选 | id | 所在容器 | 用途 |
|---|---|---|---|
| ① | `btn-save-lines` | **详细信息** | 保存订单行（AI 真正要点的，desc='保存订单行'） |
| ② | `btn-detail-edit` | 订单详情 | 底部保存（表单1+2+3） |

探测跑**初始页态**时只有一个可见 -> 名字没加消歧后缀；**进编辑态后两个同时可见** ->
`get_by_role("button", name="保存")` 命中 2 个 -> Tier1 全败 -> 报「元素定位失败」。
但探针**本来就采到了容器**（`container_heading='详细信息'`）—— 事在于是它没被用上：
`_to_ref()` 没透传、`resolve_locator` 也没有收窄这一步。

## 红线不变

收窄 = **确定性排除**（留下容器匹配的，且**恰好剩 1 个**才用），
**不是**"在多个里挑一个"。剩 0 个或多个 -> 如实失败。

**实测证据**（真实 demo，编辑态）：
    resolve_locator -> ok=True, strategy=container_narrowed, narrowed_from=2
                      命中 id='btn-save-lines'（容器=详细信息）
    反向自证：容器名不存在 -> ok=False；无 container_heading -> ok=False
"""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from framework.tools.probe import locator_bridge as LB            # noqa: E402
from framework.tools.probe.element_map import ElementRef          # noqa: E402
from framework.tools.generate.generator import _render_harness     # noqa: E402
from framework.tools.generate import probe_snapshot as PS         # noqa: E402


# ---------- 假 page/locator：把浏览器摘掉，只测收窄的**判定逻辑** ----------

class _FakeLoc:
    """只实现收窄用到的两个方法（nth / count）。"""

    def __init__(self, n: int):
        self._n = n

    def count(self):
        return self._n

    def nth(self, i):
        return _FakeItem(i)


class _FakeItem:
    def __init__(self, i: int):
        self.i = i


def _containers(monkeypatch, mapping: dict):
    """把 `_nearest_heading` 换成查表（`_narrow_by_container` 函数内 import，故 patch 源模块）。"""
    monkeypatch.setattr("framework.tools.probe.probe._nearest_heading",
                        lambda loc: mapping.get(getattr(loc, "i", -1), ""))


def _el(container=None) -> ElementRef:
    return ElementRef(semantic_name="保存@订单详情页", role="button", name="保存",
                      text="保存", container_heading=container)


# ---------- ① 收窄：恰好命中一个才用 ----------

def test_narrows_to_the_unique_candidate_in_container(monkeypatch):
    """两个候选，只有一个在目标容器里 -> 收窄成功，且**就是那一个**（序号也必须对）。"""
    _containers(monkeypatch, {0: "详细信息", 1: "订单详情"})
    r = LB._narrow_by_container(None, _el("详细信息"), _FakeLoc(2), "expr", 2)
    assert r and r["ok"] and r["strategy"] == "container_narrowed"
    assert r["locator"] == "expr.nth(0)", "收窄到了错的序号 -> 会点到别的控件（红线）"
    assert r["narrowed_from"] == 2 and r["count"] == 1


def test_narrows_when_target_is_the_second_candidate(monkeypatch):
    """目标在第二个也要取对（不许写死 nth(0)）。"""
    _containers(monkeypatch, {0: "订单详情", 1: "详细信息"})
    r = LB._narrow_by_container(None, _el("详细信息"), _FakeLoc(2), "expr", 2)
    assert r and r["locator"] == "expr.nth(1)"


# ---------- ② 反向自证：收窄不出来时必须**如实放弃**（红线） ----------

def test_gives_up_when_no_candidate_matches_container(monkeypatch):
    """容器名对不上任何一个 -> 放弃（不许乱挑一个）。"""
    _containers(monkeypatch, {0: "订单详情", 1: "订单详情"})
    assert LB._narrow_by_container(None, _el("详细信息"), _FakeLoc(2), "expr", 2) is None


def test_gives_up_when_two_candidates_share_the_container(monkeypatch):
    """**两个候补在同一个容器里** -> 收窄不到唯一 -> 放弃（这正是 container_heading 兜不住的情形）。"""
    _containers(monkeypatch, {0: "详细信息", 1: "详细信息"})
    assert LB._narrow_by_container(None, _el("详细信息"), _FakeLoc(2), "expr", 2) is None


def test_no_container_hint_never_narrows(monkeypatch):
    """**没有容器线索**就不许收窄 —— 否则等于凭空猜（红线）。"""
    _containers(monkeypatch, {0: "详细信息", 1: "订单详情"})
    assert LB._narrow_by_container(None, _el(None), _FakeLoc(2), "expr", 2) is None
    assert LB._narrow_by_container(None, _el(""), _FakeLoc(2), "expr", 2) is None


def test_single_candidate_is_not_narrowed(monkeypatch):
    """只有一个候选时本就该由上层直接命中 —— 收窄不参与（避免多一条路径）。"""
    _containers(monkeypatch, {0: "详细信息"})
    assert LB._narrow_by_container(None, _el("详细信息"), _FakeLoc(1), "expr", 1) is None


def test_strict_locate_disables_narrowing(monkeypatch):
    """`HYBRID_STRICT_LOCATE=1` -> 连收窄也不做（CI 要求名字逐字准确、零兜底）。"""
    _containers(monkeypatch, {0: "详细信息", 1: "订单详情"})
    monkeypatch.setenv("HYBRID_STRICT_LOCATE", "1")
    assert LB._narrow_by_container(None, _el("详细信息"), _FakeLoc(2), "expr", 2) is None
    monkeypatch.setenv("HYBRID_STRICT_LOCATE", "0")
    assert LB._narrow_by_container(None, _el("详细信息"), _FakeLoc(2), "expr", 2)


# ---------- ③ 自证：按序号绑定必须能证明自己 ----------

def test_gives_up_if_candidate_count_changed(monkeypatch):
    """收窄后**候选数变了**（页面在动）-> 序号不再可信 -> 放弃。

    注意：循环用的是入参 `cnt`（解析那一刻的命中数），自证时才回读 `loc.count()`。
    所以这里让 `count()` 回 3 != cnt=2，模拟"页面多了一个「保存」"。
    """
    _containers(monkeypatch, {0: "详细信息", 1: "订单详情"})
    loc = _FakeLoc(3)                            # 解析时是 2，自证时已经是 3
    assert LB._narrow_by_container(None, _el("详细信息"), loc, "expr", 2) is None


def test_uses_the_same_container_rule_as_probe():
    """容器判据必须**复用探针那一个**（`_nearest_heading`）—— 不许另写一套，否则两边会漂移。"""
    src = pathlib.Path(LB.__file__).read_text(encoding="utf-8")
    i = src.index("def _narrow_by_container")
    seg = src[i:src.index("def resolve_locator", i)]
    code = "\n".join(l for l in seg.splitlines() if not l.lstrip().startswith("#"))
    assert "_nearest_heading" in code, "收窄没复用探针的容器判据 -> 探到的和收窄用的会各自漂移"
    assert "def _nearest_heading" not in code, "自己又实现了一套容器判据（应复用，不许复制）"


def test_narrowing_is_wired_before_falling_back_to_weaker_strategy():
    """接线位置：`count>1` 时**先收窄、再**降级到下一个 Tier1 策略（同一信号 + 排除 更可信）。"""
    src = pathlib.Path(LB.__file__).read_text(encoding="utf-8")
    i = src.index("def resolve_locator")
    code = "\n".join(l for l in src[i:].splitlines() if not l.lstrip().startswith("#"))
    assert "_narrow_by_container(" in code, "resolve_locator 里没接收窄 -> 能力空转"
    i_nar = code.index("_narrow_by_container(")
    i_t2 = code.index("_tier2_fingerprint(")
    assert i_nar < i_t2, "收窄排到了 Tier2 之后 -> 先降级到指纹兜底，白丢强信号"


# ---------- ④ 线索必须**透传**到运行时（少传一个字段 = 丢一条能力） ----------

def test_harness_passes_container_and_help_text_into_locator_chain():
    """`_to_ref` 必须把 container_heading / help_text 带进定位链（事故根因就是它漏了）。"""
    src = _render_harness()
    code = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))
    i = code.index("def _to_ref(")
    seg = code[i:i + 1200]
    assert "container_heading=it.get(\"container_heading\")" in seg, \
        "_to_ref 没传 container_heading -> 运行时无权收窄（事故复发）"
    assert "help_text=it.get(\"help_text\")" in seg, "_to_ref 没传 help_text"


def test_snapshot_keeps_the_disambiguation_fields():
    """快照必须存下消歧字段 —— 不存就等于运行时拿不到线索。"""
    assert "container_heading" in PS._KEEP and "help_text" in PS._KEEP
    idx = PS.index_from_items([{"semantic_name": "保存@订单详情页", "role": "button",
                                "name": "保存", "container_heading": "详细信息"}])
    assert idx["保存@订单详情页"]["container_heading"] == "详细信息"
