"""可展开容器：识别 + 点开补探（P22 批 2）—— 缺口 1a 的解药。

为什么需要（真值 · P22 §二 缺口 1a）：
  demo 右上角角色菜单 `#nu-menu` 初始 `style="display:none"`（`demo/auth.js:188`），而探针按**可见性**过滤
  （`probe.py:442` · `explorer.py:1261`）-> 藏在菜单里的「切换为订单管理员」**永远不会进清单**
  -> 跨角色场景第 2 步无控件可引用（本项目铁律：AI/场景不许自造语义名）。

做法（复用 `_try_collect_modal_items` 的二次探测模式，不另造一套）：
  (1) 纯结构判据认出「隐藏容器 + 它的可见触发器」—— `pick_expandable_opener()`，**纯函数、可单测、不需浏览器**；
  (2) 探测期点开一次 -> 重新探测 -> 把**新出现的可见控件**并入清单（去重按 semantic_name）；
  (3) **必收尾**：再把菜单关掉 —— 「框架开了的必须由框架关」，与 `_close_open_modal` 同一条纪律
     （否则展开的菜单会挡住后续步骤，这是 2026-09-22 实测过的坑）。

[!] 绝不在陌生页面乱点：判据要求「触发器**可见可点**、且 DOM 位置在容器**之前**」，取不到就放弃；
   触发器**没有 id** 时**本版不展开**（不猜选择器），并如实打印原因 —— 宁可少一份清单，也不乱点。
"""
from __future__ import annotations

import time

from playwright.sync_api import Page

# 与 probe 同一份交互元素口径（避免两处漂移）
_INTERACTIVE = ("button, input, select, textarea, a[href], "
                "[role=button], [role=link], [role=checkbox], [role=radio], "
                "[role=menuitem], [role=tab]")

# 轻量信号：**只数**「当前可见的可交互元素」个数 —— 不取文本、不算锚点、不取行内路径，
# 因此比 `probe_page` 便宜得多。用途见 `_light_signal` 的注释（2026-10-08 超时事故的修法）。
_JS_COUNT = """() => {  /* COUNT_ONLY: light signal for expandable-wait */
  const INTER = '%s';
  let n = 0;
  for (const el of document.querySelectorAll(INTER)) {
    const r = el.getBoundingClientRect();
    if (r.width > 0 && r.height > 0) n++;
  }
  return n;
}""" % _INTERACTIVE

# 展开后的轮询间隔（毫秒）。与 settle 的倍数关系决定最多轮询几次。
_POLL_MS = 200


