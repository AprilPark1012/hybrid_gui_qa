# -*- coding: utf-8 -*-
"""弹窗探测不许把「探测所在的页面」带跑（V8.7.30）。

真实现场（2026-10-31 实测取证）
------------------------------
`_try_collect_modal_items` 的候选按钮名单是：

    _MODAL_BUTTON_HINTS = ("新建", "添加", "新增", "创建", "登记", "打开")

它**假设「新建/创建」类按钮都会开弹窗**。但「创建」有两种行为：

    · 弹窗型：弹个层，填完提交          <- 本函数要处理的
    · 导航型：整页跳到另一个页面         <- 发票列表页的「创建」就是这种

点了导航型按钮，**探测所在的页面本身就被带跑了**，实测：

    [scan_page] 发票列表页   前=invoice_list.html   后=invoice_create.html?token=...   <<<< URL 变了

于是紧跟着的 `probe_row_fields(pg)` 打在**开票页**上 —— 发票列表那条真表
（单独访问该页实测 11 列）**一条都探不到**。而 AI 拿不到列名就只能猜
（猜成「订单名称」这种表头文案），运行时必然找不到 -> 断言失败。

判据口径
--------
1. 点开候选按钮**之前**必须记下 URL；
2. 点完**之后**必须比较 URL —— 变了就是导航，必须 `return []` 且**退回原页**；
3. 退回原页要 `go_back`，失败时 `goto(原 URL)` 兜底（两条腿都要，不能只依赖浏览器历史）；
4. 弹窗型（URL 不变）路径**行为不变**（老页面照样收弹窗控件）。
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MOD = ROOT / "framework" / "features" / "f02_semantic" / "explorer_explore.py"


def _src() -> str:
    assert MOD.is_file(), f"找不到 {MOD}"
    return MOD.read_text(encoding="utf-8")


def _tree() -> ast.Module:
    return ast.parse(_src())


def _func(name: str) -> ast.FunctionDef:
    for n in ast.walk(_tree()):
        if isinstance(n, ast.FunctionDef) and n.name == name:
            return n
    raise AssertionError(f"模块里找不到函数 {name}")


def _body(name: str) -> str:
    return ast.get_source_segment(_src(), _func(name)) or ""


# ---------------------------------------------------------------- 1) 必须记点前 URL
def test_records_url_before_click():
    body = _body("_try_collect_modal_items")
    assert "_url_before" in body, (
        "点开候选按钮前必须记下 `_url_before` —— 不记就没法和点后的 URL 比，"
        "也就分不出「弹窗」和「整页导航」，导航型按钮会把探测所在页面带跑")


def test_compares_url_after_click():
    body = _body("_try_collect_modal_items")
    assert "_url_after" in body, "点完必须读 `_url_after` 做比较"
    assert "_url_after != _url_before" in body, (
        "比较必须是「点后 URL != 点前 URL」这一条判据 —— 导航型按钮的特征就是这个")


def test_navigation_returns_empty_and_goes_back():
    body = _body("_try_collect_modal_items")
    # 命中导航分支后必须：出声（print）-> 退回原页 -> 返回空
    assert "是**导航**不是弹窗" in body or "导航" in body, "导航型必须**出声**说明，不许静默"
    assert "go_back(" in body, (
        "导航型必须 `go_back()` 退回原页 —— 只跳过收集不还原页面，后面的探测全会错位")
    assert "pg.goto(_url_before" in body, (
        "`go_back` 失败时要有 `goto(原 URL)` 兜底（浏览器历史不一定在）")


def test_navigation_branch_returns_before_collecting():
    """导航分支必须在收集控件**之前**返回，否则会把别的页面的控件收进来。"""
    body = _body("_try_collect_modal_items")
    i_nav = body.find("_url_after != _url_before")
    i_modal = body.find("# ---- 第 1 层：弹窗本体")
    assert i_nav != -1, "找不到导航判断"
    assert i_modal != -1, "找不到弹窗本体收集段"
    assert i_nav < i_modal, (
        "导航判断必须排在弹窗收集**之前** —— 否则顺序反了等于没判（先把跑错页的控件收进来再判断）")


# ---------------------------------------------------------------- 2) 弹窗型行为不变
def test_modal_hints_unchanged():
    """候选名单不许因为修这个 bug 被缩小 —— 弹窗型页面还得靠它。"""
    tree = _tree()
    for n in ast.walk(tree):
        if isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name) and t.id == "_MODAL_BUTTON_HINTS":
                    vals = [e.value for e in n.value.elts if isinstance(e, ast.Constant)]
                    assert "新建" in vals and "创建" in vals, (
                        f"候选名单被缩小了：{vals} —— 修导航问题不是靠删候选词，"
                        "而是靠点完判断 URL（弹窗型页面仍需这些词）")
                    return
    raise AssertionError("找不到 _MODAL_BUTTON_HINTS 定义")


def test_success_path_still_dismisses_tips():
    """URL 没变（弹窗型）时，原有 `_dismiss_tips` 行为必须保留。"""
    body = _body("_try_collect_modal_items")
    # 导航分支里一次、正常路径一次
    assert body.count("_dismiss_tips(pg)") >= 2, (
        "正常路径与导航退回路径都应清提示浮层（权限拦截弹的浮层会挡住后续探测）")
