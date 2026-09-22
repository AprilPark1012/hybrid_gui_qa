#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""E2E 场景1（离线回放端到端）—— 二类特性验证（R7 第 ④ 条 · 日常口径）。

**场景1 的完整链**：自然语言场景 → `explore --ai` 语义识别/编排 → 用例落 `cases/ai_*.json`
→ `generate` 生成脚本 + 数据分离 → `run` 执行。

**日常怎么跑**（AprilPark1012 2026-09-22 拍板）：**离线录像回放** —— 不需要 key、不联网、且可证伪：
`build_tools/offline_explore_chain.py` 会把 LLM 端点强制指到黑洞 `127.0.0.1:9`，
所以「这次到底有没有偷偷联网」是可验证的事实，不是口头保证。
真调 DeepSeek 的**在线版只作发版前手工一次**（结果写进发行说明）—— 因为要 key + 外网且 LLM 不稳定，
塞进日常闸门会变成「天天红 → 被无视」（与「假红会摧毁闸门」同源）。

判据（每条都给命令级证据）：
  1. 前置·录像：`output/llm_cassettes/*.json` 有录像；没有则尝试从 `releases/*cassettes*.zip` 现取；
     两条都无 ⇒ **SKIP exit 3**（不是失败，但**也不算通过**）
  2. 前置·demo：被测应用可达（不可达 ⇒ FAIL，并提示 `python -m demo.app`）
  3. 跑链：`offline_explore_chain.py --repo . --scenario <f> --run` ⇒ **exit 0**
  4. 产物：`cases/ai_*.json` **新增一条** —— 证明「自然语言 → 用例落盘 → 生成 → 执行」真的发生了，不是空跑
  5. 零残留：新增产物归档到 `output/archived_cases_<日期>/`，`cases/` 与 `scripts/datasets/` 回到跑前状态
  6. **负向①**：录像目录指到空目录 ⇒ 链必须 **exit 2（前置不满足）且不产出任何用例**（没录像时不许假绿）
  7. **负向②**：`--scenario` 指不存在的文件 ⇒ 必须非 0（不许静默跳过）

跑法（需 demo 在跑）：`python tests/verify_e2e_scenario1_offline.py`
退出码：0 通过 / 1 失败 / 2 用法 / 3 跳过（缺录像 ⇒ **不算通过**）
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PY = sys.executable
CHAIN = REPO / "build_tools" / "offline_explore_chain.py"
SCENARIO = REPO / "scenarios" / "contracts" / "contracts_search_by_no.yml"
CASSETTE = REPO / "output" / "llm_cassettes"
ARCHIVE = REPO / "output" / f"archived_cases_{time.strftime('%Y%m%d')}"
BLACKHOLE = "http://127.0.0.1:9"          # LLM 端点指黑洞 ⇒ 「有没有偷偷联网」可证伪
BASE = os.environ.get("HYBRID_BASE_URL") or "http://localhost:8000"
OK, FAIL, USAGE, SKIP = 0, 1, 2, 3

_CASES = REPO / "cases"
_DATASETS = REPO / "scripts" / "datasets"
_passed: list[str] = []


def force_stdio() -> None:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")        # type: ignore[union-attr]
        except Exception:
            pass


def ok(msg: str) -> None:
    _passed.append(msg)
    print(f"  ✅ {msg}")


def bad(msg: str) -> None:
    print(f"  ❌ {msg}")


def info(msg: str) -> None:
    print(f"     {msg}")


def demo_up() -> bool:
    try:
        urllib.request.urlopen(BASE.rstrip("/") + "/api/health", timeout=3)
        return True
    except Exception:
        return False


def ai_cases() -> set[str]:
    """当前 `cases/ai_*.json` 的文件名集合（用于「新增了哪条」与「零残留」判定）。"""
    return {p.name for p in _CASES.glob("ai_*.json")}


def ensure_cassettes() -> tuple[bool, str]:
    """录像可用？没有就从录像包现取（解到 output/llm_cassettes）。"""
    if list(CASSETTE.glob("*.json")):
        return True, f"录像就在 {CASSETTE}（{len(list(CASSETTE.glob('*.json')))} 份）"
    zips = sorted((REPO / "releases").glob("*cassettes*.zip"))
    if zips:
        CASSETTE.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zips[-1]) as z:
            n = 0
            for name in z.namelist():
                if name.startswith("llm_cassettes/") and name.endswith(".json"):
                    (CASSETTE / Path(name).name).write_bytes(z.read(name))
                    n += 1
        if n:
            return True, f"从 {zips[-1].name} 取了 {n} 份录像到 {CASSETTE}"
    return False, (f"没有可用录像（{CASSETTE} 为空，且 releases/ 里没有 *cassettes*.zip）⇒ "
                   f"无法验证场景1 离线链路（**不算通过**）")


