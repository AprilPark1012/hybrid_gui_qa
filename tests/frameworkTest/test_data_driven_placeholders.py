"""数据驱动（场景 `data:` 多组数据）**不许静默退化**的判据。

2026-09-24 事故：场景 `contracts_search_by_no.yml` 写着
    在搜索框输入 '{关键词}'，点击搜索按钮，确认出现编号为 {期望编号} 的记录
    data: [3 组]
但 AI 生成的用例把占位符**解析成了第 1 组的值**（`value: "1005"` / `expect: "HT-1005"`）⇒
`generate` 判定「用例没用占位符」⇒ **不做参数化**（sets = []）⇒ 3 组数据只跑 1 条，
而这一路**只告警不报错** ⇒ 数据驱动特性静默失效（二类 `verify_data_expand` 才拦到）。

本判据守两件事：
  ① 凡"场景有 data: 的 AI 用例"⇒ 文案里**必须**出现 `{占位符}`（否则直接红）；
  ② `restore_data_placeholders()` 的确定性还原语义（长值优先 / 不动 id / 幂等 / 无组不动作）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from framework.tools.generate.case_builder import restore_data_placeholders  # noqa: E402
from framework.tools.generate.scenario import discover_scenarios            # noqa: E402

CASES = REPO / "cases"


def _scenarios_with_data() -> dict[str, list]:
    return {s.id: list(s.data) for s in discover_scenarios() if getattr(s, "data", None)}


def _texts(case: dict) -> list[str]:
    out: list[str] = []
    for st in case.get("steps") or []:
        out += [str(st.get(k) or "") for k in ("desc", "value")]
    for a in case.get("asserts") or []:
        out += [str(a.get(k) or "") for k in ("desc", "expect")]
    return out


def test_ai_cases_with_scenario_data_use_placeholders():
    """★事故本体：场景有 data: 的 AI 用例，文案里必须真的用了 {占位符}。"""
    sd = _scenarios_with_data()
    assert sd, "前置：应当存在带 data: 的场景（否则本判据无意义）"
    bad: list[str] = []
    for f in sorted(CASES.glob("ai_*.json")):
        case = json.loads(f.read_text(encoding="utf-8"))
        sid = case.get("scenario_id") or ""
        if sid not in sd:
            continue
        if not any("{" in t and "}" in t for t in _texts(case)):
            bad.append(f"{f.name}（场景 {sid} 有 {len(sd[sid])} 组 data，但文案里零占位符）")
    assert not bad, "✗ 数据驱动的 AI 用例没用占位符 ⇒ 多组数据会静默退化成只跑一组：\n  " + "\n  ".join(bad)


def test_restore_is_longest_first_and_does_not_touch_id():
    """长值优先：`HT-1005` 必须先于 `1005` 还原；`id` 是标签，不参与映射。"""
    case = {"case_id": "x", "steps": [{"op": "fill", "desc": "输入 1005", "value": "1005"}],
            "asserts": [{"desc": "出现编号 HT-1005 的记录", "expect": "HT-1005"}]}
    sets = [{"id": "编号-1005", "关键词": "1005", "期望编号": "HT-1005"}]
    restore_data_placeholders(case, sets)
    assert case["steps"][0]["value"] == "{关键词}"
    assert case["steps"][0]["desc"] == "输入 {关键词}"
    assert case["asserts"][0]["expect"] == "{期望编号}"
    assert "编号-{关键词}" not in case["asserts"][0]["desc"], "id 标签不该被当参数还原"


def test_restore_is_idempotent():
    """还原是幂等的（跑第二遍不该再改），否则每次生成都会漂移。"""
    case = {"case_id": "x", "steps": [{"op": "fill", "value": "1005"}], "asserts": []}
    sets = [{"关键词": "1005"}]
    assert restore_data_placeholders(case, sets), "第一遍应当有动作"
    assert not restore_data_placeholders(case, sets), "第二遍应当零动作（幂等）"


def test_restore_without_sets_is_noop():
    """场景没有 data: ⇒ 一个字符都不许动。"""
    case = {"case_id": "x", "steps": [{"op": "fill", "value": "1005"}], "asserts": []}
    assert restore_data_placeholders(case, []) == []
    assert case["steps"][0]["value"] == "1005"
