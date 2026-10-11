#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""未绑定名扫描（R7-b 判据的静态闸门）—— 零依赖、纯 stdlib、不依赖 demo。

**为什么需要它**（2026-10-10 干净环境 E2E 实录教训）：
`explorer._collect_page_context()` 的单页路径里引用了只在**多页路径**存在的 `page_name`
（S1 收口时把两行拷过去，漏了作用域），Python 只在**跑到那一行**才抛 `NameError`，
而它又被 `except Exception` 兜成「探测失败 → 退化 0 项」——**判据全绿、真跑才红**，
整条单页探测静默失效。这类「拷代码漏作用域」的坑每次都要靠真跑才抓到，代价极高。

本工具把这类错**在静态阶段**钉住：扫出「函数体里引用、但既不是本/外层作用域绑定、
也不是模块级名、也不是内置名」的标识符（等价 pyflakes 的 F821）。

用法：
    python tests/_runner/verify_undefined_names.py [路径 ...]     # 默认 framework/ build_tools/
    python tests/_runner/verify_undefined_names.py --json        # 机器可读
退出码：0 干净 · 1 有未绑定名 · 2 用法/导入错误

**刻意的宽松**（宁漏不误伤，与项目口径一致）：
  · 任意外层作用域绑定即算绑定（不模拟 Python 精确的类作用域规则）；
  · `globals()["X"] = ...` 动态写入的名字进白名单（如 `_CURRENT_SCENARIO`）；
  · 含 `from x import *` 的模块整体跳过（名字不可知）。
