"""判据 5：AST import 目标存在性校验（V8.0 结构重构的防漏判据）。

背景：V8.0 把 17 个业务模块挪进 `framework/tools/<layer>/`（并把仓库根 `tools/` 改名为 `build_tools/`）。
漏改一处 import 不会在语法期报错 —— 往往要走到那个分支才炸（甚至只炸在用户机器上）。
本判据把仓库全部 `.py` 的 import 解析出来，断言「仓库内部模块」在磁盘上**真实存在**，
一次抓出所有漏改；旧路径（`framework.probe` 等）会因文件不存在而被点名。

负向自证（R7 硬要求）：解析器对着一个**不存在**的模块必须报出来 ——
否则这条判据自己就是空判据（「看着在验、其实没验」）。

秒级、不需要 demo / key / 浏览器，可进 CI。

跑法：
    cd ~/hybrid_gui_qa && .venv/bin/python -m pytest frameworkTest/test_import_targets.py -v
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

# 「仓库内部包」的命名空间（只有带 __init__.py 的包才谈得上 import 目标存在性；
# frameworkTest/ featureTest/ scripts/ build_tools/ 都不是包（无 __init__.py），故不列入 —— 避免误报）
INTERNAL_ROOTS = ("framework", "demo")

# 扫描时要跳过的目录（含运行时产物与虚拟环境）
SKIP_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", "log", "output",
             "releases", "node_modules", ".mypy_cache", ".ruff_cache"}


def _iter_py_files(repo: Path):
    """仓库内所有 .py（跳过 SKIP_DIRS 与包外临时目录）。"""
    for p in sorted(repo.rglob("*.py")):
        if any(part in SKIP_DIRS for part in p.relative_to(repo).parts):
            continue
        yield p


def resolve_module(repo: Path, module: str, *, base_dir: Path | None = None) -> Path | None:
    """把模块名（含相对导入用的 base_dir）解析成磁盘文件；不存在返回 None。

    支持三种落点：包（`x/__init__.py`）· 模块（`x.py`）· 相对导入（相对 base_dir 上溯）。
    """
    parts = [p for p in module.split(".") if p]
    if base_dir is None:
        if not parts or parts[0] not in INTERNAL_ROOTS:
            return None                      # 第三方/标准库：不归本判据管
        root = repo
    else:
        root = base_dir                     # 相对导入：从导入方的包目录起算
    if not parts:
        return root / "__init__.py" if (root / "__init__.py").is_file() else None
    pkg = root
    for i, part in enumerate(parts):
        last = i == len(parts) - 1
        if last:
            as_pkg = pkg / part / "__init__.py"
            as_mod = pkg / f"{part}.py"
            return as_pkg if as_pkg.is_file() else (as_mod if as_mod.is_file() else None)
        nxt = pkg / part
        if not (nxt / "__init__.py").is_file():
            return None
        pkg = nxt
    return None


def collect_broken_imports(repo: Path):
    """返回 [(文件, 行号, 语句, 说明)] —— 只含「仓库内部但磁盘上不存在」的 import。"""
    broken = []
    for path in _iter_py_files(repo):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:                       # 语法错就当它自己先炸，别静默放过
            broken.append((path, exc.lineno or 0, "<syntax error>", str(exc)))
            continue
        rel = path.relative_to(repo)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if resolve_module(repo, alias.name) is None and \
                            alias.name.split(".")[0] in INTERNAL_ROOTS:
                        broken.append((path, node.lineno, f"import {alias.name}",
                                       f"目标不存在：{alias.name}"))
            elif isinstance(node, ast.ImportFrom):
                # 相对导入：先按包深度上溯拿到 base_dir
                base_dir = None
                if node.level:
                    pkg_dir = path.parent if path.name == "__init__.py" else path.parent
                    for _ in range(node.level - 1):
                        pkg_dir = pkg_dir.parent
                    base_dir = pkg_dir
                    if node.module:
                        target = resolve_module(repo, node.module, base_dir=base_dir)
                        if target is None:
                            broken.append((path, node.lineno,
                                           f"from {'.' * node.level}{node.module} import ...",
                                           f"目标不存在（相对 {rel.parent}）：{node.module}"))
                        continue
                if not node.module:
                    continue
                target = resolve_module(repo, node.module)
                if target is None and node.module.split(".")[0] in INTERNAL_ROOTS:
                    broken.append((path, node.lineno, f"from {node.module} import ...",
                                   f"目标不存在：{node.module}"))
    return broken


def test_all_internal_imports_resolve_to_real_files():
    """全仓内部 import 的目标文件必须真实存在（旧路径会因文件不存在被点名）。"""
    broken = collect_broken_imports(REPO)
    assert not broken, ("有 import 指向磁盘上不存在的模块（结构重构漏改 / 手滑写错）：\n"
                        + "\n".join(f"  {p.relative_to(REPO)}:{ln}  {stmt}  ⇒ {why}"
                                    for p, ln, stmt, why in broken[:30]))


def test_old_flat_module_paths_are_gone():
    """V8.0 起 `framework/<模块>.py` 平铺路径必须绝迹（旧 import 会被解析器抓住）。"""
    flat = sorted(p.name for p in (REPO / "framework").glob("*.py"))
    assert flat == ["__init__.py", "cli.py"], (
        f"framework/ 下不应再有平铺模块，实际：{flat}（V8.0 起只留 __init__.py + cli.py + tools/）")


def test_resolver_reports_nonexistent_module():
    """负向自证：解析器对不存在的模块必须返回 None（否则这条判据是空判据）。"""
    assert resolve_module(REPO, "framework.probe") is None, \
        "framework.probe 已被 V8.0 废弃 ⇒ 解析器必须判为不存在（若这里通过，说明判据没牙）"
    assert resolve_module(REPO, "framework.tools.probe.probe") is not None, \
        "新路径必须解析得到（否则判据会误报全仓）"
    assert resolve_module(REPO, "requests") is None, "第三方模块不归本判据管（返回 None 表示跳过）"


def test_collect_broken_imports_flags_bogus_import(tmp_path):
    """负向自证 2：造一个假仓库，里面写坏 import ⇒ 采集器必须点名它。"""
    good = tmp_path / "framework" / "tools" / "probe"
    good.mkdir(parents=True)
    for d in (tmp_path / "framework", tmp_path / "framework" / "tools", good):
        (d / "__init__.py").write_text("", encoding="utf-8")
    (good / "probe.py").write_text("def probe_page():\n    return None\n", encoding="utf-8")
    bad = tmp_path / "fake.py"
    # r9-legacy-ok（负向自证：故意写坏的 import 作被测样例，必须保留旧路径形态）
    bad.write_text("from framework.probe import probe_page\n"
                   "from framework.tools.probe.probe import probe_page\n", encoding="utf-8")
    broken = collect_broken_imports(tmp_path)
    assert len(broken) == 1, f"应恰好点名 1 条坏 import，实际 {broken}"
    assert "framework.probe" in broken[0][3]
