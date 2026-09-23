#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""E2E 场景1（真 AI 链路）—— AI 读 `scenarios/*.yml` 语义识别 → 生成 cases + 脚本 → 跑通。

**R7-e 场景1**（他 2026-09-23 定，口径**选 3 = 两条都要**）：
  · **日常（默认）**：`--quick` —— 只跑**一个**场景，验「**真 LLM 能不能识别出用例并生成脚本**」（快，省 token）；
  · **发版前**：`--full` —— 跑**全部**场景 + 把新生成的用例**执行一遍**（慢、花 token，只在发版前跑）。
与场景3（录制回放 mock）的**区别**：场景3 证明「没网/没 key 的机器也能干活」，
场景1 证明「**真 LLM 现在还能干活**」（模型/接口/额度变了、prompt 与场景写法漂了，只有它能发现）。
两条链都可能坏、坏法不同 ⇒ 分开验收。

判据：
  ① **前置**：得有 LLM key（`DEEPSEEK_API_KEY` 等，`config.py` 会从项目 .env / Hermes .env 加载）
     —— 没有 ⇒ **SKIP（exit 3）并说清原因**（**不伪装成通过**，也不硬失败：本机本来就不该有 key）
  ② **生成**：`explore --ai` 之后必须**新增** `cases/ai_*.json`（新增=真识别，不是复用旧产物）
  ③ **可追溯**：新用例的 `scenario_id` 必须指向**真实存在**的场景文件（防场景改名后留下孤儿用例）
  ④ **能产出脚本**：`framework.cli generate` exit 0（AI 用例能翻译成可执行脚本）
  ⑤ **（--full）能执行**：新用例 `cli run --case <id>` exit 0
  ⑥ **零残渣（L15 纪律）**：跑完把**本次新增**的用例归档 + 重跑 `generate` 复原产物
     —— 这条是本脚本存在的前提：**它自己不许把仓库弄脏**

⚠️ 本脚本会**真的调用 LLM**（花 token、联网）。默认 `--quick` 只跑一个场景。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PY = sys.executable
CASES = REPO / "cases"
SCEN_DIR = REPO / "scenarios"
ARCHIVE = REPO / "output" / f"archived_cases_scen1_{time.strftime('%Y%m%d_%H%M%S')}"
QUICK_SCENARIO = SCEN_DIR / "contracts" / "contracts_search_by_no.yml"

sys.path.insert(0, str(REPO))

# 统一 UTF-8：脚本会把子进程输出打回控制台 —— 不拉齐口径时，中文 Windows（cp936）上会显示乱码。
from framework.tools.common.text_io import force_stdio       # noqa: E402

force_stdio()

sys.path.insert(0, str(REPO / "tests" / "frameworkTest"))
sys.path.insert(0, str(REPO / "tests" / "featureTest"))

FAILS: list[str] = []


def ok(m: str) -> None:
    print(f"  ✅ {m}")


def bad(m: str) -> None:
    print(f"  ❌ {m}")
    FAILS.append(m)


def info(m: str) -> None:
    print(f"     {m}")


def run(cmd: list[str], timeout: int = 1800, env_extra: dict | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    if env_extra:
        env.update(env_extra)
    return subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout, env=env)


def ai_cases() -> set[str]:
    return {p.stem for p in CASES.glob("ai_*.json")}


def scenario_ids() -> set[str]:
    """现有场景文件的 id（文件名去掉扩展名，与用例里 `scenario_id` 同一口径）。"""
    return {p.stem for p in SCEN_DIR.rglob("*.yml")}


def has_llm_key() -> tuple[bool, str]:
    """LLM key 是否就绪（经 config.py 加载 .env 之后再判断）。"""
    try:
        import framework.tools.common.config  # noqa: F401  —— 导入即触发 load_dotenv
    except Exception as e:  # noqa: BLE001
        return False, f"框架 config 导入失败：{e}"
    for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "DEEPSEEK_API_KEY"):
        if os.environ.get(k):
            return True, k
    return False, "未检测到任何 LLM key（DEEPSEEK_API_KEY 等）"


def log_looks_like_auth_or_network(text: str) -> bool:
    t = (text or "").lower()
    return any(k in t for k in ("401", "403", "invalid_api_key", "unauthorized",
                                "incorrect api key", "connection", "timed out", "timeout",
                                "temporary failure", "name or service not known"))


def archive_new_cases(new_ids: set[str]) -> None:
    """把本次新增的 AI 用例归档（零残留），随后由调用方重跑 generate 复原产物。"""
    if not new_ids:
        return
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    for cid in sorted(new_ids):
        src = CASES / f"{cid}.json"
        if src.is_file():
            shutil.move(str(src), str(ARCHIVE / src.name))
    print(f"     归档 {len(new_ids)} 条新用例 → {ARCHIVE.relative_to(REPO)}")


