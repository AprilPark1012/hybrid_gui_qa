"""可点击性探测（A+ 档能力 ②）—— 把「实际能点、但默认选择器看不见」的元素补进清单。

## 为什么需要（实测数据，2026-10-31）

`probe.INTERACTIVE_SELECTOR` 只认 `button / input / select / textarea / a[href]`
以及少量 `[role=...]`。而真实系统（尤其老系统）里大量可点元素是：

    <div onclick="...">、<a>（没有 href，只有 onclick）、<canvas onclick="...">、<img onclick="...">

这类元素**两条路都看不见**：
  * 无障碍树把它们降级成纯文本（实测非语义页 13 个可点元素里 5 个降级、1 个彻底消失）；
  * 本框架的默认选择器**根本选不到**它们。

后果是**静默错误**：AI 看不到 = AI 说"这里没有可点的东西"，用例漏测，而链路全绿。

## 判定口径（宁漏不误伤）

只按「DOM 事实」判定，不用任何业务词：

| 信号 | 类别 | 为什么这么归 |
|---|---|---|
| `onclick` 属性 | 强 | 显式绑定，且是这批元素的典型写法 |
| 事件监听器（CDP `DOMDebugger.getEventListeners`） | 强 | `addEventListener` 绑的点击，DOM 里看不到 |
| `cursor: pointer` | 弱 | 现代页面到处都设，**单独命中会造大量假控件**（噪音 = 没提示） |
| `tabindex >= 0` | 弱 | 可聚焦不等于可点（布局容器也常设） |
| `contenteditable` | 弱 | 可编辑区域，可能需要点进去才能输 |

判定（`judge_clickable`，纯函数、可单测）：

    强信号 >= 1            -> 接受（有显式 handler，几乎不会误伤）
    否则 弱信号 >= 2        -> 接受（如 cursor:pointer + tabindex，互相印证）
    否则                    -> 拒绝

## 边界与纪律

* **只补、不改**：已探测到的控件不动（`existing_keys` 里有的直接跳过）。
* **框架开的必须自己关**：JS 侧给候选打的临时属性 `data-hybrid-clickable-idx`
  在组装完条目后**一律清除**（`_clear_marks`）。
* **取不到信号就退化为「不补」**，绝不因为拿不到信号而崩掉整条探测。
* **已知边界（有意为之）**：一个普通 `div` 若只靠 `addEventListener` 绑点击、又没有任何
  属性/样式线索（无 onclick、无 cursor:pointer、无 tabindex），它**不会被补进来** ——
  扫全页每个元素去做 CDP 监听器查询的代价不可接受，而线索为零时误判率也最高。
  宁漏不误伤：这一条写进文档，别让下一个人以为"全都能补"。
* CDP 监听器探测只在 Chromium 系可用；不可用时**降级为少一个强信号**，不报错、不阻塞。
"""
from __future__ import annotations

from framework.features.f03_locate.probe import (
    INTERACTIVE_SELECTOR,
    _accessible_name,
    _ancestor_chain,
    _ctx_token,
    _help_text,
    _nearest_container_text,
    _nearest_heading,
    _opens_new_tab,
    _role_of,
    _slug,
    _table_context,
    _visible,
    readable_name,
)
from framework.features.f03_locate.anchor_locate import container_from_ancestors, path_for_table_row

__all__ = [
    "MARK_ATTR",
    "judge_clickable",
    "detect_candidates",
    "build_items",
    "probe_clickable_extras",
]

# 候选元素的临时标记属性（组装完条目后必须清除）
MARK_ATTR = "data-hybrid-clickable-idx"

# 强 / 弱信号口径（判据直接引用这两个集合，不许在别处另写一份）
STRONG_SIGNALS = ("onclick", "listener")
WEAK_SIGNALS = ("cursor_pointer", "tabindex", "contenteditable")

# 一次 JS 往返扫全页：既收信号，也给候选打临时下标标记。
# 索引口径与 probe.py 一致：JS 侧直接回传「标记属性里的下标」，Python 侧按同一个下标取 locator。
_SCAN_JS = """(args) => {
  const [sel, mark, maxItems] = args;
  const covered = new Set();
  document.querySelectorAll(sel).forEach(e => covered.add(e));
  const out = [];
  const all = document.querySelectorAll('*');
  for (let i = 0; i < all.length && out.length < maxItems; i++) {
    const e = all[i];
    if (covered.has(e)) continue;                       // 已被默认选择器覆盖 -> 不重复补
    const r = e.getBoundingClientRect();
    if (r.width <= 1 || r.height <= 1) continue;        // 零尺寸 = 看不见
    const cs = getComputedStyle(e);
    if (cs.visibility === 'hidden' || cs.display === 'none' || cs.opacity === '0') continue;
    const hasOnclick = e.hasAttribute('onclick');
    const cursorPointer = cs.cursor === 'pointer';
    const ti = e.getAttribute('tabindex');
    const tabindex = ti !== null && Number(ti) >= 0;
    const contenteditable = e.isContentEditable === true &&
        !['INPUT', 'TEXTAREA'].includes(e.tagName);
    // 标签线索：图标/画布类元素**常常只靠 addEventListener 绑点击**（没有 onclick 属性、
    // 也不一定设 cursor:pointer），只按属性信号筛会永久漏掉它们。
    // 这里只对这几个标签开口子，且真正的采信仍由 judge_clickable 决定（监听器属强信号）。
    const tag = e.tagName.toLowerCase();
    const tagHint = ['img', 'canvas', 'svg', 'area'].includes(tag);
    if (!hasOnclick && !cursorPointer && !tabindex && !contenteditable && !tagHint) continue;
    const idx = out.length;
    e.setAttribute(mark, String(idx));
    out.push({
      idx: idx,
      tag: e.tagName.toLowerCase(),
      onclick: hasOnclick,
      cursor_pointer: cursorPointer,
      tabindex: tabindex,
      contenteditable: contenteditable,
      role_attr: (e.getAttribute('role') || '').trim(),
    });
  }
  return out;
}"""

