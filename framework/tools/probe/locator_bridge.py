"""【Playwright】分层 locator 栈 —— 本框架的技术核心（Phase 2 升级版）。

职责：把 probe 探测出的【语义】(ElementRef) 解析成一条**唯一、稳定、可直接执行**的
Playwright locator。采用业界验证过的四层思路，这里实现前两层：

  Tier1（语义精确，默认路径 ~90% 走这里）：
      data-testid > getByRole(name) > getByLabel > getByPlaceholder > getByText
      每个候选都在真实浏览器 count()==1 唯一性校验。这是确定性、最稳的路径。

  Tier2（元素指纹 + intent 判别，主 locator 失效时的兜底）：
      当 Tier1 全部失败（找不到/歧义）时，扫描页面上所有候选元素，用【指纹】
      （role + name/text + placeholder + label + test_id 加权相似度）对候选评分，
      选出「与目标指纹最接近且唯一」的那个。关键：候选要按【测试意图】判别
      （目标元素的语义约束），而不是纯属性相似 —— 否则会点错长得像的按钮
      （那是 false heal / 假通过，最危险）。

安全要点（防 false heal）：
  - Tier1 只接受 count()==1；歧义(count>1)降级；找不到(count==0)跳过。
  - Tier2 命中必须满足：最高分 >= 阈值 且 与次高分有明显差距(有唯一性) 且
    命中后 count()==1。没有把握就【如实报错】，绝不返回可能点错的 locator。
  - 返回 confidence / 命中层级 / healed 标记，供人工复核。

✔ 本文件不含任何 LLM 调用 —— 100% 确定性，是回归可复现的根基。
"""
from __future__ import annotations
from difflib import SequenceMatcher
from playwright.sync_api import Page
from framework.tools.probe.element_map import ElementRef

# ---------------- Tier1：语义精确（按稳定性从高到低） ----------------
# data-testid 是 component contract，不随视觉改版变，业界公认最稳 → 置顶。
TIER1 = [
    ("test_id",       0.95),
    ("role+name",     0.93),
    ("label",         0.88),
    ("placeholder",   0.78),
    ("text",          0.68),
]


# 方向③：Tier1 命中后意图复验阈值
INTENT_MIN_SIM = 0.15


def _intent_verify(page: Page, el: ElementRef, loc_obj, locator_expr: str) -> bool:
    """方向③：Tier1 命中唯一后，回读该元素实际语义，与目标意图核对。

    目的：防止"AI 选对了名字、但命中的元素语义与目标不符"（如选中了另一个
    长得像 / 弹窗里同名控件）。若太不像 → 返回 False，让 resolve_locator 降级。
    阈值 INTENT_MIN_SIM=0.15（保守，只拦明显不符的；包含关系直接通过）。
    """
    hint = (el.page_hint or el.semantic_name or "").strip()
    if not hint:
        return True   # 无意图信息，不校验（保持原行为）
    try:
        actual = loc_obj.evaluate(
            "e => ((e.getAttribute('placeholder')||'') + ' ' +"
            " (e.getAttribute('aria-label')||'') + ' ' +"
            " (e.getAttribute('title')||'') + ' ' +"
            " (e.textContent||''))"
        )
    except Exception:
        return True   # 回读失败 → 不拦截（保守通过，交给下游兜底）
    actual = (actual or "").strip()
    from difflib import SequenceMatcher
    if not actual:
        return True
    sim = SequenceMatcher(None, hint, actual).ratio()
    if sim >= INTENT_MIN_SIM or hint in actual or actual in hint:
        return True
    return False


def _try_test_id(page: Page, el: ElementRef):
    if el.test_id:
        loc = page.get_by_test_id(el.test_id)
        return loc, f'page.get_by_test_id("{el.test_id}")', loc.count()
    return None


def _try_role(page: Page, el: ElementRef):
    if el.role and el.name:
        loc = page.get_by_role(el.role, name=el.name)
        return loc, f'page.get_by_role("{el.role}", name="{el.name}")', loc.count()
    return None


def _try_label(page: Page, el: ElementRef):
    if el.label:
        loc = page.get_by_label(el.label)
        return loc, f'page.get_by_label("{el.label}")', loc.count()
    return None


def _try_placeholder(page: Page, el: ElementRef):
    if el.placeholder:
        loc = page.get_by_placeholder(el.placeholder)
        return loc, f'page.get_by_placeholder("{el.placeholder}")', loc.count()
    return None


