"""「编辑态 / 动态新增」补探：识别 + 点开 + 重采 + **复原**（C1）。

为什么需要（2026-10-10 实测踩到，代价 = 一条全链路用例永远过不去）：
    订单详情页的行内字段是 `<div :readonly="!editing" v-model="ln.material">` ——
    **无 id、无 name**，而且**只在「进编辑态 + 点新增行之后」才是输入框**。
    探针按静态 DOM 采（+可展开容器补探）=> 这些控件一个都进不了清单
    => AI 会填值（M-001/P-001/10）但**绑不到 element** => 映射质量闸拦下整条用例。
    对照事实：开票页的行内字段是常显的编辑表格，所以它在清单里（`数量@开票页`）——
    **同一类控件，差别只在"要不要先点两下才出现"**。

做法（复用 `expandable.py` 与 `_try_collect_modal_items` 的二次探测模式，不另造一套）：
  (1) 纯结构/语义判据认出「进编辑态」与「新增/添加」触发器 —— `pick_verb_opener()`，
      **纯函数、可单测、不需浏览器**；
  (2) 探测期点一次编辑 -> 重探；再点一次新增 -> 再重探；把**新出现的可见控件**并入清单；
  (3) **必收尾复原**：优先点「取消/退出编辑」类触发器，取不到就 `reload()`
      —— 「框架开的必须由框架关」与 `expandable` 同一条纪律；
      不做收尾会把页面留在编辑态，后续步骤的可见性与断言全会偏（2026-09-22 实测过同类坑）。

[!] 绝不在陌生页面乱点：只在**可见可点的清单项**里按**动词表**挑（表可配、框架零业务词），
    取不到就放弃并如实打印原因 —— 宁可少一份清单，也不乱点。
"""
from __future__ import annotations

import time

from playwright.sync_api import Page

#: 「进编辑态」动词（默认表；项目可用 HYBRID_EDIT_VERBS 追加，默认表里**不许出现业务专有词**）
EDIT_VERBS = ("编辑", "修改", "变更", "edit", "modify")

#: 「动态新增」动词（点一下会**长出**新控件的那种）
ADD_VERBS = ("新增", "添加", "加一行", "插入", "add", "insert", "new row")

#: 「收尾复原」动词（优先用它把页面恢复原状；取不到就 reload）
REVERT_VERBS = ("取消", "返回", "退出编辑", "放弃", "cancel", "discard", "revert")


def _env_extra(name: str) -> tuple[str, ...]:
    import os
    raw = os.environ.get(name, "") or ""
    return tuple(x.strip() for x in raw.split(",") if x.strip())


def edit_verbs() -> tuple[str, ...]:
    return EDIT_VERBS + _env_extra("HYBRID_EDIT_VERBS")


def add_verbs() -> tuple[str, ...]:
    return ADD_VERBS + _env_extra("HYBRID_ADD_VERBS")


def revert_verbs() -> tuple[str, ...]:
    return REVERT_VERBS + _env_extra("HYBRID_REVERT_VERBS")


def pick_verb_opener(items: list[dict], verbs: tuple[str, ...] | None = None) -> dict | None:
    """从清单里挑一个**可见可点**且**名字命中动词表**的控件（纯函数）。

    判据（从严，宁可返回 None）：
      · 必须 `visible` 且 role/tag 属于可点类（button/link/menuitem）；
      · 名字（semantic_name / base_name / ctx_token / name）里命中动词表；
      · 命中多个时取**最短名字**那一个（最短名 = 最贴近该动作本身的控件，
        避免选中「新增行并保存并提交」这种复合长名）。
    取不到 -> None（**绝不猜一个去点**）。
    """
    verbs = verbs if verbs is not None else edit_verbs()
    if not items or not verbs:
        return None
    cands: list[dict] = []
    for it in items:
        if not it.get("visible", True):
            continue
        role = str(it.get("role") or it.get("tag") or "").lower()
        if role not in ("button", "link", "menuitem", "a"):
            continue
        name = " ".join(str(it.get(k) or "") for k in
                        ("semantic_name", "base_name", "ctx_token", "name")).lower()
        if not name:
            continue
        if any(v.lower() in name for v in verbs):
            cands.append(it)
    if not cands:
        return None
    cands.sort(key=lambda x: len(str(x.get("semantic_name") or x.get("name") or "")))
    return cands[0]


def _names(items: list[dict]) -> set[str]:
    return {(it.get("semantic_name") or "") for it in items if it.get("semantic_name")}


def _probe(page: Page) -> list[dict]:
    from framework.tools.probe.probe import probe_page
    return probe_page(page)


