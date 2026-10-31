"""V8.7.14 判据：模型把结果写进 `content` 通道时，**不该被判成失败**。

根因（2026-10-28 实测定位，24 次真链路调用）：
  browser_use 的 `deepseek/chat.py:179-180` 在 `msg.tool_calls` 为空时**直接抛 ValueError**，
  而同一响应里的 `msg.content` 被整个丢掉。实测 8/24 命中，
  这 8 次的 content **全部是完整合法 JSON**（如 `{"steps":[...]}`），
  且 `finish_reason=stop`（正常结束，不是 length 截断、不是超时）。
  => 这是「成功被当成失败」，框架还为此白等 10~20 秒去重试。

本判据守三件事：
  ① 判定函数必须**精确**匹配那句原文，不许吞掉别的异常；
  ② content 兜底路径必须**存在且出声**（不静默，符合「静默降级=造假」的反面要求）；
  ③ `_PLANNER_SYSTEM` 不许再说「只输出 JSON」（它把模型往文本通道推）。
"""
from __future__ import annotations

from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
COMPAT = BASE / "framework/shared/llm_compat.py"
EXPLORER = BASE / "framework/features/f02_semantic/explorer_explore.py"


def test_is_missing_tool_calls_matches_only_that_error() -> None:
    """① 只认那句原文 —— 别的异常必须返回 False，不能被吞掉。"""
    from framework.shared.llm_compat import is_missing_tool_calls

    assert is_missing_tool_calls(Exception("Expected tool_calls in response but got none")) is True
    # 包装过的（ModelProviderError 里嵌着原文）也要认
    wrapped = Exception("ModelProviderError: Expected tool_calls in response but got none")
    assert is_missing_tool_calls(wrapped) is True

    # 以下都必须 False —— 吞掉它们会让真正的故障被静默掩盖
    assert is_missing_tool_calls(Exception("Request timed out.")) is False
    assert is_missing_tool_calls(Exception("429 rate limit exceeded")) is False
    assert is_missing_tool_calls(Exception("Thinking mode does not support this tool_choice")) is False
    assert is_missing_tool_calls(Exception("connection reset by peer")) is False


def test_content_fallback_exists_and_is_wired() -> None:
    """② 兜底方法存在，且 ainvoke 的 except 里真的接了它。"""
    src = COMPAT.read_text(encoding="utf-8")
    assert "async def _invoke_with_content_fallback" in src, "缺少 content 兜底方法"
    assert "if is_missing_tool_calls(e):" in src, "ainvoke 的 except 没接兜底判定"
    # 兜底必须**出声**（不静默），且明确说明走的是 content 通道
    seg = src[src.find("async def _invoke_with_content_fallback"):]
    assert "content 通道" in seg, "兜底路径没有打印说明（静默改变行为等同造假）"
    # 解析不出来必须抛错，不许返回空壳
    assert "不是可解析的 JSON" in seg, "content 解析失败时没有如实抛错"
    assert "既没有 tool_calls 也没有 content" in seg, "空响应没有单独报错"


def test_extract_json_handles_real_shapes() -> None:
    """③ `_extract_json` 能吃下真机上会遇到的几种形态。"""
    from framework.shared.llm_compat import ChatOpenAICompatible

    f = ChatOpenAICompatible._extract_json
    assert f('{"steps": [{"op": "fill"}]}') == {"steps": [{"op": "fill"}]}
    # markdown 围栏
    assert f('```json\n{"steps": []}\n```') == {"steps": []}
    # 前后有废话
    v = f('好的，结果如下：\n{"steps": [{"op": "click"}]}\n以上。')
    assert v == {"steps": [{"op": "click"}]}
    # 已经不是 dict 的情况
    assert f({"steps": []}) == {"steps": []}
    # 解析不出来必须返回 None（交给上层如实报错），而不是编一个空 dict
    assert f("完全不是 JSON 的一段话") is None
    assert f("") is None
    assert f(None) is None


def test_planner_system_no_longer_says_text_only() -> None:
    """④ `_PLANNER_SYSTEM` 不许再说「只输出 JSON」——它与强制 function calling 语义冲突。"""
    from framework.features.f02_semantic.explorer_explore import _PLANNER_SYSTEM

    assert "只输出 JSON" not in _PLANNER_SYSTEM, (
        "_PLANNER_SYSTEM 仍在说「只输出 JSON」——这句把模型往文本通道推，"
        "实测 got none 命中率显著上升；路径1 走的是强制 function calling，提示词必须要求调工具"
    )
    assert "必须调用规划工具" in _PLANNER_SYSTEM, (
        "_PLANNER_SYSTEM 没有明确要求调用工具 —— 与 output_format 的通道语义不对齐"
    )
    # 占位符铁律不能因为改首句而丢（它是多组数据展开的关键）
    assert "{占位符}" in _PLANNER_SYSTEM, "占位符铁律被改丢了"


def test_source_still_documents_the_real_cause() -> None:
    """⑤ 别只改代码不记来龙去脉：文件里必须留下「content 被丢掉」这条根因。"""
    src = COMPAT.read_text(encoding="utf-8")
    assert "被整个丢掉" in src or "被整个丢弃" in src, (
        "llm_compat.py 没记录根因（上游把 content 丢掉后才抛 got none），"
        "后来人会以为是模型不稳定又去调 effort/端点"
    )
    assert "finish_reason=stop" in src or "finish_reason" in src, (
        "没记录「finish_reason=stop 说明是正常结束」这条判据 —— "
        "它是区分『模型放弃』与『被截断』的关键证据"
    )