def _light_signal(page) -> int:
    """廉价信号：当前**可见**的可交互元素个数。

    为什么要它（2026-10-08 实测事故）：展开的等待循环原先**每轮都调 `probe_page`**（全页重扫、
    要取文本/算容器锚点/算行内相对路径）。对「点了没反应」的候选会跑满 `settle_s/0.2` 轮，
    一页最多 3 个候选（`max_opens`）、跨页 7 页 -> `generate` 实测从 ~59s 涨到 **866s**。

    修法：轮询只问这个**计数**；**只有计数变了**（说明页面上真有新东西出现，例如菜单从
    `display:none` 变可见）才去做一次昂贵的全页重扫。取不到信号时返回 -1（调用方据此退化为原行为，
    绝不因为"信号坏了"而漏探）。
    """
    try:
        return int(page.evaluate(_JS_COUNT))
    except Exception:                                                # noqa: BLE001
        return -1


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
    任何一步取不到 -> None（**绝不猜一个去点**）。
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
            continue                                   # 没有可见可点触发器 -> 放弃（判据 3）
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
      enabled=False -> 直接返回空列表（给判据当**负向自证**用：关掉这个开关就收不到菜单项，
                      从而证明"收得到"确实来自展开动作，而不是页面本来就可见）。
      max_opens：最多展开几次（有界，绝不在页面上连点）。
      settle_s：每次点开后最多等多久（有界轮询，不是固定 sleep —— 探到就走）。

    返回：**新出现**的控件项（list[dict]，与 `probe_page` 同形态，可直接并入清单）。
    """
    if not enabled:
        return []
    from framework.tools.probe.probe import probe_page, visible_key_map

    fresh: list[dict] = []
    seen = _names(base_items)
    try:
        cands = page.evaluate(_JS_SCAN) or []
    except Exception as e:                                           # noqa: BLE001
        print(f"      [probe] [!] 可展开容器扫描失败（{type(e).__name__}: {str(e)[:100]}）")
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
            print(f"      [probe] [info] 发现可展开容器 {pick['container_key']}（{pick['reason']}），"
                  f"但触发器没有 id -> 本版不展开（不猜选择器，如实少一份清单）")
            continue

        # ---- D3 的关键前提（2026-10-08 实测补正，血泪）----
        # `base_items` 已经把「点开前可见的元素」完整探过一遍了 -> 首轮**绝不该**把整页当
        # 「新元素」重探（那等于白付一次全页代价：实测发票列表页 212 元素 ≈ 60s，
        # expand 单项 65.4s 几乎全是这笔钱）。
        # [!] 基线必须在 **click 之前** 取！曾经把它放在 click 之后，结果：
        #     基线 = 点开后的 key 集合 -> 差集恒为空 -> 循环一路 continue -> 超时走兜底全探，
        #     白花的 13.7s 就是这么来的（探针插桩实测：14 次 key 表查询全是 78，一次全探）。
        try:
            before_keys = set(visible_key_map(page))
        except Exception:                                            # noqa: BLE001
            before_keys = set()

        loc = page.locator(f"#{opener_id}").first
        try:
            loc.click(timeout=3000)
        except Exception as e:                                       # noqa: BLE001
            print(f"      [probe] [!] 点开「{opener_id}」失败（{type(e).__name__}: {str(e)[:80]}）"
                  f"-> 跳过该容器（不影响其余探测）")
            continue

        # ---- 有界等待：探到新控件就走（不固定 sleep）----
        # 性能治理两刀（2026-10-08 实测 expand 118s/七页，最大单项）：
        #   A：先把「整页重扫」用廉价信号挡一道（见下）；
        #   D3：真要点扫的时候，**只探新出现的元素**（`only_indexes`）—— 点开一个菜单通常只新增
        #       几个控件，原先却把整页（212 元素 ≈ 13 次往返/元素）重探一遍，代价被页面规模放大。
        # 事故背景：原先每轮都 `probe_page`，对「点了没反应」的候选会跑满 settle_s/0.2 轮；
        # 一页最多 3 个候选、跨页 7 页 -> generate 实测 866s（原 ~59s）。
        deadline = time.time() + settle_s
        got: list[dict] = []
        seen_keys: set[str] = set(before_keys)
        scanned_any = False
        while time.time() < deadline:
            page.wait_for_timeout(_POLL_MS)
            kmap = visible_key_map(page)          # 一次廉价往返；取不到 -> {} 退化为全页探测
            if not kmap:
                # 拿不到索引表（老页面/异常）-> 保守：照本轮全页探一次后收工，绝不满负荷空转
                if scanned_any:
                    break
                scanned_any = True
                try:
                    items = probe_page(page)
                except Exception:                                    # noqa: BLE001
                    break
                got = [it for it in items if (it.get("semantic_name") or "") not in seen]
                if got:
                    break
                continue
            new_keys = set(kmap) - seen_keys
            if not new_keys:
                continue                          # 没有新 key -> 这一轮不必探测（A 的门）
            seen_keys |= set(kmap)
            scanned_any = True
            try:
                # D3：只探新出现的索引 —— 已探过的不再重复付 ~13 次往返/元素的代价
                items = probe_page(page, only_indexes={kmap[k] for k in new_keys})
            except Exception:                                        # noqa: BLE001
                break
            got = [it for it in items if (it.get("semantic_name") or "") not in seen]
            if got:
                break
        # 兜底：整段等待里一次都没扫过 -> 结束前补扫一次，绝不因优化而漏探。
        if not scanned_any:
            try:
                items = probe_page(page)
                got = [it for it in items if (it.get("semantic_name") or "") not in seen]
            except Exception:                                        # noqa: BLE001
                got = []
        if got:
            for it in got:
                seen.add(it.get("semantic_name") or "")
            fresh.extend(got)
            print(f"      [probe] [OK] 展开「{opener_id}」后补探到 {len(got)} 个控件"
                  f"（容器 {pick['container_key']}）")
        else:
            print(f"      [probe] [info] 点开「{opener_id}」后没有新控件出现（不是菜单？或渲染太慢）")
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
