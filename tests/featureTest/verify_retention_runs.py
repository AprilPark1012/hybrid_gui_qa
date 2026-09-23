#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""L5 归档保留策略 · 端到端验证（2026-09-22，服务目标 ③ 稳定 + ④ 脚本健壮）。

为什么单独一个脚本、不叫 test_*.py：它要开真浏览器跑真 demo（本机内存紧），
与 `verify_data_expand.py` / `verify_slow_target.py` 同一口径 —— 由 R7 统一入口调。

判据（全真跑）：

  ① **`summary.json` 真的会落地**：真跑一条用例（`cli run --case …`）⇒ 新 run 目录里必须有
     `summary.json`，且 `exit_code == 0`、`failed_cases == 0` —— 这是策略判「能否证明成功」的**唯一依据**
     （没有它，run 一律只瘦身）；
  ② **自动清理已接线**：`auto_prune_runs()` 在未设开关时返回结果、设 `HYBRID_NO_AUTO_PRUNE=1` 时返回 None
     （开关只有一处，不许两边各写一遍）；
  ③ **未超龄的 run 一个文件都不许动**：真跑出来那个 run（刚生成、在保留窗口内）跑完清理后
     `.log` / `report.html` / `traces/*.zip` 全部还在；
  ④ **真 CLI 的 dry-run 必须真不动**：连续两次 `prune --runs --dry-run` ⇒ 真 `log/` 的目录树
     （文件清单 + 每个文件大小）逐字节一致；
  ⑤ **破坏性路径在隔离沙箱里真跑一遍**：临时目录造 40 个 run（含录像 / 全绿 summary / 失败 summary /
     历史无 summary / 被引用清单 / 手工目录），真跑 `prune_runs(log_dir=沙箱)` ⇒ 断言
     两级处理、保护规则、单次上限、不认识的命名不动。

**本脚本绝不删真实 `log/` 里的任何东西**（判据 ④ 只读；判据 ⑤ 全在临时目录）。

跑法：cd ~/hybrid_gui_qa && .venv/bin/python tests/featureTest/verify_retention_runs.py
退出码：0 通过 / 1 失败 / 2 用法 / 3 跳过（内存不足或 demo 不可达 —— **跳过不等于通过**）
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
PY = sys.executable
OK, FAIL, USAGE, SKIP = 0, 1, 2, 3
MIN_MEM_MB = 550                      # 与 run_verifications.sh 同口径（一个 headless Chromium ≈ 515MB）
CASE = "ai_contracts_search_by_no_000813"      # 单条用例（秒级，够验证 run 目录与 summary）
sys.path.insert(0, str(BASE))

from framework.tools.common.config import LOG_DIR                                  # noqa: E402
from framework.tools.common.retention import auto_prune_runs, prune_runs           # noqa: E402

_fail: list[str] = []


def force_stdio() -> None:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")       # type: ignore[union-attr]
        except Exception:
            pass


def mem_available_mb() -> int:
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) // 1024
    return 10 ** 6


def demo_ok() -> bool:
    try:
        with urllib.request.urlopen("http://localhost:8000/api/health", timeout=4) as r:
            return r.status == 200
    except Exception:
        return False


def run(cmd: list[str], env: dict | None = None) -> subprocess.CompletedProcess:
    e = dict(os.environ)
    e.update(env or {})
    return subprocess.run(cmd, cwd=str(BASE), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=e)


def ck(cond: bool, msg: str, detail: str = "") -> None:
    print(f"  {'✅' if cond else '❌'} {msg}" + (f" —— {detail}" if detail else ""))
    if not cond:
        _fail.append(msg)


def tree_snapshot(root: Path) -> list[tuple[str, int]]:
    out = []
    for p in sorted(root.rglob("*")):
        if p.is_file():
            try:
                out.append((str(p.relative_to(root)), p.stat().st_size))
            except OSError:
                out.append((str(p.relative_to(root)), -1))
    return out


