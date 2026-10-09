# -*- coding: utf-8 -*-
"""特性2 · 「同因不重试」必须按**归一化指纹**判定，不许逐字比（V8.4）。

事故（2026-10-09 干净环境 E2E 实录）：
    三轮实跑失败点**本质是同一个** —— 第 2、3 轮都是
        waiting for get_by_text("订单系统").first to be visible
    AI 反复断言页面上不存在的「订单系统」（幻觉文字）。按设计，「同因不重试」该在第 2 轮
    之后停下（再问也是同一个答案，白烧 token）。但它一路跑到第 3 轮。

    根因：失败原因文本里**必然**带每轮都不同的东西 —— 校验日志路径自带时间戳：
        …/verify/ai_xxx_20261009_073944.log
        …/verify/ai_xxx_20261009_074246.log
    `prev.strip() == new.strip()` 逐字比较 -> **永远判「不同因」** -> 永远重试。

判据口径：纯函数级（不启浏览器）。
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CLI = REPO / "framework" / "cli.py"


def _fn(name: str):
    """取出 cli.py 里的纯函数并 exec —— **连同它依赖的同模块纯函数一起**。

    [!] 只 exec 目标函数体是不够的：`_should_retry_again` 依赖
        `_retry_reason_fingerprint`，单独 exec 会 `NameError`（本判据第一版就踩了）。
    """
    src = CLI.read_text(encoding="utf-8")
    lines = src.splitlines()
    wanted = [name, "_retry_reason_fingerprint"]
    ns: dict = {"re": re}
    found = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in wanted:
            body = "\n".join(lines[node.lineno - 1: node.end_lineno])
            exec(compile(ast.parse(body), "<cli>", "exec"), ns)   # noqa: S102
            found.add(node.name)
    if name not in found:
        raise AssertionError(f"cli.py 里找不到 {name}()（找到的是 {sorted(found)}）")
    return ns[name]


def _fn_src(name: str) -> str:
    src = CLI.read_text(encoding="utf-8")
    lines = src.splitlines()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return "\n".join(lines[node.lineno - 1: node.end_lineno])
    raise AssertionError(f"cli.py 里找不到 {name}()")


def test_same_cause_detection_ignores_log_paths():
    """同一失败原因 + 不同日志路径 -> 必须判为「同因」（不再重试）。

    这是本判据的核心：日志路径带时间戳，逐字比必然「不同因」。
    """
    fp = _fn("_retry_reason_fingerprint")
    a = ("用例 ai_x 实跑 FAILED（校验日志 /tmp/e2e/output/verify/ai_x_20261009_073944.log）：\n"
         "  E  TimeoutError: Locator.wait_for: 等待 get_by_text(\"订单系统\").first 可见超时")
    b = ("用例 ai_x 实跑 FAILED（校验日志 /tmp/e2e/output/verify/ai_x_20261009_074246.log）：\n"
         "  E  TimeoutError: Locator.wait_for: 等待 get_by_text(\"订单系统\").first 可见超时")
    assert a != b, "构造的样本本身就该不同（否则判据没意义）"
    assert fp(a) == fp(b), (
        "归一化后仍不相等 -> 「同因不重试」会失效（日志路径的时间戳把它骗过去了）"
    )


def test_fingerprint_keeps_real_differences():
    """归一化**不许把真差异抹平** —— 否则该重试的也不试了（负向：宁漏不误伤的反面）。"""
    fp = _fn("_retry_reason_fingerprint")
    a = "E  TimeoutError: 等待 get_by_text(\"订单系统\").first"
    b = "E  TimeoutError: 等待 get_by_text(\"发票列表\").first"
    assert fp(a) != fp(b), "两个不同的失败点被归一成同一个指纹 -> 该重试的不重试了"


def test_should_retry_uses_fingerprint():
    """`_should_retry_again` 必须走指纹比较（不许再逐字比 `prev.strip() == new.strip()`）。"""
    src = _fn_src("_should_retry_again")
    assert "_retry_reason_fingerprint" in src, (
        "还在逐字比较原因文本 -> 日志路径的时间戳会让「同因」永远判不出来（白烧 token）"
    )
    # 行为验证：同因（路径不同）-> 停
    f = _fn("_should_retry_again")
    a = "实跑 FAILED（校验日志 /t/a_20261009_073944.log）：E 等待 get_by_text(\"订单系统\") 超时"
    b = "实跑 FAILED（校验日志 /t/a_20261009_074246.log）：E 等待 get_by_text(\"订单系统\") 超时"
    assert f(prev=a, new=b, attempt=1, limit=2) is False, (
        "第 2 轮与上一轮同因（只是日志路径不同）却仍要重试 -> 白白多烧一轮"
    )


def test_should_retry_still_retries_on_new_cause():
    """反向自证：**真不同因**时必须继续重试（别把修复做过头）。"""
    f = _fn("_should_retry_again")
    a = "E 断言失败：期望 URL orders.html，实际 http://localhost:8000/"
    b = "E TimeoutError: 等待 get_by_text(\"订单系统\") 超时"
    assert f(prev=a, new=b, attempt=1, limit=2) is True, (
        "换了失败原因却不再重试 -> AI 连第二次机会都没有，闭环名存实亡"
    )


def test_should_retry_respects_limit_and_empty():
    """边界：次数用尽 -> 停；本轮无原因 -> 停。"""
    f = _fn("_should_retry_again")
    assert f(prev="x", new="y", attempt=2, limit=2) is False, "次数用尽还重试 -> 无界"
    assert f(prev="", new="", attempt=0, limit=2) is False, "没失败原因也重试 -> 空转"
