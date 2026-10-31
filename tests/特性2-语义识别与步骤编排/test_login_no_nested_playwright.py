# -*- coding: utf-8 -*-
"""登录链路不许在 Playwright Sync API 里嵌套开 Playwright / 嵌套跑 asyncio（V8.7.28）。

真实现场（2026-10-30 实测取证，Linux + Python 3.11）
--------------------------------------------------
清空 output/ 后首次跑 `scan_pages`，登录前置报：

    [key] 登录前置：[!] 失败 -> Error: It looks like you are using Playwright Sync API
          inside the asyncio loop. Please use the Async API instead.

而 `scan_pages` 的结构是「**先开 ctx，再登录**」：

    with sync_playwright() as p:
        b = p.chromium.launch(...); ctx = b.new_context()
        ensure_logged_in(ctx, ...)        # -> login_on_page -> plan_login -> _probe_login_page
                                          #    -> 里面又 `with sync_playwright()` ← 嵌套，必炸
                                          #    -> 里面又 asyncio.run(...)       ← 也炸

失败姿态极差：登录前置失败后**探测照常进行**，7 个页全部被 demo 重定向成
`login.html?next=...`，`probe_row_fields` 每页都探到登录页 login-accounts 的 3 条
空 field 列（角色/账号/密码），并被打上「发票列表页」等业务页名 —— 脏数据一路喂给 AI，
AI 只能猜列名（V8.7.24/26 的按页校验因此全部落空）。

Windows 上不炸，所以这个坑长期没暴露；Linux 上必炸。

判据口径
--------
1. `_probe_login_page` 必须**接受 ctx 并优先复用**（存在 `if ctx is not None` 分支）；
2. `plan_login` 必须把 ctx 透传下去（签名有 ctx + 调用点传 ctx=ctx）；
3. `login_on_page` 必须从 `page.context` 取 ctx 往下传；
4. 模块内**不许有裸的 `asyncio.run` 调用**（只允许出现在 `run_async_isolated` 内部）；
   全仓静态扫描用 AST，不扫文本（docstring 里常写着坏模式原文）。
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MOD = ROOT / "framework" / "features" / "f02_semantic" / "login_flow_explore.py"


def _src() -> str:
    assert MOD.is_file(), f"找不到 {MOD}"
    return MOD.read_text(encoding="utf-8")


def _tree() -> ast.Module:
    return ast.parse(_src())


def _func_node(name: str) -> ast.FunctionDef:
    for node in ast.walk(_tree()):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"模块里找不到函数 {name}")


# ---------------------------------------------------------------- 1) 签名必须带 ctx
def test_probe_login_page_takes_ctx():
    fn = _func_node("_probe_login_page")
    args = [a.arg for a in fn.args.args] + [a.arg for a in fn.args.kwonlyargs]
    assert "ctx" in args, (
        "`_probe_login_page` 必须接受 ctx 参数。"
        "否则它只能自己 `with sync_playwright()` —— 而真实调用方 `scan_pages` 已经开好了 ctx，"
        "嵌套必抛 `It looks like you are using Playwright Sync API inside the asyncio loop.`")


def test_plan_login_takes_ctx():
    fn = _func_node("plan_login")
    args = [a.arg for a in fn.args.args] + [a.arg for a in fn.args.kwonlyargs]
    assert "ctx" in args, "`plan_login` 必须接受 ctx 并透传给 `_probe_login_page`"


# ---------------------------------------------------------------- 2) 必须真的复用，不只是收下
def test_probe_login_page_reuses_ctx_when_given():
    fn = _func_node("_probe_login_page")
    body = ast.get_source_segment(_src(), fn) or ""
    assert "if ctx is not None" in body, (
        "`_probe_login_page` 收了 ctx 却没有 `if ctx is not None` 分支 —— "
        "收了不用等于没修（接线判据：光有参数不够，必须真走到复用那条路）")
    assert "ctx.new_page()" in body, "复用分支必须用调用方的 ctx 开页（不许另起浏览器）"


def test_plan_login_passes_ctx_down():
    fn = _func_node("plan_login")
    body = ast.get_source_segment(_src(), fn) or ""
    assert "_probe_login_page(url, ctx=ctx)" in body, (
        "`plan_login` 必须把 ctx 传给 `_probe_login_page`（否则复用分支永远走不到）")


def test_login_on_page_passes_page_context():
    fn = _func_node("login_on_page")
    body = ast.get_source_segment(_src(), fn) or ""
    assert 'ctx=getattr(page, "context", None)' in body, (
        "`login_on_page` 必须从 page 取 context 往下传 —— "
        "它由 `ensure_logged_in` 调用，手里的 page 就是那个已开好的 ctx 里的页")


# ---------------------------------------------------------------- 3) 不许有裸 asyncio.run（AST）
def test_no_bare_asyncio_run_outside_helper():
    """模块内 `asyncio.run(...)` 只允许出现在 `run_async_isolated` 内部。"""
    names = {n.name for n in ast.walk(_tree()) if isinstance(n, ast.FunctionDef)}
    assert "run_async_isolated" in names, "必须存在 `run_async_isolated`（把 asyncio.run 挪进独立线程）"
    helper = _func_node("run_async_isolated")
    helper_lo, helper_hi = helper.lineno, (helper.end_lineno or helper.lineno)
    helper_src = ast.get_source_segment(_src(), helper) or ""
    assert "asyncio.run(" in helper_src, "`run_async_isolated` 内部应真正调用 asyncio.run"

    offenders: list[int] = []
    for node in ast.walk(_tree()):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        if isinstance(f, ast.Attribute) and f.attr == "run" and isinstance(f.value, ast.Name) \
                and f.value.id == "asyncio":
            if helper_lo <= node.lineno <= helper_hi:
                continue          # helper 内部那一处是**正确**写法
            offenders.append(node.lineno)
    assert not offenders, (
        f"`run_async_isolated` 之外仍有裸 asyncio.run 调用（行号 {offenders}）—— "
        "Playwright Sync API 与 asyncio event loop 互斥，必须走 run_async_isolated（独立线程）")


def test_plan_login_call_site_uses_isolated_runner():
    body = ast.get_source_segment(_src(), _func_node("plan_login")) or ""
    assert "run_async_isolated(" in body, (
        "`plan_login` 必须用 `run_async_isolated(...)` 而不是直接 asyncio.run(...)")
    # 反向：真实调用点（不是 docstring）里不许再出现 asyncio.run(
    for line in body.splitlines():
        s = line.strip()
        if s.startswith("#"):
            continue
        assert "asyncio.run(" not in s, f"调用点仍有裸 asyncio.run: {line!r}"


# ---------------------------------------------------------------- 4) 行为：独立线程绕过 loop 限制
def test_run_async_isolated_works_inside_event_loop():
    """在有 asyncio loop 的线程里调用也必须成功（这正是它存在的理由）。"""
    import asyncio

    from framework.features.f02_semantic.login_flow_explore import run_async_isolated

    async def _coro():
        await asyncio.sleep(0)
        return "ok"

    async def _driver():
        # 当前线程已经有 loop —— 直接 asyncio.run 会 RuntimeError，run_async_isolated 必须仍可工作
        return run_async_isolated(_coro)

    assert asyncio.run(_driver()) == "ok"


def test_run_async_isolated_propagates_exception():
    from framework.features.f02_semantic.login_flow_explore import run_async_isolated

    async def _boom():
        raise ValueError("故意炸")

    with pytest.raises(ValueError, match="故意炸"):
        run_async_isolated(_boom)


def test_run_async_isolated_never_returns_none_silently():
    """线程既没异常也没值时必须报错，不许静默返回 None（那会让上层拿到 None 继续跑）。"""
    from framework.features.f02_semantic import login_flow_explore as M

    orig = M.threading.Thread

    class _DeadThread:
        def __init__(self, *a, **k):
            self.daemon = True

        def start(self):          # 不真正执行 target
            return None

        def join(self, *a, **k):
            return None

    M.threading.Thread = _DeadThread
    try:
        with pytest.raises(RuntimeError, match="没有返回结果"):
            M.run_async_isolated(lambda: None)
    finally:
        M.threading.Thread = orig
