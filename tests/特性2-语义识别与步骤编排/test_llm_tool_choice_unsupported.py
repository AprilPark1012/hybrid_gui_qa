# -*- coding: utf-8 -*-
"""特性2 · 上游不支持 `tool_choice`（thinking mode）时：explorer 侧**复用唯一权威**（V8.6.3 收敛）。

事故（AprilPark1012 2026-10-09 Windows 实录 · 每一轮都出现一次）：
    [explore] 第 1/3 次结构化输出失败 -> 结构化输出路径 ModelProviderError:
      Error code: 400 - {'error': {'message': 'Thinking mode does not support this tool_choice',
       'type': 'invalid_request_error'}}

口径（**V8.6.1 收敛，V8.6.3 收敛到唯一权威**）：
    撞到这类**上游能力差异**（不是抖动）的**动作口径 = 降级为 `tool_choice=auto`、把结构化输出救回来**，
    由 `framework/shared/llm_compat.py::ChatOpenAICompatible.ainvoke()` 承担 ——
    判定函数是 `framework/shared/llm_compat.py::rejects_named_tool_choice`，
    那个口径的**唯一权威判据**是 `tests/特性10-CLI帮助契约/test_llm_tool_choice_fallback.py`。

    [!] V8.6.3 之前 explorer 里另写了一套字符串匹配（`"tool_choice" in _low or "thinking mode" in _low`）
    —— 与上面的权威**是两套口径**，已删除。现在 explorer **只复用** `rejects_named_tool_choice()`：
      · 走到 explorer 的 except 且仍带该特征 -> 端点连**降级 auto** 都拒 -> 本会话禁用结构化路径、只走纯文本；
      · 本文件钉的是「**复用唯一权威**」，不再钉「那套自写判定还在不在」。
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
EXPLORER = REPO / "framework" / "features" / "f02_semantic" / "explorer_explore.py"

#: 唯一权威所在的模块（判定函数必须从这里来，不许就地再写一套）
AUTHORITY_MOD = "framework.shared.llm_compat"
AUTHORITY_FN = "rejects_named_tool_choice"


def _src() -> str:
    return EXPLORER.read_text(encoding="utf-8")


def test_explorer_delegates_to_single_authority():
    """explorer 必须**复用** llm_compat 的权威谓词，不许自写第二套「是不是 tool_choice 不支持」的判定。"""
    src = _src()
    assert AUTHORITY_FN in src, (
        f"explorer 没有复用 {AUTHORITY_MOD}::{AUTHORITY_FN}()（又自己写了一判断？）"
    )
    assert AUTHORITY_MOD in src, (
        f"{AUTHORITY_FN} 不是来自 {AUTHORITY_MOD}（唯一权威）"
    )


def test_handrolled_tool_choice_heuristic_is_gone():
    """自写的字符串匹配判定必须绝迹 —— 两套口径并存正是本项要收敛掉的东西。"""
    src = _src()
    assert '"thinking mode" in _low' not in src, (
        "还留着自写的 tool_choice 判定（两套口径）—— 必须只认 llm_compat 的权威谓词"
    )
    assert 'if "tool_choice" in _low' not in src, (
        "还留着自写的 tool_choice 判定（两套口径）—— 必须只认 llm_compat 的权威谓词"
    )


def test_no_structured_branch_is_gated_by_authority():
    """`_no_structured` 的触发条件必须就是权威谓词的调用结果（不是别的东西）。"""
    src = _src()
    i = src.find(f"{AUTHORITY_FN}(e)")
    assert i > 0, f"没有用权威谓词 {AUTHORITY_FN}(e) 判定结构化路径的失败"
    window = src[max(0, i - 700): i + 700]
    assert "_no_structured = True" in window, (
        "权威判定的结果没有接到「禁用结构化路径」上 -> 复用只是装饰"
    )


def test_log_is_downgraded_to_info():
    """降噪：能力差异不是错误，日志该是 `[info]` 而不是 ModelProviderError 红字。"""
    src = _src()
    i = src.find(f"{AUTHORITY_FN}(e)")
    assert i > 0
    window = src[max(0, i - 700): i + 700]
    assert "[info]" in window, (
        "tool_choice 处理处附近没有 [info] 降噪打印 -> 用户还是会看到红字"
    )
