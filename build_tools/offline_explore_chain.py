"""离线一条命令：explore 语义识别（录像回放）→ generate 生成用例脚本 [→ run 试跑]。

为什么单独一个脚本：工作电脑连不上外网 LLM，要靠录像包回放才能跑 AI 链路；而「回放」有几个
前置（录像目录 / demo 在跑 / **代码版本配套**），步骤散在 CLI 里容易漏。这里串起来逐条给结论，
并且**强制把 LLM 端点指到黑洞（127.0.0.1:9）**—— 证明这次跑下来真的没联网、也没用 key。

本脚本住在仓库的 `build_tools/`（框架自己的开发工具目录，与 pack_release.py / build_html.py 同列；
V8.0 起从仓库根 `tools/` 改名，避免与运行期的 `framework/tools/` 混淆）；
**随代码包一起交付**，不需要额外安装（纯标准库）。

用法（Windows / macOS / Linux 通用）：
    python build_tools/offline_explore_chain.py --repo . --check-deps          # ★ 只做前置检查（排查首选）
    python build_tools/offline_explore_chain.py --repo .
    python build_tools/offline_explore_chain.py --repo . --scenario scenarios/contracts/contracts_search_by_no.yml
    python build_tools/offline_explore_chain.py --repo . --scenario scenarios/contracts/contracts_search_by_no.yml --run
    python build_tools/offline_explore_chain.py --repo . --scenario-dir scenarios            # 把所有场景都回放一遍
    python build_tools/offline_explore_chain.py --repo . --scenario <f> --cassette D:\\cassettes   # 录像不在默认位置

解释器：默认自动挑「依赖齐全的那个」——候选依次是 `--python` / 环境变量 `HYBRID_PYTHON` →
`<repo>/.venv`（Linux/macOS 与 Windows 两种布局）→ 当前进程解释器 → PATH 上的 python3/python → Windows `py -3`；
**显式指定了就不偷换**（指定的那个缺依赖会直接报错，而不是悄悄换一个能跑的）。

退出码：0 = 全通 · 2 = 前置不满足（没可用解释器 / 录像缺 / demo 没起 / 代码版本不含回放）· 1 = 链路某步失败。
"""
import argparse
import json
import os
import shlex
import subprocess
import sys
import urllib.request
from pathlib import Path

BLACKHOLE = "http://127.0.0.1:9/v1"          # 指向必然连不上的地址 ⇒ 真联网就会失败
DEFAULT_BASE = "http://localhost:8000"


def ok(msg):
    print("  [OK]   " + msg)


def bad(msg):
    print("  [FAIL] " + msg)


def info(msg):
    print("  [--]   " + msg)


def head(msg):
    print("\n=== " + msg + " ===")


def child_env():
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"                   # 跨进程文本一律显式 UTF-8（中文 Windows 上尤其要）
    env["PYTHONIOENCODING"] = "utf-8"
    env["DEEPSEEK_BASE_URL"] = BLACKHOLE      # 让「有没有偷偷联网」这件事变成可证伪
    return env


def run(cmd, cwd):
    p = subprocess.run(cmd, cwd=str(cwd), env=child_env(),
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       encoding="utf-8", errors="replace")
    return p.returncode, (p.stdout or "")


def tail(text, n=12):
    lines = [l for l in text.splitlines() if l.strip()]
    for l in lines[-n:]:
        print("       | " + l[:200])
    return lines


def health(base_url):
    try:
        with urllib.request.urlopen(base_url + "/api/health", timeout=5) as r:
            return True, r.read().decode("utf-8", "replace")[:160]
    except Exception as e:                     # noqa: BLE001 —— 这里就是要「任何异常都当不可达」
        return False, "%s: %s" % (type(e).__name__, e)


def newest_ai_case(repo):
    items = sorted((repo / "cases").glob("ai_*.json"), key=lambda p: p.stat().st_mtime)
    return items[-1] if items else None


def _split_cmd(s):
    """把用户给的解释器描述拆成命令行（兼容 `py -3`、带空格的路径）。"""
    return shlex.split(s, posix=(os.name != "nt"))


def python_candidates(repo, explicit=""):
    """候选解释器（按优先级）—— 每项是 (来源说明, [命令行...])。

    为什么是**一串候选**而不是只挑一个（2026-09-21 现场反馈驱动的修复）：
      Windows 上按**旧文档**敲那条命令（`python tools/…`，V8.0 前的路径写法）时，`python` 往往是
      **系统解释器**（没装项目依赖），而旧逻辑只探测 `.venv/{bin,Scripts}` 两个固定位置，
      没命中就**默默退回当前进程解释器**，然后只甩一句「这个解释器缺依赖：No module named 'dotenv'」——
      用户看到的是「框架坏了 / 依赖没装」（他确实去 `pip list` 查过，而 `pip list` 查的是 venv，
      跟跑脚本的解释器**不是同一个**）。结论：候选要列全、逐个探测、选第一个依赖齐全的，
      并把每个候选缺什么都摆出来 —— 让用户一眼知道「我该用哪个解释器」。
    """
    cands = []
    if explicit:
        cands.append(("--python / HYBRID_PYTHON 指定", _split_cmd(explicit)))
    for p, label in ((repo / ".venv" / "bin" / "python", "仓库 venv（Linux / macOS）"),
                     (repo / ".venv" / "Scripts" / "python.exe", "仓库 venv（Windows）")):
        if p.exists():
            cands.append((label, [str(p)]))
    cands.append(("当前进程的解释器（跑本脚本的那个）", [sys.executable]))
    for name in ("python3", "python"):
        cands.append(("PATH 上的 %s" % name, [name]))
    if os.name == "nt":
        cands.append(("Windows py launcher", ["py", "-3"]))
    return cands


