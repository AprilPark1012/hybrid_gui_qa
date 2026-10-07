#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""E2E 场景2（手搓用例链路）—— 二类特性验证（R7 第 (4) 条 · 日常口径）。

**场景2 的完整链**：人写 `cases/manual/*.json` → `generate` 渲染脚本 + 数据分离 → `run` 真执行。

**为什么必须独立存在**（别并进场景1/3）：
  场景1 证明「真 AI 能干活」；场景3 证明「**没网 / 没 key 的机器也能干活**」；
  **场景2 证明「完全不靠 AI 也能干活」** —— 「手搓用例与生成器脱节」是**独立的坏法**，必须单独验收。

**离线可证伪（本脚本的核心机制）**：跑生成与执行时把 LLM 端点强制指黑洞
`DEEPSEEK_BASE_URL=http://127.0.0.1:9` 并清空 `DEEPSEEK_API_KEY` ——
**跑通本身即证明这条链一个字节都没碰 AI**（不是口头保证）。

判据（每条都给命令级证据）：
  1. 前置·demo 可达（不可达 -> FAIL，并提示怎么起 demo）
  2. 前置·手搓用例：`cases/manual/*.json` 至少一条（**一条都没有 -> SKIP exit 3**，不算通过）
  3. `generate` 渲染 -> **exit 0**，且为每条手搓用例产出脚本 + 数据集（脚本/数据分离）
  4. `run --case <每条手搓用例>` -> **exit 0**（真执行，不是 dry-run）
  5. **不碰 AI**：判据 3/4 全部在上述「端点指黑洞」的环境下完成
  6. **负向自证**：临时塞一条「元素语义不存在」的手搓用例 -> 执行必须 **FAIL**
     （证明「写错就会红」，不是假绿）；跑完清理干净
  7. **零残留**：临时用例 / 临时脚本 / 临时数据集全部清掉，不留孤儿

跑法（需 demo 在跑）：`python tests/特性1-混合链路/verify_e2e_scenario2_handwritten.py`
退出码：0 通过 / 1 失败 / 2 用法 / 3 跳过（**跳过不算通过**）
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PY = sys.executable
CASES_DIR = REPO / "cases" / "manual"
GEN_DIR = REPO / "scripts" / "generated" / "manual"
DS_DIR = REPO / "scripts" / "datasets"
BASE = os.environ.get("HYBRID_BASE_URL") or "http://localhost:8000"
BLACKHOLE = "http://127.0.0.1:9"          # LLM 端点指黑洞 -> 「有没有偷偷联网」可证伪
OK, FAIL, USAGE, SKIP = 0, 1, 2, 3

_TMP_ID = "manual_negative_probe_tmp"
_passed: list[str] = []


def force_stdio() -> None:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")        # type: ignore[union-attr]
        except Exception:
            pass


def ok(msg: str) -> None:
    _passed.append(msg)
    print(f"  [OK] {msg}")


def bad(msg: str) -> None:
    print(f"  [NG] {msg}")


def skip(msg: str) -> None:
    print(f"  [skip]  {msg}")


def offline_env() -> dict:
    """构造「不可能联网」的环境：端点指黑洞 + 清空密钥。"""
    env = dict(os.environ)
    env["DEEPSEEK_BASE_URL"] = BLACKHOLE
    env["DEEPSEEK_API_KEY"] = ""
    env["OPENAI_API_KEY"] = ""
    env["ANTHROPIC_API_KEY"] = ""
    return env


