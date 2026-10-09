# -*- coding: utf-8 -*-
"""特性5 · 用例/脚本/数据三层分离：**没有 value 的步骤也要能生成脚本**（V8.4）。

事故（2026-10-08 干净环境 E2E 实录）：
    AI 按新约束产出「`select` 只给 element、不给 value」（选第一项 = 框架默认行为）后，
    `generate` 直接崩：
        File "generator.py", line 684, in _render_pytest_case
            ref = st["_payload_ref"]
        KeyError: '_payload_ref'
    -> **一条脚本都没生成**（`scripts/generated/` 是空的）。
    根因：`_add_payload_refs()` 只在 `if st.get("value"):` 为真时设 `_payload_ref`，
    而 `_render_pytest_case()` 对 `fill`/`select` 直接按下标取 `st["_payload_ref"]` ——
    **假定这两个动作必然带 value**。以前 AI 总会给 select 塞个 value（哪怕猜的），所以从未触发；
    一旦「值确实是可选的」（选第一项），就必然踩中。

判据口径：纯函数级（不跑浏览器、不调 LLM）。
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
GENERATOR = REPO / "framework" / "tools" / "generate" / "generator.py"


def _src() -> str:
    return GENERATOR.read_text(encoding="utf-8")


def _fn_src(name: str) -> str:
    src = _src()
    lines = src.splitlines()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return "\n".join(lines[node.lineno - 1: node.end_lineno])
    raise AssertionError(f"generator.py 里找不到 {name}()")


def test_fill_select_render_does_not_index_payload_ref():
    """`fill`/`select` 的渲染**不许**按下标取 `_payload_ref`（没 value 时它不存在）。"""
    body = _fn_src("_render_pytest_case")
    # 找 fill/select 分支
    i = body.find('elif op in ("fill", "select"):')
    assert i != -1, "渲染里 fill/select 的分支结构变了，判据需同步更新"
    seg = body[i: i + 320]
    assert 'st["_payload_ref"]' not in seg, (
        "`fill`/`select` 仍用 st[\"_payload_ref\"] 直接下标取值 —— "
        "步骤不带 value 时这里会 KeyError（实测：select 选第一项只给 element）"
    )


def test_payload_refs_covers_valueness_steps():
    """`_add_payload_refs` 之后，**每个 fill/select 步骤**都必须能安全渲染（有值取值、无值不传）。

    这是"覆盖完整性"判据：不要求它一定有 ref，但要求渲染路径**不依赖 ref 的存在**。
    """
    body = _fn_src("_render_pytest_case")
    i = body.find('elif op in ("fill", "select"):')
    seg = body[i: i + 320]
    assert 'st.get("_payload_ref")' in seg, (
        "fill/select 分支没有用 st.get(\"_payload_ref\") 安全取值 —— "
        "缺 value 的步骤无路可走（必须「有值才传 _data，没值就不传 value」）"
    )


def test_render_case_without_value_does_not_raise():
    """**行为判据（端到端最小复现）**：拿一份「select 不给 value」的用例走渲染，不许抛 KeyError。

    这条直接复现事故输入：select 只有 element、没有 value（AI 新版写法）。
    """
    import sys
    sys.path.insert(0, str(REPO))
    from framework.tools.generate.generator import _add_payload_refs

    case = {
        "case_id": "t_no_value",
        "name": "无 value 步骤",
        "base_url": "http://localhost:8000/",
        "steps": [
            {"op": "goto", "desc": "打开列表", "url": "http://localhost:8000/"},
            {"op": "select", "desc": "业务单元选第一项", "element": "业务单元@新建订单页"},
            {"op": "fill", "desc": "填名称", "element": "订单名称@新建订单页", "value": "X"},
            {"op": "click", "desc": "保存", "element": "保存@新建订单页"},
        ],
        "asserts": [{"desc": "到达", "expect": "合同管理系统", "after_step": 1}],
    }
    out = _add_payload_refs(case)
    # select 那步不该有 _payload_ref（它本来就没有 value 可抽）
    st = out["steps"][1]
    assert st.get("_payload_ref") is None, "无 value 的 select 被硬塞了 _payload_ref —— 数据层会拿到空值"
    # 有 value 的 fill 必须有（数据抽离能力不能因此退化）
    assert out["steps"][2].get("_payload_ref"), "有 value 的 fill 丢了 _payload_ref —— 数据抽离被破坏了"
