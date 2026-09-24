"""P20 判据草稿 —— 落地时拷进 tests/frameworkTest/（此刻先在仓库外草拟 ✓ 不干扰在跑的验收）。

设计依据：skill 的 `references/design/P20-按id分文件生成脚本与增量生成-方案.md`（口径已获批 ✓）
目标形态：
  cases/<scenario_id>/<case_id>.json
  scripts/generated/<scenario_id>/<case_id>.py      ← 一个用例一个脚本
  scripts/generated/conftest.py
  scripts/generated/index.json                      ← case_id → {script_path, 三种指纹}
  scripts/datasets/<case_id>.json                   ← 已有 ✓ 保持
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

GEN = REPO / "scripts" / "generated"
INDEX = GEN / "index.json"
LEGACY = REPO / "scripts" / "test_cases.py"


def _index() -> dict:
    assert INDEX.is_file(), f"缺 {INDEX} ⇒ generate 还没产出 index.json（P20-1 的交付）"
    return json.loads(INDEX.read_text(encoding="utf-8"))


def test_legacy_single_file_is_gone():
    """项目负责人明确不要"一个文件装全部用例" ⇒ 老路径必须消失（不做薄壳 ✗）。"""
    assert not LEGACY.exists(), (
        f"✗ 老产物还在：{LEGACY} —— P20 是一次性切换，不留兼容薄壳；"
        "迁移说明写进 README/HTML 即可")


def test_every_index_entry_has_a_unique_script():
    """每条用例一个**唯一**脚本文件（设计口径：一套数据 = 一条用例 = 一个脚本）。"""
    idx = _index()
    seen: dict[str, str] = {}
    for cid, meta in idx.items():
        sp = REPO / meta["script_path"]
        assert sp.is_file(), f"✗ {cid} 的脚本不存在：{meta['script_path']}"
        assert sp not in seen.values(), f"✗ 脚本被两条用例共用：{sp}（{cid} / {seen.get(str(sp))}）"
        seen[cid] = sp
        assert sp.parent.name not in ("", "generated"), (
            f"✗ {cid} 的脚本没放进场景目录：{sp}（应为 scripts/generated/<scenario_id>/<case_id>.py）")


def test_index_and_disk_are_bidirectionally_consistent():
    """index ↔ 磁盘**双向**一致：孤儿脚本 / 幽灵条目都要红（与 R7-f"三目录新陈代谢"同源）。"""
    idx = _index()
    on_disk = {str(p.relative_to(REPO)) for p in GEN.glob("*/*.py") if p.name != "conftest.py"}
    in_index = {m["script_path"] for m in idx.values()}
    assert not (on_disk - in_index), f"✗ 磁盘上有 index 不认识的孤儿脚本：{sorted(on_disk - in_index)}"
    assert not (in_index - on_disk), f"✗ index 里有磁盘上不存在的幽灵条目：{sorted(in_index - on_disk)}"


def test_index_records_three_fingerprints():
    """增量生成的依据字段必须齐：用例内容 / 场景内容 / 探测结果（缺一个就没法判"变了没有"）。"""
    idx = _index()
    need = {"script_path", "case_fingerprint", "scenario_fingerprint", "probe_fingerprint"}
    for cid, meta in idx.items():
        missing = need - set(meta)
        assert not missing, f"✗ {cid} 的 index 条目缺字段：{sorted(missing)}"

def test_no_flat_case_files_in_cases_root():
    """P20：用例必须按场景分目录（AI 进 <scenario_id>/，手搓进 manual/）=> cases/ 根下不许有 .json。

    为什么必须判：旧布局残留（平铺件）会造成同一 case_id 两个实例，污染"仓库用例数 vs 包内用例数"
    这类对账，也让"按场景找用例"的脚本时好时坏。（2026-09-24 实测：修复前的 replay 还原
    把 8 条用例写回了平铺位置，就是这么来的 ✗）
    """
    flat = sorted(p.name for p in (REPO / "cases").glob("*.json"))
    assert not flat, f"✗ cases/ 根下有平铺用例（旧布局残留，应进 <场景>/ 或 manual/）：{flat[:5]}"
