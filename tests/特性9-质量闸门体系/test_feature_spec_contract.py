"""特性规格契约（V8.3.6）—— 规格与磁盘**双向一致**的守门判据。

背景（为什么单独一个文件）：
  V8.3.6 把「特性2 语义识别与分层定位」一分为二（语义识别 / 分层定位），其后顺延，
  共 10 个大特性 / 42 个子特性。规格落在 `framework/tools/spec/feature_spec.py`（单一来源），
  文档由 `build_tools/build_feature_map.py` 生成。

  但「单一来源」只有配上**校验**才成立 —— 否则加一个特性、忘了挂用例，
  文档照旧好看，实际没人验证那条特性。实测教训（同类）：
  `in_feature_dir` 里写死 `range(1, 10)`，加第 10 个特性后判据静默漏判、报假红。

本文件锁四件事：
  (1) 规格里列的每个 test/verify 文件**必须真实存在**（防"文档里有、磁盘上没有"）
  (2) 磁盘上每个 test_*.py / verify_*.py **必须有归属**（防"新加了用例没挂特性"）
  (3) 编号规范：特性连续 1..N、子特性形如 `N.M` 且同层唯一
  (4) 规格里声明的目录**必须存在**，且磁盘上的特性夹**必须都在规格里**（防目录漂移）
  (5) 生成的文档与规格一致（`build_feature_map.py --check`）

  负向自证已在设计时验证：把一个文件的归属删掉 / 加一个未挂的 test_*.py => 本文件立刻红。
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
TESTS = REPO / "tests"
sys.path.insert(0, str(REPO))

from framework.tools.spec.feature_spec import FEATURES, all_subfeatures, owner_index  # noqa: E402


def _disk_test_files() -> set[str]:
    """tests/特性N-*/ 下的所有一类/二类文件（相对 tests/ 的 path）。"""
    out: set[str] = set()
    for d in TESTS.iterdir():
        if not d.is_dir() or d.name.startswith("_"):
            continue
        for f in d.glob("*.py"):
            if f.name.startswith(("test_", "verify_")):
                out.add(f"{d.name}/{f.name}")
    return out


def _spec_files() -> set[str]:
    """规格里声明的所有文件名（不含目录）。"""
    return {fn for _n, _fn, s, _f in all_subfeatures()
            for fn in ((s.get("class1") or []) + (s.get("class2") or []))}


# ---------------- (1) 规格 -> 磁盘 ----------------

def test_every_spec_file_exists_on_disk():
    """规格里列的文件必须真实存在（防「文档写了、磁盘没有」）。"""
    disk_names = {p.name for p in TESTS.rglob("*.py")}
    missing = sorted(_spec_files() - disk_names)
    assert not missing, (
        f"规格里列了这些文件，但磁盘上找不到：{missing}\n"
        f"=> 要么文件名写错，要么文件被删了。改规格 framework/tools/spec/feature_spec.py 或补回文件。"
    )


# ---------------- (2) 磁盘 -> 规格 ----------------

def test_every_disk_case_has_an_owner():
    """磁盘上每个 test_/verify_ 文件都必须挂在某个子特性下（防「新加了用例没挂特性」）。"""
    owned = set(owner_index())
    stray = sorted({p.name for p in TESTS.rglob("*.py")
                    if p.name.startswith(("test_", "verify_"))} - owned)
    assert not stray, (
        f"这些用例文件没有归属（规格里查不到）：{stray}\n"
        f"=> 在 framework/tools/spec/feature_spec.py 里给它们挂上子特性，"
        f"否则「特性变更 => 用例同步」这条纪律就是个空话。"
    )


# ---------------- (3) 编号规范 ----------------

def test_feature_numbers_are_contiguous_from_one():
    """特性编号必须从 1 连续排到 N（不许断号，否则文档/目录编号会错位）。"""
    nos = [f["no"] for f in FEATURES]
    assert nos == list(range(1, len(nos) + 1)), (
        f"特性编号应为 1..{len(nos)} 连续，实际 {nos}"
    )


def test_subfeature_numbers_are_wellformed_and_unique():
    """子特性编号必须是 `<特性号>.<序号>` 形式，且全局唯一、同特性内从 1 连续。"""
    bad_form, dup, not_contig = [], [], []
    for f in FEATURES:
        subs = f.get("subs", [])
        seen_seq = []
        for s in subs:
            m = re.fullmatch(r"(\d+)\.(\d+)", str(s["no"]))
            if not m or int(m.group(1)) != f["no"]:
                bad_form.append(f"{s['no']}（属特性 {f['no']}）")
                continue
            seen_seq.append(int(m.group(2)))
        if seen_seq and seen_seq != list(range(1, len(seen_seq) + 1)):
            not_contig.append((f["no"], seen_seq))
    all_nos = [s["no"] for _n, _fn, s, _f in all_subfeatures()]
    dup = sorted({x for x in all_nos if all_nos.count(x) > 1})
    assert not bad_form, f"子特性编号形态不合法（应形如 2.1）：{bad_form}"
    assert not dup, f"子特性编号重复：{dup}"
    assert not not_contig, f"子特性序号不连续：{not_contig}"


def test_every_subfeature_has_name_and_goal():
    """每条子特性都要有名字和目标 —— 空壳子特性等于没拆。"""
    empty = [(f["no"], s.get("no")) for f in FEATURES for s in f.get("subs", [])
             if not (s.get("name") or "").strip() or not (s.get("goal") or "").strip()]
    assert not empty, f"这些子特性缺 name/goal：{empty}"


# ---------------- (4) 目录契约 ----------------

def test_spec_dirs_match_disk_feature_folders():
    """规格声明的目录必须存在；磁盘上的特性夹必须都在规格里（防目录漂移）。"""
    spec_dirs = {f["dir"] for f in FEATURES}
    disk_dirs = {d.name for d in TESTS.iterdir()
                 if d.is_dir() and d.name.startswith("特性")}
    missing = sorted(spec_dirs - disk_dirs)
    extra = sorted(disk_dirs - spec_dirs)
    assert not missing, f"规格声明了这些目录但磁盘没有：{missing}"
    assert not extra, f"磁盘有这些特性夹但规格没声明（新增特性要同步规格）：{extra}"


# ---------------- (5) 文档与规格一致 ----------------

def test_feature_map_doc_is_in_sync():
    """生成的 docs/feature_map.md 必须与规格一致（不一致就重跑生成器）。"""
    r = subprocess.run([sys.executable, str(REPO / "build_tools" / "build_feature_map.py"), "--check"],
                       cwd=REPO, capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, (
        f"特性映射文档与规格不一致：\n{r.stdout}\n{r.stderr}\n"
        f"=> 跑 .venv/bin/python build_tools/build_feature_map.py 重新生成。"
    )


# ---------------- (6) 统计口径抽查（防规格被"写空"）----------------

def test_spec_covers_all_case_files_by_count():
    """规格覆盖的文件名数量应与磁盘一致（防止某子特性的清单被整段删空而判据没感觉）。"""
    disk_names = {p.name for p in TESTS.rglob("*.py") if p.name.startswith(("test_", "verify_"))}
    spec = _spec_files()
    assert spec == disk_names, (
        f"规格覆盖与磁盘不一致。\n"
        f"  仅规格有：{sorted(spec - disk_names)}\n"
        f"  仅磁盘有：{sorted(disk_names - spec)}"
    )
