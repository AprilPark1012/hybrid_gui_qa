"""录像键「两级分工」策略的判据（2026-09-24 项目负责人定稿）。

背景：录像键 = `sha256(系统提示 + 提示词)`，匹配有两级：
  ① **严格级**：逐字一致 ⇒ 直接用（静默）；
  ② **结构级（回退）**：页面/控件结构相同、但这些控件的**值**与录制时不同（换机器、机器上跑过测试
     数据就变了）⇒ 仍命中，但**大声告警**「步骤是录制当时针对那批数据做的判断，请核对后再用」。

定稿的分工（不许一刀切）：
  · **日常二类**：用 ② + 告警 —— 数据值漂移不该让整轮变红（否则成"狼来了"，人会开始无视红色；
    本项目原则：**宁漏不误伤**）；
  · **发版门**（`run_acceptance.py`）：强制 ①（`--llm-cassette-strict`）—— 要发出去的东西，
    录像必须逐字对得上，不接受"结构像、数据不同"的将就。
  实测（2026-09-24）：两种口径**都通过**（3 项判据 / 全绿）⇒ 当前录像确为逐字一致 ⇒ 策略可用 ✓
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
GATE = REPO / "tests" / "featureTest" / "run_acceptance.py"
SCEN3 = REPO / "tests" / "featureTest" / "verify_e2e_scenario3_cassette.py"
TOOL = REPO / "tests" / "featureTest" / "rerecord_cassettes.py"


def _txt(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def test_release_gate_requests_strict_cassette():
    """发版门必须显式打开严格级（否则会把"结构像、数据不同"的将就当成通过）。"""
    t = _txt(GATE)
    assert "HYBRID_CASSETTE_STRICT" in t, "发版门没设 HYBRID_CASSETTE_STRICT ⇒ 严格级失效"
    assert 'os.environ["HYBRID_CASSETTE_STRICT"] = "1"' in t, "发版门没把严格开关设成 1"


def test_scenario3_script_honors_strict_switch():
    """场景3 体检脚本必须真的把开关翻成 `--llm-cassette-strict`（只设环境变量不生效 = 假开关）。"""
    t = _txt(SCEN3)
    assert "HYBRID_CASSETTE_STRICT" in t and "--llm-cassette-strict" in t, \
        "场景3 脚本没接严格开关 ⇒ 发版门设了也白设"


def test_rerecord_doc_lists_four_triggers_and_two_refinements():
    """重录工具的 docstring 必须写全：4 条必须重录的情形 + 2 条实测补充（prompt 全量重录 / 两级键）。"""
    t = _txt(TOOL)
    for kw in ("改了 `scenarios/*.yml`", "demo app 变了", "prompt", "新增特性导致页面结构变化"):
        assert kw in t, f"重录说明缺第 N 条情形的关键表述：{kw}"
    assert "全量重录" in t, "缺『改 prompt ⇒ 全量重录』这条实测补充"
    assert "结构级" in t and "--llm-cassette-strict" in t, "缺『两级键 + 严格开关』这条实测补充"
