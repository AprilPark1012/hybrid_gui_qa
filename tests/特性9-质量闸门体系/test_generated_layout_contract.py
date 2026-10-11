"""P20 判据草稿 —— 落地时拷进 tests/_helpers/（此刻先在仓库外草拟 v 不干扰在跑的验收）。

设计依据：skill 的 `references/design/P20-按id分文件生成脚本与增量生成-方案.md`（口径已获批 v）
目标形态：
  cases/<scenario_id>/<case_id>.json
  scripts/generated/<scenario_id>/<case_id>.py      ← 一个用例一个脚本
  scripts/generated/conftest.py
  scripts/generated/index.json                      ← case_id → {script_path, 三种指纹}
  scripts/datasets/<case_id>.json                   ← 已有 v 保持
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
    assert INDEX.is_file(), f"缺 {INDEX} -> generate 还没产出 index.json（P20-1 的交付）"
    return json.loads(INDEX.read_text(encoding="utf-8"))


def test_legacy_single_file_is_gone():
    """项目负责人明确不要"一个文件装全部用例" -> 老路径必须消失（不做薄壳 X）。"""
    assert not LEGACY.exists(), (
        f"X 老产物还在：{LEGACY} —— P20 是一次性切换，不留兼容薄壳；"
        "迁移说明写进 README/HTML 即可")


def test_every_index_entry_has_a_unique_script():
    """每条用例一个**唯一**脚本文件（设计口径：一套数据 = 一条用例 = 一个脚本）。"""
    idx = _index()
    seen: dict[str, str] = {}
    for cid, meta in idx.items():
        sp = REPO / meta["script_path"]
        assert sp.is_file(), f"X {cid} 的脚本不存在：{meta['script_path']}"
        assert sp not in seen.values(), f"X 脚本被两条用例共用：{sp}（{cid} / {seen.get(str(sp))}）"
        seen[cid] = sp
        assert sp.parent.name not in ("", "generated"), (
            f"X {cid} 的脚本没放进场景目录：{sp}（应为 scripts/generated/<scenario_id>/<case_id>.py）")


def test_index_and_disk_are_bidirectionally_consistent():
    """index <-> 磁盘**双向**一致：孤儿脚本 / 幽灵条目都要红（与 R7-f"三目录新陈代谢"同源）。"""
    idx = _index()
    # [!] 跨平台（2026-10-07 修）：Windows 上 str(relative_to) 给 `scripts\generated\…`，
    # 而 index.json 里存的是 `/` 风格 -> 集合永远对不上（假红）。统一用 as_posix()。
    on_disk = {p.relative_to(REPO).as_posix() for p in GEN.glob("*/*.py") if p.name != "conftest.py"}
    in_index = {m["script_path"] for m in idx.values()}
    assert not (on_disk - in_index), f"X 磁盘上有 index 不认识的孤儿脚本：{sorted(on_disk - in_index)}"
    assert not (in_index - on_disk), f"X index 里有磁盘上不存在的幽灵条目：{sorted(in_index - on_disk)}"


def test_index_records_three_fingerprints():
    """增量生成的依据字段必须齐：用例内容 / 场景内容 / 探测结果（缺一个就没法判"变了没有"）。"""
    idx = _index()
    need = {"script_path", "case_fingerprint", "scenario_fingerprint", "probe_fingerprint"}
    for cid, meta in idx.items():
        missing = need - set(meta)
        assert not missing, f"X {cid} 的 index 条目缺字段：{sorted(missing)}"


def test_renderer_fingerprint_covers_render_logic_not_only_header():
    """渲染器指纹必须覆盖**渲染逻辑**，不能只哈希模块头模板。

    为什么（2026-10-10 实测，同类栽第二回）：只哈希 `_MODULE_HEADER` 时，改了**步骤体渲染逻辑**
    （给 goto 加相对地址补齐）后 generate 照报 `重写 0 · 跳过（无变化）`，生成物里还是旧代码 ——
    "改了却没生效"被静默吞掉一整轮排查。现在指纹 = 生成器源码 + 模块头模板。
    """
    import hashlib
    import json as _json
    import framework.features.f02_semantic.generator_generate as G

    src = (REPO / "framework" / "features" / "f02_semantic" / "generator_generate.py").read_text(encoding="utf-8")
    expect = hashlib.sha256((src + "\x00" + G._MODULE_HEADER).encode("utf-8")).hexdigest()[:16]
    only_header = hashlib.sha256(G._MODULE_HEADER.encode("utf-8")).hexdigest()[:16]
    assert expect != only_header, "指纹与只哈希模块头等价 -> 渲染逻辑改了也不会重写产物"
    idx = _index()
    bad = [cid for cid, m in idx.items() if m.get("template_fingerprint") != expect]
    assert not bad, (f"X 这些用例的 template_fingerprint 不是「渲染器源码 + 模块头」的哈希：{bad[:5]}"
                     f" —— 要么重跑 generate，要么指纹退回了只覆盖模块头")
    assert "template_fingerprint" in _json.dumps(idx, ensure_ascii=False), "index 里没有渲染器指纹字段"

def test_no_flat_case_files_in_cases_root():
    """P20：用例必须按场景分目录（AI 进 <scenario_id>/，手搓进 manual/）=> cases/ 根下不许有 .json。

    为什么必须判：旧布局残留（平铺件）会造成同一 case_id 两个实例，污染"仓库用例数 vs 包内用例数"
    这类对账，也让"按场景找用例"的脚本时好时坏。（2026-09-24 实测：修复前的 replay 还原
    把 8 条用例写回了平铺位置，就是这么来的 X）
    """
    flat = sorted(p.name for p in (REPO / "cases").glob("*.json"))
    assert not flat, f"X cases/ 根下有平铺用例（旧布局残留，应进 <场景>/ 或 manual/）：{flat[:5]}"


def test_generated_case_scripts_import_every_harness_helper_they_call():
    """生成的用例脚本里调用的 `_xxx()` 辅助，必须都在 `from _harness import (...)` 名单里。

    为什么（2026-10-11 实测）：方案 ③ 框架兜底补出 `row_index=-1` -> 渲染成 `_act_row(...)`，
    而 import 名单里漏了 `_act_row` -> **生成期闸门全绿、真跑 `NameError`**（跑起来才知道）。
    「模板渲染出的调用」与「import 名单」必须成对维护 —— 靠人眼守不住，判据来守。
    """
    import re
    harness = (GEN / "_harness.py").read_text(encoding="utf-8")
    helpers = set(re.findall(r"^def (_[A-Za-z_][A-Za-z0-9_]*)", harness, re.M))
    assert helpers, "没解析出 harness 的辅助函数 -> 判据前提失效，需人工确认"
    bad: list[str] = []
    for py in sorted(GEN.rglob("*.py")):
        if py.name in ("_harness.py", "conftest.py") or "__pycache__" in str(py):
            continue
        src = py.read_text(encoding="utf-8")
        imported: set[str] = set()
        # [!] 跨行 `from _harness import (` 块里**可能有带 ASCII `)` 的注释**（如"（夹具靠它暴露）"），
        #   用 `\(([^)]*)\)` 会在那个注释处**提前截断** -> 名单后半段的名字被判成"没 import"
        #   （2026-10-11 实测：把 `_assert_wait_text` 误报成漏 import）。所以按"行首的 `)`"收块。
        i_imp = src.find("from _harness import (")
        if i_imp >= 0:
            j_end = src.find("\n)", i_imp)
            block = src[i_imp:(j_end if j_end > 0 else len(src))]
            imported |= set(re.findall(r"(_[A-Za-z_][A-Za-z0-9_]*)", block))
        for line in re.findall(r"^from _harness import ([^(\n]+)$", src, re.M):   # 单行形式
            imported |= {x.strip() for x in line.split(",") if x.strip()}
        for call in set(re.findall(r"(?<![\w.])(_[A-Za-z_][A-Za-z0-9_]*)\s*\(", src)):
            if call in helpers and call not in imported:
                bad.append(f"{py.name}: 调了 harness 的 {call}() 却没 import")
    assert not bad, ("生成的用例脚本漏 import 辅助函数（真跑必 NameError）:\n"
                     + "\n".join(sorted(set(bad))))
