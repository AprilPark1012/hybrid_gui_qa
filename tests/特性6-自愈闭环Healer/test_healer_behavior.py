# -*- coding: utf-8 -*-
"""一类判据：**自愈闭环 Healer 的行为**（2026-11-04 · 原 L11「零判据」）。

## 这道闸防的是什么

`framework/features/f06_healer/healer_run.py`（178 行）**真接在生成链上**：
`generator_generate.py:3639` 会调 `_HEALER.try_heal(page, TestStep(...))` 给 AI 产出的步骤做落地定位。
而在此之前这个特性**一条行为判据都没有**（只有 `test_docs_sync` / `test_no_stale_paths` 的非行为引用）。

自愈一动、没有任何判据会拦 -> 最坏情况是**静默点错控件、用例还绿**（自愈把「找不到」悄悄换成「找到另一个」，
业务断言又与它无关）。这类假绿用户看不见，是最贵的缺陷。

## 口径（判据就是按当前代码写的，改代码必须同步改这里）

1. **无用元素直接早退**：`element is None` 或 `op in ("goto","expect_text")` -> 不记事件、不动页面
2. **A 级用放宽阈值**：`TIER2_THRESHOLD*0.75` / `TIER2_MINGAP*0.6`（不用注释、抓真实传参）
3. **A 级失败才有 B 级**；**B 级是未实现的骨架**，任何环境都必须 `ok=False` 且 reason 含「未实现」
   —— 且**不许**回退成「需配 key」那种误导（V8.4.6 修过，实测有人因此去查 key/额度）
4. **三态裁决**：`recovered` / `real_bug` / `failed`；`real_bug` 时**不返回可用 locator**（防掩盖真 bug）
5. **可审 diff 落盘**：`_record`/`dump` 留下原语义 → 新 locator → 置信度 → 结果
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from framework.features.f03_locate.element_map import ElementRef, TestStep          # noqa: E402
from framework.features.f06_healer import healer_run as H                            # noqa: E402


def _step(op="click", name="目标控件") -> TestStep:
    return TestStep(order=7, op=op, element=ElementRef(semantic_name=name), desc="判据用步骤")


def _ok_locator(loc="page.get_by_text('目标控件')") -> dict:
    return {"ok": True, "locator": loc, "locator_obj": object(),
            "strategy": "tier2-relaxed", "confidence": 0.61, "reason": ""}


# ---------------- (1) 无用元素直接早退，不污染事件流 ----------------

def test_try_heal_short_circuits_without_target():
    """`element is None` / `goto` / `expect_text` -> 早退且**不记事件**。

    为什么必须钉：这三种情形本来就不需要定位；若它们也进 `_record`，
    `output/heals/` 里会堆满「无需定位」的噪声，真正的自愈 diff 被淹没。
    """
    h = H.Healer()
    none_step = TestStep(order=1, op="click", element=None, desc="无元素")
    goto_step = _step(op="goto")
    expect_step = _step(op="expect_text")
    for st in (none_step, goto_step, expect_step):
        r = h.try_heal(page=object(), step=st)
        assert r["recovered"] is False, f"{st.op} 不该被判成自愈成功"
        assert "无需定位" in r["reason"] or "无目标元素" in r["reason"], r
    assert h.events == [], f"早退路径污染了事件流：{[e.semantic_name for e in h.events]}"


# ---------------- (2) A 级确实用放宽阈值（抓真实传参） ----------------

def test_level_a_uses_relaxed_threshold(monkeypatch):
    """A 级必须以 `TIER2_THRESHOLD*0.75` / `TIER2_MINGAP*0.6` 调 `resolve_locator`。

    为什么钉数值而不是钉「调用过」：原样重跑严格 Tier2 等于什么都没做，
    自愈会变成「看起来在干活、其实只是重复了一次必然失败的查找」。
    """
    from framework.features.f03_locate import locator_bridge_locate as LB
    seen = {}

    def _fake(page, el, **kw):
        seen.update(kw)
        return {"ok": False, "reason": "严格阈值下无唯一命中"}

    monkeypatch.setattr(H, "resolve_locator", _fake)
    monkeypatch.setattr("framework.shared.config.auto_detect_llm", lambda: False)
    H.Healer().try_heal(page=object(), step=_step())

    assert "tier2_threshold" in seen and "tier2_gap" in seen, f"A 级没传阈值参数：{seen}"
    assert abs(seen["tier2_threshold"] - LB.TIER2_THRESHOLD * 0.75) < 1e-9, \
        f"A 级阈值没放宽：{seen['tier2_threshold']} != {LB.TIER2_THRESHOLD * 0.75}"
    assert abs(seen["tier2_gap"] - LB.TIER2_MINGAP * 0.6) < 1e-9, \
        f"A 级 MINGAP 没放宽：{seen['tier2_gap']} != {LB.TIER2_MINGAP * 0.6}"


# ---------------- (3) B 级：A 级失败才触发；且它是「未实现」的骨架 ----------------

def test_level_b_never_runs_when_no_llm_and_is_honest_skeleton(monkeypatch):
    """A 级失败 + 无 LLM -> 一步都不进 B 级；即便进了 B 级，也必须如实说「未实现」。

    `_llm_renegotiate` 是**刻意未实现的预留路径**（源码原话：不管有没有 key 都返回同一句；
    旧文案「需 key 才能启用」曾把人送去查 key/额度）。这里同时钉住「不越过 A 级」和「不许编造成功」。
    """
    monkeypatch.setattr(H, "resolve_locator", lambda page, el, **kw: {"ok": False, "reason": "A 级也没命中"})
    monkeypatch.setattr("framework.shared.config.auto_detect_llm", lambda: False)

    called = {"n": 0}
    h = H.Healer()
    monkeypatch.setattr(h, "_llm_renegotiate",
                        lambda page, el: called.__setitem__("n", called["n"] + 1) or _ok_locator())
    r = h.try_heal(page=object(), step=_step())
    assert called["n"] == 0, "无 LLM 时仍进了 B 级（不许越过 A 级直接问 LLM）"
    assert r["result"] == "failed", f"A 级失败应判 failed，实际 {r['result']}"

    # 骨架本体：任何环境都必须 ok=False，且说清「未实现」，不许误导去配 key
    # [!] 必须用**新的** Healer：上面给 h._llm_renegotiate 装了 spy（实例属性），
    #     同一个实例上再调就是调 spy —— 第一版判据就栽在这（spy 返回 ok=True -> 假红）。
    # [!] 另外注意：`_llm_renegotiate` **进门先 `probe_page(page)`**（要真 Page），
    #     所以这里把探针与 LLM 入口都替换掉，才能走到「未实现」那句返回。
    monkeypatch.setattr("framework.features.f03_locate.probe.probe_page", lambda page: [])
    monkeypatch.setattr("framework.shared.config.llm_from_env", lambda: object())
    sk = H.Healer()._llm_renegotiate(page=object(), el=ElementRef(semantic_name="目标控件"))
    assert sk["ok"] is False, "未实现的 B 级竟然返回成功"
    assert "未实现" in sk["reason"], sk["reason"]
    # [!] 措辞判据要**区分肯定与否定**：第一版写成「不许出现『配 key』」-> 把好文案也判红。
    #   现状文案是「…任何环境都不会启用，**别按「配 key」排查**」—— 这句里的「配 key」是**否定用法**，
    #   正是 V8.4.6 想要的（实测有人真去查 key/额度）。所以钉的是「有没有主动劝阻」，
    #   以及「有没有出现『需 key 才能启用』这种肯定句式」。
    assert ("别按" in sk["reason"] or "不要按" in sk["reason"]), \
        f"没劝阻「去查 key」：{sk['reason']}"
    assert "需 key 才能" not in sk["reason"] and "需要配 key" not in sk["reason"], \
        f"B 级又回到「需 key 才能启用」的肯定式误导：{sk['reason']}"


# ---------------- (4) 三态裁决 + real_bug 不许给 locator ----------------

def test_three_state_verdict_and_real_bug_returns_no_locator(monkeypatch):
    """`business_assert` 通过 -> recovered；不通过 -> real_bug **且 locator 置 None**。

    为什么最关键：若 `real_bug` 仍把 locator 返回给调用方，运行期就会**继续用这个错的 locator 点下去**，
    用例可能绿着通过、实际点的是别的控件 —— 这就是自愈掩盖真 bug 的假绿路径。
    """
    monkeypatch.setattr("framework.shared.config.auto_detect_llm", lambda: False)

    # ① recovered
    monkeypatch.setattr(H, "resolve_locator", lambda page, el, **kw: dict(_ok_locator()))
    h1 = H.Healer()
    r1 = h1.try_heal(page=object(), step=_step(), business_assert=lambda loc: True)
    assert r1["result"] == "recovered" and r1["recovered"] is True, r1
    assert r1["locator"], "recovered 必须带回可用 locator"

    # ② real_bug —— locator 必须被清空
    h2 = H.Healer()
    r2 = h2.try_heal(page=object(), step=_step(), business_assert=lambda loc: False)
    assert r2["result"] == "real_bug", r2
    assert r2["recovered"] is False
    assert not r2["locator"], f"real_bug 竟然返回了 locator={r2['locator']} —— 会掩盖真 bug"

    # ③ business_assert 抛异常也算 real_bug（不许把异常吞成 recovered）
    def _boom(loc):
        raise RuntimeError("业务校验自身炸了")
    h3 = H.Healer()
    r3 = h3.try_heal(page=object(), step=_step(), business_assert=_boom)
    assert r3["result"] == "real_bug", f"业务断言抛异常应判 real_bug，实际 {r3['result']}"
    assert not r3["locator"]


# ---------------- (5) 可审 diff 落盘 ----------------

def test_heal_events_are_auditable(monkeypatch, tmp_path):
    """每次自愈都要留下「原语义 → 新 locator → 置信度 → 结果」的可审 diff。"""
    monkeypatch.setattr("framework.shared.config.auto_detect_llm", lambda: False)
    monkeypatch.setattr(H, "resolve_locator", lambda page, el, **kw: dict(_ok_locator()))
    monkeypatch.setattr(H, "HEALS_DIR", tmp_path, raising=True)

    h = H.Healer()
    h.try_heal(page=object(), step=_step(name="发票行-数量"), business_assert=lambda loc: True)
    assert len(h.events) == 1, f"事件数不对：{len(h.events)}"
    ev = h.events[0]
    assert ev.semantic_name == "发票行-数量" and ev.result == "recovered"
    assert ev.confidence == 0.61 and ev.healed_locator, "可审 diff 缺置信度或新 locator"
    assert ev.original_semantics and ev.original_semantics.get("semantic_name") == "发票行-数量"

    paths = h.dump(suffix="_selftest")
    assert len(paths) == 2, f"应落 json + md 两份：{paths}"
    md = Path(paths[1]).read_text(encoding="utf-8")
    assert "发票行-数量" in md and "recovered" in md and "置信度" in md, md[:200]
    assert h.dump() or True   # 再调不炸（幂等性最低要求）
