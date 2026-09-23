#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""E2E 场景3（录制回放验证）—— 二类特性验证（R7 第 ④ 条的第三个场景 · 2026-09-22 新增）。

**为什么单独立一个场景**：录像一旦对不上，离线机器上的 AI 链路就整段跑不了 —— 而这件事以前
**只有现场才会发现**。实际发生过（2026-09-22）：录像包已经发出去了，体检才发现
**5 个场景里只有 1 个**有可用录像 ⇒ 无网机器上其余 4 个场景必失败。
⇒ 把「录像可用性」本身当成一个 E2E 场景来验收：**录制 → 回放 → 命中** 这条链必须能通过。

判据（日常段**零成本**：不联网、不要 key、不起浏览器）：
  1. **覆盖**：`scenarios/` 下每个场景都有可用录像（与 `build_tools/check_cassettes.py` 同一份口径）
     —— 缺 ⇒ FAIL（这就是「有些场景报录像过期」的判据化）
  2. **体检有效性（负向）**：把场景文案改掉 ⇒ 体检**必须报缺**（防「体检永远绿」）
  3. **不匹配必须 fail loud（负向）**：拿一份「对不上当前场景」的录像去回放 ⇒ 必须报「没有这一份」
     （静默挑一份用 = 拿旧结论套新场景，是红线）
  4. **录制 → 回放闭环**（**需要 key + 外网**；只在 `--with-record` 时跑，缺 key/网 ⇒ 如实 SKIP）：
     用**临时录像目录**录一份（不污染 `output/llm_cassettes`），立刻用同一目录回放 ⇒ 必须命中且链路 exit 0

跑法：`python tests/featureTest/verify_e2e_scenario3_cassette.py`                 # 日常（1~3 段）
      `python tests/featureTest/verify_e2e_scenario3_cassette.py --with-record`   # 发版前（加跑第 4 段，要 key/外网）
退出码：0 通过 / 1 失败 / 2 用法 / 3 跳过（缺录像、或缺 key 而要求录制 ⇒ **不算通过**）
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PY = sys.executable
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(REPO / "build_tools"))

CHECK = REPO / "build_tools" / "check_cassettes.py"
CASSETTE_DIR = REPO / "output" / "llm_cassettes"
SCEN_DIR = REPO / "scenarios"
OK, FAIL, USAGE, SKIP = 0, 1, 2, 3
_passed: list[str] = []


def force_stdio() -> None:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")            # type: ignore[union-attr]
        except Exception:
            pass


def ok(msg: str) -> None:
    _passed.append(msg)
    print(f"  ✅ {msg}")


def bad(msg: str) -> None:
    print(f"  ❌ {msg}")


def info(msg: str) -> None:
    print(f"     {msg}")


def _env() -> dict:
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _tail(text: str, n: int = 8) -> str:
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    return "\n".join(f"       | {ln[:170]}" for ln in lines[-n:])