"""
from __future__ import annotations

import argparse
import ast
import builtins
import json
import sys
from pathlib import Path

# [!] 统一 UTF-8 stdio（本项目纪律）：本脚本会往控制台打中文，中文 Windows 默认 cp936
#   会在 stdout 是管道时 UnicodeEncodeError 崩掉整个入口。
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from framework.tools.common.text_io import force_stdio      # noqa: E402

force_stdio()

BUILTINS = set(dir(builtins)) | {"__file__", "__name__", "__doc__", "__package__", "__spec__", "__builtins__"}


def _target_names(node, out: set) -> None:
    """把赋值/for/with 的目标里的名字收进 out。"""
    if node is None:
        return
    if isinstance(node, ast.Name):
        out.add(node.id)
    elif isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        for e in node.elts:
            _target_names(e, out)
    elif isinstance(node, ast.Starred):
        _target_names(node.value, out)
    # Attribute / Subscript 目标（obj.attr = ...）不绑定新名字


class _Scope:
    def __init__(self, kind: str, name: str, parent: "_Scope | None"):
        self.kind = kind          # module / function / class / lambda / comprehension
        self.name = name
        self.parent = parent
        self.bound: set[str] = set()
        self.globals: set[str] = set()
        self.uses: list[tuple[str, int]] = []     # (name, lineno)


def _collect_module_binds(tree: ast.Module) -> tuple[set, set, bool]:
    """模块级绑定名 / 动态 globals 白名单 / 是否星号导入。

    [!] 必须**递归进复合语句**（`if __name__ == "__main__":` / try / with / for 内部的赋值同样是
        模块级绑定）—— 否则 `runner.py`、`build_html.py` 的 `__main__` 块会被误报成未绑定名。
        但**不递归进函数/类体**（那是各自的作用域）。
    """
    names: set[str] = set()
    dynamic: set[str] = set()
    star = False

    def _scan_body(body) -> None:
        for node in body:
            _scan_stmt(node)

    def _scan_stmt(node) -> None:
        nonlocal star
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
            return                                   # 不进函数/类体
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if any(a.name == "*" for a in node.names):
                star = True
            for a in node.names:
                if a.name != "*":
                    names.add((a.asname or a.name).split(".")[0])
            return
        if isinstance(node, ast.Assign):
            for t in node.targets:
                _target_names(t, names)
                if isinstance(t, ast.Subscript) and isinstance(t.value, ast.Call) \
                        and isinstance(t.value.func, ast.Name) and t.value.func.id == "globals":
                    sl = t.slice
                    if isinstance(sl, ast.Constant) and isinstance(sl.value, str):
                        dynamic.add(sl.value)
        elif isinstance(node, ast.AnnAssign):
            _target_names(node.target, names)
        elif isinstance(node, ast.AugAssign):
            _target_names(node.target, names)
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            _target_names(node.target, names)
        elif isinstance(node, ast.ExceptHandler):
            if node.name:
                names.add(node.name)
        elif isinstance(node, ast.NamedExpr):
            _target_names(node.target, names)
        elif isinstance(node, ast.comprehension):
            _target_names(node.target, names)
        # 继续往下钻（复合语句的子块；函数/类已在上面 return 掉了）
        for field in ("body", "orelse", "finalbody", "handlers", "items"):
            sub = getattr(node, field, None)
            if isinstance(sub, list):
                _scan_body(sub)
        # 模块级**表达式**里的绑定（推导式目标 `[x for x in ...]` / 海象 `:=`）
        #   —— 漏了它会把 tests 里 `"\\n".join(f"第 {i} 行" for i in range(200))` 这类
        #   当成未绑定名（实测误报 4 处）。宽松处理：整棵子树扫，宁可多绑不误伤。
        for sub in ast.walk(node):
            if isinstance(sub, ast.comprehension):
                _target_names(sub.target, names)
            elif isinstance(sub, ast.NamedExpr):
                _target_names(sub.target, names)
        if isinstance(node, (ast.With, ast.AsyncWith)):
            for it in node.items:
                _target_names(it.optional_vars, names)
        if isinstance(node, ast.Try):
            for h in node.handlers:
                _scan_stmt(h)

    _scan_body(tree.body)
    return names, dynamic, star


class _Walker(ast.NodeVisitor):
    def __init__(self, module_names: set[str], dynamic: set[str]):
        self.module_names = module_names
        self.dynamic = dynamic
        self.findings: list[tuple[int, str, str]] = []   # (line, name, scope 描述)

    # ---- 作用域创建 ----
    def _enter_func(self, node, kind="function"):
        scope = _Scope(kind, getattr(node, "name", "<lambda>"), self.scope)
        if kind == "function":
            a = node.args
            for arg in list(a.posonlyargs) + list(a.args) + list(a.kwonlyargs):
                scope.bound.add(arg.arg)
            if a.vararg:
                scope.bound.add(a.vararg.arg)
            if a.kwarg:
                scope.bound.add(a.kwarg.arg)
        self._walk_body(getattr(node, "body", []), scope, node)

    def _walk_body(self, body, scope, node):
        # 先收集本作用域的绑定（含 global 声明），再查引用 —— 顺序无关，避免「先用后绑」误报
        prev, self.scope = getattr(self, "scope", None), scope
        for stmt in body if isinstance(body, list) else [body]:
            self._bind_stmt(stmt, scope)
        # global/nonlocal 声明
        for sub in ast.walk(node):
            if isinstance(sub, (ast.Global, ast.Nonlocal)):
                scope.globals |= set(sub.names)
        for stmt in (body if isinstance(body, list) else [body]):
            self.visit(stmt)
        self.scope = prev

    def _bind_stmt(self, stmt, scope: _Scope) -> None:
        """收集一个作用域内所有绑定（递归进嵌套语句，但不进嵌套函数/类的内部）。"""
        for node in ast.walk(stmt):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                scope.bound.add(node.name)
            elif isinstance(node, ast.Lambda):
                pass
            elif isinstance(node, ast.Assign):
                for t in node.targets:
                    _target_names(t, scope.bound)
            elif isinstance(node, ast.AnnAssign):
                _target_names(node.target, scope.bound)
            elif isinstance(node, ast.AugAssign):
                _target_names(node.target, scope.bound)
            elif isinstance(node, (ast.For, ast.AsyncFor)):
                _target_names(node.target, scope.bound)
            elif isinstance(node, (ast.With, ast.AsyncWith)):
                for it in node.items:
                    _target_names(it.optional_vars, scope.bound)
            elif isinstance(node, ast.ExceptHandler):
                if node.name:
                    scope.bound.add(node.name)
            elif isinstance(node, ast.NamedExpr):
                _target_names(node.target, scope.bound)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for a in node.names:
                    if a.name != "*":
                        scope.bound.add((a.asname or a.name).split(".")[0])
            elif isinstance(node, ast.comprehension):
                _target_names(node.target, scope.bound)

    # ---- 访问 ----
    def visit_Name(self, node: ast.Name):
        if isinstance(node.ctx, ast.Load):
            self._check(node.id, node.lineno)

    def visit_FunctionDef(self, node):
        self.scope.bound.add(node.name)
        self._enter_func(node)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Lambda(self, node):
        scope = _Scope("lambda", "<lambda>", self.scope)
        a = node.args
        for arg in list(a.posonlyargs) + list(a.args) + list(a.kwonlyargs):
            scope.bound.add(arg.arg)
        if a.vararg:
            scope.bound.add(a.vararg.arg)
        if a.kwarg:
            scope.bound.add(a.kwarg.arg)
        prev, self.scope = self.scope, scope
        self.visit(node.body)
        self.scope = prev

    def visit_ClassDef(self, node):
        self.scope.bound.add(node.name)
        scope = _Scope("class", node.name, self.scope)
        prev, self.scope = self.scope, scope
        for stmt in node.body:
            self._bind_stmt(stmt, scope)
        for stmt in node.body:
            self.visit(stmt)
        self.scope = prev

    def _check(self, name: str, lineno: int) -> None:
        if name in self.dynamic or name in BUILTINS:
            return
        s = getattr(self, "scope", None)
        while s is not None:
            if name in s.bound:
                return
            s = s.parent
        if name in self.module_names:
            return
        where = getattr(self.scope, "name", "<module>") if getattr(self, "scope", None) else "<module>"
        self.findings.append((lineno, name, where))


def scan_file(path: Path) -> tuple[list[tuple[int, str, str]], str | None]:
    try:
        src = path.read_text(encoding="utf-8")
    except Exception as e:                      # 编码异常等 -> 明确报，不静默
        return [], f"读取失败: {e}"
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return [], f"语法错误: {e}"
    module_names, dynamic, star = _collect_module_binds(tree)
    if star:
        return [], "跳过（含 from x import *，名字不可知）"
    w = _Walker(module_names, dynamic)
    w.scope = _Scope("module", "<module>", None)
    w.scope.bound |= module_names
    for stmt in tree.body:
        w.visit(stmt)
    return w.findings, None


def main() -> int:
    ap = argparse.ArgumentParser(description="未绑定名扫描（F821 等价 · 纯 stdlib）")
    ap.add_argument("paths", nargs="*", default=["framework", "build_tools"])
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[2]
    targets: list[Path] = []
    for p in args.paths:
        q = (root / p) if not Path(p).is_absolute() else Path(p)
        if q.is_dir():
            targets += sorted(q.rglob("*.py"))
        elif q.is_file():
            targets.append(q)
        else:
            print(f"[NG] 路径不存在: {p}", file=sys.stderr)
            return 2
    targets = [t for t in targets if "__pycache__" not in t.parts and ".venv" not in t.parts]

    all_findings, skipped = [], []
    for f in targets:
        fnd, err = scan_file(f)
        if err:
            skipped.append((str(f.relative_to(root)), err))
            continue
        for ln, nm, where in fnd:
            try:
                rel = str(f.relative_to(root))
            except ValueError:                      # 仓外路径（自测/临时文件）直接原样
                rel = str(f)
            all_findings.append({"file": rel, "line": ln, "name": nm, "scope": where})

    if args.json:
        print(json.dumps({"files": len(targets), "findings": all_findings, "skipped": skipped},
                         ensure_ascii=False, indent=1))
    else:
        print(f"[scan] {len(targets)} 个文件 · 未绑定名 {len(all_findings)} 处 · 跳过 {len(skipped)} 个")
        for it in all_findings:
            print(f"  [NG] {it['file']}:{it['line']}  `{it['name']}`（在 {it['scope']} 里引用，作用域内无绑定）")
        for f, why in skipped:
            print(f"  [skip] {f} —— {why}")
        if not all_findings:
            print("  [OK] 无未绑定名（这类错一旦发生会被 except 兜成静默降级，故静态钉死）")
    return 1 if all_findings else 0


if __name__ == "__main__":
    sys.exit(main())
