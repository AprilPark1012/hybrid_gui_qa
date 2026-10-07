"""可展开容器：识别 + 点开补探（P22 批 2）—— 缺口 1a 的解药。

为什么需要（真值 · P22 §二 缺口 1a）：
  demo 右上角角色菜单 `#nu-menu` 初始 `style="display:none"`（`demo/auth.js:188`），而探针按**可见性**过滤
  （`probe.py:442` · `explorer.py:1261`）⇒ 藏在菜单里的「切换为订单管理员」**永远不会进清单**
  ⇒ 跨角色场景第 2 步无控件可引用（本项目铁律：AI/场景不许自造语义名）。

做法（复用 `_try_collect_modal_items` 的二次探测模式，不另造一套）：
  ① 纯结构判据认出「隐藏容器 + 它的可见触发器」—— `pick_expandable_opener()`，**纯函数、可单测、不需浏览器**；
  ② 探测期点开一次 ⇒ 重新探测 ⇒ 把**新出现的可见控件**并入清单（去重按 semantic_name）；
  ③ **必收尾**：再把菜单关掉 —— 「框架开了的必须由框架关」，与 `_close_open_modal` 同一条纪律
     （否则展开的菜单会挡住后续步骤，这是 2026-09-22 实测过的坑）。

⚠️ 绝不在陌生页面乱点：判据要求「触发器**可见可点**、且 DOM 位置在容器**之前**」，取不到就放弃；
   触发器**没有 id** 时**本版不展开**（不猜选择器），并如实打印原因 —— 宁可少一份清单，也不乱点。
"""
from __future__ import annotations

import time

from playwright.sync_api import Page

# 与 probe 同一份交互元素口径（避免两处漂移）
_INTERACTIVE = ("button, input, select, textarea, a[href], "
                "[role=button], [role=link], [role=checkbox], [role=radio], "
                "[role=menuitem], [role=tab]")

# 一次 evaluate 扫全页：找「隐藏 + 内含交互控件」的容器，并把它的**兄弟节点**描述带回来。
# 纯数据、不含任何 CSS selector（本项目铁律：不给 AI 猜 CSS 的机会；这里的定位由框架自己确定性地做）。
_JS_SCAN = """() => {
  const INTER = '%s';
  const vis = (el) => {
    const r = el.getBoundingClientRect();
    const st = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && st.display !== 'none' && st.visibility !== 'hidden';
  };
  const kOf = (el, i) => el.id || el.getAttribute('data-switch') || el.getAttribute('data-testid')
                          || (el.tagName.toLowerCase() + '@' + i);
  const out = [];
  for (const el of document.querySelectorAll('*')) {
    const st = getComputedStyle(el);
    if (st.display !== 'none' && st.visibility !== 'hidden') continue;   // 只认隐藏容器
    if (!el.querySelector(INTER)) continue;                              // 且内含交互控件
    const parent = el.parentElement;
    if (!parent || parent.children.length < 2) continue;
    const kids = Array.from(parent.children);
    const sibs = kids.map((k, i) => ({
      key: kOf(k, i),
      id: k.id || '',
      tag: k.tagName.toLowerCase(),
      visible: vis(k),
      interactive: k.matches(INTER),
      contains_interactive: !!k.querySelector(INTER),
      order: i,
      aria_controls: k.getAttribute('aria-controls') || '',
      aria_haspopup: k.hasAttribute('aria-haspopup'),
    }));
    const ci = kids.indexOf(el);
    out.push({ container_key: kOf(el, ci), container_id: el.id || '',
               container_tag: el.tagName.toLowerCase(), siblings: sibs });
  }
  return out;
}""" % (_INTERACTIVE,)


