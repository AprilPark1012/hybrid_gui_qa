"""AI 用例「换代清理」的**安全边界**判据（2026-09-24 事故复盘）。

**事故**：D3 要求「同一场景只保留一条当前用例」，我实现成"写入时按 `scenario_id` 清掉同场景更早的用例"。
但**临时/手搓用例往往会继承样板场景的 `scenario_id`** —— 例如此时 `verify_data_expand` 造的
`cases/manual/zz_verify_data_expand_tmp.json` 就是从真用例复制来的，`case_id` 改了、`scenario_id` 没改。
⇒ 于是写这条临时用例时，真用例 `ai_contracts_search_by_no_*.json` 被当成"旧件"**删掉了** ✗✗
⇒ 后果：二类里 `verify_data_expand` / `verify_retention_runs` 同时红（找不到样例用例），
   而且这是**静默删数据** —— 没有报错，只有"文件不见了"。

✅ 定死的边界：
  1. **只有 AI 用例（`case_id` 形如 `ai_…`）写入时才做同场景清理**；
  2. 临时/手搓用例（`zz_…` / 中文名 / 无 `ai_` 前缀）写入 ⇒ **一律不清理别人**；
  3. AI 用例换代 ⇒ 旧 AI 用例与它的 dataset 该清（D3 的本意 ✓），但**不误伤**临时/手搓用例。
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from framework.tools.generate.case_builder import write_case  # noqa: E402


def _mk(tmp_path: Path):
    cases = tmp_path / "cases"
    (tmp_path / "scripts" / "datasets").mkdir(parents=True, exist_ok=True)
    cases.mkdir(parents=True, exist_ok=True)
    return cases


def _case(cid: str, sid: str) -> dict:
    return {"case_id": cid, "scenario_id": sid, "steps": [], "asserts": []}


def test_temp_case_write_does_not_delete_ai_case(tmp_path):
    """★事故本体：写"继承了 scenario_id 的临时用例"绝不能删掉同场景的 AI 用例。"""
    cases = _mk(tmp_path)
    write_case(_case("ai_demo_000001", "demo"), cases_dir=cases)
    assert (cases / "demo" / "ai_demo_000001.json").exists()

    write_case(_case("zz_tmp_probe", "demo"), cases_dir=cases)     # 临时用例（继承 scenario_id）
    assert (cases / "demo" / "ai_demo_000001.json").exists(), (
        "✗ 临时用例把真 AI 用例删掉了 —— 这就是 2026-09-24 的静默删数据事故")


def test_ai_case_replacement_still_prunes_old_ai_case_and_dataset(tmp_path):
    """D3 的本意仍要成立：AI 用例换代 ⇒ 旧 AI 用例与其 dataset 被清。"""
    cases = _mk(tmp_path)
    ds = tmp_path / "scripts" / "datasets"
    write_case(_case("ai_demo_000001", "demo"), cases_dir=cases)
    (ds / "ai_demo_000001.json").write_text("{}", encoding="utf-8")

    write_case(_case("ai_demo_000002", "demo"), cases_dir=cases)
    assert not (cases / "demo" / "ai_demo_000001.json").exists(), "AI 用例换代应清掉旧件（D3）"
    assert not (ds / "ai_demo_000001.json").exists(), "旧件的 dataset 也应一起清（D3）"
    assert (cases / "demo" / "ai_demo_000002.json").exists()


def test_ai_case_write_does_not_touch_temp_or_manual_cases(tmp_path):
    """AI 用例换代时，同场景的**临时/手搓**用例不许被误伤。"""
    cases = _mk(tmp_path)
    write_case(_case("zz_tmp_probe", "demo"), cases_dir=cases)
    write_case(_case("手搓_冒烟", "demo"), cases_dir=cases)

    write_case(_case("ai_demo_000001", "demo"), cases_dir=cases)
    write_case(_case("ai_demo_000002", "demo"), cases_dir=cases)
    assert (cases / "manual" / "zz_tmp_probe.json").exists(), "临时用例被 AI 用例的清理误伤了"
    assert (cases / "manual" / "手搓_冒烟.json").exists(), "手搓用例被 AI 用例的清理误伤了"


def test_write_case_without_scenario_id_never_prunes(tmp_path):
    """没有 scenario_id 的用例（历史形态）写入 ⇒ 不做任何清理（向后兼容）。"""
    cases = _mk(tmp_path)
    write_case(_case("ai_demo_000001", "demo"), cases_dir=cases)
    write_case({"case_id": "ai_orphan_000009", "steps": [], "asserts": []}, cases_dir=cases)
    assert (cases / "demo" / "ai_demo_000001.json").exists(), "无 scenario_id 的写入不该触发清理"


def test_ai_prefixed_temp_case_does_not_prune(tmp_path):
    """★第二版守卫被击穿的形态：`ai_` 前缀但**不是** AI 用例的合法命名（如 `ai_xxx_tmp` / `ai_xxx-2`）。

    第一版守卫只看「是否以 ai_ 开头」⇒ 迟早被这类 id 绕过（真凶至今未定论，但这类 id 一定存在）
    ⇒ 改成严格形态 `ai_<scenario_id>_<6位数字>` 之后，这些一律**不许触发清理**。
    """
    cases = _mk(tmp_path)
    write_case(_case("ai_demo_000001", "demo"), cases_dir=cases)
    for bogus in ("ai_demo_000001_tmp", "ai_demo_tmp", "ai_demo_000001-2", "ai_demo_99"):
        write_case(_case(bogus, "demo"), cases_dir=cases)
        assert (cases / "demo" / "ai_demo_000001.json").exists(), f"✗ {bogus} 触发了清理（守卫太宽松）"
    # 严格形态的**新 AI 用例**才允许清掉旧的
    write_case(_case("ai_demo_000002", "demo"), cases_dir=cases)
    assert not (cases / "demo" / "ai_demo_000001.json").exists(), "严格形态的新 AI 用例应清掉旧件（D3）"


def test_prune_never_deletes_the_just_written_file_even_on_name_collision(tmp_path):
    """重名落盘会变成 `xxx-2.json` ⇒ 老件绝不能被"按路径比对"误杀（改按 case_id 比对）。"""
    cases = _mk(tmp_path)
    write_case(_case("ai_demo_000001", "demo"), cases_dir=cases)
    # 同 id 再写一次 ⇒ AI 用例**直接覆盖**（不落 -2）⇒ 既不丢原版、也不留孤儿
    write_case(_case("ai_demo_000001", "demo"), cases_dir=cases)
    assert (cases / "demo" / "ai_demo_000001.json").exists(), "✗ 同 id 重写把原版弄丢了"
    assert not (cases / "demo" / "ai_demo_000001-2.json").exists(), "✗ AI 用例不该落成 -2（会引发误删原版）"