def probe_deps(cmd, repo):
    """探测某个解释器依赖是否齐全 ⇒ (是否齐全, 最后一行的报错或结论)。"""
    rc, out = run(list(cmd) + ["-c", "import dotenv, playwright, pytest; print('deps-ok')"], repo)
    return (rc == 0 and "deps-ok" in out), ((out.strip().splitlines() or [""])[-1][:200])


def pick_python(repo, explicit="", probe=None):
    """挑解释器 ⇒ (选中的命令行 or None, 来源说明, 探测清单)。

    ⚠️ 刻意语义：**显式指定了就不偷换** —— 指定的解释器缺依赖时必须报错退出，
    而不是静默换一个「能跑的」：否则用户以为在用 A、实际跑的是 B（沉默的错比报错贵得多）。
    """
    probe = probe or (lambda cmd: probe_deps(cmd, repo))
    tried = []
    for src, cmd in python_candidates(repo, explicit):
        good, why = probe(cmd)
        tried.append((src, " ".join(cmd), good, why))
        if good:
            return cmd, src, tried
        if src.startswith("--python"):
            return None, "", tried          # 显式指定不可用 ⇒ 停，不往下试
    return None, "", tried


def main():
    ap = argparse.ArgumentParser(description="离线 explore(回放) → generate 一条命令")
    ap.add_argument("--repo", default=".",
                    help="仓库根目录（默认当前目录）")
    ap.add_argument("--scenario", action="append", default=[],
                    help="场景文件（可重复；与 --scenario-dir 二选一）")
    ap.add_argument("--scenario-dir", default="",
                    help="场景目录（批量回放）")
    ap.add_argument("--cassette", default="",
                    help="录像目录（默认 <repo>/output/llm_cassettes）")
    ap.add_argument("--base-url", default=DEFAULT_BASE,
                    help="被测 demo 地址（默认 %s）" % DEFAULT_BASE)
    ap.add_argument("--python", default="",
                    help="跑本仓库用的解释器（默认自动用 <repo>/.venv 里的那个）")
    ap.add_argument("--run", action="store_true",
                    help="generate 之后再 run 试跑刚生成的那条用例（多花约 10 秒）")
    ap.add_argument("--check-deps", action="store_true",
                    help="只做前置检查（解释器 / 代码版本 / 录像 / demo）就退出，不跑链路 —— 排查首选")
    args = ap.parse_args()

    repo = Path(args.repo).resolve()
    cassette = Path(args.cassette).resolve() if args.cassette else (repo / "output" / "llm_cassettes")
    scenarios = list(args.scenario)

    print("仓库: %s" % repo)
    print("录像目录: %s" % cassette)

    # ---------- 一、前置检查（任一条不满足就别往下跑）----------
    head("一、前置检查")
    cli_py = repo / "framework" / "cli.py"
    exp_py = repo / "framework" / "tools" / "explore" / "explorer.py"
    if not cli_py.exists():
        bad("找不到 framework/cli.py —— --repo 指错目录了？")
        return 2
    blob = cli_py.read_text(encoding="utf-8", errors="replace") + \
        exp_py.read_text(encoding="utf-8", errors="replace")
    if "--llm-cassette" not in blob or "llm_cassette" not in blob:
        bad("这套代码**不含录像回放功能**（CLI 里没有 --llm-cassette）")
        info("录像包只能配「带 cassette 的版本」用 ⇒ 先拿到含该功能的代码（V7.7 起）再来跑")
        return 2
    ok("代码含录像回放（--llm-cassette）")

    explicit = args.python or os.environ.get("HYBRID_PYTHON", "")
    py, py_src, tried = pick_python(repo, explicit)
    if py is None:
        if explicit:
            bad("你显式指定的解释器依赖不全：%s" % explicit)
            info("（按「显式指定不偷换」的约定停下：不会静默改用别的解释器，否则你不知道实际跑的是哪个）")
        else:
            bad("没找到依赖齐全的解释器（共探测 %d 个候选）" % len(tried))
        for src, cmd, good, why in tried:
            info("  %-40s %s" % (src, "✓ 可用" if good else "✗ " + why))
        info("修法（任选一条）：")
        info("  ① 给某个候选装依赖：<解释器> -m pip install -r requirements.txt "
             "&& <解释器> -m playwright install chromium")
        info("  ② 显式指定能用的那个：--python \"<解释器路径>\"（或设环境变量 HYBRID_PYTHON）")
        info("  ③ Windows 上若仓库有 venv，直接拿它跑本脚本：<repo>\\.venv\\Scripts\\python.exe …")
        return 2
    print("解释器: %s（来源：%s）" % (" ".join(py), py_src))
    if len(tried) > 1:
        info("候选探测：试了 %d 个、前 %d 个不可用" % (len(tried), len(tried) - 1))
    ok("依赖齐全（dotenv / playwright / pytest）")

    cas = sorted(cassette.glob("*.json"))
    if not cas:
        bad("录像目录里没有录像：%s" % cassette)
        info("把录像包（hybrid_gui_qa_llm_cassettes_*.zip）解开，把里面的 llm_cassettes/ 整个目录")
        info("放到 %s" % (repo / "output"))
        return 2
    ok("录像 %d 份（%s）" % (len(cas), cassette.name))

    alive, detail = health(args.base_url)
    if not alive:
        bad("被测 demo 不可达（%s）：%s" % (args.base_url, detail))
        info("另开一个窗口起 demo：cd %s && python -m demo.app" % repo)
        return 2
    ok("demo 可达：%s" % detail[:80])

    if args.check_deps:
        print("\n结论：前置检查全部通过（解释器 / 代码版本 / 录像 / demo）"
              " ⇒ 去掉 --check-deps 即可正式跑链路")
        return 0

    if not scenarios and not args.scenario_dir:
        scenarios = sorted(str(p.relative_to(repo)) for p in repo.glob("scenarios/*/*.yml"))
        info("没指定场景 ⇒ 默认回放 scenarios/ 下全部 %d 个场景" % len(scenarios))

    # ---------- 二、explore：AI 语义识别（录像回放，不联网）----------
    head("二、explore 语义识别（离线回放；端点已指黑洞 %s）" % BLACKHOLE)
    cmd = [*py, "-m", "framework.cli", "explore", "--ai", "--llm-cassette", str(cassette),
           "--no-verify"]
    if args.scenario_dir:
        cmd += ["--scenario-dir", args.scenario_dir]
    else:
        for s in scenarios:
            cmd += ["--scenario-file", s]
    rc, out = run(cmd, repo)
    tail(out, 14)
    if rc != 0:
        bad("explore 失败（退出码 %s）" % rc)
        info("若报「没有这一份」= 录像与当前 prompt 不匹配：录像键含【场景文案 + 页面 url + 控件骨架】")
        info("⇒ 核对 demo 与框架版本是否与录制时一致；或去有网机器重录：")
        info("   python -m framework.cli explore --ai --scenario-file <场景.yml> --llm-record --no-cases --no-verify")
        return 1
    if "命中录像" not in out and "回放" not in out:
        bad("explore 退出码为 0，但输出里看不到「回放命中」—— 不敢当通过（可能是走了实时调用？）")
        return 1
    ok("回放命中，AI 语义识别完成")

    case = newest_ai_case(repo)
    if case is not None:
        try:
            rec = json.loads(case.read_text(encoding="utf-8"))
            ok("产出用例：cases/%s（llm_source=%s，%d 步）"
               % (case.name, rec.get("llm_source"), len(rec.get("steps") or [])))
        except Exception as e:                 # noqa: BLE001
            info("产出用例 %s（读取失败：%s）" % (case.name, e))

    # ---------- 三、generate：生成可跑的用例脚本 ----------
    head("三、generate 生成用例脚本（普通 generate，不带开关）")
    rc, out = run([*py, "-m", "framework.cli", "generate"], repo)
    tail(out, 8)
    script = repo / "scripts" / "test_cases.py"
    unmapped = script.read_text(encoding="utf-8", errors="replace").count("元素未映射") if script.exists() else -1
    if rc != 0 or unmapped != 0:
        bad("generate 失败（退出码 %s / 未映射 %s）" % (rc, unmapped))
        return 1
    ok("脚本已生成：scripts/test_cases.py（未映射 0）")
    info("新增用例是否进脚本：%s"
         % ("是" if case and case.stem in script.read_text(encoding="utf-8", errors="replace") else "否"))

    # ---------- 四、（可选）run 试跑 ----------
    if args.run and case is not None:
        head("四、run 试跑刚生成的那条用例")
        rc, out = run([*py, "-m", "framework.cli", "run", "--workers", "1", "--case", case.stem], repo)
        tail(out, 8)
        if rc != 0:
            bad("run 失败（退出码 %s）—— 打开 log/<run_id>/<case>.log 与 report.html 看真因" % rc)
            return 1
        ok("用例实测通过")

    print("\n结论：离线链路可用 —— explore（录像回放识别控件）→ generate（生成用例脚本）%s"
          % ("→ run（实测通过）" if args.run else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
