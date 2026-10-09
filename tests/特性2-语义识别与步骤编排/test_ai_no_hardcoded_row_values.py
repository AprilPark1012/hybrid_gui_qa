# -*- coding: utf-8 -*-
"""特性2 · AI 产出**不许写死表格行数据的具体值**（V8.4.1 · Windows 实测暴露）。

事故（AprilPark1012 2026-10-09 在 Windows 上跑 `explore --ai` 实录，一行行核对出来的）：
    场景原话是「选中**第一行**合同」，AI 却把它具体化成了 demo 里的**字面值**：

        ai_..._110109.json:
          step 5: goto  -> http://localhost:8000/order_new.html?contract_no=HT-1001
          step 6: check -> 选择合同_HT_1001
          step 43: expect_text -> assert=HT-1001

    -> 现在能跑通，只是因为**当前 demo 第一行恰好是 HT-1001**。
      换一批数据 / 换个排序 / 换个环境，立刻崩 —— 而用例看着「完全正常」。

这直接违反「补能力必须与场景解耦、不能写死」（他 2026-09-30 定的原则）：
    · 框架层零业务词（订单号 / 控件名 / 页面名 / 角色名不许写死）；
    · **不许把「观测到的具体值」当地基** —— 写死 `SO-1101`、某个固定 index，
      都是「拿实测值当能力」。

正确形态：行数据一律走**声明式定位**（行锚 `row_text` / 首行断言 `expect_first_row` /
`cell_field`），具体值由场景或数据层提供。
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
EXPLORER = REPO / "framework" / "tools" / "explore" / "explorer.py"


def _fn_src(name: str, path: Path = EXPLORER) -> str:
    src = path.read_text(encoding="utf-8")
    lines = src.splitlines()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return "\n".join(lines[node.lineno - 1: node.end_lineno])
    raise AssertionError(f"{path.name} 里找不到 {name}()")


def _namespace(path: Path = EXPLORER):
    """取 explorer 模块里与「行数据写死」相关的纯函数，供行为级验证。"""
    src = path.read_text(encoding="utf-8")
    lines = src.splitlines()
    # 注意：这些符号在 explorer.py 里是**模块级**的；本函数把它们摘出来单独 exec。
    # 依赖顺序：常量 -> 函数（函数体里引用常量）。
    wanted = {"_HARDCODE_ID_RE", "_HARDCODE_EXEMPT",
              "looks_like_hardcoded_row_value", "reject_hardcoded_row_values",
              # V8.4.3：写死检测新增「对照场景原文」豁免（编号规范化比较）
              "_norm_id", "_ids_all_declared_in_scenario"}
    ns: dict = {"re": re}
    found = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id in wanted:
                    exec(compile(ast.Module(body=[node], type_ignores=[]), "<x>", "exec"), ns)   # noqa: S102
                    found.add(t.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in wanted:
            body = "\n".join(lines[node.lineno - 1: node.end_lineno])
            exec(compile(ast.parse(body), "<x>", "exec"), ns)   # noqa: S102
            found.add(node.name)
    if not (wanted & found):
        raise AssertionError(f"这些符号一个都没有：{sorted(wanted)}（功能缺失 -> 判据红）")
    return ns


def test_detector_recognizes_demo_row_ids():
    """识别器必须认得 demo 的行数据形态（HT-1001 / SO-1011 / HT_1001）。"""
    ns = _namespace()
    f = ns["looks_like_hardcoded_row_value"]
    for v in ["HT-1001", "SO-1011", "HT_1001", "contract_no=HT-1001"]:
        assert f(v) is True, f"{v!r} 应被判为写死的行数据值"
    for v in ["全链路-{datetime}", "订单名称", "新建订单", "orders.html",
              "{合同编号}", "SO-xxxx", "HT-xxxx"]:
        assert f(v) is False, f"{v!r} 是声明式/占位符/页面标识，不该被误判（宁漏不误伤）"


def test_gate_rejects_steps_with_hardcoded_values():
    """闸门必须能把「带写死行数据值」的步骤挑出来（给重试闭环当原因）。"""
    ns = _namespace()
    gate = ns["reject_hardcoded_row_values"]

    class _E:
        def __init__(self, n): self.semantic_name = n

    class _S:
        def __init__(self, order, op, desc, value=None, element=None, url=None):
            self.order, self.op, self.description = order, op, desc
            self.value, self.element, self.url = value, element, url

    steps = [
        _S(5, "check", "选中第一行合同 HT-1001", element=_E("选择合同_HT_1001")),
        _S(6, "goto", "等价直达新建订单页", url="http://localhost:8000/order_new.html?contract_no=HT-1001"),
        _S(9, "fill", "填写订单名称", value="全链路-{datetime}"),
    ]
    bad = gate(steps)
    assert len(bad) == 2, f"应挑出 2 条写死行数据的步骤，实际 {len(bad)}：{bad}"
    assert any("HT-1001" in str(b) for b in bad)


def test_gate_is_clean_on_good_output():
    """反向自证：合规产出（占位符 / 行锚 / 首行断言）**一条都不许挑**（宁漏不误伤）。"""
    ns = _namespace()
    gate = ns["reject_hardcoded_row_values"]

    class _E:
        def __init__(self, n): self.semantic_name = n

    class _S:
        def __init__(self, order, op, desc, value=None, element=None, url=None):
            self.order, self.op, self.description = order, op, desc
            self.value, self.element, self.url = value, element, url

    steps = [
        _S(1, "goto", "进入合同列表页", url="http://localhost:8000/"),
        _S(9, "fill", "填写订单名称", value="全链路-{datetime}"),
        _S(19, "expect_first_row", "确认首行是刚建的订单", value="全链路-{datetime}"),
        _S(20, "click", "点该行的订单名称进入详情", element=_E("订单名称@订单列表页")),
        _S(43, "expect_text", "确认搜到刚创建的发票", value="{合同编号}"),
    ]
    assert gate(steps) == [], "合规产出被误判 -> 会逼着人绕过闸门（宁漏不误伤）"


def test_prompt_forbids_hardcoded_row_values():
    """提示词必须**显式禁止**把行数据具体值写进用例（根因在提示词，闸门只是兜底）。"""
    body = _fn_src("_build_planner_prompt")
    assert ("HT-1001" in body or "行数据" in body or "写死" in body), (
        "提示词里没有任何「禁止写死行数据」的约束 -> AI 还会继续把第一行具体化"
    )
    assert ("row_text" in body or "expect_first_row" in body or "行锚" in body), (
        "提示词没告诉 AI「该用什么替代」（行锚/首行断言）-> 它只会换个写法继续写死"
    )


def _code_only(body: str) -> str:
    """剔掉整行注释 —— **判据必须只看真代码**。

    [!] 踩过的坑（2026-10-09 负向自证抓到）：判据原本查 `"写死" in body`，而
        `_finalize_map` 里有一行 `# P0-1：写死行数据 …` 注释 -> 把真调用摘掉后
        判据**照样绿**（空转）。凡「断言某段代码存在」的判据，都要先剔注释。
    """
    return "\n".join(l for l in body.splitlines() if not l.strip().startswith("#"))


def test_gate_is_wired_into_finalize_map():
    """闸门必须挂在 `_finalize_map` 单点收口处（3 处调用全覆盖），否则等于没接。"""
    code = _code_only(_fn_src("_finalize_map"))
    assert "reject_hardcoded_row_values(" in code, (
        "`_finalize_map` 没**真正调用**「写死行数据」闸门（只有注释不算）-> 三条产出路径总有一条漏网"
    )
