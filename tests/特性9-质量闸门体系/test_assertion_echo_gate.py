# -*- coding: utf-8 -*-
"""L36 · 断言闸门：**输入回显 = 硬红线**（不再是告警）。

## 为什么有这一组判据

2026-10-21（L35 真跑）AI 重规划后写 `expect_text "全链路-20261021215943"` —— 那正是**本用例
自己 fill 进去**的订单名（场景 `data:` 模板渲染）。结果：列表里 5s 内不可见 -> 207s 超时。

提示词规则 6 早就写着「不得与 fill 的 value 相同」，但它只进 `case_warnings`（告警），
AI 犯规照样落盘 —— **写了规矩、没有闸门**。本组判据守的就是这个闸门：

  J1  回显断言 -> `assertion_hard_errors()` 给出理由（并且真的接进了落盘前的红线计算）
  J2  `kind=first_row` 豁免（它验的是「落在第一行」，期望值本来就该等于刚填的值）
  J3  场景 `assert_guard.allow_input_echo: true` 可显式豁免（豁免必须是人写的决定）
  J4  提示词里必须写明「这条有闸门」+ 豁免开关名（否则 AI 不知道会被拒）
  J5  负向自证：换一个非回显的断言 -> 零红线（判据不是恒红）
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

CASE_ECHO = {
    "case_id": "l36_echo",
    "steps": [
        {"order": 1, "op": "fill", "element": {"semantic_name": "订单名称"},
         "value": "全链路-20261021", "desc": "填订单名"},
        {"order": 2, "op": "click", "element": {"semantic_name": "保存"}, "desc": "保存"},
    ],
    "asserts": [
        {"kind": "text", "expect": "全链路-20261021", "desc": "看到刚填的订单名"},
    ],
}

CASE_FIRST_ROW = {
    "case_id": "l36_firstrow",
    "steps": [{"order": 1, "op": "fill", "element": {"semantic_name": "订单名称"},
               "value": "全链路-20261021", "desc": "填订单名"}],
    "asserts": [{"kind": "first_row", "cell_field": "订单名称", "expect": "全链路-20261021"}],
}

CASE_OK = {
    "case_id": "l36_ok",
    "steps": [{"order": 1, "op": "fill", "element": {"semantic_name": "订单名称"},
               "value": "全链路-20261021", "desc": "填订单名"}],
    "asserts": [{"kind": "text", "expect": "草稿", "desc": "状态变草稿"},
                {"kind": "url", "expect": "order_detail", "desc": "跳到详情页"}],
}


def _mod():
    from framework.features.f02_semantic import case_builder_generate as C
    return C


# ============================ J1：回显被拦 ============================

def test_j1_input_echo_is_a_hard_error():
    C = _mod()
    bad = C.assertion_hard_errors(CASE_ECHO)
    assert bad, ("回显断言没有被判成红线 —— 那它仍会被落盘，用例要么超时挂、"
                 "要么在别的数据批次下侥幸相等（假绿）")
    assert "输入回显" in bad[0] and "allow_input_echo" in bad[0], (
        f"红线理由要说明「怎么改」（含豁免开关名），实际：{bad[0]}")


def test_j1b_gate_is_wired_into_the_write_path():
    """红线必须真的参与**落盘前**的判定，不能只是"存在一个函数"。"""
    src = _read(REPO / "framework/features/f02_semantic/case_builder_generate.py")
    red_lines = [ln for ln in src.splitlines()
                 if "case_errors(case" in ln and "=" in ln]
    assert red_lines, "找不到落盘前的红线计算行"
    assert any("assertion_hard_errors" in ln for ln in red_lines), (
        "`assertion_hard_errors()` 没接进落盘前的红线计算 -> 闸门是个摆设：\n" + "\n".join(red_lines))


# ============================ J2 / J3：两处豁免 ============================

def test_j2_first_row_is_exempt():
    C = _mod()
    assert C.assertion_hard_errors(CASE_FIRST_ROW) == [], (
        "expect_first_row 被当成回显拦了 —— 它验的是「新建记录落在第一行」，"
        "期望值本来就该等于刚填的值，拦掉会让「新建」类用例无法表达")


def test_j3_scenario_can_opt_out_explicitly():
    C = _mod()
    assert C.assertion_hard_errors(CASE_ECHO, guard={"allow_input_echo": True}) == [], (
        "场景显式写了 allow_input_echo: true 仍被拦 —— 豁免必须生效（否则「保存后值仍在」没法表达）")


# ============================ J4：提示词要说清有闸门 ============================

def test_j4_prompt_tells_ai_the_gate_exists():
    src = _read(REPO / "framework/features/f02_semantic/explorer_explore.py")
    assert "有闸门" in src and "allow_input_echo" in src, (
        "提示词没告诉 AI「回显断言会被拒」+ 豁免开关名 -> AI 会一直犯规，"
        "然后每一轮都被同一处挡住（重试闭环空转）")


# ============================ J5：负向自证（不是恒红）============================

def test_j5_non_echo_assertions_pass():
    C = _mod()
    assert C.assertion_hard_errors(CASE_OK) == [], (
        "正常断言（状态文案 / 跨页证据）也被判红了 —— 判据恒红会把 AI 逼到不敢断言")


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")
