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
    print(" 口径（2026-09-22 升级）：**内容指纹**为主 + mtime 降级；touch 不算改动")
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

    # ①-b 前提：必须存在**属于当前进程**的指纹快照（否则只能退回 mtime 口径，测不出指纹能力）
    st0 = df.check()
    if not st0.get("snapshot_used"):
        print("  快照不存在或不属于当前进程 ⇒ 真重启一次以落快照（本脚本自建前提）")
        df.restart(quiet=True)
        st0 = df.check()
    record("② 前提：存在属于当前 demo 进程的指纹快照",
           bool(st0.get("snapshot_used")) and (st0.get("state") == "fresh"),
           f"snapshot_used={st0.get('snapshot_used')} · fp={st0.get('fingerprint')}")

    original_bytes = TARGET.read_bytes()
    original_mtime = TARGET.stat().st_mtime
    fp_baseline = df.demo_fingerprint()["fingerprint"]
    try:
        # ③ ★ 核心负向（新口径堵的正是这个洞）：**内容变了、但 mtime 拨回旧值** ⇒ 必须 stale
        TARGET.write_bytes(original_bytes + b"\n# p16-gate-probe: content changed, mtime rolled back\n")
        os.utime(TARGET, (original_mtime, original_mtime))
        rc, out = cli("--check")
        record("③ 负向证伪【mtime 漏判口】：内容变了但 mtime 没前进 ⇒ 必须判 stale（exit 3）",
               rc == 3 and "不新鲜" in out, f"exit={rc}")
        st = df.check()
        record("   负向细节：check() state=stale 且理由指向「内容/指纹」（不是 mtime）",
               st["state"] == "stale" and ("内容" in st["detail"] or "指纹" in st["detail"]),
               st["detail"])

        # ④ 内容还原（mtime 同样还原）⇒ 必须 fresh：闸门不许无故报警
        TARGET.write_bytes(original_bytes)
        os.utime(TARGET, (original_mtime, original_mtime))
        st2 = df.check()
        record("④ 正向：内容还原 ⇒ 判 fresh（闸门不无故报警）",
               st2["state"] == "fresh", f"state={st2['state']} · {st2['detail']}")

        # ⑤ 只动 mtime（touch，内容一字未改）⇒ 必须 fresh（touch 不是改动）
        os.utime(TARGET, (time.time(), time.time()))
        st3 = df.check()
        record("⑤ 负向：只 touch 不改内容 ⇒ 必须 fresh（不许把 touch 当改动，否则天天白重启）",
               st3["state"] == "fresh", f"state={st3['state']} · {st3['detail']}")

        # ⑥ 修复路径：内容变（真改动）⇒ --ensure 必须真重启 + 复检 fresh + 快照指纹同步更新
        TARGET.write_bytes(original_bytes + b"\n# p16-gate-probe: ensure must restart\n")
        fp_before = df.demo_fingerprint()["fingerprint"]
        rc, out = cli("--ensure")
        record("⑥ --ensure 自动重启后复检为新鲜（exit 0）", rc == 0 and "新鲜" in out, f"exit={rc}")
        record("   重启后 demo 可服务（/api/health 200）", health_ok())
        st4 = df.check()
        record("   重启后 state=fresh 且是**新进程**（started_epoch 就在刚刚）",
               st4["state"] == "fresh" and (st4["started_epoch"] or 0) >= time.time() - 120,
               f"started={time.strftime('%H:%M:%S', time.localtime(st4['started_epoch'] or 0))}")
        record("   快照已同步为新指纹（下一轮才能用指纹判 fresh）",
               (st4.get("snapshot") or {}).get("fingerprint") == fp_before,
               f"snapshot={((st4.get('snapshot') or {}).get('fingerprint'))} vs 当前={fp_before}")
    finally:
        # ⑦ 收尾：内容与 mtime 一起还原，并 ensure 到新鲜，留给后续脚本用
        TARGET.write_bytes(original_bytes)
        os.utime(TARGET, (original_mtime, original_mtime))
        print(f"  ↩️  已还原 demo/app.py 内容与 mtime（逐字节相同 · "
              f"{time.strftime('%H:%M:%S', time.localtime(original_mtime))}）")
        rc_restore, _ = cli("--ensure")
        print(f"  ↩️  收尾 --ensure：exit {rc_restore}（把 demo 交回新鲜态）")

    rc, out = cli("--check")
    record("⑦ 还原后仍新鲜（闸门不会无故报警）", rc == 0, f"exit={rc}")
    record("   还原后内容逐字节一致 + 指纹回到基线",
           TARGET.read_bytes() == original_bytes and df.demo_fingerprint()["fingerprint"] == fp_baseline,
           f"fp={df.demo_fingerprint()['fingerprint']} vs 基线={fp_baseline}")

    bad = [n for n, ok, _ in checks if not ok]
    print("-" * 64)
    if bad:
        print(f"  ❌ 未通过：{len(bad)} 项 —— {bad}")
        return 1
    print(f"  ✅ 全部通过（{len(checks)} 项判据：内容指纹正/负向 + touch 不误报 + 真重启 + 逐字节还原）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
