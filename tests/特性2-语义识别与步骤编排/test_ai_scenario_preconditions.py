# -*- coding: utf-8 -*-
"""特性2 · AI 编排必须尊重「场景级前置声明」+ 不许幻觉业务数据（V8.4）。

事故（2026-10-08 干净环境 E2E 实录，两次生成的用例对比得出）：
    同一场景（`scenarios/orders/orders_invoice_full_lifecycle.yml`）生成两次，一次对一次错 ——
      · 老版 [OK]：step1「打开合同列表页（登录由场景级登录前置完成，无需手工登录）」，全程无登录步骤；
      · 新版 [NG]：AI **自己编了一套登录流程**（goto 登录页 → fill 账号 → **fill 密码 = `123456`**），
                而场景 yml 的 `auth:` 段里真密码是 `super@123` -> 登录失败、停在登录页 ->
                后续断言等不到元素 -> FAILED -> explore 质量闸如实报「实测未通过」。
    根因两类：
      ① **无视场景级前置**：`auth:` 已声明（框架会自动登录），AI 不该再生成登录步骤；
      ② **幻觉业务数据**：编了个密码（真值就在喂给它的场景文本里，它没照抄）。

判据口径：全部走**纯函数 / 假数据**，不联网、不依赖真 LLM（本项目判据必须能在无 key 环境跑）。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
EXPLORER = REPO / "framework" / "tools" / "explore" / "explorer.py"


def _src() -> str:
    return EXPLORER.read_text(encoding="utf-8")


def _fn_src(name: str) -> str:
    src = _src()
    lines = src.splitlines()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return "\n".join(lines[node.lineno - 1: node.end_lineno])
    raise AssertionError(f"explorer.py 里找不到 {name}()")


def _fn_params(name: str) -> set[str]:
    src = _src()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return {a.arg for a in node.args.args} | {a.arg for a in node.args.kwonlyargs}
    raise AssertionError(f"explorer.py 里找不到 {name}()")


# ---------------------------------------------------------------- 提示词侧

def test_prompt_accepts_auth():
    """`_build_planner_prompt` 必须能知道「本场景声明了登录前置」——否则它无从约束 AI。"""
    assert "auth" in _fn_params("_build_planner_prompt"), (
        "_build_planner_prompt() 没有 auth 参数 —— AI 不知道场景已声明登录前置，会自己编登录流程"
    )


def test_prompt_forbids_login_steps_when_auth_declared():
    """声明了 `auth:` -> 提示词必须**明确禁止** AI 生成任何登录步骤。"""
    from framework.tools.explore.explorer import _build_planner_prompt

    prompt = _build_planner_prompt(
        "打开合同列表页，选中第一行合同", [], "http://x/",
        auth={"username": "u", "password": "p", "login_api": "/api/login"},
    )
    flat = prompt.replace("\n", "")
    assert "登录" in flat, "提示词里根本没提登录，无法约束 AI"
    # 必须出现「禁止/不要/无需」这类**否定式**约束，而不是只描述登录怎么做
    assert any(w in flat for w in ("禁止生成", "不要生成", "无需生成", "禁止写", "不要写")), (
        "提示词没有『禁止 AI 生成登录步骤』的硬约束 —— 实测就是这里放过了 AI 自编登录流程"
    )
    assert "前置" in flat or "框架会" in flat, (
        "提示词必须说明『登录由框架前置完成』，否则 AI 仍会觉得自己该做这一步"
    )


def test_prompt_has_no_login_ban_without_auth():
    """**负向的另一面**：没声明 `auth:` 的场景，不该被塞进这条约束（避免过度约束误伤）。"""
    from framework.tools.explore.explorer import _build_planner_prompt

    prompt = _build_planner_prompt("打开待办页，添加一条待办", [], "http://x/", auth=None)
    flat = prompt.replace("\n", "")
    assert "禁止生成" not in flat or "登录" not in flat, (
        "未声明 auth 的场景也被加了『禁止登录步骤』约束 —— 约束条件写错了（会误伤真需要登录的场景）"
    )


def test_prompt_requires_grounded_business_values():
    """提示词必须要求「业务数据一律照抄场景/清单，不许自己编」——治幻觉密码那类问题。"""
    from framework.tools.explore.explorer import _build_planner_prompt

    prompt = _build_planner_prompt("随便什么场景", [], "http://x/", auth={"username": "u"})
    flat = prompt.replace("\n", "")
    assert any(w in flat for w in ("编造", "幻觉", "照抄", "原样", "只能取自", "不许自己")), (
        "提示词没有『业务数据必须照抄来源、不许编造』的约束"
    )


def test_prompt_grounds_select_value():
    """下拉选择（select）必须明确「值怎么来」——**优先 index，不许猜选项 value**（V8.4）。

    事故（2026-10-08 干净环境 E2E，同一场景两版用例对比）：
      · 老版 [OK]：`select 业务单元选第一行` 用 **`index=0`** -> 通过；
      · 新版 [NG]：同样一句，AI 写了 **`value="1"`**（它猜选项的 value 是 1）-> `did not find some options` 失败。
    根因：AI **看不到**真实选项的 value（探测清单里只有控件、没有 option 列表），
    而提示词只要求「select 必须给 semantic_name」，**没规定值从哪来** -> 它只能猜。
    """
    from framework.tools.explore.explorer import _build_planner_prompt

    prompt = _build_planner_prompt("打开新建订单页，业务单元选第一行", [], "http://x/",
                                   auth={"username": "u"})
    flat = prompt.replace("\n", "")
    i = flat.find("下拉选择")
    assert i != -1, "提示词里没有【下拉选择（select）的值从哪来】这一节"
    seg = flat[i: i + 400]          # 只看这一节，别被别处的 index 字样蒙混过去
    assert "index" in seg, (
        "下拉这一节没要求优先用 index（实测：老版用 index=0 通过，新版猜 value='1' 失败）"
    )
    assert any(w in seg for w in ("不许猜", "不要猜", "禁止猜", "看不到", "无法得知", "永远不要")), (
        "下拉这一节没说明『AI 看不到真实选项 value、不许猜』——不说清 AI 还会继续猜"
    )


# ---------------------------------------------------------------- 生成后闸门

def test_login_step_gate_exists():
    """必须有一个「AI 产出里不许夹带登录步骤」的闸门（且是独立可测的函数）。"""
    assert "_reject_login_steps" in _src(), (
        "explorer.py 缺少 `_reject_login_steps(...)` —— 生成后没有闸门，AI 夹带登录步骤会直接落盘"
    )


def test_login_step_gate_rejects_login_flow():
    """给一段**含登录流程**的产出 -> 闸门必须拒绝。"""
    from framework.tools.explore.explorer import _reject_login_steps

    bad = [
        {"op": "goto", "desc": "打开登录页", "value": "http://x/login.html"},
        {"op": "fill", "desc": "填写账号", "semantic_name": "账号", "value": "super"},
        {"op": "fill", "desc": "填写密码", "semantic_name": "密码", "value": "123456"},
        {"op": "click", "desc": "以超级管理员登录", "semantic_name": "登_录"},
    ]
    with pytest.raises(Exception) as ei:
        _reject_login_steps(bad)
    msg = str(ei.value)
    assert "登录" in msg, f"拒绝信息必须说清原因，实际：{msg}"


def test_login_step_gate_allows_normal_steps():
    """**负向自证**：正常的业务步骤（含『登录』二字出现在**描述**里但操作的是业务控件）不许误拦。

    口径：判定看的是「打开的是登录页 / 填的是账号密码这类登录专用字段」，不是"描述里出现登录"。
    """
    from framework.tools.explore.explorer import _reject_login_steps

    good = [
        {"op": "goto", "desc": "打开合同列表页（登录由场景级登录前置完成）", "value": "http://x/"},
        {"op": "click", "desc": "展开右上角角色切换入口", "semantic_name": "nu-avatar"},
        {"op": "fill", "desc": "填写订单名称", "semantic_name": "订单名称", "value": "X"},
        {"op": "click", "desc": "保存", "semantic_name": "保存"},
    ]
    _reject_login_steps(good)          # 不抛即为通过


# ---------------------------------------------------------------- 接线

def test_ai_explore_passes_auth_into_prompt():
    """接线判据：`_ai_explore_async` 必须把 auth 传进 `_build_planner_prompt`（否则上面全是空谈）。"""
    body = _fn_src("_ai_explore_async")
    call = body[body.index("_build_planner_prompt("):]
    call = call[: call.index(")") + 1]
    assert "auth" in call, (
        "_ai_explore_async 调 _build_planner_prompt 时没传 auth —— 提示词里的前置约束永远不生效"
    )


def test_ai_explore_calls_login_gate():
    """接线判据：产出步骤必须过一遍登录闸门（不许只在别的分支上拦）。

    口径（实现定：**单点收口**）：实测有 **3 处** `_finalize_map(...)` 调用（离线回放 / LLM 成功 /
    兜底路径），闸门放在 `_finalize_map` 内部 -> 3 条路径自动全覆盖 —— 与「探测步骤收敛到唯一入口」
    同一个思路。**只在一处 if 分支里拦是不够的**，那会让另外两条路径绕过闸门。
    """
    assert "_reject_login_steps(" in _fn_src("_finalize_map"), (
        "_finalize_map 里没有调用登录闸门 —— 它有 3 个调用点，放这里才能全覆盖"
    )
