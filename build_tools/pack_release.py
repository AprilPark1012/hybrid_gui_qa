#!/usr/bin/env python3
"""交付打包器（V7.5.1）：组装 zip + **用标准库自检包内产物**，不达标就不出包。

为什么自带自检（2026-09-15 交付事故）：
  V7.5 的包夹带了一份「16 个用例、每步都是 `pytest.fail(元素未映射)` 存根」的
  `scripts/test_cases.py` —— 打包时**没人检查过包内产物**，于是它被交付出去，
  直到AprilPark1012在 Windows 上跑慢目标闸门才炸成 50 条失败（真因已无处可查）。
  更糟的是当时那次「检查」还是**假绿**：本机没装 `unzip`，`unzip -p … | grep -c` 收到空输入
  ⇒ 数到 0 命中 ⇒ 被当成「包是干净的」。
  ⇒ 铁律：**自检只用标准库（zipfile / hashlib），绝不依赖外部解压命令**；判据不过就非 0 退出、不留半成品包。

用法：
  python build_tools/pack_release.py                     # 打包（自检不过不出包）
  python build_tools/pack_release.py --out /tmp/pkg
  python build_tools/pack_release.py --check <zip>       # 只审计已有包，不打包（可审计历史包）
  python build_tools/pack_release.py --allow-broken-artifacts   # 调试用逃生口（会大声警告）
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import zipfile
from datetime import date, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from framework.tools.common import config
from framework.tools.common.text_io import force_stdio, run_capture      # noqa: E402

# 不进包的东西（与 .gitignore 口径一致 + 交付无关产物）
EXCLUDE_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", "log", "output",
                "dist", "build", ".idea", ".vscode", "node_modules"}
# ⚠️ releases/ **不能**整体排除（2026-09-18 口径）：升级日志 RELEASE_NOTES_*.md 落在 releases/ 下，
#    而它们是交付物的一部分，**必须进包**（AprilPark1012 明确要求「打压缩包时要带上这些升级日志文件」）。
#    这里只放行升级日志；同目录下的交付包本体（zip/tar.gz）、records/ 内部记录、SHA256SUMS.txt
#    一律不进包 —— 见 _is_release_note()。
RELEASES_DIRNAME = "releases"
RELEASE_NOTES_GLOB = "RELEASE_NOTES_*.md"
EXCLUDE_SUFFIX = {".zip", ".tar.gz", ".pyc", ".pyo"}
# 包里必须有的东西（少一个说明包不完整）
REQUIRED = ("README.md", "build_tools/build_html.py", "docs/training.html", "framework/cli.py",
            "framework/tools/common/text_io.py", "scripts/test_cases.py", "scripts/conftest.py",
            "cases", "frameworkTest", "featureTest", "demo", "scenarios")
# r9-legacy-block:begin —— 历史形态别名：审计**旧包**时按当时的路径形态认（有意保留旧路径）
# 历史形态别名（2026-09-19）：**结构与文件位置变过，审计历史包不该因此误报**。
# 先例：升级日志本来就「两种落点都认」（见下面 notes 那段）。这里收纳两次结构调整：
#   build_html.py → tools/build_html.py      （2026-09-19：从仓库根挪进开发工具目录）
#                    → build_tools/build_html.py （V8.0 结构重构：开发期工具统一进 build_tools/）
#   framework/<模块>.py → framework/tools/<层>/<模块>.py （V8.0 业务流程分层重构）
#   training.html → docs/training.html    （2026-09-19 归位 docs/）
# ⚠️ 只影响**必需项审计**：新包一定按当前仓库布局打包 ⇒「两个位置都没有」时照样报缺项，
#    别名绝不会放过真缺项（负向判据见 frameworkTest/test_pack_release.py）。
LEGACY_ALIASES = {
    # 键 = 当前 REQUIRED 路径；值 = 历史形态候选（结构变更前的包里可能是这些）
    "build_tools/build_html.py": ("tools/build_html.py", "build_html.py"),
    "framework/tools/common/text_io.py": ("framework/text_io.py",),
    "docs/training.html": ("training.html",),
    #   tests/ → frameworkTest/ + featureTest/   （2026-09-23：R7 两类验证分目录）
    "frameworkTest": ("tests",),
    "featureTest": ("tests",),
}
# r9-legacy-block:end


def _required_hit(req: str, rel) -> tuple[bool, str | None]:
    """→ (是否命中, 历史形态说明或 None)。"""
    if any(k == req or k.startswith(req + "/") for k in rel):
        return True, None
    for alt in LEGACY_ALIASES.get(req, ()):
        if any(k == alt or k.startswith(alt + "/") for k in rel):
            return True, f"{req} 用历史形态 {alt} 命中（结构变更前的包，不拦）"
    return False, None


# 生成物必须带的接线（与 frameworkTest/test_artifacts_health.py 同口径）
REQUIRED_CONFTEST = ("_act", "_goto", "_reset_target_data", "_assert_text", "_assert_value")


def _version() -> tuple[str, str]:
    """版本号从 `build_tools/build_html.py` 读（**版本单一来源**，路径定义在 framework/tools/common/config.py）；读不到就如实说 unknown。"""
    v, d = config.read_version()
    return (v, d or date.today().isoformat())


def collect_files(exclude_test_artifacts: bool = False) -> list[Path]:
    """收集要进包的文件：优先 git（**已跟踪 + 未跟踪但不被忽略**，否则新写的 RELEASE_NOTES 会漏掉），
    退化到遍历。"""
    files: list[Path] = []
    try:                       # ⚠️ git 不在 PATH 时要能退化，不能抛（Windows/受限环境实测踩到）
        r = run_capture(["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                        cwd=str(REPO))
    except Exception:
        r = None
    if r is not None and r.returncode == 0 and r.stdout.strip():
        for line in r.stdout.splitlines():
            p = REPO / line.strip()
            if p.is_file():
                files.append(p)
    else:
        for p in REPO.rglob("*"):
            if not p.is_file():
                continue
            if any(part in EXCLUDE_DIRS for part in p.relative_to(REPO).parts):
                continue
            files.append(p)
    out = []
    for p in files:
        rel = p.relative_to(REPO)
        if any(part in EXCLUDE_DIRS for part in rel.parts):
            continue
        if rel.parts and rel.parts[0] == RELEASES_DIRNAME and not _is_release_note(rel):
            continue                      # releases/ 下**只**放行升级日志
        if p.suffix in EXCLUDE_SUFFIX or p.name.endswith(".tar.gz"):
            continue
        out.append(p)
    return sorted(set(out))


def _is_release_note(rel: Path) -> bool:
    """是不是「升级日志」（releases/RELEASE_NOTES_*.md）—— 唯一允许进包的 releases/ 内容。

    判据用**文件名前缀**而不是完整路径：交付包内一律放在 `<tag>/releases/…`，
    而历史包（≤V7.6）的升级日志在包根 ⇒ 两种形态都得知得出来。
    """
    return (len(rel.parts) == 2 and rel.parts[0] == RELEASES_DIRNAME
            and rel.name.startswith("RELEASE_NOTES"))


def repo_release_notes() -> list[str]:
    """仓库 releases/ 下的升级日志清单（打包时用来核对「历史日志有没有全带上」）。"""
    d = REPO / RELEASES_DIRNAME
    return sorted(p.name for p in d.glob(RELEASE_NOTES_GLOB)) if d.is_dir() else []


def check_zip(zip_path: Path, expect_cases: int | None = None,
              require_notes_for: str | None = None,
              expect_notes: int | None = None,
              legacy_notes: list[str] | None = None) -> list[str]:
    """审计一个包：返回问题清单（空 = 通过）。**只用标准库，不依赖 unzip。**

    `legacy_notes`：可选的出参列表 —— 历史形态命中（结构变更前的包）会写进来，
    由调用方打印**不拦**。不传也照样审计，只是看不到那些提示。
    """
    problems: list[str] = []
    with zipfile.ZipFile(zip_path) as z:
        names = z.namelist()
        rel = {n.split("/", 1)[1]: n for n in names if "/" in n}

        for req in REQUIRED:
            ok, note = _required_hit(req, rel)
            if not ok:
                problems.append(f"包内缺必需项：{req}")
            elif note and legacy_notes is not None:
                legacy_notes.append(note)

        def read(key: str) -> str:
            n = rel.get(key)
            return z.read(n).decode("utf-8", "replace") if n else ""

        tc = read("scripts/test_cases.py")
        if tc:
            n = tc.count("元素未映射")
            if n:
                problems.append(f"scripts/test_cases.py 含 {n} 处「元素未映射」存根 "
                                f"（探测失败时落盘的垃圾产物，正是 V7.5 交付事故本体）")
            if "_goto(" not in tc:
                problems.append("scripts/test_cases.py 没走就绪契约 _goto（F1）")
            if "page.goto(" in tc:
                problems.append("scripts/test_cases.py 里有裸 page.goto（绕过就绪契约）")
        cf = read("scripts/conftest.py")
        if cf:
            miss = [f"def {n}" for n in REQUIRED_CONFTEST if f"def {n}" not in cf]
            if miss:
                problems.append(f"scripts/conftest.py 缺接线：{miss}")

        n_cases = sum(1 for k in rel if k.startswith("cases/") and k.endswith(".json"))
        if expect_cases is not None and n_cases != expect_cases:
            problems.append(f"cases/*.json 数量 {n_cases} ≠ 仓库的 {expect_cases}")
        if n_cases == 0:
            problems.append("包内没有任何 cases/*.json")

        bad = [k for k in rel if k.startswith(("output/", "log/", ".venv/"))
               or k.endswith(".env") or "__pycache__" in k]
        if bad:
            problems.append(f"包内含不该发的内容：{bad[:5]}{' …' if len(bad) > 5 else ''}")

        # 升级日志：按**文件名**判断（2026-09-18 起它们落在 releases/ 下；历史包在包根 ⇒ 两种都认）
        notes = {k.rsplit("/", 1)[-1] for k in rel
                 if k.rsplit("/", 1)[-1].startswith("RELEASE_NOTES")}
        if not notes:
            problems.append("包内没有 RELEASE_NOTES_*.md（升级日志是交付物的一部分）")
        else:
            if require_notes_for and require_notes_for != "unknown":
                want = f"RELEASE_NOTES_V{require_notes_for}.md"
                if want not in notes:
                    problems.append(f"包内没有本次版本的 {want}（版本号改了但发版说明没写）")
            if expect_notes is not None and len(notes) < expect_notes:
                problems.append(f"包内升级日志只有 {len(notes)} 份，仓库里 {expect_notes} 份"
                                f"（历史升级日志要一并带上）")
    return problems


# ---------- LLM 录像包：交付「两件套」的第二件（给连不上外网 LLM 的机器）----------
# 2026-09-19 收编：原先它住在 ~/deliver_scripts/pack_cassettes.py（一个仓库外的独立脚本），
# 结果是「录像包」这条交付形态没有任何判据、路径也容易漂（旧脚本里就残留着 build_html.py 的老路径）。
# 现在与代码包同一个打包器管：代码包**不含**录像（output/ 永不进包），录像单独一件。
CASSETTE_SRC = REPO / "output" / "llm_cassettes"
CASSETTE_HELPER = REPO / "build_tools" / "offline_explore_chain.py"
CASSETTE_SCENARIO_DIR = REPO / "scenarios"
CASSETTE_CHECK = REPO / "build_tools" / "check_cassettes.py"


def cassette_coverage_problems(scenario_dir: Path | None = None,
                               cassette_dir: Path | None = None) -> list[str]:
    """录像包**出厂前体检**：`scenarios/` 下每个场景都要有可用录像 ⇒ 返回问题清单（空 = 通过）。

    ★ 为什么必须拦（2026-09-22 实测）：录像包曾经「发出去之后才发现 5 个场景里只有 1 个有可用录像」
    —— 包看着有内容（6 份录像），实际对另外 4 个场景毫无用处；无网机器上那些场景**直接跑不了**。
    打包环节以前**没有任何检查**会告诉你这件事。

    口径不重写一遍：subprocess 调 `build_tools/check_cassettes.py`（同一份体检口径；显式 UTF-8，
    中文路径 / 中文 Windows 下都不依赖 locale）。
    """
    if not CASSETTE_CHECK.exists():
        return [f"体检脚本不在（{CASSETTE_CHECK}）⇒ 先解决它再打包，不许「没体检就出厂」"]
    cmd = [sys.executable, str(CASSETTE_CHECK)]
    if scenario_dir is not None:
        cmd += ["--scenario-dir", str(scenario_dir)]
    if cassette_dir is not None:
        cmd += ["--dir", str(cassette_dir)]
    p = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=300)
    if p.returncode == 0:
        return []
    out = (p.stdout or "") + "\n" + (p.stderr or "")
    if p.returncode == 1:                       # 1 = 有场景缺可用录像（体检的正式判定）
        lines = [ln.strip() for ln in out.splitlines()
                 if ln.strip().startswith("❌") or "缺录像" in ln]
        return lines or ["体检报「有场景缺录像」，但没解析出逐条明细（见上面的体检输出）"]
    hint = {2: "用法问题（体检脚本的参数被改坏了？）",
            3: "环境问题（没有录像目录 / 没有场景文件 ⇒ 根本没法判定覆盖）"}.get(
                p.returncode, f"体检自身退出码 {p.returncode}")
    return [f"体检没跑成：{hint}"]

CASSETTE_README = """# hybrid_gui_qa · LLM 录像包（在**连不上外网**的机器上跑 explore 用）