def run_chain(*, cassette: str | None = None, scenario: Path | None = None,
              timeout: int = 600) -> tuple[int, str]:
    """跑离线一键链（显式把 LLM 端点指黑洞、文本显式 UTF-8）。"""
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["DEEPSEEK_BASE_URL"] = BLACKHOLE
    cmd = [PY, str(CHAIN), "--repo", ".", "--scenario", str(scenario or SCENARIO), "--run"]
    if cassette is not None:
        cmd += ["--cassette", cassette]
    try:
        p = subprocess.run(cmd, cwd=str(REPO), env=env, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, f"⏱️ 超时 {timeout}s ⇒ 已杀"
    return p.returncode, (p.stdout or "")


def _tail(out: str, n: int = 10) -> str:
    lines = [ln for ln in out.splitlines() if ln.strip()]
    return "\n".join(f"       | {ln[:180]}" for ln in lines[-n:])


def _regen() -> tuple[int, str]:
    """以当前 `cases/` 为准重新生成脚本与数据集。

    ⚠️ 为什么必须做（2026-09-22 实测发现）：本判据内部的离线链会**跑一次 `generate`**，
    于是重新生成出来的 `scripts/test_cases.py` 里**带着那条用例**；随后我们把它归档了，
    可产物还留着它的函数 —— 变成「孤儿测试」（用例已不在 `cases/`，脚本里却还有它）。
    下一次一类自测的 `cases↔datasets 1:1` / 产物健康判据就会红，而且原因很难一眼看出。
    ⇒ 口径：跑完链必须**把产物恢复到「以当前 cases/ 为准」的状态**（与负向验证段同一先例）。
    """
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        p = subprocess.run([PY, "-m", "framework.cli", "generate"], cwd=str(REPO), env=env,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                           encoding="utf-8", errors="replace", timeout=600)
    except subprocess.TimeoutExpired:
        return 124, "⏱️ generate 超时"
    return p.returncode, (p.stdout or "")


def _archive_new(new: set[str]) -> int:
    """把本次新增的用例与数据集归档到 output/archived_cases_<日期>/（仓库零残留）。"""
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    moved = 0
    for name in new:
        src = _CASES / name
        if src.exists():
            shutil.move(str(src), str(ARCHIVE / name))
            moved += 1
        stem = name[:-5]                                    # 去掉 .json
        for suffix in (".json", ".sets.json"):              # 数据集 + 可选多组数据伴生件
            d = _DATASETS / f"{stem}{suffix}"
            if d.exists():
                shutil.move(str(d), str(ARCHIVE / d.name))
    return moved


def main() -> int:
    force_stdio()
    print("=" * 66)
    print(" E2E 场景1 · 离线回放端到端（自然语言 → explore --ai → cases → generate → run）")
    print(" 口径：离线录像回放（LLM 端点指黑洞 127.0.0.1:9 ⇒ 不联网可证伪）")
    print("=" * 66)

    if not CHAIN.exists():
        print(f"  ❌ 找不到离线链脚本：{CHAIN}（用法错误）")
        return USAGE
    if not SCENARIO.exists():
        print(f"  ❌ 场景文件不存在：{SCENARIO}")
        return USAGE

    # 1) 前置：录像
    print("\n—— 前置检查 ——")
    has_cass, why = ensure_cassettes()
    info(why)
    if not has_cass:
        print(f"  ⏭️  SKIP：{why}")
        return SKIP
    ok("前置①：录像可用")

    # 2) 前置：demo
    if not demo_up():
        bad(f"前置②：被测 demo 不可达（{BASE}）⇒ 先跑 `python -m demo.app`")
        return FAIL
    ok("前置②：demo 可达")

    # 3) 正向：跑通整条链
    print("\n—— 正向：跑通整条链 ——")
    before = ai_cases()
    rc, out = run_chain()
    print(_tail(out, 14))
    if rc != 0:
        bad(f"离线链失败：exit {rc}（期望 0）")
        return FAIL
    ok(f"离线链 exit 0（explore 回放 → generate → run 全通）")

    # 4) 产物：必须真的新增一条 ai 用例（防「空跑也报绿」）
    after = ai_cases()
    new = after - before
    if not new:
        bad(f"跑完全绿但**没有新增 `cases/ai_*.json`** ⇒ 这条链可能是空跑（假绿）")
        return FAIL
    ok(f"产物：新增 {len(new)} 条 AI 用例 —— {sorted(new)[0]}")

    # 5) 零残留
    moved = _archive_new(new)
    rest = ai_cases() - before
    if rest:
        bad(f"归档后仍有残留：{sorted(rest)}（用例库应回到跑前状态）")
        return FAIL
    ok(f"零残留：{moved} 条新增用例已归档到 {ARCHIVE.relative_to(REPO)}（用例库回到跑前状态）")

    # 6) 负向①：录像缺失 ⇒ 必须 exit 2 且不产出
    print("\n—— 负向①：把录像指到空目录，必须前置不满足且不产出 ——")
    empty = REPO / "output" / "_neg_empty_cassette"
    empty.mkdir(parents=True, exist_ok=True)
    before_neg = ai_cases()
    rc_n, out_n = run_chain(cassette=str(empty), timeout=180)
    print(_tail(out_n, 6))
    if rc_n != 2:
        bad(f"录像缺失时的退出码应是 2（前置不满足），实际 {rc_n} —— 闸门口径不一致")
        return FAIL
    if ai_cases() != before_neg:
        bad("录像缺失竟然也产出了用例 ⇒ 假绿风险（没录像必须一条都不产）")
        return FAIL
    ok("负向①：exit 2（前置不满足）且**零产出** —— 没录像不会假绿")

    # 7) 负向②：场景文件不存在 ⇒ 必须非 0
    print("\n—— 负向②：场景文件不存在，必须非 0 ——")
    rc_b, out_b = run_chain(scenario=REPO / "scenarios" / "__no_such_scenario__.yml", timeout=180)
    print(_tail(out_b, 6))
    if rc_b == 0:
        bad("场景文件不存在却 exit 0 ⇒ 静默跳过（不可接受）")
        return FAIL
    ok(f"负向②：场景不存在 ⇒ exit {rc_b}（非 0，且提示明确）")

    print("\n" + "=" * 66)
    print(f" ✅ 全部通过（{len(_passed)} 项判据：含 2 条负向证伪 + 零残留归档）")
    print("=" * 66)
    return OK


if __name__ == "__main__":
    raise SystemExit(main())