def pick_expandable_opener(siblings: list[dict]) -> dict | None:
    """从「同一父容器下的兄弟节点」里判出可展开容器 + 它的触发器（纯结构判据 · J1）。

    判据优先级：
      1. 显式声明：隐藏容器的 `aria-controls` 指向某个可见可点的兄弟（`reason="aria-controls"`）
      2. 显式声明：可见可点兄弟带 `aria-haspopup`，其后有隐藏容器（`reason="aria-haspopup"`）
      3. 结构判据：隐藏容器（内含交互控件）+ 同父中 **DOM 在前的可见可点**兄弟
         （取**最靠近容器**的那一个；`reason="hidden-container-after-visible-trigger"`）
    任何一步取不到 ⇒ None（**绝不猜一个去点**）。
    """
    if not siblings:
        return None
    by_key = {s.get("key"): s for s in siblings}
    hidden = [s for s in siblings if not s.get("visible") and s.get("contains_interactive")]

    # 1) aria-controls
    for c in hidden:
        ac = (c.get("aria_controls") or "").strip()
        t = by_key.get(ac)
        if t and t.get("visible") and t.get("interactive"):
            return {"opener_key": t["key"], "container_key": c["key"], "reason": "aria-controls"}

    # 2) aria-haspopup
    for s in siblings:
        if s.get("visible") and s.get("interactive") and s.get("aria_haspopup"):
            after = [c for c in hidden if c.get("order", 0) > s.get("order", 0)]
            if after:
                return {"opener_key": s["key"], "container_key": after[0]["key"],
                        "reason": "aria-haspopup"}

    # 3) 结构判据
    for c in hidden:
        cands = [s for s in siblings
                 if s.get("visible") and s.get("interactive") and s.get("order", 0) < c.get("order", 0)]
        if not cands:
            continue                                   # 没有可见可点触发器 ⇒ 放弃（判据 3）
        cands.sort(key=lambda s: s.get("order", 0), reverse=True)   # 取最近的那个
        return {"opener_key": cands[0]["key"], "container_key": c["key"],
                "reason": "hidden-container-after-visible-trigger"}
    return None


def _names(items: list[dict]) -> set[str]:
    return {(it.get("semantic_name") or "") for it in items if it.get("semantic_name")}


def expand_and_collect(page: Page, base_items: list[dict], *, enabled: bool = True,
                       max_opens: int = 3, settle_s: float = 2.5) -> list[dict]:
    """扫「可展开容器」→ 逐个点开 → 有界等待新控件 → 并入清单 → **收尾关掉**。

    参数：
      enabled=False ⇒ 直接返回空列表（给判据当**负向自证**用：关掉这个开关就收不到菜单项，
                      从而证明"收得到"确实来自展开动作，而不是页面本来就可见）。
      max_opens：最多展开几次（有界，绝不在页面上连点）。
      settle_s：每次点开后最多等多久（有界轮询，不是固定 sleep —— 探到就走）。

    返回：**新出现**的控件项（list[dict]，与 `probe_page` 同形态，可直接并入清单）。
    """
    if not enabled:
        return []
    from framework.tools.probe.probe import probe_page

    fresh: list[dict] = []
    seen = _names(base_items)
    try:
        cands = page.evaluate(_JS_SCAN) or []
    except Exception as e:                                           # noqa: BLE001
        print(f"      [probe] ⚠️ 可展开容器扫描失败（{type(e).__name__}: {str(e)[:100]}）")
        return []

    if not cands:
        return []

    opened = 0
    for cand in cands:
        if opened >= max_opens:
            break
        pick = pick_expandable_opener(cand.get("siblings") or [])
        if not pick:
            continue
        sibs = {s.get("key"): s for s in cand["siblings"]}
        opener_id = (sibs.get(pick["opener_key"]) or {}).get("id") or ""
        if not opener_id:
            print(f"      [probe] ℹ️ 发现可展开容器 {pick['container_key']}（{pick['reason']}），"
                  f"但触发器没有 id ⇒ 本版不展开（不猜选择器，如实少一份清单）")
            continue

        loc = page.locator(f"#{opener_id}").first
        try:
            loc.click(timeout=3000)
        except Exception as e:                                       # noqa: BLE001
            print(f"      [probe] ⚠️ 点开「{opener_id}」失败（{type(e).__name__}: {str(e)[:80]}）"
                  f"⇒ 跳过该容器（不影响其余探测）")
            continue

        # ---- 有界等待：探到新控件就走（不固定 sleep）----
        deadline = time.time() + settle_s
        got: list[dict] = []
        while time.time() < deadline:
            page.wait_for_timeout(200)
            try:
                items = probe_page(page)
            except Exception:                                        # noqa: BLE001
                break
            got = [it for it in items if (it.get("semantic_name") or "") not in seen]
            if got:
                break
        if got:
            for it in got:
                seen.add(it.get("semantic_name") or "")
            fresh.extend(got)
            print(f"      [probe] ✅ 展开「{opener_id}」后补探到 {len(got)} 个控件"
                  f"（容器 {pick['container_key']}）")
        else:
            print(f"      [probe] ℹ️ 点开「{opener_id}」后没有新控件出现（不是菜单？或渲染太慢）")
        opened += 1

        # ---- 收尾：框架开的必须由框架关掉（探测 = 只读动作）----
        try:
            if loc.is_visible():
                loc.click(timeout=3000)
                page.wait_for_timeout(120)
        except Exception:                                            # noqa: BLE001
            try:
                page.keyboard.press("Escape")
            except Exception:                                        # noqa: BLE001
                pass
    return fresh
