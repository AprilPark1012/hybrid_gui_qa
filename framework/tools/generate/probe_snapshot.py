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

#: 快照文件名（落在 `scripts/generated/` 下，与 `_harness.py` 同目录）——
#: 运行时按 `Path(__file__).parent` 找它，不依赖任何绝对路径/环境变量。
SNAPSHOT_FILENAME = "_probe_snapshot.json"

#: 快照里保留的字段（= 定位所需的最小集；`_to_ref` 要用的都在）
_KEEP = ("semantic_name", "test_id", "role", "tag", "name", "placeholder", "text",
         "label", "nearby_text", "container_heading", "help_text", "page", "page_hint",
         "anchor", "path", "opens_new_tab")


def _norm(it: dict) -> dict:
    """只留定位要用到的字段（体积可控，且与探测源头无关时形状一致）。"""
    out = {k: it[k] for k in _KEEP if it.get(k) not in (None, "", False)}
    if not out.get("semantic_name"):
        return {}
    return out


def items_from_element_map(data: dict) -> list[dict]:
    """从 explore 的 `element_map_*.json` 建条目（**这一步就是 AI 看到的那份命名**）。

    两个来源，缺一不可（2026-10-10 S1 收口）：
      · `steps[].element`：AI **实际用到**的名字（老行为，保持优先）；
      · `probe_items`：本次探索**喂给 AI 的完整清单**（权威名字来源）—— 手搓用例 / 断言引用的、
        AI 没用过的控件名只能从这里拿到（现场重探拿不到跨页唯一化的上下文，实测补 0/1）。
    """
    out: list[dict] = []
    seen: set[str] = set()
    for src in (list((data or {}).get("steps") or []), list((data or {}).get("probe_items") or [])):
        for entry in src:
            el = (entry.get("element") or {}) if isinstance(entry, dict) and "element" in entry else entry
            if not isinstance(el, dict):
                continue
            n = _norm(el)
            if n and n["semantic_name"] not in seen:
                seen.add(n["semantic_name"])
                out.append(n)
    return out


def items_from_probe_snapshot(data) -> list[dict]:
    """从 `probe_*.json` 快照建条目（兼容它既可能是 list 也可能是 {"items": [...]}）。"""
    raw = data.get("items") if isinstance(data, dict) else data
    out: list[dict] = []
    seen: set[str] = set()
    for it in raw or []:
        if not isinstance(it, dict):
            continue
        n = _norm(it)
        if n and n["semantic_name"] not in seen:
            seen.add(n["semantic_name"])
            out.append(n)
    return out


def index_from_items(items: list[dict]) -> dict[str, dict]:
    """条目列表 -> {语义名: 条目}（后者不覆盖前者，保持首次出现优先）。"""
    out: dict[str, dict] = {}
    for it in items or []:
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
    return index_from_items(items_from_probe_snapshot(data))
