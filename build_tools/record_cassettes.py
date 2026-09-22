#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批量重录录像 —— 把当前版本所有场景的录像补齐 / 刷新（**需要 key + 外网**，发版前跑一次）。

为什么需要它（2026-09-22 现场反馈驱动）：
  ① 录像的键含场景文案与控件骨架 ⇒ 改了场景 / 页面 / 命名逻辑后，旧录像会失效；
  ② 手工重录是「每个场景敲一条 `explore --ai --llm-record`」——场景一多就没人愿意干，
     于是录像越来越旧、离线机器上"有些场景就是跑不了"；
  ③ 发版时应该**先把录像补齐再打包**，而不是发出去等人踩（今早那个录像包就是这么出问题的）：
     体检（`check_cassettes.py`）报缺 4 个场景，而包已经发出去了。

用法：
    python build_tools/record_cassettes.py                  # 录全部场景（scenarios/ 递归）
    python build_tools/record_cassettes.py --missing-only    # ★ 只录「体检说缺」的（省 token，推荐）
    python build_tools/record_cassettes.py --only 子串        # 只录文件名含该子串的
    python build_tools/record_cassettes.py --list            # 只看会录哪些（不执行）
    python build_tools/record_cassettes.py --check-deps      # 只做前置检查（key / demo / 解释器）

退出码：**0** 全成功 · **1** 有失败 · **2** 前置不满足（缺 key / 没场景 / 解释器不可用）· **3** 跳过（没有要录的）

口径（与项目红线一致）：
  · **录制 = 真调 LLM**（花钱、要外网）⇒ 参数必须显式、失败要大声；绝不静默降级成"看着像录了"；
  · 录完**不动 `cases/`**（`--no-cases --no-verify`）⇒ 录制过程绝不污染用例库；
  · 录完请接着跑 `check_cassettes.py` 复检；发版时再 `pack_release.py --with-cassettes` 重打录像包。
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))          # 同目录工具

OK, FAIL, USAGE, SKIP = 0, 1, 2, 3


def _force_stdio() -> None:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")          # type: ignore[union-attr]
        except Exception:
            pass


def _env() -> dict:
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def has_key() -> bool:
    """有没有可用的 LLM key（环境变量 or 项目根 .env）—— 只判断有无，不打印内容。"""
    if os.environ.get("DEEPSEEK_API_KEY"):
        return True
    env_file = REPO / ".env"
    if env_file.is_file():
        try:
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith("DEEPSEEK_API_KEY") and "=" in line:
                    return bool(line.split("=", 1)[1].strip())
        except OSError:
            return False
    return False


def demo_up() -> bool:
    import urllib.request
    base = os.environ.get("HYBRID_BASE_URL") or "http://localhost:8000"
    try:
        urllib.request.urlopen(base.rstrip("/") + "/api/health", timeout=3)
        return True
    except Exception:
        return False


def pick_python() -> str:
    """复用离线链的解释器挑选逻辑（候选逐个探测，显式指定不偷换）。"""
    try:
        from offline_explore_chain import pick_python as _pick
        cmd, src, tried = _pick(REPO, os.environ.get("HYBRID_PYTHON", ""))
        if cmd:
            print(f"   解释器: {src} → {' '.join(cmd)}")
            return cmd[0] if len(cmd) == 1 else " ".join(cmd)
        for s, c, good, why in tried:
            print(f"     ✗ {s:<40} {'✓' if good else why}")
    except Exception as e:
        print(f"   （解释器自动挑选不可用：{type(e).__name__}: {e}⇒ 退回本进程解释器）")
    return sys.executable


def target_scenarios(args) -> list[Path]:
    files = sorted((REPO / args.scenario_dir).rglob("*.yml"))
    if args.only:
        files = [f for f in files if args.only in f.name]
    if args.missing_only:
        try:
            from check_cassettes import check, load_cassettes, scenario_text_of      # noqa: F401
            from framework.tools.explore.llm_cassette import default_dir
            covered, missing = check(files, load_cassettes(default_dir()))
            miss_names = {Path(str(m["scenario"])).name for m in missing}
            files = [f for f in files if f.name in miss_names]
        except Exception as e:
            print(f"   ⚠️ --missing-only 取「缺录像」清单失败（{type(e).__name__}: {e}）⇒ 录全部")
    return files