_CLEAR_JS = """(mark) => {
  const nodes = document.querySelectorAll('[' + mark + ']');
  let n = nodes.length;
  nodes.forEach(e => e.removeAttribute(mark));
  return n;
}"""


# ---------------------------------------------------------------- 纯判定（可单测）

def judge_clickable(signals: dict) -> tuple[bool, list[str]]:
    """按「强 / 弱信号」口径判定一个候选是否算可点击。

    参数 `signals` 只认 `STRONG_SIGNALS` / `WEAK_SIGNALS` 里出现的键（真值为 True 才算命中）。
    返回 `(是否可点, 命中信号名列表)`；信号名列表按「强在前、弱在后」稳定排序，供留痕。

    为什么不用分数/权重：权重会把判断藏进一个数字里，且调权重等于彩票；
    这里只有一条可陈述的规则 —— 有显式 handler 就信，只有样式类弱信号就要两条互相印证。
    """
    hits_strong = [k for k in STRONG_SIGNALS if signals.get(k)]
    hits_weak = [k for k in WEAK_SIGNALS if signals.get(k)]
    hits = hits_strong + hits_weak
    if hits_strong:
        return True, hits
    if len(hits_weak) >= 2:
        return True, hits
    return False, hits


# ---------------------------------------------------------------- 页面侧探测

def _listener_flags(page, idxs: list[int]) -> tuple[dict[int, bool], str]:
    """用 CDP 查「这些元素上有没有绑定事件监听器」（`addEventListener` 在 DOM 里看不到）。

    返回 `(下标 -> 是否有点击类监听器, 说明)`。
    **不支持的浏览器 / 任何异常 => 返回空 dict**：少一个强信号，不阻塞探测（降级不报错）。
    """
    if not idxs:
        return {}, "no-candidates"
    try:
        cdp = page.context.new_cdp_session(page)
    except Exception:                                              # noqa: BLE001
        return {}, "cdp-unavailable"
    out: dict[int, bool] = {}
    try:
        for i in idxs:
            expr = ("document.querySelector('[%s=\"%d\"]')" % (MARK_ATTR, i))
            try:
                res = cdp.send("Runtime.evaluate",
                               {"expression": expr, "objectGroup": "hybclick"})
                obj_id = (res.get("result") or {}).get("objectId")
                if not obj_id:
                    continue
                ev = cdp.send("DOMDebugger.getEventListeners",
                              {"objectId": obj_id, "depth": 0, "pierce": False})
                listeners = ev.get("listeners") or []
                out[i] = any(
                    "click" in str((x or {}).get("type", "")).lower() for x in listeners
                )
            except Exception:                                      # noqa: BLE001
                continue
    finally:
        try:
            cdp.send("Runtime.releaseObjectGroup", {"objectGroup": "hybclick"})
        except Exception:                                          # noqa: BLE001
            pass
        try:
            cdp.detach()
        except Exception:                                          # noqa: BLE001
            pass
    return out, "ok"


def detect_candidates(page, *, max_items: int = 30) -> list[dict]:
    """扫出「默认选择器覆盖不到、但看起来能点」的候选元素（未判定，只收信号）。

    每一项：`{idx, tag, ring(signals dict), verdict(是否可点), hits(命中信号名)}`。
    **不写任何业务词**；阈值口径全部来自 `judge_clickable`。
    """
    try:
        raw = page.evaluate(_SCAN_JS, [INTERACTIVE_SELECTOR, MARK_ATTR, max_items]) or []
    except Exception:                                              # noqa: BLE001
        return []
    if not raw:
        return []
    listener_map, _why = _listener_flags(page, [int(r.get("idx", -1)) for r in raw])
    out: list[dict] = []
    for r in raw:
        idx = int(r.get("idx", -1))
        signals = {
            "onclick": bool(r.get("onclick")),
            "listener": bool(listener_map.get(idx)),
            "cursor_pointer": bool(r.get("cursor_pointer")),
            "tabindex": bool(r.get("tabindex")),
            "contenteditable": bool(r.get("contenteditable")),
        }
        ok, hits = judge_clickable(signals)
        if not ok:
            continue
        out.append({"idx": idx, "tag": r.get("tag", ""), "signals": signals,
                    "hits": hits, "role_attr": r.get("role_attr", "")})
    return out


