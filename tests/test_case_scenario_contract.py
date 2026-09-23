"""cases ↔ scenarios 的**来源契约**（R8 · 2026-09-23 AprilPark1012定）。

**契约（两条链路各自的来源，必须能一眼分清）**
  · **场景①（AI 链路）**：`cases/ai_*.json` **必须**带场景来源 —— `scenario_id` + `source_scenario`，
    且 `source_scenario` 指向**真实存在**的 `scenarios/**/*.yml`。
    ⇒ 内联 `--scenario "…"` 生成的用例**没有 yml 来源**，属**孤儿**：要么补一个场景文件，
    要么删掉（2026-09-23 就清掉一条这样的孤儿）。
  · **场景②（手搓链路）**：**其他所有用例都是手搓**，**不得**带 `scenario_id` / `source_scenario`。

**为什么需要**：现场发现 cases/ 里混着一条孤儿 AI 用例
（`ai_在合同列表页面的搜索框输入_1005_点击搜索按_235545`，内联场景生成、无 yml 来源，
内容还与 `contracts_search_by_no` 场景重复）—— 它的存在让「哪些用例能从场景**重现**」变得说不清，
而**可重现**正是这套框架的价值所在。判据把契约钉死，防止再混进来。

跑法（秒级，不需要 demo / key）：
    python -m pytest tests/test_case_scenario_contract.py -v
"""
from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CASES = REPO / "cases"
SCENARIOS = REPO / "scenarios"

# 场景来源字段（explore 落盘时回写）
SRC_FIELDS = ("scenario_id", "source_scenario")
_YML_REF = re.compile(r"^scenarios/[\w./-]+\.ya?ml$")


def load_case(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:                       # 坏 JSON 本身就是问题，如实抛出
        raise AssertionError(f"{path.name} 不是合法 JSON：{e}") from e
    return data if isinstance(data, dict) else {}


def iter_cases(cases_dir: Path):
    for p in sorted(cases_dir.glob("*.json")):
        yield p, load_case(p)


def scenario_files(scen_dir: Path) -> set[str]:
    return {p.relative_to(scen_dir.parent).as_posix() for p in sorted(scen_dir.rglob("*.yml"))}


def missing_scenario_sources(cases_dir: Path, repo: Path) -> list[str]:
    """AI 用例里「没有 / 指向不存在场景」的（返回可读说明，空 = 合规）。"""
    have = scenario_files(repo / "scenarios")
    bad: list[str] = []
    for p, d in iter_cases(cases_dir):
        if not p.name.startswith("ai_"):
            continue
        sid, src = d.get("scenario_id"), d.get("source_scenario")
        if not sid or not src:
            bad.append(f"{p.name}：缺 {'/'.join(f for f in SRC_FIELDS if not d.get(f))}（内联生成的用例属孤儿）")
            continue
        if not _YML_REF.match(str(src)) or str(src) not in have:
            bad.append(f"{p.name}：source_scenario={src} 不存在（可选项：{'、'.join(sorted(have))[:200]}）")
    return bad


def manual_cases_with_source(cases_dir: Path) -> list[str]:
    """手搓用例里「带了场景来源字段」的（返回可读说明，空 = 合规）。"""
    bad: list[str] = []
    for p, d in iter_cases(cases_dir):
        if p.name.startswith("ai_"):
            continue
        carried = [f for f in SRC_FIELDS if d.get(f)]
        if carried:
            bad.append(f"{p.name}：手搓用例不该带 {'/'.join(carried)}（场景②的来源是 cases/ 本身）")
    return bad


# ---------------- ① AI 用例必须有真实场景来源 ----------------

def test_ai_cases_have_existing_scenario():
    bad = missing_scenario_sources(CASES, REPO)
    assert not bad, (
        "AI 用例（ai_*.json）必须有**真实存在**的场景来源（场景①的契约）：\n  - " + "\n  - ".join(bad)
        + "\n  修法：补 `scenarios/**/*.yml` 后重跑 `explore --ai --scenario-file`，或删掉这条孤儿用例。")


# ---------------- ② 手搓用例不得带场景来源 ----------------

def test_manual_cases_have_no_scenario_source():
    bad = manual_cases_with_source(CASES)
    assert not bad, "手搓用例（场景②）不该带场景来源字段：\n  - " + "\n  - ".join(bad)


# ---------------- 负向自证（判据自身必须抓得住坏输入）----------------

def _fake(tmp: Path, cases: dict[str, dict], scenarios: tuple[str, ...] = ("a.yml",)):
    (tmp / "cases").mkdir(parents=True, exist_ok=True)
    for name, body in cases.items():
        (tmp / "cases" / name).write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
    (tmp / "scenarios").mkdir(parents=True, exist_ok=True)
    for s in scenarios:
        f = tmp / "scenarios" / s
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("scenario: x\n", encoding="utf-8")
    return tmp


def test_negative_orphan_ai_case_is_detected(tmp_path):
    """无场景来源的 AI 用例必须被抓（这正是 2026-09-23 清掉的那类）。"""
    t = _fake(tmp_path, {"ai_orphan.json": {"case_id": "ai_orphan", "steps": [], "asserts": []}})
    assert missing_scenario_sources(t / "cases", t) != []


def test_negative_dangling_scenario_reference_is_detected(tmp_path):
    """指向不存在场景的 AI 用例必须被抓（引用悬空比缺字段更隐蔽）。"""
    t = _fake(tmp_path, {"ai_x.json": {"case_id": "ai_x", "scenario_id": "x",
                                       "source_scenario": "scenarios/contracts/nope.yml"}},
              scenarios=("contracts/real.yml",))
    bad = missing_scenario_sources(t / "cases", t)
    assert len(bad) == 1 and "不存在" in bad[0], bad


def test_negative_manual_case_with_source_is_detected(tmp_path):
    """手搓用例偷偷带 source_scenario 也要被抓。"""
    t = _fake(tmp_path, {"manual_x.json": {"case_id": "manual_x", "scenario_id": "x"}})
    assert manual_cases_with_source(t / "cases") != []


def test_negative_valid_pair_is_not_flagged(tmp_path):
    """合规样例不许误伤（假红与假绿一样会摧毁闸门）。"""
    t = _fake(tmp_path, {
        "ai_ok.json": {"case_id": "ai_ok", "scenario_id": "ok",
                       "source_scenario": "scenarios/contracts/ok.yml"},
        "manual_ok.json": {"case_id": "manual_ok"},
    }, scenarios=("contracts/ok.yml",))
    assert missing_scenario_sources(t / "cases", t) == []
    assert manual_cases_with_source(t / "cases") == []
