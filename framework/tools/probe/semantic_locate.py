"""语义定位入口（面向**人写脚本**的薄封装）—— P16 批 6：demo 对齐生产后的统一定位方式。

**为什么需要它**：口径 C 定下后，demo 里只剩**顶层容器**有埋点（`tbl-*` / `modal-*` / `pager` /
`status`…），所有子元素（行、单元格、行内链接、**弹层里的字段与按钮**）**没有任何埋点**
⇒ 人写脚本不能再 `get_by_test_id("o-name")` 这种写法（生产里根本不存在）。

**定位顺序**（与框架 `locator_bridge` 的口径一致，只是这里是"按语义名直接来"的短路径）：
  ① 现场探测拿到该语义名的元素（含 `anchor` + `path` 结构化信号）
  ② 有「锚点 + 相对路径」⇒ 走 `scope_locate` 下钻（**生产真路径**）
  ③ 没锚点（页面级唯一控件）⇒ 用 `test_id` → `role+name` → `placeholder` 兜底
  ④ 都拿不到 ⇒ **如实抛错**（带现有语义名清单，方便改脚本；绝不猜）

⚠️ 缓存与刷新：探测一次有成本（订单页 ~140 控件）。默认缓存；**弹层开/关之后 DOM 变了**，
   必须 `refresh=True` 或调 `invalidate(page)` —— 否则拿着旧清单定位，会得到"看起来对、其实指错元素"。
"""
from __future__ import annotations

from pathlib import Path

_CACHE: dict[int, dict[str, dict]] = {}


def probe_names(page, *, refresh: bool = False) -> dict[str, dict]:
    """现场探测一次 ⇒ `{语义名: 元素}`（缓存；refresh=True 强制重探）。"""
    key = id(page)
    if refresh or key not in _CACHE:
        from framework.tools.probe.probe import probe_page
        items = probe_page(page)
        _CACHE[key] = {it["semantic_name"]: it for it in items if it.get("semantic_name")}
    return _CACHE[key]


def invalidate(page) -> None:
    """DOM 大改（弹窗开/关、换页、搜索刷新）后调用，下次 locate 会重新探测。"""
    _CACHE.pop(id(page), None)


def locate(page, name: str, *, refresh: bool = False):
    """按语义名定位 ⇒ Locator。定位不唯一/找不到就抛错并说明原因（绝不猜）。"""
    from framework.tools.probe.scope_locate import scope_locate

    names = probe_names(page, refresh=refresh)
    it = names.get(name)
    if it is None:
        cand = ", ".join(sorted(names)[:14])
        raise RuntimeError(f"语义名 {name!r} 不在现场探测清单里。现有（前 14 个）：{cand} …")
    if it.get("anchor") and it.get("path"):
        r = scope_locate(page, it["anchor"], it["path"])
        if not r.get("ok"):
            raise RuntimeError(f"「锚点 + 相对路径」下钻失败：{name!r} → {r.get('reason')}")
        return r["locator_obj"]
    if it.get("test_id"):
        loc = page.get_by_test_id(it["test_id"])
        if loc.count() == 1:
            return loc
        raise RuntimeError(f"{name!r} 用 test_id 命中 {loc.count()} 个（要求唯一）")
    if it.get("role") and it.get("name"):
        loc = page.get_by_role(it["role"], name=it["name"])
        if loc.count() == 1:
            return loc
        if loc.count() == 0:
            raise RuntimeError(f"{name!r} 按 role+name 命中 0 个（元素可能还没渲染/已消失）")
        raise RuntimeError(f"{name!r} 按 role+name 命中 {loc.count()} 个（歧义，需换更细的语义名）")
    raise RuntimeError(f"{name!r} 没有任何可定位信号（anchor/path/test_id/role 都空）：{it}")


def find(page, name: str, *, refresh: bool = False):
    """定位 ⇒ Locator；**找不到时返回 None**（用于"不该存在"的负向断言，别用 locate 硬抛）。"""
    try:
        return locate(page, name, refresh=refresh)
    except RuntimeError:
        return None