def _clear_marks(page) -> int:
    """清掉探测期打的临时属性（框架开的必须自己关）。"""
    try:
        return int(page.evaluate(_CLEAR_JS, MARK_ATTR) or 0)
    except Exception:                                              # noqa: BLE001
        return 0


def _norm_key(tag: object, element_id: object, name_attr: object, test_id: object, text: object) -> str:
    return "|".join([str(tag or ""), str(element_id or ""), str(name_attr or ""),
                     str(test_id or ""), str(text or "")])


def _existing_keys(items: list[dict]) -> set[str]:
    return {_norm_key(it.get("tag"), it.get("element_id"), it.get("name_attr", ""),
                      it.get("test_id"), it.get("text")) for it in items}


def build_items(page, candidates: list[dict], *, page_name: str | None = None) -> list[dict]:
    """把候选元素组装成**与 `probe.probe_page` 同构**的清单条目（字段名一处不差）。

    为什么要同构：下游（命名 / 映射 / 生成 / 提示词）只认这一套字段，
    换一套就得处处加分支 —— 那就是「同一件事维护两份」。
    """
    items: list[dict] = []
    for cand in candidates:
        idx = cand["idx"]
        try:
            loc = page.locator("[%s=\"%d\"]" % (MARK_ATTR, idx)).first
            if not _visible(page, loc):
                continue
            tag = loc.evaluate("e => e.tagName.toLowerCase()")
            role = _role_of(loc, page)
            name = _accessible_name(loc)
            placeholder = (loc.get_attribute("placeholder") or "").strip()
            text = (name or placeholder or "")[:60]
            test_id = (loc.get_attribute("data-testid") or "").strip()
            element_id = (loc.get_attribute("id") or "").strip()
            name_attr = (loc.get_attribute("name") or "").strip()
            nearby_text = _nearest_container_text(loc)
            container_heading = _nearest_heading(loc)
            help_text = _help_text(page, loc)
            chain = _ancestor_chain(loc)
            if chain:
                chain[-1]["heading"] = container_heading
            anchor = container_from_ancestors(chain)
            row_ctx = _table_context(loc)
            path = None
            if row_ctx:
                path = path_for_table_row(row_text=row_ctx.get("row_text"),
                                          cell_field=row_ctx.get("col_field"),
                                          col_header=row_ctx.get("col_header"),
                                          col_index=row_ctx.get("col_index"),
                                          row_id=row_ctx.get("row_id") or None,
                                          target_role=role, target_text=None) or None
            elif anchor:
                for by, val in (("text", text), ("title", help_text)):
                    if val:
                        path = [{"axis": "target", "by": by, "value": val}]
                        break
            base = _slug(readable_name(text, help_text) or tag or ("el%d" % idx))
            items.append({
                "base_name": base,
                "ctx_token": _ctx_token(nearby_text, container_heading, help_text),
                "tag": tag,
                "role": role,
                "name": name,
                "placeholder": placeholder,
                "label": "",
                "test_id": test_id,
                "element_id": element_id,
                "name_attr": name_attr,
                "text": text,
                "nearby_text": nearby_text,
                "container_heading": container_heading,
                "help_text": help_text,
                "page": page_name or "",
                "opens_new_tab": _opens_new_tab(loc, tag),
                "anchor": anchor,
                "path": path,
                # 本模块特有：留痕「凭什么判它可点」—— 排障时不用再猜
                "clickable_by": list(cand.get("hits") or []),
                "isValid": True,
            })
        except Exception:                                          # noqa: BLE001
            continue
    return items


def _default_enabled() -> bool:
    """开关口径与其它补探一致：环境变量 `HYBRID_CLICKABLE_PROBE=0` 即关。"""
    import os
    return (os.environ.get("HYBRID_CLICKABLE_PROBE", "1") or "1").strip() != "0"


def probe_clickable_extras(page, existing_items: list[dict] | None = None, *,
                           page_name: str | None = None,
                           max_items: int = 30,
                           enabled: bool | None = None) -> list[dict]:
    """一步到位：扫候选 -> 判定 -> 组装成同构条目 -> 清临时标记。

    `existing_items` 用于去重（已在默认清单里的元素不重复补）；传 None 表示不去重。
    """
    if enabled is None:
        enabled = _default_enabled()
    if not enabled:
        return []                       # 关掉开关 => 空列表（判据拿它做负向自证）
    existing = existing_items or []
    seen = _existing_keys(existing)
    try:
        cands = detect_candidates(page, max_items=max_items)
        if not cands:
            return []
        items = build_items(page, cands, page_name=page_name)
    finally:
        _clear_marks(page)                                         # 框架开的必须自己关
    if seen:
        items = [it for it in items
                 if _norm_key(it.get("tag"), it.get("element_id"), it.get("name_attr"),
                              it.get("test_id"), it.get("text")) not in seen]
    return items
