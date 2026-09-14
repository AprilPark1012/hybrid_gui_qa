"""【Healer】自愈闭环 —— Phase 3 核心，把"降人力"推到极致。

职责：当一个测试步骤的元素定位失败（resolve_locator 返回 ok=False）时，
**不中断整个场景**，而是进入分层自愈流程：

  Level-A  确定性再协商：放宽 Tier2 指纹阈值再找一次（无 LLM，确定性强）
  Level-B  LLM 语义重猜：抓 DOM 快照 + 目标语义 + 意图，让 LLM 重新挑最接近的
           element（可选，需 .env 配 LLM key；无 key 自动跳过）

关键安全设计（绝不掩盖真 bug）：
  1. 自愈只是"帮你找到**可能**是目标的新元素"，它的点错概率存在。
  2. 所以每一条 heal 都记录成**可审 diff**（原语义 → 新 locator → 置信度 →
     结果），落盘到 output/heals/，供人工 review。**绝不静默改写**。
  3. 自愈后是否真对了，由**业务后置断言**裁决：heal 先执行动作，再执行
     该步骤的目标业务结果校验；若业务断言不过 → 判定【真 bug】，不应用
     heal，如实报错。自愈只修 locator 漂移，不掩盖功能回归。

✔ Level-A 不含 LLM；Level-B 仅当检测到 LLM key 才启用。
"""
from __future__ import annotations
import json
import datetime as _dt
from dataclasses import dataclass
from playwright.sync_api import Page
from .element_map import ElementRef, TestStep
from .locator_bridge import resolve_locator, TIER2_THRESHOLD, TIER2_MINGAP
from .config import HEALS_DIR


@dataclass
class HealEvent:
    """一次自愈的完整记录（可审 diff）。"""
    step: int
    semantic_name: str
    original_semantics: dict
    healed_locator: str | None
    strategy: str | None
    confidence: float
    business_ok: bool | None
    result: str          # "recovered" / "real_bug" / "failed"

    def to_dict(self) -> dict:
        return self.__dict__

    def to_markdown(self) -> str:
        return (f"### Step {self.step} · `{self.semantic_name}` · **{self.result}**\n"
                f"- 原语义: `{json.dumps(self.original_semantics, ensure_ascii=False)}`\n"
                f"- 自愈 locator: `{self.healed_locator}`\n"
                f"- 策略: `{self.strategy}` · 置信度 **{self.confidence}**\n"
                f"- 业务后置断言: `{self.business_ok}`\n")


