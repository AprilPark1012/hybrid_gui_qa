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
  python tools/pack_release.py                     # 打包（自检不过不出包）
  python tools/pack_release.py --out /tmp/pkg
  python tools/pack_release.py --check <zip>       # 只审计已有包，不打包（可审计历史包）
  python tools/pack_release.py --allow-broken-artifacts   # 调试用逃生口（会大声警告）
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
import zipfile
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from framework.text_io import force_stdio, run_capture      # noqa: E402

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
REQUIRED = ("README.md", "build_html.py", "training.html", "framework/cli.py",
            "framework/text_io.py", "scripts/test_cases.py", "scripts/conftest.py",
            "cases", "tests", "demo", "scenarios")
# 生成物必须带的接线（与 tests/test_artifacts_health.py 同口径）
REQUIRED_CONFTEST = ("_act", "_goto", "_reset_target_data", "_assert_text", "_assert_value")


def _version() -> tuple[str, str]:
    """版本号从 build_html.py 读（**版本单一来源**）；读不到就如实说 unknown。"""
    try:
        src = (REPO / "build_html.py").read_text(encoding="utf-8")
        v = re.search(r'^VERSION\s*=\s*"([^"]+)"', src, re.M)
        d = re.search(r'^VERSION_DATE\s*=\s*"([^"]+)"', src, re.M)
        return (v.group(1) if v else "unknown", d.group(1) if d else date.today().isoformat())
    except Exception:
        return "unknown", date.today().isoformat()


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
              expect_notes: int | None = None) -> list[str]:
    """审计一个包：返回问题清单（空 = 通过）。**只用标准库，不依赖 unzip。**"""
    problems: list[str] = []
    with zipfile.ZipFile(zip_path) as z:
        names = z.namelist()
        rel = {n.split("/", 1)[1]: n for n in names if "/" in n}

        for req in REQUIRED:
            if not any(k == req or k.startswith(req + "/") for k in rel):
                problems.append(f"包内缺必需项：{req}")

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


def main() -> int:
    force_stdio()
    ap = argparse.ArgumentParser(description="交付打包 + 包内自检（只用标准库）")
    ap.add_argument("--out", default=str(REPO / "releases"),
                    help="输出目录（默认 <仓库>/releases —— 交付产物落库到仓库内，不再用 /tmp）")
    ap.add_argument("--check", default=None, help="只审计已有 zip，不打包")
    ap.add_argument("--allow-broken-artifacts", action="store_true",
                    help="调试逃生口：跳过「坏产物」判据（交付永不用）")
    a = ap.parse_args()

    repo_cases = len(list((REPO / "cases").glob("*.json")))
    repo_notes = repo_release_notes()

    if a.check:
        zp = Path(a.check)
        print(f"[pack] 审计 {zp}")
        # 审计历史包时**不**强制「升级日志份数一致」：老包的日志在包根、份数也不同（形态差异不是缺陷）
        problems = check_zip(zp, expect_cases=repo_cases, require_notes_for=_version()[0])
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

    problems = check_zip(out_zip, expect_cases=repo_cases, require_notes_for=ver,
                         expect_notes=len(repo_notes) or None)
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
