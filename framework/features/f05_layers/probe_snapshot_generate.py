# -*- coding: utf-8 -*-
"""explore 探测快照的**唯一读写入口**（V8.4.3+）。

## 为什么需要它（实测事故）

运行时解析「语义名 → 控件」走过**两条链路**，而它们的**命名规则不同**：

| 链路 | 命名规则 | 同一控件实测拿到的名字 |
|---|---|---|
| explore（跨页合并 -> **AI 看到的就是这份**） | 跨页重名 -> `原名@页名` | `保存@订单详情页` |
| generate/试跑（`probe_page` **单页**重探） | 同页容器唯一化 -> `原名@容器` | `保存` / `保存@订单详情` |

结果：AI 照它看到的清单写 `保存@订单详情页`，运行时索引里没有 -> 模糊兜底发现
多个名字含它 -> 抛「语义名歧义」直接失败。

**这不是某个场景的特例**：凡是跨页重名控件（保存 / 取消 / 返回 / 编辑…）都会踩。

## 口径

**explore 快照 = 唯一权威的名字来源**（AI 看的和跑的必须是同一份）。
现场重探只用于补快照里**没有**的名字（例如弹层打开后才出现的控件），且必须出声留痕。

本模块把「快照长什么样、从哪些来源能建出来」收敛到一处，
避免 generate 与运行时各写一套解析（那正是本项目反复复发的那类问题）。
"""
from __future__ import annotations

import json
from pathlib import Path

from framework.features.f03_locate.element_map import load_pages

#: 快照文件名（落在 `scripts/generated/` 下，与 `_harness.py` 同目录）——
#: 运行时按 `Path(__file__).parent` 找它，不依赖任何绝对路径/环境变量。
SNAPSHOT_FILENAME = "_probe_snapshot.json"

#: 快照里保留的字段（= 定位所需的最小集；`_to_ref` 要用的都在）
_KEEP = ("semantic_name", "test_id", "element_id", "role", "tag", "name", "placeholder", "text",
         "label", "nearby_text", "container_heading", "help_text", "page", "page_hint",
         "anchor", "path", "opens_new_tab",
         # P25 片 3：**有效性标记要进运行时快照**（D3：置 false 的条目保留在快照里 = 留痕，
         #   但**不参与定位索引** —— 见 index_from_items）。
         "isValid")


def _norm(it: dict) -> dict:
    """只留定位要用到的字段（体积可控，且与探测源头无关时形状一致）。"""
    out = {k: it[k] for k in _KEEP if it.get(k) not in (None, "", False)}
    if not out.get("semantic_name"):
        return {}
    return out


def _entry_element(entry) -> dict | None:
    """从「步骤条目」或「控件条目」里取出**控件字典**（步骤条目嵌在 element 里）。"""
    if hasattr(entry, "element") or hasattr(entry, "action"):        # TestStep
        el = getattr(entry, "element", None)
        if el is None:
            return None
        return el.to_dict() if hasattr(el, "to_dict") else (el if isinstance(el, dict) else None)
    if isinstance(entry, dict) and "element" in entry:
        el = entry.get("element")
        return el if isinstance(el, dict) else None
    return entry if isinstance(entry, dict) else None


def items_from_element_map(data) -> list[dict]:
    """从 explore 的 elementMap 产物建条目（**这一步就是 AI 看到的那份命名**）。

    两个来源，缺一不可（2026-10-10 S1 收口）：
      · `steps[].element`：AI **实际用到**的名字（老行为，保持优先）；
      · `probe_items`：本次探索**喂给 AI 的完整清单**（权威名字来源）—— 手搓用例 / 断言引用的、
        AI 没用过的控件名只能从这里拿到（现场重探拿不到跨页唯一化的上下文，实测补 0/1）。

    [!] P25 片 3：读法**收敛到 `element_map.load_pages` 一处** —— 产物形态（list 一页一对象）
        变了之后，各处再各写一套「先判 list 还是 dict」必漏一处（本模块原先就有第二种读法
        `items_from_probe_snapshot`，两套永远只改一套）。**steps 优先于 probe_items**
        （同名先到先得）在跨页下同样保持：先收全部页的 steps，再收全部页的 probe_items。
    """
    pages = load_pages(data)
    from framework.features.f03_locate.element_map import merge_entry_fields
    # 先收集**权威清单**（probe_items）—— 只有它有探测期的定位信号（anchor/path/test_id）
    manifest: dict[str, dict] = {}
    for pg in pages:
        for it in (pg.probe_items or []):
            if isinstance(it, dict) and it.get("semantic_name"):
                manifest.setdefault(str(it["semantic_name"]), it)
    out: list[dict] = []
    seen: set[str] = set()
    for key in ("steps", "probe_items"):
        for pg in pages:
            for entry in (getattr(pg, key, None) or []):
                el = _entry_element(entry)
                if not isinstance(el, dict):
                    continue
                # [!] 名字仍按「steps 优先」，但**用清单条目补齐定位字段** ——
                #   否则 AI 的名字引用会把探测期的 anchor/path 顶掉（真 bug，见 element_map 注释）。
                src = manifest.get(str(el.get("semantic_name") or ""))
                if src is not None and src is not el:
                    el = merge_entry_fields(el, src)
                n = _norm(el)
                if n and n["semantic_name"] not in seen:
                    seen.add(n["semantic_name"])
                    out.append(n)
    return out


def items_from_runtime_snapshot(data) -> list[dict]:
    """从运行时快照（`_probe_snapshot.json`，形态 `{"items": [...]}`）建条目。

    [!] 保留它是因为**它自己的产物形态**与 elementMap 不同（那是运行期索引缓存，不是探测产物）；
        但读法同样收敛到 `load_pages`（`load_pages` 认 `{"items": [...]}` 这条容器形态），
        不再有第二套解析。原 `items_from_probe_snapshot` 承担的就是这件事，已合并到这里。
    """
    return items_from_element_map(data)


def index_from_items(items: list[dict]) -> dict[str, dict]:
    """条目列表 -> {语义名: 条目}（后者不覆盖前者，保持首次出现优先）。

    [!] P25 片 3（D3）：`isValid=false` 的条目**进快照留痕、但不进索引** ——
        索引是运行时定位用的，收进失效控件 = 运行期照样点到它（报出来的错还指向别处）。
    """
    out: dict[str, dict] = {}
    for it in items or []:
        if isinstance(it, dict) and it.get("isValid") is False:
            continue
        n = _norm(it)
        if n:
            out.setdefault(n["semantic_name"], n)
    return out


def write_snapshot(dir_path: Path, items: list[dict]) -> Path | None:
    """把条目落成 `_probe_snapshot.json`。条目为空则不写（避免留下空快照误导运行时）。"""
    idx = index_from_items(items)
    if not idx:
        return None
    d = Path(dir_path)
    d.mkdir(parents=True, exist_ok=True)
    p = d / SNAPSHOT_FILENAME
    p.write_text(json.dumps({"items": list(idx.values())}, ensure_ascii=False, indent=1),
                 encoding="utf-8")
    return p


def load_snapshot(dir_path: Path | str) -> dict[str, dict]:
    """读快照 -> {语义名: 条目}。读不到/格式坏 -> 返回空 dict（运行时退回现场探测）。"""
    p = Path(dir_path) / SNAPSHOT_FILENAME
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return index_from_items(items_from_runtime_snapshot(data))
