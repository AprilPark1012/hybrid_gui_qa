"""二类「不进日常」自声明机制的判据（D2/D6 · 2026-09-24 他定）。

**为什么要有它**：他定了「场景1 真 AI 不进日常二类」（单轮 8~10 分钟），同时要求
「一旦新加特性或 demo 变化就要重新录制，跑场景3 时能拦住问题」。
实现方式：脚本在**自己文件头部**声明 `# HYBRID_DAILY_SKIP: <原因>` ⇒ 二类日常不收，
`--full` 照收；`run_acceptance.py`（发版门）**显式**调用它。
好处：不用维护中心化清单 ⇒ 保住「自动收录、绝不漏新脚本」这个好性质。

判据：
  ① runner 有 `daily_skip_reason()` 且能认出头部声明（窗口足够宽——我第一版只扫 12 行，
     而标记在第 24 行 ⇒ **静默失效**，实测踩到）
  ② 声明了就必须**如实列出来**（附原因），不许悄悄消失
  ③ 场景1 真 AI 脚本确实声明了（D2 的落地物）
  ④ 负向自证：没有声明的脚本不许被判成排除
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RUNNER = REPO / "tests" / "featureTest" / "run_verifications.py"
AI_SCRIPT = REPO / "tests" / "featureTest" / "verify_e2e_scenario1_online.py"
MARKER = "HYBRID_DAILY_SKIP:"


def _runner():
    spec = importlib.util.spec_from_file_location("_rv_daily", RUNNER)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_rv_daily"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_marker_detected_when_declared(tmp_path):
    m = _runner()
    f = tmp_path / "verify_x.py"
    f.write_text(f'"""doc"""\n\n# {MARKER} 太慢了，不进日常\n', encoding="utf-8")
    why = m.daily_skip_reason(f)
    assert why and "太慢" in why, f"头部声明没被认出来：{why!r}"


def test_marker_detected_even_after_a_long_docstring(tmp_path):
    """窗口必须够宽：标记常常写在长 docstring 之后（第一版 12 行窗口 ⇒ 静默失效）。"""
    m = _runner()
    f = tmp_path / "verify_y.py"
    f.write_text('"""' + "\n".join(["填充"] * 30) + '"""\n# ' + MARKER + " 原因\n", encoding="utf-8")
    assert m.daily_skip_reason(f), "长 docstring 之后的声明被漏掉 ⇒ 窗口太窄"


def test_ai_scenario_declares_daily_skip():
    assert AI_SCRIPT.is_file(), f"缺 {AI_SCRIPT}"
    why = _runner().daily_skip_reason(AI_SCRIPT)
    assert why, "场景1（真 AI）没声明不进日常 ⇒ 二类会被它拖长 8~10 分钟（D2 要求不进）"


def test_negative_plain_script_is_not_skipped(tmp_path):
    m = _runner()
    f = tmp_path / "verify_z.py"
    f.write_text('"""普通脚本。"""\nprint("hi")\n', encoding="utf-8")
    assert m.daily_skip_reason(f) is None, "没声明的脚本被判成排除 ⇒ 会静默少跑验证"