def _try_text(page: Page, el: ElementRef):
    if el.text:
        loc = page.get_by_text(el.text, exact=True)
        return loc, f'page.get_by_text("{el.text}", exact=True)', loc.count()
    return None


_TIER1_FNS = {
    "test_id": _try_test_id, "role+name": _try_role, "label": _try_label,
    "placeholder": _try_placeholder, "text": _try_text,
}

# ---------------- Tier2：元素指纹 + intent 判别 + P4 语义上下文消歧 ----------------
TIER2_THRESHOLD = 0.42      # 最低可接受相似度
TIER2_MINGAP = 0.12         # 最高分与次高分的必要差距（唯一性）
_T2_W = {"role": 0.30, "name": 0.20, "text": 0.15,
         "placeholder": 0.15, "label": 0.10, "test_id": 0.10}
# P4：语义上下文权重（用于同 role+name 元素的消歧）。nearby_text 是"所属逻辑单元
# 的关键文本"，对区分同名元素价值最高 → 权重最高；container_heading 次之；help_text 兜底。
_T2_CTX_W = {"nearby_text": 0.30, "container_heading": 0.18, "help_text": 0.12}


def _sim(a: str, b: str) -> float:
    """字符串相似度：完全一致=1，否则 SequenceMatcher 比例。"""
    a, b = (a or "").strip(), (b or "").strip()
    if not a and not b:
        return 0.0
    if a == b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def _ctx_sim(a: str, b: str) -> float:
    """语义上下文相似度：模糊匹配（目标文本包含在候选里，或两者相似）。
    不同于 _sim 的纯比例——"买牛奶" ⊆ "写周报 ... 买牛奶" 这类包含关系更可信。"""
    a, b = (a or "").strip(), (b or "").strip()
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if a in b or b in a:
        return 0.9                     # 包含关系 → 高度相关
    return _sim(a, b)                   # 否则按字符串相似度


def _fingerprint_score(el: ElementRef, cand: dict) -> float:
    """目标 ElementRef 与页面候选元素(probe 字典)的加权相似度。"""
    s = 0.0
    if el.role and cand.get("role") == el.role:
        s += _T2_W["role"]
    s += _T2_W["name"] * _sim(el.name, cand.get("name") or "")
    s += _T2_W["text"] * _sim(el.text, cand.get("text") or "")
    if el.placeholder and cand.get("placeholder") == el.placeholder:
        s += _T2_W["placeholder"]
    if el.label and cand.get("label") == el.label:
        s += _T2_W["label"]
    if el.test_id and cand.get("test_id") == el.test_id:
        s += _T2_W["test_id"]

    # ---- P4：语义上下文消歧（目标带上下文时才参与，否则不加不减） ----
    # 这是"同一 role+name 命中多个元素"时的破局项：目标指明属哪个逻辑单元，
    # 只有上下文匹配的那个候选获得高权重 → 从同结构元素中唯一选出。
    if el.nearby_text:
        s += _T2_CTX_W["nearby_text"] * _ctx_sim(el.nearby_text, cand.get("nearby_text") or "")
    if el.container_heading:
        s += _T2_CTX_W["container_heading"] * _ctx_sim(el.container_heading, cand.get("container_heading") or "")
    if el.help_text:
        s += _T2_CTX_W["help_text"] * _ctx_sim(el.help_text, cand.get("help_text") or "")

    # intent 判别：若给了 page_hint（元素语义/所属区块意图），候选语义须相关
    if el.page_hint:
        hint = el.page_hint.strip()
        blob = f"{cand.get('name','')} {cand.get('text','')} {cand.get('label','')} " \
               f"{cand.get('nearby_text','')} {cand.get('container_heading','')}"
        if _sim(hint, blob) < 0.15 and hint not in blob:
            s -= 0.20          # 与意图相悖的候选，明显降权
    return s