生成时间：{ts} · 录像份数：{n} · 对应框架版本：V{ver}

## 这是什么
`explore --ai` 每次问 LLM 的「prompt → 回答」原件。带上它们，**没有外网**的机器（工作电脑）
也能跑**完整**的 AI 链路：`explore` 语义识别 → `generate` 生成用例脚本 → `run` 实测，
而且**不需要 API key、全程不联网**。

## 交付形态 = 两件套（都用上才完整）
1. **代码包** `hybrid_gui_qa_V<版本>_<日期>.zip` —— 含回放引擎 `framework/tools/explore/llm_cassette.py`
   与一键脚本 `build_tools/offline_explore_chain.py`
2. **本录像包** —— 含录像数据 `llm_cassettes/` + 一份用法说明

## 最快上手（一条命令，含前置体检）
1. 解开**代码包**，把本包里的 `llm_cassettes/` 整个目录放到仓库根的 `output/` 下
   （`output/` 已在 .gitignore，不会被提交）
2. 起被测 demo：`python -m demo.app`
3. 跑：
   ```
   python build_tools/offline_explore_chain.py --repo . --run
   ```
   它依次做：① 前置体检（代码是否含回放 / 录像份数 / demo 是否可达 / 依赖是否齐）
   ② `explore --ai --llm-cassette` 回放识别控件 ③ `generate`（要求未映射 0）
   ④ （`--run`）实测跑一遍刚生成的用例。**全程把 LLM 端点指到黑洞 127.0.0.1:9**
   ⇒「有没有偷偷联网」这件事是可证伪的。
   只跑指定场景：`--scenario scenarios/contracts/contracts_search_by_no.yml`