def record_one(py: str, yml: Path, timeout: int = 420) -> tuple[int, str]:
    """录一个场景：真调 LLM，落一份录像（**不产用例**）。"""
    cmd = [*py.split(), "-m", "framework.cli", "explore", "--ai",
           "--scenario-file", str(yml.relative_to(REPO)), "--llm-record", "--no-cases", "--no-verify"]
    try:
        p = subprocess.run(cmd, cwd=str(REPO), env=_env(), stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, f"⏱️ 超时 {timeout}s ⇒ 已杀"
    return p.returncode, (p.stdout or "")


def main(argv: list[str]) -> int:
    _force_stdio()
    ap = argparse.ArgumentParser(
        prog="record_cassettes.py",
        description="批量重录录像（需 key + 外网；录制=真调 LLM，会花钱）",
    )
    ap.add_argument("--scenario-dir", default="scenarios", help="场景目录（默认 scenarios/）")
    ap.add_argument("--only", default="", metavar="子串", help="只录文件名含该子串的场景")
    ap.add_argument("--missing-only", action="store_true", help="★ 只录体检说缺录像的场景（省 token）")
    ap.add_argument("--list", action="store_true", help="只列出会录哪些（不执行）")
    ap.add_argument("--check-deps", action="store_true", help="只做前置检查（key / demo / 解释器）")
    ap.add_argument("--timeout", type=int, default=420, metavar="秒", help="单场景超时（默认 420s）")
    args = ap.parse_args(argv)

    files = target_scenarios(args)
    print("=" * 66)
    print(" 批量重录录像（录制 = 真调 LLM，需要 key + 外网；会花钱，谨慎跑）")
    print(f" 场景目录: {args.scenario_dir}/  ·  待录: {len(files)} 个")
    print("=" * 66)
    for f in files:
        print(f"   · {f.relative_to(REPO)}")

    if args.list:
        return OK
    if not files:
        print("⏭️  SKIP：没有要录的场景（--missing-only 时说明体检没报缺）；**不算通过**")
        return SKIP

    print("\n—— 前置检查 ——")
    print(f"   key(环境变量或项目根 .env): {'有' if has_key() else '缺'}")
    print(f"   demo 可达: {'是' if demo_up() else '否（先跑 python -m demo.app）'}")
    py = pick_python()
    if args.check_deps:
        bad = (not has_key()) or (not demo_up())
        print(f"   ⇒ 结论：{'前置不满足（上面标「缺/否」的项先解决）' if bad else '前置齐全，可以录'}")
        return USAGE if bad else OK
    if not has_key():
        print("❌ 缺 LLM key（录制必须真调模型）⇒ 在项目根 .env 配 DEEPSEEK_API_KEY，或从有网机器拷录像")
        return USAGE
    if not demo_up():
        print("❌ demo 不可达 ⇒ 先另开一个窗口跑 `python -m demo.app`（录制要探测真实页面控件）")
        return USAGE

    print(f"\n—— 开始录制（{len(files)} 个场景）——")
    done, failed = [], []
    for i, f in enumerate(files, 1):
        print(f"\n[{i}/{len(files)}] {f.relative_to(REPO)}")
        t0 = time.time()
        rc, out = record_one(py, f, timeout=args.timeout)
        tail = [ln for ln in out.splitlines() if ln.strip()][-6:]
        for ln in tail:
            print(f"     | {ln[:170]}")
        if rc == 0:
            done.append(f.name)
            print(f"   ✅ 已录（{time.time() - t0:.0f}s）")
        else:
            failed.append((f.name, rc))
            print(f"   ❌ 失败 exit {rc}（{time.time() - t0:.0f}s）")

    print("\n" + "=" * 66)
    print(f" 汇总：成功 {len(done)} · 失败 {len(failed)}")
    for name, rc in failed:
        print(f"   ❌ {name}  exit {rc}")
    print("=" * 66)
    if failed:
        print("❌ 有失败 ⇒ 修完重录（录像不齐，无网机器上那些场景跑不了）")
        return FAIL
    print("✅ 全部录好。下一步：① `python build_tools/check_cassettes.py` 复检；"
          "② 发版时 `python build_tools/pack_release.py --with-cassettes` 重打录像包")
    return OK


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