def run(cmd: list[str], env: dict | None = None, timeout: int = 900) -> tuple[int, str]:
    p = subprocess.run(cmd, cwd=str(REPO), env=env or offline_env(),
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def demo_reachable() -> bool:
    try:
        with urllib.request.urlopen(f"{BASE}/api/health", timeout=5) as r:
            return r.status == 200
    except Exception:
        return False


def manual_cases() -> list[Path]:
    return sorted(p for p in CASES_DIR.glob("*.json") if p.is_file())


def cleanup() -> None:
    for p in (CASES_DIR / f"{_TMP_ID}.json",
              GEN_DIR / f"{_TMP_ID}.py",
              DS_DIR / f"{_TMP_ID}.json"):
        try:
            p.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass
    for d in (GEN_DIR / "__pycache__", REPO / "scripts" / "generated" / "__pycache__"):
        shutil.rmtree(d, ignore_errors=True)


def main() -> int:
    force_stdio()
    print("=" * 72)
    print("E2E 场景2 · 手搓用例链路（不依赖 AI —— 端点指黑洞，跑通即证明）")
    print("=" * 72)

    # ── (1) 前置：demo ───────────────────────────────────────
    print("\n[1] 前置 · demo 可达性")
    if not demo_reachable():
        bad(f"demo 不可达（{BASE}/api/health）-> 先起 demo：`python -m demo.app`")
        return FAIL
    ok(f"demo 可达（{BASE}）")

    # ── (2) 前置：手搓用例 ────────────────────────────────────
    print("\n[2] 前置 · 手搓用例存在性")
    cases = manual_cases()
    if not cases:
        skip(f"`cases/manual/` 里一条手搓用例都没有 -> SKIP（跳过不算通过）")
        return SKIP
    ids = [c.stem for c in cases]
    ok(f"手搓用例 {len(cases)} 条：{', '.join(ids)}")

    # ── (3) generate（黑洞环境）────────────────────────────────
    print("\n[3] generate 渲染（LLM 端点已指黑洞 -> 不可能联网）")
    rc, out = run([PY, "-m", "framework.cli", "generate"])
    if rc != 0:
        bad(f"generate 退出码 {rc}\n{out[-900:]}")
        return FAIL
    for cid in ids:
        script, ds = GEN_DIR / f"{cid}.py", DS_DIR / f"{cid}.json"
        if not script.is_file():
            bad(f"用例 {cid}：没产出脚本 {script.relative_to(REPO)}")
            return FAIL
        if not ds.is_file():
            bad(f"用例 {cid}：没产出数据集 {ds.relative_to(REPO)}（脚本/数据未分离）")
            return FAIL
    ok(f"generate exit 0；{len(ids)} 条用例各有脚本 + 数据集（分离到位）")

    # ── (4) run 真执行（黑洞环境）─────────────────────────────
    print("\n[4] run 真执行（黑洞环境 -> 通过即证明不依赖 AI）")
    for cid in ids:
        rc, out = run([PY, "-m", "framework.cli", "run", "--case", cid])
        if rc != 0:
            bad(f"用例 {cid} 执行退出码 {rc}\n{out[-900:]}")
            return FAIL
        ok(f"{cid} 执行 exit 0")

    # ── (5) 负向自证：写错必须红 ───────────────────────────────
    print("\n[5] 负向自证 · 「元素语义不存在」必须 FAIL（防假绿）")
    src = json.loads(cases[0].read_text(encoding="utf-8"))
    neg = dict(src)
    neg["case_id"] = _TMP_ID
    # [!] 负向构造的坑（2026-10-07 实测两轮才对）：
    #   (1) 改 element 成不存在的语义 -> **generate 阶段就被质量闸拦下**（「元素未映射」不许生成），
    #      验不到「执行时会红」；(2) 改页面名为不存在的页面 -> 同样在 generate 阶段挂。
    #   -> 正解：**goto 指到一个不存在的 url**（页面打不开/空白）—— generate 校验的是语义与页面，
    #      不校验运行期可达性；到执行时后续 click 必然找不到元素 -> **必须红**。
    steps = [dict(s) for s in src.get("steps", [])]
    for s in steps:
        if s.get("op") == "goto":
            s["url"] = "http://localhost:8000/__negative_probe_does_not_exist__.html"
            break
    else:
        skip("样例用例里没有 goto 型步骤 -> 负向无法构造（跳过这一条，不算通过）")
        return SKIP
    neg["steps"] = steps
    (CASES_DIR / f"{_TMP_ID}.json").write_text(
        json.dumps(neg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        rc_g, _ = run([PY, "-m", "framework.cli", "generate"])
        if rc_g != 0:
            bad("负向用例 generate 就失败了 -> 负向无效（构造有问题）")
            return FAIL
        rc_r, out_r = run([PY, "-m", "framework.cli", "run", "--case", _TMP_ID])
        if rc_r == 0:
            bad("负向用例居然跑通了 -> **假绿**！定位机制把不存在的语义当成了可跳过/可模糊命中")
            return FAIL
        ok(f"负向用例如预期 FAIL（run 退出码 {rc_r}）—— 「写错就会红」成立")
    finally:
        cleanup()

    # ── (6) 零残留 + 复原 ─────────────────────────────────────
    print("\n[6] 零残留 · 复原到跑前状态")
    rc, out = run([PY, "-m", "framework.cli", "generate"])
    if rc != 0:
        bad(f"复原 generate 失败（退出码 {rc}）\n{out[-600:]}")
        return FAIL
    leftovers = [p for p in (CASES_DIR / f"{_TMP_ID}.json",
                             GEN_DIR / f"{_TMP_ID}.py",
                             DS_DIR / f"{_TMP_ID}.json") if p.exists()]
    if leftovers:
        bad(f"临时文件没清干净：{[str(x.relative_to(REPO)) for x in leftovers]}")
        return FAIL
    ok("临时用例 / 脚本 / 数据集已全部清理，产物复原")

    print("\n" + "=" * 72)
    print(f"结论：场景2（手搓链路）全部符合预期 —— {len(_passed)} 条判据通过（全程 LLM 端点指黑洞）")
    print("=" * 72)
    return OK


if __name__ == "__main__":
    try:
        sys.exit(main())
    except subprocess.TimeoutExpired:
        print("  [NG] 子进程超时（场景2 超时上限 900s）")
        sys.exit(FAIL)
    except KeyboardInterrupt:
        cleanup()
        sys.exit(USAGE)
