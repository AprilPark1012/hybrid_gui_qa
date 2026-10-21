"""L34-a 守卫：步骤字段命名只许一套 —— `op` / `desc`（方案 A，2026-10-21 定）。

为什么需要这条判据（历史）：
  控件图层（`TestStep`，落 `output/element_maps/*.json`）曾用 `action` / `description`，
  用例层（`cases/*.json`）用 `op` / `desc`。为让两侧互通，代码里长出了：
    · 一张**恒等映射**表 `_OP_MAP`（`{"goto": "goto", ...}`）—— 它真正的作用只是白名单，
      却让「改名」看起来像「翻译」；
    · **6 处「两个名字都认」的垫片**（`step_get(x, "op") or step_get(x, "action")`）。
  垫片的害处是**静默**：`TestStep.from_dict` 对缺键不抛错，于是老产物缺 `op` 时
  静默得到空串 -> 页面分组/行定位兜底悄悄失效，测试照样绿。一条规则两个名字，
  最终没人能回答「产物里到底该有哪个键」。

本判据把口径钉成一条：**`op` / `desc`，只此一套**。
  1. 源码单名：`framework/` `build_tools/` `scripts/` `tests/` 的 `.py` 里出现旧键名的
     **字典键、属性访问、以及 `.get(旧键)` 双读**，一律红（五种形态见下方 `PATTERNS`）；
  2. 产物键集：`cases/**/*.json` 与 `output/element_maps/**/*.json` 的 `steps[*]`
     出现 `action` / `description` -> 红；并断言「`TestStep.__dataclass_fields__` 的名字集
     == 产物键集」（堵住「字段加了、`to_dict` 漏传」那类静默丢字段的坑 —— 当天 `cell_by`
     就是这么丢的）；
  3. 禁映射表：`_OP_MAP` / `_ACTION_MAP` / `action_to_op` 在 `framework/` 与 `build_tools/`
     下 0 命中（白名单要写成 `frozenset`，不要再造一张「看起来在翻译」的表）；
  4. 负向自证：tmp 假仓造 5 种双轨形态断言必抓；造 3 种合法形态
     （`scenarios/*.yml` 的 `description:` 元数据、`asserts[].desc`、提示词里的 `op=`）
     断言不误伤。

[!] 本文件**自身**必须干净：负向样例里的坏 key 由 `_ACT` / `_DESC` 拼出来，不写死字面量 ——
    否则本判据会抓到它自己的样例（假红），然后被迫给真问题开豁免口子。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests" / "_helpers"))
import repo_files  # noqa: E402

# ---- 扫描范围（只查「活代码」；releases/ 是冻结历史，不回头改）------------------
SCAN_PREFIXES = ("framework/", "build_tools/", "scripts/", "tests/")

# ---- 豁免：已确认**不是步骤字段**的同名残留，逐行标记（标记行内必须写理由）------
# 例：`llm_compat.py` 里 JSON schema 的 `description` 那栏（值是 "Return a JSON object of type …"）
#     是 LLM 客户端的 function-calling 函数描述，与「步骤说明」无关。
MARKER_OK = "l34a-ok"

# ---- 双轨形态（五种；都是「一套字段两个名字」的写法）---------------------------
_ACT = "act" + "ion"            # 拼出来，避免本文件被自己抓到
_DESC = "desc" + "ription"
DUAL_FIELDS = (_ACT, _DESC)

PATTERNS = (
    (re.compile(r'"' + _ACT + r'"\s*:'),
     "步骤字典键 " + _ACT + "（应为 op）", "键名改成 op"),
    (re.compile(r"\." + _ACT + r"\b"),
     "步骤属性 ." + _ACT + "（应为 .op）", "属性名改成 op"),
    (re.compile(r'\.get\("' + _ACT + r'"'),
     "双读垫片 .get(\"" + _ACT + "\")（只许认 op）", "删掉宽容双读，只读 op"),
    (re.compile(r'"' + _DESC + r'"\s*:'),
     "步骤字典键 " + _DESC + "（应为 desc）", "键名改成 desc"),
    (re.compile(r"\." + _DESC + r"\b"),
     "步骤属性 ." + _DESC + "（应为 .desc）", "属性名改成 desc"),
)

# ---- 禁映射表（恒等映射表 = 假的翻译层，真职能只是白名单）---------------------
BANNED_TABLES = ("_OP_MAP", "_ACTION_MAP", "action_to_op")
BANNED_TABLE_PREFIXES = ("framework/", "build_tools/")

ELEMENT_MAP_DIR = REPO / "output" / "element_maps"
CASES_DIR = REPO / "cases"

# cases 产物允许出现的**非 TestStep 字段**：`url`。
#   goto 步骤的目标地址在用例层是 `url`、在控件层存 `value`（两处代码都读 —— 见
#   element_map.py 里 `step_get(st,"value") or step_get(st,"url")` 的注释）。
#   这属**另一条**双轨，不在 L34-a（action/description）范围内：只在此登记，不动它。
CASE_EXTRA_KEYS = frozenset({"url"})


# ============================ 1. 源码单名 ============================

def is_scanned_source(rel: str) -> bool:
    return rel.endswith(".py") and rel.startswith(SCAN_PREFIXES)


def scan_source_text(rel: str, text: str):
    """扫一段源码文本 -> [(lineno, why, fix, line), ...]（已应用行内豁免标记）。"""
    if not is_scanned_source(rel):
        return []
    hits = []
    for i, line in enumerate(text.splitlines(), start=1):
        if MARKER_OK in line:
            continue
        for pat, why, fix in PATTERNS:
            if pat.search(line):
                hits.append((i, why, fix, line.strip()[:150]))
                break
    return hits


def scan_sources(repo: Path = REPO):
    rels, source = repo_files.file_list(repo)
    hits, scanned = [], 0
    for rel in rels:
        if not is_scanned_source(rel):
            continue
        text = repo_files.read_text_file(repo / rel)
        if text is None:
            continue
        scanned += 1
        for lineno, why, fix, src in scan_source_text(rel, text):
            hits.append((rel, lineno, why, fix, src))
    return hits, scanned, source


def test_sources_use_one_step_field_name():
    """源码里只许 `op` / `desc`；`action` / `description` 作为步骤字段一律红。"""
    hits, scanned, source = scan_sources()
    assert scanned > 50, f"扫描面太小（{scanned} 个 .py），判据可能空转：{source}"
    assert not hits, (
        f"发现 {len(hits)} 处步骤字段双轨残留（口径：只许 op / desc）：\n"
        + "\n".join(f"  [NG] {r}:{n}  {why}\n       修法：{fix}\n       原文：{s}"
                    for r, n, why, fix, s in hits)
        + f"\n\n  若某处**不是**步骤字段（如 function-calling schema 里的函数描述），"
          f"在同一行写 `# {MARKER_OK} 理由` 显式豁免；不许放宽上面的规则。"
    )


# ============================ 3. 禁映射表 ============================

def test_no_step_field_mapping_tables():
    """`_OP_MAP` 这类恒等映射表不许回来：白名单就写白名单，别装成翻译层。"""
    rels, source = repo_files.file_list(REPO)
    hits = []
    for rel in rels:
        if not rel.startswith(BANNED_TABLE_PREFIXES):
            continue
        if rel.startswith("releases/"):
            continue
        text = repo_files.read_text_file(REPO / rel)
        if text is None:
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            if MARKER_OK in line:
                continue
            for tok in BANNED_TABLES:
                if tok in line:
                    hits.append((rel, i, tok, line.strip()[:150]))
    assert not hits, (
        "发现步骤字段映射表残留（L34-a 已删除 `_OP_MAP`，白名单用 `_STEP_OPS = frozenset(...)`）：\n"
        + "\n".join(f"  [NG] {r}:{n}  含 {tok}\n       原文：{s}" for r, n, tok, s in hits)
    )


# ============================ 2. 产物键集 ============================

def iter_step_dicts(obj):
    """从 cases / element_map 产物里取出所有「步骤字典」（两种产物形状都认）。"""
    if isinstance(obj, list):
        for x in obj:
            yield from iter_step_dicts(x)
        return
    if not isinstance(obj, dict):
        return
    steps = obj.get("steps")
    if isinstance(steps, list):
        for s in steps:
            if isinstance(s, dict):
                yield s


def load_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def test_step_dict_keys_match_dataclass_fields():
    """`TestStep` 的名字集必须与产物键集**逐字相同**。

    为什么单独立一条：字段加了、`to_dict()` 漏写，产物就**静默少一个键**（当天 `cell_by`
    就是这么丢的：AI 写得对、落盘没了、定位才崩）。这一条与业务无关，只要键集不等就红。
    """
    from framework.features.f03_locate.element_map import TestStep

    fields = set(TestStep.__dataclass_fields__)
    assert "op" in fields and "desc" in fields, f"TestStep 字段名不对：{sorted(fields)}"
    assert not (fields & set(DUAL_FIELDS)), f"TestStep 仍留着双轨字段：{sorted(fields & set(DUAL_FIELDS))}"

    produced = set(TestStep(order=1, op="click").to_dict())
    assert produced == fields, (
        f"TestStep.to_dict() 的键集与 dataclass 字段不一致：\n"
        f"  只在字段里：{sorted(fields - produced)}\n"
        f"  只在产物里：{sorted(produced - fields)}\n"
        f"  -> 少一个键 = 该字段在落盘时静默消失（cell_by 的老坑）"
    )

    # 产物的每一条步骤：键集必须是字段集的子集（cases 允许 `url`），且 op / desc 在位
    from framework.features.f03_locate.element_map import TestStep as _TS
    bad = []
    for p in sorted(CASES_DIR.rglob("*.json")):
        for st in iter_step_dicts(load_json(p)):
            extra = set(st) - fields - CASE_EXTRA_KEYS
            if extra or "op" not in st or "desc" not in st:
                bad.append((p.relative_to(REPO).as_posix(), sorted(extra),
                            "op" in st, "desc" in st))
    assert not bad, (
        "用例产物的步骤键集违反契约（多出来的键 = 字段名不同步；缺 op/desc = 老产物未迁移）：\n"
        + "\n".join(f"  [NG] {r}  多余键={e} 有op={o} 有desc={d}" for r, e, o, d in bad)
    )
    # element_map 是 `TestStep.to_dict()` 的**直接产物** -> 键集必须与字段集**逐字相等**
    #   （不是子集：多一个键说明有人绕开 to_dict 手写了产物，少一个说明 to_dict 漏传）
    maps = sorted(ELEMENT_MAP_DIR.rglob("*.json")) if ELEMENT_MAP_DIR.exists() else []
    drift = []
    for p in maps:
        for st in iter_step_dicts(load_json(p)):
            if set(st) != fields:
                drift.append((p.relative_to(REPO).as_posix(),
                              sorted(fields - set(st)), sorted(set(st) - fields)))
    assert not drift, (
        "element_map 产物的步骤键集与 TestStep 字段集不一致（多/少都算漂移）：\n"
        + "\n".join(f"  [NG] {r}  缺={m} 多={e}" for r, m, e in drift)
    )
    assert _TS is not None


def test_products_have_no_dual_step_keys():
    """`cases/**/*.json` 与 `output/element_maps/**/*.json` 的步骤里不许有双轨键。"""
    bad = []
    cases = sorted(CASES_DIR.rglob("*.json"))
    for p in cases:
        for st in iter_step_dicts(load_json(p)):
            for k in DUAL_FIELDS:
                if k in st:
                    bad.append((p.relative_to(REPO).as_posix(), k))
    maps = sorted(ELEMENT_MAP_DIR.rglob("*.json")) if ELEMENT_MAP_DIR.exists() else []
    for p in maps:
        for st in iter_step_dicts(load_json(p)):
            for k in DUAL_FIELDS:
                if k in st:
                    bad.append((p.relative_to(REPO).as_posix(), k))

    assert cases, "cases/ 下没有任何用例产物 -> 这条判据会空转（不许静默通过）"
    assert not bad, (
        "产物里仍有双轨步骤键（老文件要跑 build_tools/migrate_element_map_keys.py）：\n"
        + "\n".join(f"  [NG] {r}  键={k}" for r, k in bad)
    )
    if not maps:
        # 不是通过：产物不存在就没有键集可查。显式标注，别让它冒充「已验证」。
        pytest.skip("output/element_maps/ 下无产物（本次未跑 explore）-> 无产物键集可查")


# ============================ 4. 负向自证 ============================

def _fake_repo(tmp_path: Path) -> Path:
    (tmp_path / "framework" / "features").mkdir(parents=True, exist_ok=True)
    return tmp_path


@pytest.mark.parametrize("snippet, why_fragment", [
    ('STEPS = [{"' + _ACT + '": "click"}]\n', "字典键"),
    ("st." + _ACT + " = 'click'\n", "属性"),
    ('op = st.get("' + _ACT + '")\n', "双读垫片"),
    ('STEPS = [{"' + _DESC + '": "说明"}]\n', "字典键"),
    ("print(st." + _DESC + ")\n", "属性"),
])
def test_negative_each_dual_form_is_caught(tmp_path, snippet, why_fragment):
    """5 种双轨形态：每一种都必须被点名（漏一种就是假绿）。"""
    rel = "framework/features/fake.py"
    p = _fake_repo(tmp_path) / rel
    p.write_text(snippet, encoding="utf-8")
    hits = scan_source_text(rel, p.read_text(encoding="utf-8"))
    assert len(hits) == 1, f"应恰好抓 1 条，实际 {hits}"
    assert why_fragment in hits[0][1], f"归因不对：{hits[0][1]}"


def test_marker_line_is_exempt():
    """行内豁免必须是**逐行**的，且只豁免带标记那一行。"""
    text = ('x = {"' + _DESC + '": "函数描述"}   # ' + MARKER_OK + ' function schema\n'
            'y = {"' + _DESC + '": "步骤说明"}\n')
    hits = scan_source_text("framework/features/fake.py", text)
    assert len(hits) == 1 and hits[0][0] == 2, f"标记只许豁免本行，实际 {hits}"


def test_negative_legal_forms_are_not_flagged(tmp_path):
    """3 种**合法**形态不许误伤（假红与假绿一样会摧毁闸门）。"""
    # (a) 场景 YAML 的 description: 是**场景元数据**，不是步骤字段（本判据只扫 .py）
    yml = "name: 合同全链路\n" + _DESC + ": 打开列表页并勾选一条合同\nsteps:\n  - op: goto\n"
    assert scan_source_text("scenarios/contracts.yml", yml) == []

    # (b) 用例断言用 asserts[].desc（本来就是 desc，不该被抓）
    cases = {"asserts": [{"kind": "url", "desc": "已换页", "expect": "detail"}]}
    assert not any(k in st for st in iter_step_dicts(cases) for k in DUAL_FIELDS)

    # (c) 提示词正文里的 `op=goto` 写法（自然语言契约，不是字段定义）
    prompt = 'prompt = "换页用 op=goto + value=<该页 URL>；断言用 op=expect_url"\n'
    assert scan_source_text("framework/features/f02_semantic/fake.py", prompt) == []


def test_negative_cases_product_with_dual_key_is_caught(tmp_path):
    """产物侧负向自证：造一份带双轨键的用例，断言抓得到。"""
    p = tmp_path / "x.json"
    p.write_text(json.dumps({"steps": [{"order": 1, _ACT: "goto", "desc": "打开"}]},
                            ensure_ascii=False), encoding="utf-8")
    found = [k for st in iter_step_dicts(load_json(p)) for k in DUAL_FIELDS if k in st]
    assert found == [_ACT], f"产物侧双轨键必须被抓到，实际 {found}"
