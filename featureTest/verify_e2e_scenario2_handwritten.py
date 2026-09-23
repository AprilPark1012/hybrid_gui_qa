#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""E2E 场景2（手搓链路）—— 人写 `cases/*.json` → generate 出脚本 → 全量执行通过。

**R7-e 场景2**（他 2026-09-23 定）：证明「**完全不靠 AI 也能干活**」——
手搓用例这条路不退化。与场景1（真 AI）/ 场景3（录制回放 mock）**分开验收**：三条链的坏法不同。

判据（每条都给命令级证据；含负向自证）：
  ① **覆盖**：`cases/` 下每条**手搓**用例（非 `ai_*`）都能在 `scripts/test_cases.py` 里找到对应测试函数
     —— 缺 ⇒ FAIL（说明 generate 漏了它，或用例格式不合契约）
  ② **数据分离**：每条手搓用例都有对应的 `scripts/datasets/<case_id>.json`（参数化抽离产物）
  ③ **全量执行**：`framework.cli run --case <id>`（逐条）**全部 exit 0** —— 这是本脚本的核心：
     「手搓的能跑通」不能只看生成成功，必须真的跑
  ④ **负向自证**：故意用一个**不存在**的 case_id 去查 ⇒ 必须报「找不到」（防「查什么都说有」）
  ⑤ **零残渣**：本脚本不新增/删除 cases、datasets、scenarios（纯读 + 执行）

耗时：约 1~3 分钟（取决于手搓用例数）。需要 demo 在跑（`frameworkTest/demo_freshness.py --ensure`）。
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PY = sys.executable
CASES = REPO / "cases"
SCRIPTS = REPO / "scripts"
DATASETS = SCRIPTS / "datasets"
TEST_CASES = SCRIPTS / "test_cases.py"

sys.path.insert(0, str(REPO))

# 统一 UTF-8：脚本会把子进程输出打回控制台 —— 不拉齐口径时，中文 Windows（cp936）上会显示乱码。
from framework.tools.common.text_io import force_stdio       # noqa: E402

force_stdio()

sys.path.insert(0, str(REPO / "frameworkTest"))       # 共享辅助（demo_freshness / artifacts）
sys.path.insert(0, str(REPO / "featureTest"))

FAILS: list[str] = []
NOTES: list[str] = []


def ok(msg: str) -> None:
    print(f"  ✅ {msg}")


def bad(msg: str) -> None:
    print(f"  ❌ {msg}")
    FAILS.append(msg)


def note(msg: str) -> None:
    print(f"     {msg}")
    NOTES.append(msg)


def run(cmd: list[str], timeout: int = 900) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)


def hand_cases() -> list[str]:
    """手搓用例 = `cases/` 下非 `ai_*` 的用例 id（AI 用例归场景1/3 验收）。"""
    return sorted(p.stem for p in CASES.glob("*.json") if not p.name.startswith("ai_"))


def gen_funcs(text: str) -> set[str]:
    """`scripts/test_cases.py` 里定义的测试函数名（`def test_<case_id>(`）。"""
    return set(re.findall(r"^def test_([A-Za-z0-9_\u4e00-\u9fff]+)\s*\(", text, re.M))


# ---------------- ① 覆盖 ----------------

def step_cover(cases: list[str]) -> None:
    print("\n① 覆盖：每条手搓用例都有对应测试函数")
    if not TEST_CASES.is_file():
        bad(f"缺 {TEST_CASES.relative_to(REPO)}（先跑 framework.cli generate）")
        return
    funcs = gen_funcs(TEST_CASES.read_text(encoding="utf-8", errors="replace"))
    missing = [c for c in cases if c not in funcs]
    if missing:
        bad(f"这些手搓用例没有对应测试函数（generate 漏了？）：{missing[:6]}")

    # ④ 负向自证：不存在的 case 必须查不到
    if "definitely_missing_case_xyz" in funcs:
        bad("负向自证失败：不存在的 case_id 竟然「有」测试函数 ⇒ 覆盖判定不可信")
    else:
        ok(f"负向自证：不存在的 case_id 不会被误判为已覆盖")
    if not missing:
        ok(f"{len(cases)} 条手搓用例全部有对应测试函数：{cases}")