def _locator_for_candidate(page: Page, cand: dict):
    """用候选元素的语义构造真实 Playwright locator（Tier2 命中后执行用）。

    新增 P4 上下文锚点分支：当候选是"裸 role 元素"（无 name/text/placeholder），
    但 nearby_text（所属逻辑单元关键文本）能锚定其父单元时，用
    `父单元含文本 → 取 role` 的 Playwright 过滤表达式唯一命中——这正是
    "买牛奶 vs 写周报同名 checkbox" 这类消歧场景的破局定位。
    """
    # 1) 优先命中上下文锚点（nearby_text 能唯一定位父逻辑单元，比裸 CSS 更语义化）
    if cand.get("nearby_text") and cand.get("role"):
        # Playwright 用 filter(has_text=..) 锚定父单元，再取该单元的 role 元素
        for parent in ("li", "tr", "[role=listitem]", "[role=row]", "article"):
            try:
                unit_loc = page.locator(parent).filter(has_text=cand["nearby_text"])
                if unit_loc.count() == 1:
                    role_loc = unit_loc.get_by_role(cand["role"])
                    if role_loc.count() == 1:
                        expr = (f'page.locator("{parent}")'
                                f'.filter(has_text={cand["nearby_text"]!r})'
                                f'.get_by_role("{cand["role"]}")')
                        return role_loc, expr
            except Exception:
                continue
    # 2) 标准语义锚点
    if cand.get("test_id"):
        loc = page.get_by_test_id(cand["test_id"])
        return loc, f'page.get_by_test_id("{cand["test_id"]}")'
    if cand.get("role") and cand.get("name"):
        loc = page.get_by_role(cand["role"], name=cand.get("name"))
        return loc, f'page.get_by_role("{cand["role"]}", name="{cand.get("name")}")'
    if cand.get("placeholder"):
        loc = page.get_by_placeholder(cand["placeholder"])
        return loc, f'page.get_by_placeholder("{cand["placeholder"]}")'
    if cand.get("text"):
        loc = page.get_by_text(cand["text"], exact=True)
        return loc, f'page.get_by_text("{cand["text"]}", exact=True)'
    return None, None


def _tier2_fingerprint(page: Page, el: ElementRef,
                       threshold: float = TIER2_THRESHOLD,
                       mingap: float = TIER2_MINGAP):
    """Tier2：指纹相似度匹配。返回 locator 结果 dict 或 None（无把握放弃）。

    threshold/mingap 可放宽（供 Healer 自愈再协商用），默认取严格值。"""
    from framework.tools.probe.probe import probe_page
    candidates = probe_page(page)
    scored = [(_fingerprint_score(el, c), c) for c in candidates]
    scored.sort(key=lambda x: -x[0])
    if not scored:
        return None
    best_score, best = scored[0]
    second = scored[1][0] if len(scored) > 1 else 0.0
    if best_score < threshold or (best_score - second) < mingap:
        return None                                # 无把握，如实放弃
    loc_obj, expr = _locator_for_candidate(page, best)
    if loc_obj is None:
        return None
    try:
        cnt = loc_obj.count()
    except Exception:
        return None
    if cnt != 1:                                   # 二次唯一性校验
        return None
    return {"ok": True, "locator": expr, "locator_obj": loc_obj,
            "strategy": "fingerprint", "count": cnt,
            "confidence": round(best_score, 2), "healed": True}


# ---------------- 入口：分层解析 ----------------
def resolve_locator(page: Page, el: ElementRef,
                    tier2_threshold: float = TIER2_THRESHOLD,
                    tier2_gap: float = TIER2_MINGAP) -> dict:
    """按 Tier1 → Tier2 顺序解析，返回第一个"唯一命中"的 locator。

    返回 {ok, locator(字符串), locator_obj(真实Locator对象), strategy,
          count, confidence, healed}
      - ok=True: 唯一命中，locator_obj 可直接执行。
      - ok=False: T1/T2 都无把握 → 如实报错，不猜。
    tier2_threshold / tier2_gap 可由 Healer 自愈时放宽。
  """
    for strategy, conf in TIER1:
        fn = _TIER1_FNS[strategy]
        r = fn(page, el)
        if r:
            loc_obj, expr, cnt = r
            if cnt == 1:
                # 方向③：Tier1 唯一命中后，意图复验（防"选对名字但语义不符"）
                if not _intent_verify(page, el, loc_obj, expr):
                    continue   # 复验不过 → 降级到下一个 Tier1 策略
                return {"ok": True, "locator": expr, "locator_obj": loc_obj,
                        "strategy": strategy, "count": cnt,
                        "confidence": conf, "healed": False}
            # count>1 歧义 → 降级下一策略；count==0 找不到 → 跳过
    # Tier1 全败 → Tier2 指纹兜底
    t2 = _tier2_fingerprint(page, el, tier2_threshold, tier2_gap)
    if t2:
        return t2
    return {"ok": False, "locator": None, "locator_obj": None,
            "strategy": None, "count": None, "confidence": 0.0, "healed": False,
            "reason": "Tier1 语义 & Tier2 指纹均无法唯一确定，请补 data-testid 或核对语义"}
