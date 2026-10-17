"""`scenarios/` · `cases/` · `scripts/` 三目录新陈代谢判据（R7-f · 2026-09-23 他定）。

**为什么要有它**（他的原话：无效文件要及时清理）：三个目录层层依赖，任何一层留孤儿，
最终都会变成「打包里有跑不通的东西」。已有判据只守住 `cases <-> datasets <-> test_cases.py`
（L15 那套），**场景层没人守** -> 场景改名/删除后，AI 用例会变成**指向不存在场景的孤儿**。

口径（他 2026-09-23 选 1：**孤儿直接红**，不告警放行）：
  (1) `cases/ai_*.json` 的 `scenario_id` **必须指向真实存在的场景文件** —— 孤儿 -> **红**；
  (2) `cases/ai_*.json` 的 `source_scenario` 必须**真实可解析**（形如 `scenarios/**/*.yml` 且文件在）；
  (3) `cases/ai_*.json` 必须带 `scenario_fingerprint` 且与**当前**场景文件一致（场景改了要刷新用例）；
  (4) `scenarios/` 下的场景**要么有 AI 用例、要么有非 AI 用例**覆盖 —— 未覆盖只**告警**
     （场景可以先写、用例后补；这不是"无效文件"，不该拦住开发）；
  (5) 反向：`scripts/datasets/` 不许有孤儿数据集（= L15 判据，这里只做交叉引用，不重复实现）；
  (6) 负向自证：判据自己能抓坏输入（造孤儿 / 悬空引用 / 改场景 -> 必须报）。

[!] 录像 <-> 场景 的对账**不在这里**：录像住运行期目录（`output/llm_cassettes/`），
一类判据必须与 demo/运行期无关 -> 那条归 `tests/_runner/verify_e2e_scenario3_cassette*.py`。

===============================================================================
[!] V8.6.4（合并重复判据 · 第二批 · 组 2）—— 本文件**保名**（它已含防空转守卫 + 覆盖告警，
    是三者里最全的），并吸收另两条同源判据：

  · `tests/特性9-质量闸门体系/test_case_scenario_contract.py`（**整文件删**）
      迁入：`source_scenario` 字段级校验 + `_YML_REF` 正则（原 :33 / :60-65）
            -> `test_ai_cases_have_resolvable_source_scenario`
      迁入：两条负向（孤儿「无来源」/ 悬空「指向不存在场景」）-> **合并成一条 parametrize**
      删掉：「合规不误伤」那条（原 :107-114）—— 接手 = 本文件 `test_negative_orphan_detected`
            末句「正常用例不许误报」（同一个意思，不必两份）
      删掉：重复的「场景存在性」检查（原 :58-59、:64 的 `sid not in ids`）——
            本文件 `orphan_ai_cases` / `scenario_ids` **已在查**，同一件事只留一处口径
  · `tests/特性9-质量闸门体系/test_ai_case_scenario_sync.py`（**整文件删**）
      迁入：`scenario_fingerprint` 同步（原 :70-77）+ 它的负向自证（原 :80-88）
            -> `test_ai_cases_record_scenario_fingerprint` / `test_negative_fingerprint_detects_change`
      删掉：重复的「场景存在性」检查（原 :58-59）同上

[!] `source_scenario` **不是死字段**（已核实，所以保持**硬要求**）：
    `generator_generate.py:148` 真的读它 —— `_scenario_text_of(str(case.get("source_scenario") or ""))`
    （注释写明「声明等待时长要用它」），:713 还拿它作 `scenario_id` 的回落取值，
    `kit_check_generate.py:82` 也消费它。
===============================================================================
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
CASES = REPO / "cases"
SCENARIOS = REPO / "scenarios"

#: `source_scenario` 的形态契约（从 test_case_scenario_contract.py 原样迁入）
_YML_REF = re.compile(r"^scenarios/[\w./-]+\.ya?ml$")


# ---------------- 纯函数层（负向自证钉这几个）----------------

def scenario_ids(scen_dir: Path = SCENARIOS) -> set[str]:
    """现有场景 id（文件 stem；与用例里 `scenario_id` 同一口径）。"""
    return {p.stem for p in scen_dir.rglob("*.yml")}


def case_payload(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8", errors="replace"))


def ai_cases(cases_dir: Path = CASES):
    """仓库里的 AI 用例（`ai_*.json`），跳过解析失败的（那类由 `orphan_ai_cases` 报）。"""
    for p in sorted(cases_dir.rglob("ai_*.json")):
        try:
            yield p, case_payload(p)
        except Exception:  # noqa: BLE001
            continue


def orphan_ai_cases(scen_dir: Path = SCENARIOS, cases_dir: Path = CASES) -> list[str]:
    """返回「scenario_id 指向不存在场景」的 AI 用例（`<case>:<sid>` 形式）。"""
    ids = scenario_ids(scen_dir)
    out: list[str] = []
    for p in sorted(cases_dir.rglob("ai_*.json")):
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


def scenario_files(scen_dir: Path = SCENARIOS) -> set[str]:
    """`scenarios/**/*.yml` 的**仓库相对路径**（`source_scenario` 的同一口径）。"""
    return {p.relative_to(scen_dir.parent).as_posix() for p in sorted(scen_dir.rglob("*.yml"))}


def source_scenario_problems(scen_dir: Path = SCENARIOS, cases_dir: Path = CASES) -> list[str]:
    """AI 用例的 `source_scenario`：必须存在、形如 `scenarios/**/*.yml`、且指向真实文件。

    [!] 只查来源字段本身 —— 「场景是否存在（`scenario_id`）」由 `orphan_ai_cases` 查，
    两条判据各守一个字段，不重复报警（同一件事只留一处口径）。
    """
    have = scenario_files(scen_dir)
    out: list[str] = []
    for p, payload in ai_cases(cases_dir):
        src = str(payload.get("source_scenario", "") or "").strip()
        if not src:
            out.append(f"{p.stem}:<缺 source_scenario>（内联场景生成的用例属孤儿）")
        elif not _YML_REF.match(src) or src not in have:
            out.append(f"{p.stem}:source_scenario={src} 不存在"
                       f"（可选项：{'、'.join(sorted(have))[:200]}）")
    return out


def scenario_fingerprint(path: Path) -> str:
    """场景文件内容指纹（只跟内容有关，与路径/时间无关）—— 与用例落盘时的口径同源。"""
    data = path.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
    return hashlib.sha256(data.encode("utf-8")).hexdigest()[:16]


def fingerprint_problems(scen_dir: Path = SCENARIOS, cases_dir: Path = CASES) -> list[str]:
    """AI 用例的场景指纹必须与**当前**场景文件一致（不一致 -> 场景改过而用例没刷新）。

    [!] 只查指纹 —— 「缺 scenario_id」/「场景不存在」由 `orphan_ai_cases` 报，不重复说。
    """
    files = {p.stem: p for p in scen_dir.rglob("*.yml")}
    out: list[str] = []
    for p, payload in ai_cases(cases_dir):
        sid = str(payload.get("scenario_id", "") or "").strip()
        if not sid or sid not in files:
            continue
        fp = str(payload.get("scenario_fingerprint", "") or "").strip()
        if not fp:
            out.append(f"{p.stem}:<缺 scenario_fingerprint（D3 要求记录场景指纹）>")
            continue
        want = scenario_fingerprint(files[sid])
        if fp != want:
            out.append(f"{p.stem}:<场景 {sid} 变过（指纹 {fp} -> {want}）-> 要刷新用例>")
    return out


def uncovered_scenarios(scen_dir: Path = SCENARIOS, cases_dir: Path = CASES) -> list[str]:
    """场景中**既没有 AI 用例、也没有非 AI 用例点名**的那些（告警用，不拦）。"""
    ids = scenario_ids(scen_dir)
    covered: set[str] = set()
    for p in cases_dir.rglob("*.json"):
        try:
            payload = case_payload(p)
        except Exception:  # noqa: BLE001
            continue
        sid = str(payload.get("scenario_id", "")).strip()
        if sid:
            covered.add(sid)
        # 非 AI 用例可能用 scenario 段或 name 里提场景 id（宽松认一次）
        blob = json.dumps(payload, ensure_ascii=False)
        for sid2 in ids:
            if sid2 and sid2 in blob:
                covered.add(sid2)
    return sorted(ids - covered)


# ---------------- (1) 孤儿 AI 用例（直接红）----------------

def test_no_orphan_ai_cases():
    """★R7-f 核心：AI 用例的 `scenario_id` 必须指向真实场景（场景删了 -> 用例要跟着清）。"""
    orphans = orphan_ai_cases()
    assert not orphans, (
        "这些 AI 用例指向了不存在的场景（孤儿，R7-f 要求直接红并当批清理）：\n  - "
        + "\n  - ".join(orphans))


# ---------------- (2) 场景来源字段（`source_scenario`，直接红）----------------

def test_ai_cases_have_resolvable_source_scenario():
    """★AI 用例的 `source_scenario` 必须是**真实可解析**的 `scenarios/**/*.yml` 引用。

    为什么**保持硬要求**（不是历史遗留）：这条字段**有人真的在读** ——
    `generator_generate.py:148` 用它取场景原文（`_scenario_text_of(...)`，
    注释写明「声明等待时长要用它」）、:713 拿它作 `scenario_id` 的回落取值、
    `kit_check_generate.py:82` 也消费它。字段缺失/悬空 -> 下游悄悄退化成「没有场景原文」，
    表现为「等待时长没按场景声明走」这类**看着像业务问题**的故障。

    原住在 `test_case_scenario_contract.py`（V8.6.4 整文件删，本条迁入）。
    """
    bad = source_scenario_problems()
    assert not bad, (
        "AI 用例（ai_*.json）的 `source_scenario` 缺失或指向不存在的场景文件：\n  - "
        + "\n  - ".join(bad)
        + "\n  修法：补 `scenarios/**/*.yml` 后重跑 "
          "`explore --ai --scenario-file <场景.yml>`，或删掉这条孤儿用例。")


# ---------------- (3) 场景指纹同步（直接红）----------------

def test_ai_cases_record_scenario_fingerprint():
    """★D3 核心：AI 用例必须记下场景指纹，且与当前场景文件一致。

    **他的原话**：「补一条 AI 用例，但是**如果关联的 scenario 变化了，它就要刷新过来，保证同步**。」
    -> 场景文件一改（指纹变）-> 判据当场红 -> 必须重新生成才能绿。
    刷新命令（用录像回放，不花 token）：
      `python -m framework.cli explore --ai --scenario-file <场景.yml> --llm-cassette`
      然后 `python -m framework.cli generate`

    原住在 `test_ai_case_scenario_sync.py`（V8.6.4 整文件删，本条迁入）。
    """
    got = fingerprint_problems()
    assert not got, (
        "这些 AI 用例与场景不同步（D3 要求：场景变了就把用例刷新过来）：\n  - "
        + "\n  - ".join(got)
        + "\n刷新办法：python -m framework.cli explore --ai --scenario-file <场景.yml> --llm-cassette"
          " && python -m framework.cli generate")


# ---------------- (4) 场景覆盖（告警，不拦）----------------

def test_scenarios_are_covered_by_some_case():
    """场景未覆盖只告警（场景可以先写、用例后补）—— 但要让它**看得见**。"""
    miss = uncovered_scenarios()
    if miss:
        print(f"\n[!] 告警（不拦）：这些场景目前没有 AI 用例也没有非 AI 用例覆盖：{miss}"
              "\n    -> 要么补用例，要么确认它只是备用的场景模板。")


# ---------------- (5) 防空转哨兵（全仓唯一 · V8.6.4 加固）----------------

def test_scenario_and_case_dirs_are_nonempty():
    """★防空转哨兵（**全仓唯一**）—— 它守着本文件三条对账 + 另一条判据的仓库扫描。

    **为什么必须有它**：本文件的判据全是「遍历目录里的文件，逐个检查，有坏的就红」。
    这类判据有一个共同的坏法 —— **目录空了，循环体恒空，判据全绿**（假阳）。
    具体兜着四条：
      · 本文件 `test_no_orphan_ai_cases`（遍历 `ai_*.json`）
      · 本文件 `test_ai_cases_have_resolvable_source_scenario`（同上）
      · 本文件 `test_ai_cases_record_scenario_fingerprint`（同上）
      · `test_case_evidence_gate.py::test_repo_cases_have_no_weak_evidence`（遍历 `cases/**.json` 查弱换页证据）

    口径（V8.6.4 **加固**）：原来只判「非空」—— 只要 `cases/` 下还有任何 json（例如只剩手搓用例）
    就绿；而 `ai_*.json` **归零**时，上面三条 AI 用例对账**同时变成空转**，哨兵却不会响。
    所以改成**分别**要求：
      · `cases/` 下 `ai_*.json` **>= 1**（AI 用例归零 -> 三条对账全空转）
      · `scenarios/` 下 `*.yml` **>= 1**（场景归零 -> 覆盖告警与孤儿判据全空转）
    真值余量极小（2026-10-17：`cases/` 只有 **1** 条 `ai_*.json`、`scenarios/` 只有 **1** 个 yml），
    所以这条哨兵不是形式主义 —— 清一次产物就会踩到。
    """
    ai = sorted(CASES.rglob("ai_*.json"))
    scen = sorted(SCENARIOS.rglob("*.yml"))
    assert ai, (
        "cases/ 下一条 ai_*.json 都没有 -> 本文件三条 AI 用例对账（孤儿 / 来源 / 指纹）"
        "与 test_case_evidence_gate 的仓库扫描会**同时空转**（循环体恒空 = 全绿假阳）。"
        "不是判据该放宽，而是仓库状态不对：要么补回 AI 用例，要么明确「本仓不再有 AI 用例」"
        "并同步删掉那几条对账判据。"
    )
    assert scen, (
        "scenarios/ 下一个 yml 都没有 -> 场景侧对账（覆盖告警 / 孤儿判定）全部空转（假绿）。"
    )


# ---------------- 负向自证 ----------------

def test_negative_orphan_detected(tmp_path):
    """造一个孤儿 -> 必须被抓住（否则 (1) 判据等于没写）。"""
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


@pytest.mark.parametrize("name,body,expect", [
    # 孤儿：内联场景生成、没有 yml 来源（2026-09-23 真清掉的就是这一类）
    ("ai_orphan.json",
     {"case_id": "ai_orphan", "scenario_id": "real_one", "steps": [], "asserts": []},
     "缺 source_scenario"),
    # 悬空：引用了不存在的场景文件（比缺字段更隐蔽）
    ("ai_dangling.json",
     {"case_id": "ai_dangling", "scenario_id": "real_one",
      "source_scenario": "scenarios/contracts/nope.yml"},
     "不存在"),
])
def test_negative_source_scenario_problems_detected(tmp_path, name, body, expect):
    """负向自证（两条合一 parametrize）：孤儿（无来源）/ 悬空（指向不存在场景）各造一例。

    合并的唯一依据：**它们共同的前提一样** —— 都要求 `source_scenario_problems()`
    对**字段本身**有问题的那条用例报出一条、且报的条数恰好 1（不重不漏）；
    两条的差别只在「坏在哪」。原住在 `test_case_scenario_contract.py`（V8.6.4 迁入）。
    """
    scen = tmp_path / "scenarios" / "contracts"
    scen.mkdir(parents=True)
    (scen / "real_one.yml").write_text("scenario: x\n", encoding="utf-8")
    cases = tmp_path / "cases"
    cases.mkdir()
    (cases / name).write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
    got = source_scenario_problems(tmp_path / "scenarios", cases)
    assert len(got) == 1 and expect in got[0], got


def test_negative_fingerprint_detects_change(tmp_path):
    """负向自证：改一个字 -> 指纹必须变（否则同步判据永远绿）；改回来 -> 复原。

    「改回来必须复原」这半句才是关键：它证明指纹**只跟内容有关**（跟路径/时间/mtime 无关），
    否则每次重跑判据都会红（假红比假绿一样致命）。原住在 `test_ai_case_scenario_sync.py`。
    """
    f = tmp_path / "s.yml"
    f.write_text("id: a\ntitle: 甲\n", encoding="utf-8")
    h1 = scenario_fingerprint(f)
    f.write_text("id: a\ntitle: 乙\n", encoding="utf-8")
    assert scenario_fingerprint(f) != h1, "场景内容变了但指纹没变 -> 同步判据失效"
    f.write_text("id: a\ntitle: 甲\n", encoding="utf-8")
    assert scenario_fingerprint(f) == h1, "内容改回来指纹应复原（说明只跟内容有关）"


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