# ---------------- ② 数据分离 ----------------

def step_datasets(cases: list[str]) -> None:
    print("\n② 数据分离：每条手搓用例都有 datasets 抽离产物")
    missing = [c for c in cases if not (DATASETS / f"{c}.json").is_file()]
    if missing:
        bad(f"缺 datasets：{missing[:6]}（数据没抽离 ⇒ 用例数据写死在脚本里）")
    else:
        ok(f"{len(cases)} 条手搓用例的数据集齐备")


# ---------------- ③ 全量执行 ----------------

def step_run_all(cases: list[str], budget_s: int = 900) -> None:
    print(f"\n③ 全量执行：逐条跑 {len(cases)} 条手搓用例（预算 {budget_s}s）")
    t0 = time.time()
    bads: list[str] = []
    for i, cid in enumerate(cases, 1):
        r = run([PY, "-m", "framework.cli", "run", "--case", cid], timeout=budget_s)
        took = time.time() - t0
        tail = [ln for ln in (r.stdout or "").splitlines() if ln.strip()][-1:] or [""]
        if r.returncode != 0:
            bads.append(f"{cid}(exit {r.returncode})")
            print(f"     [{i}/{len(cases)}] ❌ {cid} exit={r.returncode} · {tail[0][:70]}")
        else:
            print(f"     [{i}/{len(cases)}] ✅ {cid} （累计 {took:.0f}s）")
    if bads:
        bad(f"手搓用例执行失败：{bads}")
    else:
        ok(f"全部 {len(cases)} 条手搓用例执行通过（共 {time.time()-t0:.0f}s）")


# ---------------- ⑤ 零残渣 ----------------

def step_no_residue(before: dict[str, set[str]]) -> None:
    print("\n⑤ 零残渣：本脚本不该改动用例 / 数据集 / 场景")
    now = snapshot()
    for key in before:
        added = now[key] - before[key]
        removed = before[key] - now[key]
        if added or removed:
            bad(f"{key} 被改动了（新增 {sorted(added)[:3]} / 消失 {sorted(removed)[:3]}）"
                f" —— 本脚本应只读+执行")
    if not FAILS:
        ok("用例 / 数据集 / 场景集合与跑前一致")


def snapshot() -> dict[str, set[str]]:
    return {
        "cases": {p.name for p in CASES.glob("*.json")},
        "datasets": {p.name for p in DATASETS.glob("*.json")},
        "scenarios": {p.name for p in (REPO / "scenarios").rglob("*.yml")},
    }


def main() -> int:
    print("=" * 66)
    print(" E2E 场景2（手搓链路）：cases → generate → 全量执行")
    print("=" * 66)
    cases = hand_cases()
    if not cases:
        bad("cases/ 下没有任何手搓用例（非 ai_*）⇒ 场景2 无从验收")
        print(f"\n结论：❌ 未通过（{len(FAILS)} 项）")
        return 1
    note(f"手搓用例 {len(cases)} 条（AI 用例不在此列，归场景1/3）")
    before = snapshot()

    # demo 新鲜度闸门（②④ 的前提；旧 demo ⇒ 后面白跑）—— 走它自己的 CLI 口径
    r = run([PY, "frameworkTest/demo_freshness.py", "--ensure", "--start-if-missing"], timeout=300)
    note(f"demo 新鲜度闸门：exit={r.returncode}（--ensure --start-if-missing）")
    if r.returncode != 0:
        bad(f"demo 新鲜度闸门未通过（exit {r.returncode}）⇒ 后面的执行结论不可信")

    step_cover(cases)
    step_datasets(cases)
    step_run_all(cases)
    step_no_residue(before)

    print("\n" + "=" * 66)
    if FAILS:
        print(f"结论：❌ 未通过（{len(FAILS)} 项）")
        for f in FAILS:
            print(f"   - {f}")
        return 1
    print(f"结论：✅ 通过（手搓链路 {len(cases)} 条用例全跑通）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
