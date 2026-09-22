"""R7 验收统一入口的判据（一类，秒级，不需要 demo）。

背景（AprilPark1012 2026-09-22 刷新 R7）：四条验收原则要能「**一条命令**跑完」——
③ demo 新鲜度闸门 → ② 特性自测 → ④ E2E（场景2 = `cli run` 全量 / 场景1 = 离线回放端到端）→ ① 框架自测。
本文件是那个入口（`tests/run_acceptance.py`）的**契约锁**：

- 入口存在、四项齐全、**顺序正确**（顺序本身是原则的一部分：闸门必须排在 ②④ 之前）；
- `--list` 可核（不许手写清单漂移 —— 新增/改名一处，这里当场抓）；
- **SKIP 不算通过**（有跳过 ⇒ 退出码 3），与二类统一入口同一口径；
- 场景 1 的离线判据脚本必须**可证伪地不联网**（LLM 端点指黑洞 `127.0.0.1:9`），
  否则「离线也能跑通场景 1」这句话本身就无从验证。

⚠️ **TDD 口径**：本文件在 `tests/run_acceptance.py` / `verify_e2e_scenario1_offline.py` 落地
**之前**先写好（先红后绿）；红态证据记在提交信息里（P15 §五 批 0）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))

ENTRY = REPO / "tests" / "run_acceptance.py"
SCEN1 = REPO / "tests" / "verify_e2e_scenario1_offline.py"

# 四项的稳定标识 —— **顺序即执行顺序**：③ 闸门 → ① 框架自测 → ④ E2E → ② 特性自测。
# ⚠️ 这不是按编号排的（编号 ≠ 执行顺序）：AprilPark1012 2026-09-22 拍板「便宜先跑 + fail fast」——
#    ① 只需 15s 且不依赖 demo，先跑能在几十秒内判定「框架/环境是否根本性坏了」；
#    ② 最慢（单个脚本可达 7 分钟）放最后，免得堵住前面的快检查。
# 另：③ 之前还要先跑一次「闸门自身判据」（verify_demo_freshness，~1s），见文件尾的专门判据。
ORDER = ["demo_freshness", "framework_selftest", "e2e", "feature_selftest"]


def _run_entry(args: list[str]):
    import subprocess
    return subprocess.run([sys.executable, "tests/run_acceptance.py", *args],
                          cwd=str(REPO), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=120)


def test_acceptance_entry_exists():
    """入口必须存在 —— 这是 R7「四条一条命令跑完」的落点。"""
    assert ENTRY.exists(), f"缺验收统一入口：{ENTRY}（R7 四条无法一键验收）"


def test_acceptance_lists_four_items_in_order():
    """★ 四项必须齐全、且**顺序**是 闸门 → 特性 → E2E → 框架（顺序错误 = 闸门可能没起到前置作用）。"""
    r = _run_entry(["--list"])
    assert r.returncode == 0, f"--list 应 exit 0：{r.stdout}\n{r.stderr}"
    out = r.stdout
    positions = []
    for key in ORDER:
        idx = out.find(key)
        assert idx >= 0, f"--list 里没列出 {key}：\n{out}"
        positions.append(idx)
    assert positions == sorted(positions), f"四项顺序不对（要求 {ORDER}）：\n{out}"


def test_acceptance_unknown_flag_exits_2():
    r = _run_entry(["--no-such-flag"])
    assert r.returncode == 2, f"未知参数必须 exit 2，实际 {r.returncode}"


def test_acceptance_skip_ai_marks_scenario1_skipped():
    """`--skip-ai`：场景 1 的在线段跳过（日常口径），但**必须显式标出**，不许静默省略。"""
    r = _run_entry(["--list", "--skip-ai"])
    assert r.returncode == 0, r.stderr
    line = [ln for ln in r.stdout.splitlines() if "scenario1" in ln or "场景1" in ln or "场景 1" in ln]
    assert line, f"--list --skip-ai 里没有场景1 这一行：\n{r.stdout}"
    assert "skip" in line[0].lower() or "跳过" in line[0], f"场景1 没标成跳过：{line[0]}"


def test_summarize_skip_is_not_pass():
    """★ 口径锁：**有跳过 ⇒ 退出码 3（不算通过）**；全绿才 0。"""
    import run_acceptance as ra
    assert ra.summarize([("a", "ok"), ("b", "ok")])[-1] == 0
    assert ra.summarize([("a", "ok"), ("b", "skip")])[-1] == 3, "有 SKIP 不许算通过"
    assert ra.summarize([("a", "ok"), ("b", "fail")])[-1] == 1
    # 负向自证：失败优先于跳过（两者都有时不能报 3 把失败藏起来）
    assert ra.summarize([("a", "fail"), ("b", "skip")])[-1] == 1, "有失败时不许退化成「跳过」"


def test_scenario1_offline_verifier_exists_and_is_falsifiably_offline():
    """场景 1 的离线端到端判据必须存在，且**可证伪地不联网**（端点指黑洞）。"""
    assert SCEN1.exists(), f"缺场景1 离线端到端判据：{SCEN1}"
    src = SCEN1.read_text(encoding="utf-8")
    assert "127.0.0.1:9" in src, "脚本里没有「端点指黑洞」的证据 ⇒ 「离线跑通」无从证伪"


def test_acceptance_runs_gate_selfcheck_first():
    """★ 先验「闸门自己」再验别人（AprilPark1012 2026-09-22 拍板）：③ 之前必须先跑闸门自身判据（~1s，红则停手）。

    为什么：③ 的结论是 ②④ 的前提 —— 若闸门本身坏了（判定逻辑退化 / 读不到进程时刻），
    它报「新鲜」就没有意义，后面跑的一切都建在沙子上。闸门自身的判据 `verify_demo_freshness.py`
    约 1 秒（含负向证伪），当作验收第 0 步代价极低。
    """
    r = _run_entry(["--list"])
    out = r.stdout
    assert "verify_demo_freshness" in out, f"--list 里没有「闸门自检」这一步：\n{out}"
    assert out.find("verify_demo_freshness") < out.find("framework_selftest"), \
        f"闸门自检必须排在框架自测（① ）之前：\n{out}"
