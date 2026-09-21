"""demo 新鲜度闸门的端到端验证（二类 · 需 demo）—— 证明「闸门真的会拦、拦截后真能修好」。

为什么必须有这一条（R7：新增特性 = 一类 + 二类各至少一条）：
一类只验判定函数；**「改了 demo 没重启 ⇒ 二类验证白跑」这件事只有在真进程上才验证得了**。
本脚本用真 demo 进程演一遍事故形态（只改 mtime、**不改内容**，跑完原样还原）：

  ① 现状检查（不新鲜就先 ensure 到新鲜，作为基线）
  ② **负向证伪**：把 `demo/app.py` 的 mtime 拨到当前 ⇒ 闸门**必须**判 stale 且 `--check` 退出码 = 3
  ③ **修复路径真跑**：`--ensure` 必须真重启 demo，并复检到 fresh；重启后 `/api/health` 必须是 200
  ④ 收尾：mtime 还原（内容一字未动），demo 留给后续验证用

退出码：0 通过 · 3 跳过（demo 不在跑，不硬起）· 1 失败 · 2 用法错误
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))
# 统一 UTF-8（R7 判据强制每个 verify_*.py 都调；Windows cp936 控制台否则中文乱码 —— 2026-09-15 实测过）
from framework.tools.common.text_io import UTF8_ENV, force_stdio   # noqa: E402
import demo_freshness as df          # noqa: E402

force_stdio()
_U8 = {**os.environ, **UTF8_ENV}      # 给子进程注入 UTF-8 口径

PY = sys.executable
TARGET = REPO / "demo" / "app.py"
checks: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, ok, detail))
    print(f"  {'✅' if ok else '❌'} {name}" + (f" —— {detail}" if detail else ""))


def cli(*args: str) -> tuple[int, str]:
    r = subprocess.run([PY, "tests/demo_freshness.py", *args], cwd=str(REPO), env=_U8,
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=90)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def health_ok() -> bool:
    try:
        urllib.request.urlopen(df.BASE_URL.rstrip("/") + "/api/health", timeout=3)
        return True
    except Exception:
        return False


def main() -> int:
    print("=" * 64)
    print(" demo 新鲜度闸门 · 端到端验证（改了 demo 必须重启，否则验证白跑）")
    print("=" * 64)

    if not df.demo_pids():
        print("  ⏭️  demo 未在运行 ⇒ 跳过（本脚本不擅自起 demo；先跑 python -m demo.app 或 run_verifications.sh）")
        return 3

    # ① 基线：先确保新鲜
    rc, out = cli("--ensure")
    record("① 基线：--ensure 把 demo 带到新鲜态", rc == 0 and "新鲜" in out, out.strip().splitlines()[0] if out else "")
    if rc != 0:
        print("  基线都不新鲜 ⇒ 后续无意义，终止")
        return 1

    original = TARGET.stat().st_mtime
    try:
        # ② 负向：只拨 mtime（内容不变）⇒ 必须判 stale
        os.utime(TARGET, (time.time(), time.time()))
        rc, out = cli("--check")
        record("② 负向证伪：改了 demo 没重启 ⇒ 必须判 stale（exit 3）",
               rc == 3 and "不新鲜" in out, f"exit={rc}")
        st = df.check()
        record("   负向细节：check() 的 state 必须是 stale", st["state"] == "stale", st["detail"])

        # ③ 修复路径：--ensure 必须真重启 + 复检 fresh + 健康
        rc, out = cli("--ensure")
        record("③ --ensure 自动重启后复检为新鲜（exit 0）", rc == 0 and "新鲜" in out, f"exit={rc}")
        record("   重启后 demo 可服务（/api/health 200）", health_ok())
        st2 = df.check()
        record("   重启后进程时刻 > 源码 mtime（真重启，不是把时间戳改回去）",
               st2["state"] == "fresh" and (st2["started_epoch"] or 0) >= time.time() - 120,
               f"started={time.strftime('%H:%M:%S', time.localtime(st2['started_epoch'] or 0))}")
    finally:
        # ④ 还原 mtime（内容从未改动）
        os.utime(TARGET, (original, original))
        print(f"  ↩️  已还原 demo/app.py 的 mtime（{time.strftime('%H:%M:%S', time.localtime(original))}）；内容未动")

    rc, out = cli("--check")
    record("④ 还原后仍新鲜（闸门不会无故报警）", rc == 0, f"exit={rc}")

    bad = [n for n, ok, _ in checks if not ok]
    print("-" * 64)
    if bad:
        print(f"  ❌ 未通过：{len(bad)} 项 —— {bad}")
        return 1
    print(f"  ✅ 全部通过（{len(checks)} 项判据：含负向证伪 + 真重启 + 还原）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