def run_check(*, scenario_dir: str = "scenarios", cassette_dir: Path | None = None) -> tuple[int, str]:
    cmd = [PY, str(CHECK), "--scenario-dir", scenario_dir]
    if cassette_dir is not None:
        cmd += ["--dir", str(cassette_dir)]
    p = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=180)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def run_explore(extra: list[str], *, timeout: int = 420, need_key: bool = False) -> tuple[int, str]:
    env = _env()
    if not need_key:
        env["DEEPSEEK_BASE_URL"] = "http://127.0.0.1:9"      # 回放路径必须不联网（可证伪）
    try:
        p = subprocess.run([PY, "-m", "framework.cli", "explore", "--ai", *extra],
                           cwd=str(REPO), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           text=True, encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, f"⏱️ 超时 {timeout}s ⇒ 已杀"
    return p.returncode, (p.stdout or "")


# ---------------- 判据 1：覆盖 ----------------

def seg1_coverage() -> int:
    print("\n—— 1) 覆盖：每个场景都要有可用录像 ——")
    rc, out = run_check()
    print(_tail(out, 12))
    if rc != 0:
        bad(f"有场景没有可用录像（体检 exit {rc}）⇒ 无网机器上那些场景必失败；"
            f"修法：`python build_tools/record_cassettes.py --missing-only`（需 key+外网）")
        return FAIL
    ok("覆盖：scenarios/ 下所有场景都有可用录像")
    return OK


# ---------------- 判据 2：体检有效性（负向）----------------

def seg2_checker_effectiveness() -> int:
    print("\n—— 2) 负向：改了场景文案，体检必须报缺（防「体检永远绿」）——")
    try:
        import check_cassettes as cc
    except Exception as e:
        bad(f"导入体检模块失败：{type(e).__name__}: {e}")
        return FAIL
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        # 造一个「文案与录像对不上」的场景 + 一个「正好对得上」的场景
        src = sorted(SCEN_DIR.rglob("*.yml"))
        if not src:
            bad("scenarios/ 下没有场景文件")
            return USAGE
        text = cc.scenario_text_of(src[0])
        if not text:
            bad(f"取不到 {src[0].name} 的 scenario 文案")
            return FAIL
        miss = tmp / "tampered.yml"
        miss.write_text(f"scenario: {text}（外加一句让结构键对不上的话）\n", encoding="utf-8")
        covered, missing = cc.check([miss], cc.load_cassettes(CASSETTE_DIR))
        if not missing:
            bad("改过文案的场景竟然被判为「有录像」⇒ 体检失效（会放过真实的录像过期）")
            return FAIL
        ok(f"负向：改过文案的场景被如实判缺（最像的一份字符重合 "
           f"{missing[0].get('nearest_ratio')}）")
    return OK


# ---------------- 判据 3：不匹配必须 fail loud（负向）----------------

def seg3_mismatch_fails_loud() -> int:
    print("\n—— 3) 负向：录像对不上当前场景时，必须报「没有这一份」（不许静默挑一份用）——")
    if not list(CASSETTE_DIR.glob("*.json")):
        print("  ⏭️  SKIP：录像目录是空的，这条负向无从构造；**不算通过**")
        return SKIP
    # 找一个「体检说缺录像」的场景 —— 它天然对不上现有录像
    try:
        import check_cassettes as cc
        _covered, missing = cc.check(sorted(SCEN_DIR.rglob("*.yml")), cc.load_cassettes(CASSETTE_DIR))
    except Exception as e:
        bad(f"取缺录像清单失败：{type(e).__name__}: {e}")
        return FAIL
    # ★2026-09-22 修：原来「所有场景都有录像」时直接 SKIP；但这条判据守的是**红线**
    # （没有匹配录像 ⇒ 必须如实报「没有这一份」，绝不静默套用别的录像）。
    # 录像补齐后它会**永远 SKIP** ⇒ 等于这条红线长期无人守（SKIP 不算通过，也没人逼它）。
    # 正解：反例自己造 —— 仓库内临时场景，保证「绝不会有对应录像」；
    # 清理一律走 finally，任何中途 return/异常都不留残渣（仓库零残留是硬要求）。
    _tmp_scen: Path | None = None
    if not missing:
        import yaml
        # ⚠️ 文件名必须是合法场景 id（小写蛇形，正则 ^[a-z][a-z0-9_]*$）：以 `_` 开头会被
        # explore 判「id 不合法」退出 2 ⇒ 判据会（正确地）判我「归因不够硬」——实测踩过。
        _tmp_scen = REPO / "scenarios" / "tmp_verify_missing_scen.yml"
        _tmp_scen.write_text(
            yaml.safe_dump({"scenario": "体检用临时场景：打开一个不存在的页面做一件不可能的事。"},
                           allow_unicode=True, sort_keys=False), encoding="utf-8")
        yml = _tmp_scen
    else:
        yml = REPO / str(missing[0]["scenario"])
    try:
        rc, out = run_explore(["--scenario-file", str(yml.relative_to(REPO)),
                               "--llm-cassette", str(CASSETTE_DIR), "--no-cases", "--no-verify"])
        print(_tail(out, 8))
        if rc == 0:
            bad(f"{yml.name} 明明没有匹配的录像却 exit 0 ⇒ 静默用了别的录像（红线）")
            return FAIL
        if "没有这一份" not in out:
            bad(f"退出码 {rc} 可以，但没明确报「没有这一份」⇒ 归因不够硬")
            return FAIL
        ok(f"负向：无匹配录像 ⇒ exit {rc} 且明确报「没有这一份」（{yml.name}）")
        return OK
    finally:
        if _tmp_scen is not None:
            _tmp_scen.unlink(missing_ok=True)


# ---------------- 判据 4：录制 → 回放闭环（需 key/外网）----------------

def has_key() -> bool:
    if os.environ.get("DEEPSEEK_API_KEY"):
        return True
    env_file = REPO / ".env"
    if env_file.is_file():
        try:
            return any(ln.strip().startswith("DEEPSEEK_API_KEY") and ln.split("=", 1)[1].strip()
                       for ln in env_file.read_text(encoding="utf-8").splitlines() if "=" in ln)
        except OSError:
            return False
    return False


def demo_up() -> bool:
    base = os.environ.get("HYBRID_BASE_URL") or "http://localhost:8000"
    try:
        urllib.request.urlopen(base.rstrip("/") + "/api/health", timeout=3)
        return True
    except Exception:
        return False


def seg4_record_replay() -> int:
    print("\n—— 4) 录制 → 回放闭环（要 key + 外网；用临时录像目录，不污染 output/）——")
    if not has_key():
        print("  ⏭️  SKIP：本机没有 LLM key ⇒ 录制段跑不了（**不算通过**；发版前在配了 key 的机器上跑）")
        return SKIP
    if not demo_up():
        print("  ⏭️  SKIP：demo 不可达 ⇒ 先跑 `python -m demo.app`；**不算通过**")
        return SKIP
    yml = sorted(SCEN_DIR.rglob("*.yml"))[0]
    with tempfile.TemporaryDirectory() as td:
        tmp_rec = Path(td) / "cass"
        print(f"     录制：{yml.name} → 临时目录 {tmp_rec}")
        rc, out = run_explore(["--scenario-file", str(yml.relative_to(REPO)),
                               "--llm-record", str(tmp_rec), "--no-cases", "--no-verify"],
                              need_key=True)
        print(_tail(out, 6))
        if rc != 0 or not list(tmp_rec.glob("*.json")):
            bad(f"录制失败（exit {rc}，落盘 {len(list(tmp_rec.glob('*.json')))} 份）")
            return FAIL
        print(f"     回放：同一场景 ← 刚录的 {len(list(tmp_rec.glob('*.json')))} 份录像（端点指黑洞）")
        rc2, out2 = run_explore(["--scenario-file", str(yml.relative_to(REPO)),
                                 "--llm-cassette", str(tmp_rec), "--no-cases", "--no-verify"])
        print(_tail(out2, 6))
        if rc2 != 0:
            bad(f"刚录的录像回放却失败（exit {rc2}）⇒ 录制/回放不自洽")
            return FAIL
        if "回放" not in out2:
            bad("回放成功但日志里没有明确标注「离线回放」⇒ 来源标注缺失（红线：回放必须可见）")
            return FAIL
        ok("录制 → 回放闭环：刚录的录像立刻命中且链路 exit 0（不联网）")
    return OK


def main(argv: list[str]) -> int:
    force_stdio()
    with_record = "--with-record" in argv
    for a in argv:
        if a not in ("--with-record",):
            print(f"未知参数：{a}（用法见文件头）")
            return USAGE
    print("=" * 70)
    print(" E2E 场景3 · 录制回放验证（录像可用性 = 离线机器上跑得了 AI 链路的前提）")
    print(f" 模式：日常（1~3 段，零成本）{'+ 录制闭环（要 key/外网）' if with_record else ''}")
    print("=" * 70)
    if not CHECK.exists():
        print(f"  ❌ 找不到体检工具：{CHECK}")
        return USAGE

    codes = [seg1_coverage()]
    if codes[0] == OK:
        codes.append(seg2_checker_effectiveness())
        codes.append(seg3_mismatch_fails_loud())
    if with_record and all(c == OK for c in codes):
        codes.append(seg4_record_replay())

    print("\n" + "=" * 70)
    print(f" 汇总：通过 {sum(1 for c in codes if c == OK)} · 跳过 {sum(1 for c in codes if c == SKIP)}"
          f" · 失败 {sum(1 for c in codes if c == FAIL)}")
    print("=" * 70)
    if any(c == FAIL for c in codes):
        print("❌ 有失败 ⇒ 录像链路不可用（离线机器上 AI 链路会失败）")
        return FAIL
    if any(c == SKIP for c in codes):
        print("⚠️ 有跳过项（**不算通过**）⇒ 补齐后重跑（发版前必须四项全绿）")
        return SKIP
    print(f"✅ 全部通过（{len(_passed)} 项判据：含 2 条负向证伪）")
    return OK


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
