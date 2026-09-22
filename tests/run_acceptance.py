"""R7 验收统一入口 —— 把「四条原则」变成一条命令（跨平台 Python 实现）。

AprilPark1012 2026-09-22 刷新的 R7 四条：
  ① 框架自测通过 · ② 特性自测通过 · ③ demo 新鲜度闸门通过 · ④ E2E（场景1/2/3）通过

执行顺序（**拍板口径：便宜先跑 + fail fast；编号 ≠ 执行顺序**）：

  [0] gate_selfcheck      闸门自检 `tests/verify_demo_freshness.py`（~1s；**红则停手**）
                          —— 先验「闸门自己」：它若坏了，③ 的「新鲜」结论毫无意义，后面全建在沙子上
  [1] demo_freshness      ③ `tests/demo_freshness.py --ensure --start-if-missing`
  [2] framework_selftest  ① `pytest tests/ -q`（~15s，**不依赖 demo** —— 一类自测刻意与 demo 解耦）
  [3] e2e                 ④ 三个场景（见下）
  [4] feature_selftest    ② `tests/run_verifications.py`（最慢：单个脚本可达 7 分钟 ⇒ 放最后）

④ E2E 的三个场景：
  · **场景3 = 录制回放验证**（`verify_e2e_scenario3_cassette.py`，零成本 ⇒ 放最前）：
    录像可用性体检 + 体检有效性负向 + 不匹配必须 fail loud（+ `--with-record` 时跑录制闭环，要 key/外网）
  · **场景2 = 手写用例驱动**（`cli run` 全量）
  · **场景1 = 自然语言 → AI 链路**（`verify_e2e_scenario1_offline.py`：explore 回放 → cases → generate → run）

退出码：**0** 全通过 · **1** 有失败 · **2** 环境/用法错 · **3** 有跳过（**SKIP ≠ 通过**，与二类入口同口径）

用法：
    python tests/run_acceptance.py                 # 验收全量（场景1 走离线回放）
    python tests/run_acceptance.py --list          # 只看会跑哪些（不执行）
    python tests/run_acceptance.py --skip-ai       # 跳过场景1 那一步（会如实标「跳过」且不算通过）
    python tests/run_acceptance.py --with-record   # 额外跑场景3 的「录制→回放闭环」（要 key + 外网）
    python tests/run_acceptance.py --only e2e      # 只跑某一项（排查用）
    python tests/run_acceptance.py --keep-going    # 默认遇失败即停（fail fast）；这个开关改成跑完再汇总
    python tests/run_acceptance.py --min-mem 400   # 内存阈值（透传给二类入口）

场景1 的**在线真跑**（真调 DeepSeek）不进本入口的日常段：它要 key + 外网且 LLM 不稳定，按拍板只作
**发版前手工一次**（结果写进发行说明）—— 那一次同时把录像重录 + 重打录像包（见 P15）。
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_verifications as rv          # 复用：解释器定位 / 内存探测 / 北京时间（同目录工具）

# 步骤 id 与 `test_acceptance_entry.py` 的 ORDER 一一对应（判据锁着顺序）
STEP_IDS = ["gate_selfcheck", "demo_freshness", "framework_selftest", "e2e", "feature_selftest"]

HELP_TEXT = {
    "gate_selfcheck": "闸门自检：verify_demo_freshness.py（~1s；红则停手）",
    "demo_freshness": "③ demo 新鲜度闸门：demo_freshness.py --ensure --start-if-missing",
    "framework_selftest": "① 框架自测：pytest tests/ -q（不依赖 demo）",
    "e2e": "④ E2E：场景3 录制回放验证 · 场景2 cli run 全量 · 场景1 离线回放端到端",
    "feature_selftest": "② 特性自测：run_verifications.py（最慢，放最后）",
}


def summarize(results: list[tuple[str, str]]) -> tuple[int, int, int, int]:
    """汇总 ⇒ (通过, 跳过, 失败, 退出码)。

    口径（与二类入口一致，**SKIP 不是绿灯**）：
      有失败 ⇒ 1（且**失败优先于跳过** —— 不许拿「有跳过」把失败盖过去）；
      无失败但有跳过 ⇒ 3（不算通过）；全绿 ⇒ 0。
    """
    ok = sum(1 for _, s in results if s == "ok")
    skip = sum(1 for _, s in results if s == "skip")
    fail = sum(1 for _, s in results if s == "fail")
    if fail:
        code = 1
    elif skip:
        code = 3
    else:
        code = 0
    return ok, skip, fail, code


def _run(py: str, args: list[str], *, timeout: float | None = None) -> tuple[int, str]:
    """跑一步子命令 ⇒ (退出码, 输出尾部)。显式 UTF-8（跨平台文本口径）。"""
    try:
        p = subprocess.run([py, *args], cwd=str(REPO), stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, f"⏱️ 超时（{timeout}s）⇒ 已杀，不计通过"
    tail = "\n".join([ln for ln in (p.stdout or "").splitlines() if ln.strip()][-12:])
    return p.returncode, tail


def _verdict(rc: int) -> str:
    return "ok" if rc == 0 else ("skip" if rc == 3 else "fail")


def step_gate_selfcheck(py: str) -> tuple[str, int, str]:
    """[0] 闸门自身的判据（先验闸门自己再验别人）。"""
    rc, tail = _run(py, ["tests/verify_demo_freshness.py"], timeout=300)
    return _verdict(rc), rc, tail


def step_demo_freshness(py: str) -> tuple[str, int, str]:
    """[1] ③ demo 新鲜度闸门（不新鲜就自动重启并等到就绪）。"""
    rc, tail = _run(py, ["tests/demo_freshness.py", "--ensure", "--start-if-missing"], timeout=120)
    return _verdict(rc), rc, tail


def step_framework_selftest(py: str) -> tuple[str, int, str]:
    """[2] ① 框架自测（一类；与 demo 无关）。"""
    rc, tail = _run(py, ["-m", "pytest", "tests/", "-q"], timeout=900)
    return _verdict(rc), rc, tail


def step_e2e(py: str, *, skip_ai: bool, with_record: bool = False) -> tuple[str, int, str, list[tuple[str, int]]]:
    """[3] ④ E2E 三个场景：**场景3（体检，零成本）→ 场景2（cli run）→ 场景1（离线回放）**。

    顺序理由：场景3 的体检是零成本前置 —— 它能立刻告诉你「录像齐不齐」，而场景1 恰恰依赖录像；
    把最便宜、又能决定后面有没有意义的放前面（与四步整体口径一致）。
    `--skip-ai` 时场景1 记为跳过（仍如实列出，退出码按「不算通过」处理）。
    """
    subs: list[tuple[str, int]] = []
    logs: list[str] = []

    args3 = ["tests/verify_e2e_scenario3_cassette.py"] + (["--with-record"] if with_record else [])
    rc3, tail3 = _run(py, args3, timeout=1800)
    subs.append(("scenario3", rc3))
    logs.append("· 场景3（录制回放验证%s）：exit %d\n%s"
                % ("，含录制闭环" if with_record else "", rc3, tail3))

    rc2, tail2 = _run(py, ["-m", "framework.cli", "run", "--workers", "2"], timeout=1800)
    subs.append(("scenario2", rc2))
    logs.append("· 场景2（generate → run 手写用例驱动）：exit %d\n%s" % (rc2, tail2))

    if skip_ai:
        subs.append(("scenario1", 3))
        logs.append("· 场景1（离线回放端到端）：跳过（--skip-ai）")
    else:
        rc1, tail1 = _run(py, ["tests/verify_e2e_scenario1_offline.py"], timeout=1800)
        subs.append(("scenario1", rc1))
        logs.append("· 场景1（自然语言 → explore 回放 → cases → generate → run）：exit %d\n%s"
                    % (rc1, tail1))

    worst = 1 if any(_verdict(rc) == "fail" for _, rc in subs) else (
        3 if any(_verdict(rc) == "skip" for _, rc in subs) else 0)
    return _verdict(worst), worst, "\n".join(logs), subs


def step_feature_selftest(py: str, min_mem: int) -> tuple[str, int, str]:
    """[4] ② 特性自测（二类；最慢）。"""
    rc, tail = _run(py, ["tests/run_verifications.py", "--min-mem", str(min_mem)], timeout=None)
    return _verdict(rc), rc, tail


def _print_plan(skip_ai: bool, with_record: bool) -> None:
    print("=" * 70)
    print(" R7 验收 · 执行顺序（便宜先跑 + fail fast；编号 ≠ 执行顺序）")
    print("=" * 70)
    for i, sid in enumerate(STEP_IDS):
        print(f"  [{i}] {sid:<19} {HELP_TEXT[sid]}")
        if sid == "e2e":
            mark = "   ← 场景1 将被跳过（--skip-ai）" if skip_ai else "   ← 场景1：离线回放（日常口径）"
            print(f"        ├ scenario3  录制回放验证：体检 + 负向（零成本）"
                  f"{'＋录制闭环（--with-record）' if with_record else ''}")
            print(f"        ├ scenario2  cli run 全量（手写用例驱动）")
            print(f"        └ scenario1  verify_e2e_scenario1_offline.py{mark}")
    if skip_ai:
        print("      ⚠️ 跳过场景1 ⇒ 本次验收**不算通过**（SKIP ≠ 通过）")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        prog="run_acceptance.py",
        description="R7 验收统一入口：闸门自检 → ③ demo 新鲜度 → ① 框架自测 → ④ E2E（场景1/2/3）→ ② 特性自测。",
    )
    ap.add_argument("--list", action="store_true", help="只列出会跑哪些步骤（不执行）")
    ap.add_argument("--skip-ai", action="store_true", help="跳过场景1 那一步（会如实标「跳过」，且不算通过）")
    ap.add_argument("--with-record", action="store_true",
                    help="E2E 场景3 额外跑「录制→回放闭环」（要 key + 外网；发版前用）")
    ap.add_argument("--only", default="", metavar="步骤id",
                    help="只跑某一步（排查用）：" + " / ".join(STEP_IDS))
    ap.add_argument("--keep-going", action="store_true", help="遇失败不即停，跑完再汇总（默认 fail fast）")
    ap.add_argument("--min-mem", type=int, default=550, metavar="MB", help="内存阈值（透传二类入口，默认 550）")
    args = ap.parse_args(argv)

    if args.only and args.only not in STEP_IDS:
        print(f"未知步骤：{args.only}（可用：{', '.join(STEP_IDS)}）")
        return 2
    if args.list:
        _print_plan(args.skip_ai, args.with_record)
        return 0

    py = rv._venv_python()
    mb = rv.mem_available_mb()
    print("=" * 70)
    print(f" R7 验收 · {rv._now_cst()}")
    print(f" 仓库: {REPO}")
    print(f" 解释器: {py}")
    print(f" 内存: " + (f"MemAvailable {mb}MB" if mb is not None else "⚠️ 未测（平台拿不到数字）⇒ 不据此跳过"))
    print("=" * 70)

    todo = [s for s in STEP_IDS if not args.only or s == args.only]
    results: list[tuple[str, str]] = []
    t_all = time.time()
    for sid in todo:
        print(f"\n———— [{sid}] {HELP_TEXT[sid]} ————")
        t0 = time.time()
        if sid == "gate_selfcheck":
            st, rc, tail = step_gate_selfcheck(py)
        elif sid == "demo_freshness":
            st, rc, tail = step_demo_freshness(py)
        elif sid == "framework_selftest":
            st, rc, tail = step_framework_selftest(py)
        elif sid == "e2e":
            st, rc, tail, _subs = step_e2e(py, skip_ai=args.skip_ai, with_record=args.with_record)
        else:
            st, rc, tail = step_feature_selftest(py, args.min_mem)
        print(tail)
        print(f"  → {st}（exit {rc}，{time.time() - t0:.0f}s）")
        results.append((sid, st))
        if st == "fail" and not args.keep_going:
            print(f"\n⛔ [{sid}] 失败 ⇒ 按 fail-fast 停手（后面的步骤建在它之上，跑了也没意义）")
            break

    ok, skip, fail, code = summarize(results)
    print("\n" + "=" * 70)
    print(f" R7 验收汇总（通过 {ok} · 跳过 {skip} · 失败 {fail}）· 用时 {time.time() - t_all:.0f}s")
    for sid, st in results:
        mark = {"ok": "✅", "skip": "⏭️", "fail": "❌"}[st]
        print(f"   {mark} {sid:<19} {st}")
    print("=" * 70)
    if code == 0:
        print("✅ R7 四项全部通过")
    elif code == 1:
        print("❌ 有失败 ⇒ 先修再提交")
    else:
        print("⚠️ 有跳过项（**不算通过**）⇒ 补跑后重验")
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