def main() -> int:
    ap = argparse.ArgumentParser(description="E2E 场景1（真 AI 链路）")
    ap.add_argument("--full", action="store_true",
                    help="跑全部场景 + 执行新用例（发版前用；默认只跑一个场景）")
    ap.add_argument("--keep-cases", action="store_true",
                    help="保留本次生成的用例（默认归档清零残留；调试时才用）")
    args = ap.parse_args()

    print("=" * 66)
    print(f" E2E 场景1（真 AI 链路）：{'--full（全部场景 + 执行）' if args.full else '--quick（一个场景，验证能生成）'}")
    print("=" * 66)

    # ① 前置：key
    have, why = has_llm_key()
    if not have:
        print(f"\n⚠️ SKIP：{why}")
        print("   ⇒ 本机没有 LLM key，场景1（真 AI）无从验收。")
        print("   ⇒ 这不是失败：**没网/没 key 的机器请用场景3（录制回放）**，那条链专门为它存在。")
        print("   ⇒ 要跑场景1：在项目 .env 或 Hermes .env 里配 DEEPSEEK_API_KEY。")
        return 3
    info(f"LLM key 就绪：{why}（值不打印）")

    before_ai = ai_cases()
    before_ids = before_ai | set()
    keep = args.keep_cases
    rc = 1
    try:
        # ② 生成：真调 LLM
        if args.full:
            cmd = [PY, "-m", "framework.cli", "explore", "--ai", "--scenario-dir", "scenarios/"]
        else:
            if not QUICK_SCENARIO.is_file():
                bad(f"快版场景文件不存在：{QUICK_SCENARIO.relative_to(REPO)}")
                return 1
            cmd = [PY, "-m", "framework.cli", "explore", "--ai",
                   "--scenario-file", str(QUICK_SCENARIO.relative_to(REPO))]
        print(f"\n② 真 AI 语义识别：{' '.join(cmd[2:])}")
        t0 = time.time()
        r = run(cmd, timeout=1800)
        info(f"explore exit={r.returncode} · 耗时 {time.time()-t0:.0f}s")
        if r.returncode != 0:
            tail = "\n".join((r.stdout or "").splitlines()[-6:] + (r.stderr or "").splitlines()[-3:])
            if log_looks_like_auth_or_network(tail):
                print(f"\n⚠️ SKIP：真 AI 调用失败，看着像 key/额度/网络问题（不伪装成通过）")
                print(f"   {tail[-400:]}")
                return 3
            bad(f"explore --ai 失败（exit {r.returncode}）")
            print(f"   {tail[-500:]}")

        new_ids = ai_cases() - before_ids
        if not new_ids:
            bad("explore --ai 之后没有新增任何 `cases/ai_*.json` ⇒ 语义识别没产出用例")
        else:
            ok(f"新增 AI 用例 {len(new_ids)} 条：{sorted(new_ids)}")

        # ③ 可追溯：scenario_id 必须指向真实场景
        bads = []
        for cid in sorted(new_ids):
            d = json.loads((CASES / f"{cid}.json").read_text(encoding="utf-8", errors="replace"))
            sid = str(d.get("scenario_id", "")).strip()
            if not sid:
                bads.append(f"{cid}（无 scenario_id）")
            elif sid not in scenario_ids():
                bads.append(f"{cid}→{sid}（场景不存在）")
        if bads:
            bad(f"新用例的场景可追溯性不成立：{bads}")
        elif new_ids:
            ok(f"场景可追溯：{len(new_ids)} 条新用例的 scenario_id 都指向真实场景")

        # ④ 能产出脚本
        print("\n④ generate：把 AI 用例翻译成可执行脚本")
        g = run([PY, "-m", "framework.cli", "generate"], timeout=1800)
        if g.returncode != 0:
            bad(f"generate 失败（exit {g.returncode}）—— AI 用例没能变成脚本")
            print("   " + "\n   ".join((g.stdout or "").splitlines()[-6:]))
        else:
            ok("generate exit 0（AI 用例已生成脚本 + 数据分离）")

        # ⑤ --full：执行新用例
        if args.full and new_ids and not FAILS:
            print(f"\n⑤ 执行新用例（{len(new_ids)} 条）")
            for cid in sorted(new_ids):
                rr = run([PY, "-m", "framework.cli", "run", "--case", cid], timeout=1200)
                if rr.returncode == 0:
                    info(f"✅ {cid}")
                else:
                    bad(f"新用例执行失败：{cid}（exit {rr.returncode}）")
            if not FAILS:
                ok(f"{len(new_ids)} 条新用例全部执行通过")

        rc = 0 if not FAILS else 1
    finally:
        # ⑥ 零残渣：归档本次新增 + 重跑 generate 复原产物（L15 纪律）
        new_ids = ai_cases() - before_ids
        if keep:
            print(f"\n⑥ 保留 {len(new_ids)} 条新用例（--keep-cases）")
        else:
            print("\n⑥ 零残渣：归档本次新增用例 + 重跑 generate 复原产物")
            archive_new_cases(new_ids)
            g2 = run([PY, "-m", "framework.cli", "generate"], timeout=1800)
            info(f"复原 generate exit={g2.returncode}")
            left = ai_cases() - before_ids
            if left:
                bad(f"归档后仍残留新用例：{sorted(left)}")
            else:
                ok("仓库已回到跑前状态（cases/ 与 scripts/ 一致）")

    print("\n" + "=" * 66)
    if rc == 0:
        print(f"结论：✅ 通过（真 AI 链路：识别 → 生成{' → 执行' if args.full else ''}）")
    else:
        print(f"结论：❌ 未通过（{len(FAILS)} 项）")
        for f in FAILS:
            print(f"   - {f}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