## 手动跑（不想用脚本时）
```
python -m framework.cli explore --ai --scenario-file scenarios/contracts/contracts_search_by_no.yml --llm-cassette
python -m framework.cli generate
python -m framework.cli run --workers 1
```

## 三条铁律（不满足会「跑不起来」，报错会告诉你差在哪）
1. **代码必须是含回放功能的版本**（CLI 里有 `--llm-cassette`；V7.7 起）。老版本会 exit 2 ——
   录像包单独放进去没用，它只是「LLM 的回答」，**功能在代码里**。
2. **demo 与场景文件必须与录制时同版本**。回放键包含：场景文案 · 页面清单（页名 + url，含端口）·
   每个控件的骨架（semantic_name / role / name / label / placeholder / test_id / opens_new_tab / page）。
   ⇒ 改过 demo 页面、场景文案、端口，或升级了改动**命名逻辑**的框架版本，都会不命中。
3. **数据值不同没关系，结构必须一致**。回放先试严格键、再用结构键兜底；命中结构键时**大声告警**
   （步骤是录制当时针对那批数据做的判断，请核对再用）。只认逐字一致时加 `--llm-cassette-strict`。

## 怎么确认「这次 AI 判断是回放来的」
- CLI 会打印 `LLM 模式：离线回放（非实时 AI）`
- 产出的用例 json 里带 `llm_source: cassette:<键>`

