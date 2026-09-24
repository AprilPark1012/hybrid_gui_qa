"""P20 之后二类脚本的共享小助手：把 case_id 映射到**新布局**的脚本路径。

为什么需要：产物从「单个 `scripts/test_cases.py`」改成
「`scripts/generated/<scenario_id>/<case_id>.py`（一个用例一个文件）」，
所以「按 case_id 跑一条用例」这件事不能再拼 `test_cases.py::test_<id>`，
而要查 `scripts/generated/index.json`（case_id → script_path 的唯一权威来源）。

⚠️ 只读、不改产物：本模块不做任何写操作（二类脚本的纪律：能不动产物就不动）。
"""
from __future__ import annotations

import json
from pathlib import Path

# tests/featureTest/_gen_layout.py → 仓库根
REPO = Path(__file__).resolve().parents[2]
GEN_DIR = REPO / "scripts" / "generated"
INDEX = GEN_DIR / "index.json"
DATASETS = REPO / "scripts" / "datasets"


def load_index() -> dict:
    """读 case_id → 元数据（含 script_path）。没生成过就返回空 dict（调用方自己判红）。"""
    try:
        return json.loads(INDEX.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def script_of(case_id: str) -> Path | None:
    """case_id → 该用例的脚本绝对路径；查不到返回 None（**不猜路径** ✗）。"""
    meta = load_index().get(case_id)
    if not meta:
        return None
    p = Path(meta["script_path"])
    return p if p.is_absolute() else (REPO / p)


def node_of(case_id: str, test_name: str | None = None) -> str | None:
    """case_id → pytest node id（`<脚本路径>::test_<case_id>`）；查不到返回 None。"""
    p = script_of(case_id)
    if p is None:
        return None
    return f"{p}::test_{test_name or case_id}"


def case_ids() -> list[str]:
    """当前产物的全部 case_id（按 index 排序，稳定可对账）。"""
    return sorted(load_index())


def dataset_of(case_id: str) -> Path:
    return DATASETS / f"{case_id}.json"