class Healer:
    """自愈器。持有日志；heal_ok 走确定性再协商，heal_llm 走 LLM 语义重猜。"""

    def __init__(self):
        self.events: list[HealEvent] = []

    # ---- 方法：尝试自愈一个步骤 ----
    def try_heal(self, page: Page, step: TestStep, business_assert=None) -> dict:
        """对定位失败的 step 尝试自愈。business_assert 是可选后置校验 callable。"""
        el = step.element
        if el is None or step.action in ("goto", "expect_text"):
            return {"recovered": False, "reason": "无目标元素或无需定位"}
        # 尝试 Level-A / Level-B，拿到一个"唯一命中"的 locator
        resolved = self._negotiate(page, el)
        if not resolved["ok"]:
            return self._record(step, resolved, recovered=False,
                                business_ok=None, result="failed")
        # 唯一性校验通过 → 业务后置断言兜底
        business_ok = True
        if business_assert is not None:
            try:
                business_ok = business_assert(resolved["locator_obj"])
            except Exception as e:
                business_ok = False
                resolved["reason"] = f"业务后置断言未通过: {e}"
        result = "recovered" if business_ok else "real_bug"
        # real_bug → 不返回可用 locator（防止掩盖真 bug）
        if result == "real_bug":
            resolved = {"ok": False, "locator": None, "locator_obj": None,
                        "reason": "自愈后业务断言未通过（疑似真 bug，请人工确认）"}
        return self._record(step, resolved, recovered=(result == "recovered"),
                            business_ok=business_ok, result=result)

    def _negotiate(self, page: Page, el: ElementRef) -> dict:
        """Level-A 确定性再协商（放宽阈值）；必要时 Level-B LLM。默认即 Tier2。"""
        # Level-A：用更宽松的阈值再跑一次 Tier2（默认已含严格 Tier2）
        r = resolve_locator(page, el,
                            tier2_threshold=TIER2_THRESHOLD * 0.75,
                            tier2_gap=TIER2_MINGAP * 0.6)
        if r["ok"]:
            return r
        # Level-B：可选 LLM 语义重猜（无 key 自动跳过）
        from .config import auto_detect_llm
        if auto_detect_llm():
            r = self._llm_renegotiate(page, el)
            return r
        return r

    def _llm_renegotiate(self, page: Page, el: ElementRef) -> dict:
        """LLM 语义重猜：抓 DOM 语义快照 → LLM 挑最接近元素 → 唯一性校验。"""
        import json as _json
        from .probe import probe_page
        candidates = probe_page(page)
        from .config import llm_from_env
        from browser_use.llm import ChatOpenAI, ChatAnthropic, ChatGoogle  # noqa
        try:
            llm = llm_from_env()
        except Exception as e:
            return {"ok": False, "reason": f"LLM 未就绪: {e}"}
        semantics = {k: getattr(el, k) for k in
                     ("role", "name", "label", "placeholder", "text", "test_id")
                     if getattr(el, k)}
        prompt = (f"目标元素语义: {_json.dumps(semantics, ensure_ascii=False)}\n"
                  f"意图: {el.page_hint or el.semantic_name}\n"
                  f"页面候选: {_json.dumps(candidates[:30], ensure_ascii=False)}\n"
                  f"请挑出最匹配目标语义的候选 semantic_name，只输出一个名字。")
        # 这里用 LLM 的文本返回挑一个最接近候选；再走唯一性。
        # （教学骨架：真实可用 structured_output 拿可控对象。无 key 环境此步不被触发。）
        return {"ok": False, "reason": "LLM 重猜路径已预留（需 key 才能启用）"}

    def _record(self, step: TestStep, resolved: dict, recovered: bool,
                business_ok: bool | None, result: str) -> dict:
        ev = HealEvent(
            step=step.order,
            semantic_name=step.element.semantic_name if step.element else "",
            original_semantics=(step.element.to_dict() if step.element else {}),
            healed_locator=resolved.get("locator"),
            strategy=resolved.get("strategy"),
            confidence=resolved.get("confidence", 0.0),
            business_ok=business_ok,
            result=result,
        )
        self.events.append(ev)
        return {"recovered": recovered, "locator": resolved.get("locator"),
                "locator_obj": resolved.get("locator_obj"),
                "strategy": resolved.get("strategy"),
                "confidence": resolved.get("confidence"),
                "reason": resolved.get("reason", ""), "result": result}

    def record_heal(self, step: TestStep, resolved: dict) -> None:
        """记录一次"resolve 层指纹自愈(healed=True)"的事件（供落盘可审 diff）。"""
        ev = HealEvent(
            step=step.order,
            semantic_name=step.element.semantic_name if step.element else "",
            original_semantics=(step.element.to_dict() if step.element else {}),
            healed_locator=resolved.get("locator"),
            strategy=resolved.get("strategy"),
            confidence=resolved.get("confidence", 0.0),
            business_ok=True,
            result="recovered",
        )
        self.events.append(ev)

    def dump(self, suffix: str = "") -> list[str]:
        """把 heal 事件落盘成 json + markdown（可审 diff），返回路径。

        suffix：并发场景下给文件名加区分（如 xdist worker 名），避免多 worker 同秒同名相撞。
        """
        if not self.events:
            return []
        ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S") + suffix
        HEALS_DIR.mkdir(parents=True, exist_ok=True)
        jp = HEALS_DIR / f"heals_{ts}.json"
        mp = HEALS_DIR / f"heals_{ts}.md"
        jp.write_text(json.dumps([e.to_dict() for e in self.events],
                                 ensure_ascii=False, indent=2), encoding="utf-8")
        mp.write_text("# 自愈记录（可审 diff）\n\n" + "\n\n".join(
            e.to_markdown() for e in self.events), encoding="utf-8")
        return [str(jp), str(mp)]
