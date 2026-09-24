#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""录像重录工具（D2 · 2026-09-24 他定）。

**他的原话**：「一旦新加特性或者 demo app 有变化，需要重新录制，你记住**能确保重新录制**
就没问题了，**跑场景3的时候就能把问题拦住**。」

⇒ 本工具负责「**能确保重新录制**」这一半；另一半（拦住）由场景3 的录像键机制天然保证：
   录像键 = 【场景文案 + 页面 url + 控件骨架】，场景改了 / demo 控件变了 ⇒ 键变了 ⇒
   `explore --llm-cassette` 找不到对应录像 ⇒ **明确报「没有这一份」** ⇒ 场景3 当场红。
   所以日常流程是：**场景3 红了 ⇒ 跑本工具重录 ⇒ 再跑场景3 确认绿**。

**什么时候必须重录**（任何一条命中就要重录）：
  1. 改了 `scenarios/*.yml`（场景文案变了 ⇒ 键变）；
  2. demo app 变了（页面 url / 控件骨架 / 文案变了 ⇒ 键变），例如 `demo/app.py` 改动；
  3. 升级了 `framework/tools/explore/` 的 prompt / 语义识别逻辑；
  4. 新增特性导致页面结构变化。
  反过来：**只改验证脚本、只改用例数据 ⇒ 不需要重录**（录像只覆盖"语义识别"这一步）。

**⚠️ 2026-09-24 实测补充（项目负责人确认，务必连同上面四条一起看）**：

  **(甲) 第 3 条的实际代价比字面更重：改 prompt ⇒ 九份录像**全部**失效。**
  键 = `sha256(系统提示 + 提示词)`，系统提示一改、**所有**场景的键同时变
  ⇒ 没有"只改一点"的余地，只能 `--all` 全量重录（实测 ≈ 5 分钟，真调 LLM）。
  ⇒ 所以改 prompt 前先问自己：**这次改动值不值一次全量重录？**
  实例：为治"AI 把场景 `{占位符}` 内联甚至自编数据"，在系统提示里加了铁律 ⇒ 全量重录 9 个场景。

  **(乙) 键匹配有**两级**，不止"逐字一致"这一级：**
  · ① 严格级：`system + prompt` 逐字一致 ⇒ 直接用（静默 ✓）；
  · ② 结构级（回退）：**页面/控件结构相同、但这些控件的"值"与录制时不同**（换台机器、或机器上跑过测试，
    数据就变了）⇒ 仍会命中录像，但会**大声告警**：
    「按**结构键**命中录像…步骤是录制当时针对那批数据做的判断，**请核对后再用**」。
  ⇒ 口径（两级分工，别一刀切）：
    · **日常二类：用回退级 + 告警**（不许因为"数据值漂移"就整轮变红 —— 那会变成狼来了，
      人会开始无视红色；本项目原则：**宁漏不误伤**）；
    · **发版门：强制严格级**（`--llm-cassette-strict`）—— 要发出去的东西，录像必须逐字对得上，
      不接受"结构像、数据不同"的将就。`--llm-cassette-strict` 就是给这一级用的。

**用法**：
  python tests/featureTest/rerecord_cassettes.py --list          # 列出场景与录像现状（零成本）
  python tests/featureTest/rerecord_cassettes.py --scenario contracts_search_by_no   # 重录一个
  python tests/featureTest/rerecord_cassettes.py --all           # 重录全部（会真调 LLM，慢）
  python tests/featureTest/rerecord_cassettes.py --all --verify  # 重录完顺带跑场景3 体检

⚠️ 会**真调 LLM**（花 token、要外网）。没有 key / 断网 ⇒ 明确报错退出（exit 2），不假装成功。
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PY = sys.executable
SCEN = REPO / "scenarios"
CASSETTE_DIR = REPO / "output" / "llm_cassettes"

sys.path.insert(0, str(REPO))


def force_stdio() -> None:
    """统一 UTF-8（项目约定：脚本会把子进程输出打回控制台 ⇒ 中文 Windows 上会乱码）。"""
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001
            pass


force_stdio()

FAILS: list[str] = []


def ok(m: str) -> None:
    print(f"  ✅ {m}")


def bad(m: str) -> None:
    print(f"  ❌ {m}")
    FAILS.append(m)


def info(m: str) -> None:
    print(f"     {m}")


def scenarios() -> list[Path]:
    return sorted(SCEN.rglob("*.yml"))


def has_llm_key() -> tuple[bool, str]:
    try:
        import framework.tools.common.config  # noqa: F401
    except Exception as e:  # noqa: BLE001
        return False, f"框架 config 导入失败：{e}"
    for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "DEEPSEEK_API_KEY"):
        if os.environ.get(k):
            return True, k
    return False, "未检测到 LLM key（DEEPSEEK_API_KEY 等）"