# --------------------------------------------------------------- 沙箱：破坏性路径真跑一遍
def sandbox_case() -> None:
    now = datetime(2026, 9, 22, 12, 0, 0)
    tmp = Path(tempfile.mkdtemp(prefix="retention_sandbox_"))
    log, ver = tmp / "log", tmp / "output" / "verify"
    log.mkdir(parents=True)
    ver.mkdir(parents=True)
    green = {"exit_code": 0, "failed_cases": 0}
    red = {"exit_code": 1, "failed_cases": 2}

    def mk(name: str, *, traces: int = 0, summary: dict | None = None) -> Path:
        d = log / name
        (d / "traces").mkdir(parents=True)
        (d / "case.log").write_text("[CHECK] ✓ 断言\n", encoding="utf-8")
        (d / "report.html").write_text("<html>report</html>", encoding="utf-8")
        for i in range(traces):
            (d / "traces" / f"c{i}_trace.zip").write_bytes(b"x" * 1_000_000)
        if summary is not None:
            (d / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
        return d

    fresh = mk("20260922_110000", traces=2)                        # 唯一在最近 keep 个之内 ⇒ 完全不动
    ok_new = mk("20260914_120000", traces=2, summary=green)        # 最近一次全绿 ⇒ 受保护（只瘦身）
    ok_old = mk("20260823_120000", traces=2, summary=green)        # 更老的全绿 ⇒ 整删
    legacy = mk("20260901_120000", traces=3)                        # 历史无 summary ⇒ 只瘦身
    fail_run = mk("20260901_130000", traces=2, summary=red)         # 失败 ⇒ 只瘦身
    ref = mk("20260902_120000", traces=2)                           # 被引用 ⇒ 完全不碰
    (log / ".protected_runs").write_text(f"{ref.name}  # 沙箱：模拟被台账引用\n", encoding="utf-8")
    (log / "manual_dir").mkdir()
    (log / "manual_dir" / "用户手工.txt").write_text("别动我\n", encoding="utf-8")
    for i in range(10):                                            # verify 日志（老）
        f = ver / f"nonexistent_case_{(now - timedelta(days=30 - i)).strftime('%Y%m%d_%H%M%S')}.log"
        f.write_text("pytest session\n", encoding="utf-8")

    # keep=1：只有 `fresh` 落在"最近 1 个"内 ⇒ 其余超龄 run 都进入候选（才测得到保护规则）
    res = prune_runs(keep=1, keep_days=7, log_dir=log, verify_dir=ver,
                     dry_run=False, now=now, quiet_if_none=False)
    ck(not ok_old.exists(), "沙箱：更老的全绿 run（能证明成功且超龄）⇒ 整删")
    ck(ok_new.exists() and not list(ok_new.glob("traces/*.zip")),
       "沙箱：最近一次全绿 ⇒ 保护（只瘦身、不整删）")
    ck(legacy.exists() and (legacy / "case.log").exists()
       and (legacy / "report.html").exists() and not list(legacy.glob("traces/*.zip")),
       "沙箱：历史无 summary ⇒ 只瘦身，日志与报告留下")
    ck(fail_run.exists() and (fail_run / "summary.json").exists()
       and not list(fail_run.glob("traces/*.zip")), "沙箱：失败 run ⇒ 只瘦身且 summary 保留")
    ck(len(list(ref.glob("traces/*.zip"))) == 2, "沙箱：被引用 run ⇒ 完全不碰")
    ck((log / "manual_dir" / "用户手工.txt").exists(), "沙箱：不认识的手工目录 ⇒ 不动")
    ck(len(list(fresh.glob("traces/*.zip"))) == 2, "沙箱：未超龄 run ⇒ 一个文件都不动")
    ck(res["removed_dirs"] == [ok_old.name], f"沙箱：整删集正是『更老的全绿』（{res['removed_dirs']}）")
    ck(set(res["slimmed_dirs"]) == {legacy.name, fail_run.name, ok_new.name},
       f"沙箱：瘦身集 = 历史/失败/最近全绿（{sorted(res['slimmed_dirs'])}）")
    shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    force_stdio()
    print("=" * 72)
    print(" L5 归档保留策略 · 端到端验证（真跑 · 只读真实 log/，破坏性路径在沙箱）")
    print("=" * 72)

    mem = mem_available_mb()
    if mem < MIN_MEM_MB:
        print(f"  ⏭️  SKIP：MemAvailable {mem}MB < {MIN_MEM_MB}MB —— 内存不足，跳过（跳过不是通过）")
        return SKIP
    if not demo_ok():
        print("  ⏭️  SKIP：demo 不可达（http://localhost:8000/api/health）—— 先 `python -m demo.app`")
        return SKIP
    print(f"  （MemAvailable {mem}MB · demo 可达）")

    # ---- ① 真跑一条用例 ⇒ summary.json 必须落地 ----
    print("\n[判据①] 真跑一条用例，验证 summary.json 落地")
    before_dirs = {d.name for d in LOG_DIR.iterdir() if d.is_dir()}
    r = run([PY, "-m", "framework.cli", "run", "--case", CASE, "--workers", "1", "--debug"])
    print(f"  （pytest 退出码 {r.returncode}；输出尾部：{(r.stdout or '').strip().splitlines()[-1][:70] if r.stdout else ''}）")
    new_dirs = sorted({d.name for d in LOG_DIR.iterdir() if d.is_dir()} - before_dirs)
    ck(len(new_dirs) == 1, f"本次运行新建了 1 个 run 目录", str(new_dirs))
    run_dir = LOG_DIR / new_dirs[0] if new_dirs else None
    if run_dir is not None:
        summ = run_dir / "summary.json"
        ck(summ.is_file(), "summary.json 已生成")
        if summ.is_file():
            data = json.loads(summ.read_text(encoding="utf-8"))
            ck(data.get("exit_code") == 0, f"summary.exit_code == 0（实为 {data.get('exit_code')}）")
            ck(data.get("failed_cases") == 0, f"summary.failed_cases == 0（实为 {data.get('failed_cases')}）")
            ck(int(data.get("case_logs", 0)) >= 1, f"summary.case_logs 计数正常（{data.get('case_logs')}）")
        # ---- ③ 未超龄的 run 一个文件都不许动 ----
        print("\n[判据③] 刚生成的 run（保留窗口内）跑完清理后必须完好")
        logs = sorted(p.name for p in run_dir.glob("*.log"))
        traces = sorted(p.name for p in (run_dir / "traces").glob("*.zip"))
        ck(bool(logs) and (run_dir / "report.html").is_file() and bool(traces),
           f"日志 {len(logs)} / report.html / trace {len(traces)} 全在")

    # ---- ② 自动清理已接线 + 开关有效 ----
    print("\n[判据②] 自动清理入口与开关")
    got = auto_prune_runs(quiet_if_none=True)
    ck(isinstance(got, dict), "auto_prune_runs() 正常返回结果（= 未设开关时会执行）")
    off = subprocess.run([PY, "-c",
                          "import os,sys; sys.path.insert(0,'.'); "
                          "from framework.tools.common.retention import auto_prune_runs as a; "
                          "print(a(quiet_if_none=True))"],
                         cwd=str(BASE), capture_output=True, text=True, encoding="utf-8",
                         errors="replace", env={**os.environ, "HYBRID_NO_AUTO_PRUNE": "1"})
    ck(off.stdout.strip() == "None", f"HYBRID_NO_AUTO_PRUNE=1 时返回 None（实为 {off.stdout.strip()!r}）")

    # ---- ④ 真实 log/ 上跑两次 dry-run：必须真不动 ----
    print("\n[判据④] 真 CLI · prune --runs --dry-run 连跑两次，目录树逐字节一致")
    s1 = tree_snapshot(LOG_DIR)
    d1 = run([PY, "-m", "framework.cli", "prune", "--runs", "--dry-run"])
    d2 = run([PY, "-m", "framework.cli", "prune", "--runs", "--dry-run"])
    s2 = tree_snapshot(LOG_DIR)
    ck(d1.returncode == 0 and d2.returncode == 0, f"两次 dry-run 都 exit 0（{d1.returncode}/{d2.returncode}）")
    ck(s1 == s2, f"真 log/ 目录树未变（{len(s1)} 个文件）")
    ck("dry-run" in (d1.stdout or ""), "dry-run 输出里明确标注是预演")

    # ---- ⑤ 沙箱里真跑破坏性路径 ----
    print("\n[判据⑤] 沙箱里真跑破坏性路径（两级处理 / 保护 / 上限 / 手工目录不动）")
    sandbox_case()

    print("\n" + "=" * 72)
    if _fail:
        print(f"❌ 未通过 {len(_fail)} 项：")
        for m in _fail:
            print(f"   - {m}")
        return FAIL
    print("✅ 全部通过")
    return OK


if __name__ == "__main__":
    sys.exit(main())