def _click_item(page: Page, item: dict, timeout_ms: int = 3000) -> bool:
    """按清单项自带的定位信息点它（优先 id / role+name），点不到就如实返回 False。"""
    loc = None
    elem_id = item.get("id") or item.get("element_id")
    if elem_id:
        try:
            cand = page.locator(f"#{elem_id}")
            if cand.count() == 1:
                loc = cand
        except Exception:                                          # noqa: BLE001
            loc = None
    if loc is None:
        base = str(item.get("base_name") or item.get("name") or
                   (item.get("ctx_token") or "").lstrip("*")).strip()
        role = str(item.get("role") or "").lower()
        if base and role in ("button", "link", "menuitem"):
            try:
                cand = page.get_by_role(role, name=base)
                if cand.count() >= 1:
                    loc = cand.first
            except Exception:                                      # noqa: BLE001
                loc = None
    if loc is None:
        return False
    try:
        loc.click(timeout=timeout_ms)
        return True
    except Exception as first:                                     # noqa: BLE001
        # [!] 回退 force（2026-10-10 干净环境实测踩到）：
        #   探测期的**权限上下文可能与执行业务步骤时不同**（例如场景里"切角色"是后面的一步，
        #   而探测在之前就跑了）-> 此时「编辑」是 `aria-disabled`，**Playwright 常规点击会被直接拒绝**
        #   （TimeoutError），补探一进门就放弃。
        #   这与本 demo「权限不足的按钮置灰但仍可点、点了弹提示」的口径一致
        #   （`tests/特性2-*/verify_role_switch_click.py` 的判据 1c 已把它钉成事实）——
        #   所以探测期用 force 点一次是**安全**的：真有权限限制时应用只会弹提示、状态不变。
        try:
            loc.click(timeout=timeout_ms, force=True)
            print(f"      [probe] [info] 「{item.get('semantic_name')}」常规点击被拒"
                  f"（{type(first).__name__}）-> 改用 force 点一次（探测期权限上下文可能不同）")
            return True
        except Exception as second:                                # noqa: BLE001
            print(f"      [probe] [!] 点不动「{item.get('semantic_name')}」"
                  f"（常规 {type(first).__name__} / force {type(second).__name__}）-> 放弃这一步补探")
            return False


def _settle_new(page: Page, before: set[str], settle_s: float) -> list[dict]:
    """有界轮询等「新控件出现」（探到就走，不是固定 sleep）。"""
    deadline = time.time() + max(0.2, settle_s)
    while True:
        try:
            now = _probe(page)
        except Exception:                                          # noqa: BLE001
            return []
        fresh = [it for it in now if (it.get("semantic_name") or "") not in before]
        if fresh:
            return fresh
        if time.time() >= deadline:
            return []
        time.sleep(0.2)


def _default_enabled() -> bool:
    import os
    return (os.environ.get("HYBRID_EDITABLE_PROBE", "1") or "1").strip() != "0"


def enter_editable_and_collect(page: Page, base_items: list[dict], *, enabled: bool | None = None,
                               settle_s: float = 2.5) -> list[dict]:
    """点「编辑」+「新增」各一次 -> 重采 -> **复原** -> 返回新出现的控件。

    参数：
      enabled=False -> 直接返回空列表（给判据当**负向自证**用：关掉开关就收不到行内字段，
                       也可以在环境里关：HYBRID_EDITABLE_PROBE=0）
                       从而证明"收得到"确实来自这两次点击，而不是页面本来就有）。
      settle_s：每次点完后最多等多久（有界轮询）。

    返回：**新出现**的控件项（与 `probe_page` 同形态，可直接并入清单）。
    """
    if enabled is None:
        enabled = _default_enabled()
    if not enabled:
        return []
    fresh: list[dict] = []
    seen = _names(base_items)
    cur = list(base_items)

    enter_edit = pick_verb_opener(cur, edit_verbs())
    if enter_edit is None:
        return []
    if not _click_item(page, enter_edit):
        return []
    new1 = _settle_new(page, seen, settle_s)
    if not new1:
        print("      [probe] [!] 点了编辑后没有新控件出现 -> 结束这轮补探（并复原）")
    fresh.extend(new1)
    seen |= _names(new1)
    cur = new1 or cur

    add_new = pick_verb_opener(cur, add_verbs()) or pick_verb_opener(base_items, add_verbs())
    if add_new is not None:
        if _click_item(page, add_new):
            new2 = _settle_new(page, seen, settle_s)
            if not new2:
                print(f"      [probe] [!] 点开「{add_new.get('semantic_name')}」后没有任何新控件出现"
                      "（不是动态新增？或页面响应太慢）")
            fresh.extend(new2)
            seen |= _names(new2)

    _restore(page, cur)
    return fresh


def _restore(page: Page, cur: list[dict]) -> None:
    """**必收尾**：把页面从编辑态恢复原状（框架开的必须由框架关）。"""
    back = pick_verb_opener(cur, revert_verbs())
    if back is not None and _click_item(page, back):
        print(f"      [probe] [OK] 已用「{back.get('semantic_name')}」复原页面（编辑态已退出）")
        return
    try:
        page.reload(wait_until="domcontentloaded")
        print("      [probe] [OK] 已 reload 复原页面（没找到可用的取消/返回触发器）")
    except Exception as e:                                         # noqa: BLE001
        print(f"      [probe] [!] 复原失败（{type(e).__name__}）—— 页面可能停在编辑态，"
              "后续步骤的可见性判断会偏")
