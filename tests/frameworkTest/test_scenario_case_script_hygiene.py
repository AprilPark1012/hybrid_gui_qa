"""`scenarios/` · `cases/` · `scripts/` 三目录新陈代谢判据（R7-f · 2026-09-23 他定）。

**为什么要有它**（他的原话：无效文件要及时清理）：三个目录层层依赖，任何一层留孤儿，
最终都会变成「打包里有跑不通的东西」。已有判据只守住 `cases ⇄ datasets ⇄ test_cases.py`
（L15 那套），**场景层没人守** ⇒ 场景改名/删除后，AI 用例会变成**指向不存在场景的孤儿**。

口径（他 2026-09-23 选 1：**孤儿直接红**，不告警放行）：
  ① `cases/ai_*.json` 的 `scenario_id` **必须指向真实存在的场景文件** —— 孤儿 ⇒ **红**；
  ② `scenarios/` 下的场景**要么有 AI 用例、要么有手搓用例**覆盖 —— 未覆盖只**告警**
     （场景可以先写、用例后补；这不是"无效文件"，不该拦住开发）；
  ③ 反向：`scripts/datasets/` 不许有孤儿数据集（= L15 判据，这里只做交叉引用，不重复实现）；
  ④ 负向自证：判据自己能抓坏输入（造孤儿 ⇒ 必须报）。

⚠️ 录像 ⇄ 场景 的对账**不在这里**：录像住运行期目录（`output/llm_cassettes/`），
一类判据必须与 demo/运行期无关 ⇒ 那条归 `tests/featureTest/verify_e2e_scenario3_cassette*.py`。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CASES = REPO / "cases"
SCENARIOS = REPO / "scenarios"


# ---------------- 纯函数层（负向自证钉这几个）----------------

def scenario_ids(scen_dir: Path = SCENARIOS) -> set[str]:
    """现有场景 id（文件 stem；与用例里 `scenario_id` 同一口径）。"""
    return {p.stem for p in scen_dir.rglob("*.yml")}


def case_payload(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8", errors="replace"))


def orphan_ai_cases(scen_dir: Path = SCENARIOS, cases_dir: Path = CASES) -> list[str]:
    """返回「scenario_id 指向不存在场景」的 AI 用例（`<case>:<sid>` 形式）。"""
    ids = scenario_ids(scen_dir)
    out: list[str] = []
    for p in sorted(cases_dir.glob("ai_*.json")):
        try:
            sid = str(case_payload(p).get("scenario_id", "")).strip()
        except Exception:  # noqa: BLE001
            out.append(f"{p.stem}:<用例无法解析>")
            continue
        if not sid:
            out.append(f"{p.stem}:<缺 scenario_id>")
        elif sid not in ids:
            out.append(f"{p.stem}:{sid}")
    return out


def uncovered_scenarios(scen_dir: Path = SCENARIOS, cases_dir: Path = CASES) -> list[str]:
    """场景中**既没有 AI 用例、也没有手搓用例点名**的那些（告警用，不拦）。"""
    ids = scenario_ids(scen_dir)
    covered: set[str] = set()
    for p in cases_dir.glob("*.json"):
        try:
            payload = case_payload(p)
        except Exception:  # noqa: BLE001
            continue
        sid = str(payload.get("scenario_id", "")).strip()
        if sid:
            covered.add(sid)
        # 手搓用例可能用 scenario 段或 name 里提场景 id（宽松认一次）
        blob = json.dumps(payload, ensure_ascii=False)
        for sid2 in ids:
            if sid2 and sid2 in blob:
                covered.add(sid2)
    return sorted(ids - covered)


# ---------------- ① 孤儿 AI 用例（直接红）----------------

def test_no_orphan_ai_cases():
    """★R7-f 核心：AI 用例的 `scenario_id` 必须指向真实场景（场景删了 ⇒ 用例要跟着清）。"""
    orphans = orphan_ai_cases()
    assert not orphans, (
        "这些 AI 用例指向了不存在的场景（孤儿，R7-f 要求直接红并当批清理）：\n  - "
        + "\n  - ".join(orphans))


# ---------------- ② 场景覆盖（告警，不拦）----------------

def test_scenarios_are_covered_by_some_case():
    """场景未覆盖只告警（场景可以先写、用例后补）—— 但要让它**看得见**。"""
    miss = uncovered_scenarios()
    if miss:
        print(f"\n⚠️ 告警（不拦）：这些场景目前没有 AI 用例也没有手搓用例覆盖：{miss}"
              "\n    ⇒ 要么补用例，要么确认它只是备用的场景模板。")


def test_scenario_and_case_dirs_are_nonempty():
    """空目录也算「新陈代谢」失灵（场景/用例都没了 ⇒ 后面的对账全变空转）。"""
    assert scenario_ids(), "scenarios/ 下一个场景都没有 ⇒ 判据会空转"
    assert list(CASES.glob("*.json")), "cases/ 下一条用例都没有 ⇒ 判据会空转"


# ---------------- 负向自证 ----------------

def test_negative_orphan_detected(tmp_path):
    """造一个孤儿 ⇒ 必须被抓住（否则 ① 判据等于没写）。"""
    scen = tmp_path / "scenarios"
    scen.mkdir()
    (scen / "real_one.yml").write_text("scenario: x\n", encoding="utf-8")
    cases = tmp_path / "cases"
    cases.mkdir()
    (cases / "ai_ok.json").write_text(
        json.dumps({"case_id": "ai_ok", "scenario_id": "real_one"}), encoding="utf-8")
    (cases / "ai_orphan.json").write_text(
        json.dumps({"case_id": "ai_orphan", "scenario_id": "gone_away"}), encoding="utf-8")
    (cases / "ai_noid.json").write_text(
        json.dumps({"case_id": "ai_noid"}), encoding="utf-8")
    got = orphan_ai_cases(scen, cases)
    assert "ai_orphan:gone_away" in got, got
    assert any("缺 scenario_id" in g for g in got), got
    assert not any(g.startswith("ai_ok") for g in got), "正常用例不许误报"


def test_negative_uncovered_detected(tmp_path):
    scen = tmp_path / "scenarios"
    (scen / "sub").mkdir(parents=True)
    (scen / "sub" / "lonely.yml").write_text("scenario: y\n", encoding="utf-8")
    cases = tmp_path / "cases"
    cases.mkdir()
    (cases / "hand.json").write_text(json.dumps({"case_id": "hand"}), encoding="utf-8")
    assert uncovered_scenarios(scen, cases) == ["lonely"]
    (cases / "ai_c.json").write_text(
        json.dumps({"case_id": "ai_c", "scenario_id": "lonely"}), encoding="utf-8")
    assert uncovered_scenarios(scen, cases) == [], "被覆盖后不该再报"