def cassette_snapshot() -> dict:
    """录像文件快照：{文件名: mtime}。

    2026-09-24 踩坑：原来用**数量**判断"录到了没"⇒ 覆盖重录（同名文件被更新）时 delta=0
    ⇒ 明明录成功了却报"录像数没增加（录到哪儿去了？）"，害我去查一个不存在的问题 ✗
    ⇒ 改成比对**内容有没有变**（mtime 快照）：新增与覆盖都算成功。
    """
    if not CASSETTE_DIR.is_dir():
        return {}
    return {p.name: p.stat().st_mtime for p in CASSETTE_DIR.glob("*.json")}


def run(cmd: list[str], timeout: int = 1800) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout, env=env)


def record_one(scen: Path) -> bool:
    rel = scen.relative_to(REPO)
    print(f"\n  ▶ 重录：{rel}")
    before = cassette_snapshot()
    t0 = time.time()
    r = run([PY, "-m", "framework.cli", "explore", "--ai",
             "--scenario-file", str(rel), "--llm-record", "--no-cases", "--no-verify"])
    dt = time.time() - t0
    after = cassette_snapshot()
    if r.returncode != 0:
        tail = "\n".join((r.stdout or "").splitlines()[-6:] + (r.stderr or "").splitlines()[-3:])
        if any(k in tail.lower() for k in ("401", "403", "connection", "timeout", "unauthorized",
                                           "name or service not known")):
            bad(f"{scen.name} 重录失败：看着像 key/网络问题（{dt:.0f}s）\n   {tail[-400:]}")
            return False
        bad(f"{scen.name} 重录失败（exit {r.returncode}，{dt:.0f}s）\n   {tail[-400:]}")
        return False
    changed = [n for n, v in after.items() if before.get(n) != v]
    delta = len(changed)
    if delta <= 0:
        bad(f"{scen.name}：命令 exit 0 但录像文件没有更新（内容与 mtime 都没变 ⇒ 真没录到）")
        return False
    ok(f"{scen.name}：写入/更新 {delta} 份录像（共 {len(after)} 份）· 用时 {dt:.0f}s")
    return True


def verify_scenario3() -> bool:
    print("\n  ▶ 重录后体检：跑场景3（录像 ⇄ 当前场景是否匹配）")
    r = run([PY, "tests/featureTest/verify_e2e_scenario3_cassette.py"], timeout=1800)
    tail = "\n".join((r.stdout or "").splitlines()[-8:])
    print("   " + tail.replace("\n", "\n   "))
    if r.returncode != 0:
        bad("场景3 体检没过 ⇒ 录像与当前场景仍不匹配（重录没覆盖到？）")
        return False
    ok("场景3 体检通过（录像与当前场景匹配）")
    return True


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="录像重录（D2）：场景/demo 变了就跑它")
    ap.add_argument("--list", action="store_true", help="只列场景与录像现状（零成本）")
    ap.add_argument("--all", action="store_true", help="重录全部场景")
    ap.add_argument("--scenario", default="", metavar="名字/子串", help="只重录匹配的场景（按文件名子串）")
    ap.add_argument("--verify", action="store_true", help="重录完顺带跑场景3 体检")
    args = ap.parse_args(argv)

    scen = scenarios()
    print("=" * 66)
    print(" 录像重录工具（D2）—— 场景改了 / demo 变了 / explore prompt 变了 ⇒ 先跑它")
    print("=" * 66)
    print(f" 场景 {len(scen)} 个 · 录像目录 {CASSETTE_DIR.relative_to(REPO)} · 现有录像 {len(cassette_snapshot())} 份")

    if args.list or not (args.all or args.scenario):
        for s in scen:
            print(f"   · {s.relative_to(REPO)}")
        print("\n 要重录：--scenario <子串> 或 --all（会真调 LLM）")
        return 0

    have, why = has_llm_key()
    if not have:
        print(f"\n❌ 不能重录：{why}")
        print("   ⇒ 重录必须在**有 key + 能出网**的机器上做；离线机器只能用现成录像。")
        return 2
    info(f"LLM key 就绪：{why}（值不打印）")

    targets = scen if args.all else [s for s in scen if args.scenario in s.name]
    if not targets:
        print(f"\n❌ 没有匹配 --scenario {args.scenario!r} 的场景")
        return 2
    print(f"\n 将重录 {len(targets)} 个场景（每个约 3~5 分钟，真调 LLM）")

    for s in targets:
        record_one(s)

    if args.verify:
        verify_scenario3()

    print("\n" + "=" * 66)
    if FAILS:
        print(f"结论：❌ 未全部成功（{len(FAILS)} 项）")
        for f in FAILS:
            print(f"   - {f}")
        return 1
    print(f"结论：✅ 重录完成（{len(targets)} 个场景）")
    if not args.verify:
        print("   建议接着跑场景3 体检确认：python tests/featureTest/verify_e2e_scenario3_cassette.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