## 重录（在有外网的机器上）
```
python -m framework.cli explore --ai --scenario-file <场景.yml> --llm-record --no-cases --no-verify
python -m framework.cli explore --ai --scenario-dir scenarios/ --llm-record --no-cases --no-verify
```
改 demo 页面 / 场景文案 / 命名逻辑后**必须重录并重打本包**。

## 包内清单
- `build_tools/offline_explore_chain.py` · 一条命令跑通「回放 → generate → run」+ 前置体检
- `llm_cassettes_README.md` · 本文件
- 录像 {n} 份（场景 → 键 → 录制时间 → 大小）：
{listing}
"""


def pack_cassettes(out_dir: Path, ver: str, *, allow_missing: bool = False,
                   scenario_dir: Path | None = None,
                   cassette_src: Path | None = None) -> Path | None:
    """打**独立**录像包（代码包保持干净、不夹带运行时数据）→ 路径；无录像 / 体检不过则 None。

    ★ 出厂闸门（2026-09-22）：打包**前**强制体检「scenarios/ 里每个场景都有可用录像」，
    不通过就**不产包**（返回 None ⇒ main 里 return 2）。实测教训：录像包曾「发出去之后才发现
    5 个场景只有 1 个有可用录像」，那种包在无网机器上等于废包。
    `allow_missing` = 显式调试逃生口（问题照样打出来，只降噪不掩盖）。
    `scenario_dir` / `cassette_src` 只为判据可注入（默认走仓库真实路径）。
    """
    src = Path(cassette_src) if cassette_src else CASSETTE_SRC
    files = sorted(src.glob("*.json"))
    if not files:
        print(f"[pack] ❌ --with-cassettes：录像目录为空（{src}）"
              f" ⇒ 先在**有外网**的机器上 `--llm-record` 录一份")
        return None

    problems = cassette_coverage_problems(scenario_dir, src)
    if problems:
        if not allow_missing:
            print(f"[pack] ❌ 录像包体检不过（{len(problems)} 项）⇒ **不产包**"
                  f"（无网机器上这些场景会直接跑不了）：")
            for x in problems[:10]:
                print(f"       - {x}")
            print("[pack]    修法：python build_tools/record_cassettes.py --missing-only"
                  "（需 key + 外网；录完再跑 build_tools/check_cassettes.py 复检）")
            print("[pack]    调试逃生口（**交付永不用**）：--allow-missing-cassettes")
            return None
        print("[pack] ⚠️⚠️ --allow-missing-cassettes 生效：体检问题只警告不拦（**永不允许用于交付**）")
        for x in problems[:10]:
            print(f"       - {x}")

    zp = out_dir / f"hybrid_gui_qa_llm_cassettes_{date.today().strftime('%Y%m%d')}.zip"
    rows, total = [], 0
    for f in files:
        rec = {}
        try:
            rec = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            pass
        kinds = ",".join(sorted({r.get("kind", "?") for r in (rec.get("responses") or [])}))
        size = f.stat().st_size
        total += size
        rows.append(f"- `{f.name}` · 录制于 {rec.get('created_at', '?')} · 模型 "
                    f"{rec.get('model', '?')} · 回答 {kinds or '?'} · {size} B")
    readme = (CASSETTE_README.replace("{ts}", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
              .replace("{n}", str(len(files))).replace("{listing}", "\n".join(rows))
              .replace("{ver}", ver))
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            z.write(f, f"llm_cassettes/{f.name}")
        z.writestr("llm_cassettes_README.md", readme)
        if CASSETTE_HELPER.exists():
            z.write(CASSETTE_HELPER, f"build_tools/{CASSETTE_HELPER.name}")
    with zipfile.ZipFile(zp) as z:            # 自检：别把「打出来是坏的」发出去
        broken = z.testzip()
        n_json = sum(1 for n in z.namelist() if n.endswith(".json"))
    if broken or n_json != len(files):
        zp.unlink(missing_ok=True)
        print(f"[pack] ❌ 录像包自检失败 ⇒ 已删除，不交付（坏条目={broken} · 录像数 {n_json}≠{len(files)}）")
        return None
    print(f"[pack] ✅ 录像包：{zp.name}（录像 {len(files)} 份 · 原始 {total} B · "
          f"zip {zp.stat().st_size} B · 含一键脚本 {CASSETTE_HELPER.exists()}）")
    print(f"[pack]    sha256 {hashlib.sha256(zp.read_bytes()).hexdigest()}")
    return zp


def refresh_sums(out_dir: Path) -> None:
    """重写 SHA256SUMS.txt 的**有效行** = 本目录现存 *.zip（`#` 注释台账原样保留）。

    为什么自动做：清单与包必须**永远一致**，手抄 sha256 是典型错误源（抄错 / 漏改 / 忘删）。
    """
    sums = out_dir / "SHA256SUMS.txt"
    old = sums.read_text(encoding="utf-8").splitlines() if sums.exists() else []
    keep = [l for l in old if l.startswith("#") or not l.strip()]
    before = {l.split(None, 1)[1].strip() for l in old if l.strip() and not l.startswith("#")}
    zips = sorted(out_dir.glob("*.zip"))
    lines = [f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}" for p in zips]
    after = {p.name for p in zips}
    sums.write_text("\n".join(keep + lines) + "\n", encoding="utf-8")
    note = []
    if after - before:
        note.append(f"新增 {sorted(after - before)}")
    if before - after:
        note.append(f"移除 {sorted(before - after)}（已不在目录里）")
    print(f"[pack] SHA256SUMS.txt 已同步：现存 {len(zips)} 个包" + (" · " + " · ".join(note) if note else ""))


def main() -> int:
    force_stdio()
    ap = argparse.ArgumentParser(description="交付打包 + 包内自检（只用标准库）")
    ap.add_argument("--out", default=str(REPO / "releases"),
                    help="输出目录（默认 <仓库>/releases —— 交付产物落库到仓库内，不再用 /tmp）")
    ap.add_argument("--check", default=None, help="只审计已有 zip，不打包")
    ap.add_argument("--allow-broken-artifacts", action="store_true",
                    help="调试逃生口：跳过「坏产物」判据（交付永不用）")
    ap.add_argument("--with-cassettes", action="store_true",
                    help="同时打**独立的 LLM 录像包**（给连不上外网 LLM 的机器；"
                         "交付形态 = 代码包 + 录像包「两件套」）；"
                         "★ 打包前强制体检「每个场景都有可用录像」，不过就不产包")
    ap.add_argument("--allow-missing-cassettes", action="store_true",
                    help="调试逃生口：录像体检不过也照打录像包（**交付永不用**；"
                         "正常情形请先跑 record_cassettes.py --missing-only 补齐再打）")
    a = ap.parse_args()

    repo_cases = len(list((REPO / "cases").glob("*.json")))
    repo_notes = repo_release_notes()

    if a.check:
        zp = Path(a.check)
        print(f"[pack] 审计 {zp}")
        # 审计历史包时**不**强制「升级日志份数一致」：老包的日志在包根、份数也不同（形态差异不是缺陷）
        legacy: list[str] = []
        problems = check_zip(zp, expect_cases=repo_cases, require_notes_for=_version()[0],
                             legacy_notes=legacy)
        for n in legacy:
            print(f"[pack] ◐ {n}")
        if problems:
            print(f"[pack] ❌ 发现 {len(problems)} 个问题：")
            for p in problems:
                print(f"       - {p}")
            return 2
        print("[pack] ✅ 包内产物自检通过")
        return 0

    ver, vdate = _version()
    out_dir = Path(a.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    tag = f"hybrid_gui_qa_V{ver}_{vdate.replace('-', '')}"
    out_zip = out_dir / f"{tag}.zip"

    files = collect_files()
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files:
            z.write(p, arcname=f"{tag}/{p.relative_to(REPO).as_posix()}")
    print(f"[pack] 已写出 {out_zip}（{len(files)} 个文件，{out_zip.stat().st_size / 1024:.0f} KB）")

    legacy: list[str] = []
    problems = check_zip(out_zip, expect_cases=repo_cases, require_notes_for=ver,
                         expect_notes=len(repo_notes) or None, legacy_notes=legacy)
    for n in legacy:          # 新包不该出现（出现=打包收集漏了当前布局）⇒ 大声打出来
        print(f"[pack] ⚠️ {n}")
    if a.allow_broken_artifacts:
        # 逃生口只降噪，不掩盖：问题照样打出来
        print("[pack] ⚠️⚠️ --allow-broken-artifacts 生效：问题只警告不拦（**永不允许用于交付**）")
        for p in problems:
            print(f"       - {p}")
        problems = [p for p in problems if "元素未映射" not in p]
    if problems:
        out_zip.unlink(missing_ok=True)          # 不留半成品包
        print(f"[pack] ❌ 包内自检不过（{len(problems)} 项）→ 已删除该 zip，不产出交付物：")
        for p in problems:
            print(f"       - {p}")
        print("[pack]    多半是「目标没起就 generate」：先起 `python -m demo.app` 再 "
              "`python -m framework.cli generate`，然后重新打包。")
        return 2

    sha = hashlib.sha256(out_zip.read_bytes()).hexdigest()
    print(f"[pack] ✅ 包内自检通过（cases={repo_cases} · 升级日志 {len(repo_notes)} 份 · "
          f"未映射=0 · _goto 接线在 · 无 output/log/.env）")
    print(f"[pack] sha256 {sha}")

    if a.with_cassettes:
        if pack_cassettes(out_dir, ver, allow_missing=a.allow_missing_cassettes) is None:
            return 2                       # 显式要了却打不出来 / 体检不过 ⇒ 别当成功
    refresh_sums(out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
