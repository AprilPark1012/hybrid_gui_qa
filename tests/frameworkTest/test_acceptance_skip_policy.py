"""发版门（`run_acceptance.py`）的跳过口径判据（D1 · 2026-09-24 他定）。

**他 2026-09-24 的决定（D1）**：场景1（真 AI）在发版门里 **SKIP 算通过** ——
理由：场景3 已用录像覆盖同一条链，没有 key / 连不上外网的机器不该被发版门卡死。
⇒ 但**只有场景1** 有这个豁免；其他任何一步「跳过」仍然不算通过（SKIP ≠ 通过，R7 硬口径）。

**同时纠正命名**（按他的编号）：
- 场景1 = **真 AI**：`verify_e2e_scenario1_online.py`
- 场景2 = **手搓**：`verify_e2e_scenario2_handwritten.py`（门里用 `cli run` 驱动）
- 场景3 = **录制回放**：`verify_e2e_scenario3_replay.py`

判据：
  ① 纯函数：`summarize` 在有「允许的跳过」时 ⇒ 退出码 0（且在报告里如实可见，不是被吞掉）
  ② 纯函数：普通跳过 ⇒ 3；有失败 ⇒ 1（**失败优先于跳过**，不许被盖）
  ③ 源码契约：E2E 那一步按**他的编号**调用三个脚本，且场景1 走"允许跳过"这条路
  ④ 负向自证：把"允许跳过"错当成"全部跳过都好使" ⇒ 必须被①③抓住
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
GATE = REPO / "tests" / "featureTest" / "run_acceptance.py"


def _load_gate():
    """按文件路径加载发版门模块（它不是包，只能这样导入）。"""
    spec = importlib.util.spec_from_file_location("_acceptance_gate", GATE)
    assert spec and spec.loader, f"无法按路径加载 {GATE}"
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_acceptance_gate"] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------- ① 允许的跳过 ⇒ 不算失败（D1 的核心）----------------

def test_allowed_skip_does_not_block_release_gate():
    g = _load_gate()
    results = [("framework_selftest", "ok"), ("e2e", "ok"), ("scenario1", "ok_skipped"),
               ("feature_selftest", "ok")]
    ok, skip, fail, code = g.summarize(results)
    assert code == 0, f"场景1 的 SKIP 被当成拦路项（exit {code}）⇒ D1 没落地：{results}"
    assert fail == 0 and ok == 4, '被允许的跳过应计入通过（4 项全通过）'
    # 必须**如实可见**（不能被吞成"通过"了事）—— format_summary 必须存在，不许"没有就跳过检查"（那会假绿）
    assert hasattr(g, "format_summary"), (
        "发版门没有 format_summary ⇒ 判据无法核对「允许的跳过要如实可见」，"
        "而按可选属性写会让本判据假绿（2026-09-24 自查发现）")
    out = g.format_summary(ok, skip, fail, code, results)
    assert "场景1" in out and ("跳过" in out or "SKIP" in out), out
    assert "允许" in out or "豁免" in out, f"没说明这是「被允许的跳过」⇒ 人会误读：\n{out}"


# ---------------- ② 普通跳过 / 失败 仍然照旧 ----------------

def test_normal_skip_still_blocks():
    g = _load_gate()
    _, skip, _, code = g.summarize([("framework_selftest", "ok"), ("e2e", "skip")])
    assert skip == 1 and code == 3, "普通跳过必须仍不算通过（R7 硬口径）"


def test_failure_wins_over_skip():
    g = _load_gate()
    _, skip, fail, code = g.summarize([("e2e", "skip"), ("scenario2", "fail")])
    assert fail == 1 and code == 1, "有失败时必须 exit 1（失败优先于跳过，不许被跳过盖过去）"


# ---------------- ③ 源码契约：编号对齐 + 场景1 走允许跳过 ----------------

def test_gate_uses_his_scenario_numbering():
    src = GATE.read_text(encoding="utf-8")
    for must in ("verify_e2e_scenario1_online.py",     # 场景1 真 AI
                 "verify_e2e_scenario2_handwritten.py",  # 场景2 手搓
                 "verify_e2e_scenario3_replay.py"):      # 场景3 录制回放
        assert must in src, f"发版门里没提到 {must}（编号必须与场景定义一致）"
    assert "verify_e2e_scenario1_offline.py" not in src, "旧名残留（已按他的编号改名）"


def test_scenario1_is_called_with_allow_skip():
    src = GATE.read_text(encoding="utf-8")
    assert "allow_skip" in src, (
        "发版门里没有 allow_skip 这条路 ⇒ 场景1 的 SKIP 仍会被当成拦路项（D1 要求允许）")


# ---------------- ④ 负向自证：允许跳过 ≠ 所有跳过都好使 ----------------

def test_negative_allow_skip_is_scoped():
    g = _load_gate()
    v = g._verdict
    # 允许跳过时 rc=3 ⇒ ok_skipped；不允许时 rc=3 ⇒ skip（这两者必须不同）
    assert v(3, allow_skip=True) != v(3, allow_skip=False), (
        "_verdict 对「允许跳过」和「普通跳过」给出同一个判定 ⇒ 豁免会泛滥到所有步骤")
