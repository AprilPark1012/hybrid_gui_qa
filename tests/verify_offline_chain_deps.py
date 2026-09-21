"""离线一键脚本的「解释器自愈」端到端验证（二类 · 需 demo）。

现场反馈驱动（2026-09-21）：用户按文档敲 `python <chain>.py --repo . --run` 得到
`[FAIL] 这个解释器缺依赖：No module named 'dotenv'`，但他 `pip list` 里有 dotenv、手动三步也能跑。
本脚本用**真实解释器**验证修复后的两条行为（一类只用假 probe 逻辑，摸不到真环境）：

  ① 正向·自愈：拿一个**确定没装项目依赖**的解释器跑本脚本 ⇒ 必须**自己挑到能用的那个**并整体 exit 0
     （输出里要能看到「来源：」= 它明确告诉你选的是谁）；找不到这种解释器 ⇒ SKIP（不硬造）。
  ② 负向·不偷换：`--python <那个缺依赖的解释器>` ⇒ 必须 exit 2 且明说是「显式指定」的问题，
     不许静默改用别的（否则用户以为在跑 A、实际跑 B）。
  ③ 正向·常规：正常环境下 `--check-deps` exit 0。

退出码：0 通过 · 1 失败 · 2 用法/环境不满足 · 3 跳过（缺可用的「坏解释器」样本，或 demo 不在跑）
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from framework.tools.common.text_io import UTF8_ENV, force_stdio   # noqa: E402

force_stdio()
_U8 = {**os.environ, **UTF8_ENV}
CHAIN = REPO / "build_tools" / "offline_explore_chain.py"
checks: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, ok, detail))
    print(f"  {'✅' if ok else '❌'} {name}" + (f" —— {detail}" if detail else ""))


def run_chain(py: str, *extra: str):
    r = subprocess.run([py, str(CHAIN), "--repo", str(REPO), "--check-deps", *extra],
                       cwd=str(REPO), env=_U8, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=180)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def _candidate_interpreters() -> list:
    """探测「可能没装项目依赖」的解释器候选 —— **不写本机绝对路径**。

    ⚠️ 2026-09-21 修（打包闸门提示 + 外发前复查发现）：这里原先硬编码了**打包机**上的
    一条私有解释器路径（形如 `<用户主目录>/.local/bin/python3.x`）。两个毛病：
      ① 交付包要被带到别人的机器上（还有 Windows），那条路径必然不存在 ⇒ 判据在对方机器上
         等于失效；② 把开发机的机器痕迹写进对外产物。
    正确做法：显式覆盖走 `HYBRID_BAD_PY`，其余**按名字探测**系统解释器（跨平台）。
    """
    out = [os.environ.get("HYBRID_BAD_PY", "")]
    for name in ("python3", "python", "py"):        # py = Windows 官方启动器
        p = shutil.which(name)
        if p:
            out.append(p)
    out += [sys.executable, "/usr/bin/python3", "/usr/local/bin/python3"]
    seen, uniq = set(), []
    for c in out:
        if c and c not in seen:
            seen.add(c)
            uniq.append(c)
    return uniq


def find_dep_less_python() -> str:
    """找一个「确实没装项目依赖」的解释器当样本（找不到就 SKIP，不硬造）。"""
    for c in _candidate_interpreters():
        if not Path(c).exists():
            continue
        r = subprocess.run([c, "-c", "import dotenv"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=60)
        if r.returncode != 0:
            return c
    return ""


def main() -> int:
    print("=" * 66)
    print(" 离线一键脚本 · 解释器自愈验证（现场反馈驱动的修复）")
    print("=" * 66)
    if not CHAIN.exists():
        print(f"  ⏭️  找不到 {CHAIN} ⇒ 跳过")
        return 3

    # ⓪ demo 必须在跑（--check-deps 会检查它；不在跑就跳过，本脚本不擅自起服务）
    import urllib.request
    try:
        urllib.request.urlopen("http://localhost:8000/api/health", timeout=3)
        demo_ok = True
    except Exception:
        demo_ok = False
    if not demo_ok:
        print("  ⏭️  demo 未在跑 ⇒ 跳过（先起 demo，或走 tests/run_verifications.sh 的统一入口）")
        return 3

    good_py = str(REPO / ".venv" / "bin" / "python")
    bad_py = find_dep_less_python()

    # ③ 常规：正常环境
    rc, out = run_chain(good_py)
    record("③ 常规环境 --check-deps 全通过（exit 0）", rc == 0 and "前置检查全部通过" in out,
           f"exit={rc}")
    record("   输出里能看到「解释器: …（来源：…）」—— 选谁不黑箱",
           "解释器:" in out and "来源：" in out,
           next((l.strip() for l in out.splitlines() if l.startswith("解释器:")), "")[:88])

    if not bad_py:
        print("  ⏭️  找不到「没装项目依赖的解释器」样本 ⇒ ① ② 跳过（不当通过）")
        bad = [n for n, ok, _ in checks if not ok]
        return 1 if bad else 3

    # ① 正向：自愈（用坏解释器跑，脚本应自己挑到能用的）
    rc, out = run_chain(bad_py)
    record("① 用「缺依赖的解释器」跑 ⇒ 自动挑到能用的那个并全通过（exit 0）",
           rc == 0 and "前置检查全部通过" in out, f"exit={rc}（样本 {bad_py}）")
    record("   且确实不是用样本解释器跑的（来源应指向 venv/其他可用候选）",
           "来源：仓库 venv" in out or "来源：PATH" in out or "来源：当前进程" in out,
           next((l.strip() for l in out.splitlines() if l.startswith("解释器:")), "")[:88])

    # ② 负向：显式指定缺依赖的解释器 ⇒ 停手，不许偷换
    rc, out = run_chain(good_py, "--python", bad_py)
    record("② 负向：--python 指定缺依赖的解释器 ⇒ 必须 exit 2 且明说「显式指定」",
           rc == 2 and "显式指定" in out, f"exit={rc}")
    record("   且不静默改用别的解释器（提示里要有「不偷换」的说明）",
           "不偷换" in out or "不会静默改用" in out)

    bad = [n for n, ok, _ in checks if not ok]
    print("-" * 66)
    if bad:
        print(f"  ❌ 未通过 {len(bad)} 项：{bad}")
        return 1
    print(f"  ✅ 全部通过（{len(checks)} 项判据：含自愈正向 + 不偷换负向）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
