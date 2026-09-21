"""离线一条命令：explore 语义识别（录像回放）→ generate 生成用例脚本 [→ run 试跑]。

为什么单独一个脚本：工作电脑连不上外网 LLM，要靠录像包回放才能跑 AI 链路；而「回放」有几个
前置（录像目录 / demo 在跑 / **代码版本配套**），步骤散在 CLI 里容易漏。这里串起来逐条给结论，
并且**强制把 LLM 端点指到黑洞（127.0.0.1:9）**—— 证明这次跑下来真的没联网、也没用 key。

本脚本住在仓库的 `tools/`（框架工具目录，与 pack_release.py / build_html.py 同列）；
**随代码包一起交付**，不需要额外安装（纯标准库）。

用法（Windows / macOS / Linux 通用）：
    python build_tools/offline_explore_chain.py --repo .
    python build_tools/offline_explore_chain.py --repo . --scenario scenarios/contracts/contracts_search_by_no.yml
    python build_tools/offline_explore_chain.py --repo . --scenario scenarios/contracts/contracts_search_by_no.yml --run
    python build_tools/offline_explore_chain.py --repo . --scenario-dir scenarios            # 把所有场景都回放一遍
    python build_tools/offline_explore_chain.py --repo . --scenario <f> --cassette D:\\cassettes   # 录像不在默认位置

退出码：0 = 全通 · 2 = 前置不满足（录像缺 / demo 没起 / 代码版本不含回放）· 1 = 链路某步失败。
"""
import argparse
import json
import os
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


def guess_python(repo):
    """优先用仓库自带的 venv 解释器 —— 依赖（dotenv / playwright / pytest）都装在那儿。

    为什么必须有这一步：用系统 python 跑仓库 CLI 会当场 `ModuleNotFoundError: dotenv`
    （实测：本机 ~/.local/bin/python3.11 就没装项目依赖）—— 那看起来像「框架坏了」，
    其实只是解释器选错了。Windows 的 venv 解释器在 .venv\\Scripts\\python.exe。
    """
    for cand in (repo / ".venv" / "bin" / "python",            # Linux / macOS
                 repo / ".venv" / "Scripts" / "python.exe"):   # Windows
        if cand.exists():
            return str(cand)
    return ""


def deps_ok(py, repo):
    rc, out = run([py, "-c", "import dotenv, playwright, pytest; print('deps-ok')"], repo)
    return (rc == 0 and "deps-ok" in out), (out.strip().splitlines() or [""])[-1]


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

    venv_py = guess_python(repo)
    py = args.python or venv_py or sys.executable
    print("解释器: %s%s" % (py, "（仓库 venv）" if (venv_py and py == venv_py) else ""))
    good, why = deps_ok(py, repo)
    if not good:
        bad("这个解释器缺依赖：%s" % why)
        if venv_py:
            info("用仓库 venv 的：--python \"%s\"" % venv_py)
        else:
            info("仓库里没找到 .venv ⇒ 先建环境并装依赖（uv 口径）：")
            info("   uv venv .venv --python 3.11 && uv pip install -r requirements.txt "
                 "&& python -m playwright install chromium")
        return 2
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

    if not scenarios and not args.scenario_dir:
        scenarios = sorted(str(p.relative_to(repo)) for p in repo.glob("scenarios/*/*.yml"))
        info("没指定场景 ⇒ 默认回放 scenarios/ 下全部 %d 个场景" % len(scenarios))

    # ---------- 二、explore：AI 语义识别（录像回放，不联网）----------
    head("二、explore 语义识别（离线回放；端点已指黑洞 %s）" % BLACKHOLE)
    cmd = [py, "-m", "framework.cli", "explore", "--ai", "--llm-cassette", str(cassette),
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
    rc, out = run([py, "-m", "framework.cli", "generate"], repo)
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
        rc, out = run([py, "-m", "framework.cli", "run", "--workers", "1", "--case", case.stem], repo)
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
