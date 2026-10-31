"""V8.7.14 · content 通道兜底的**单元级**验证（不依赖真链路偶发）。

为什么必须单测而不是只靠真链路：
  · `got none` 是偶发的：修复前一次抓到 8/10，之后再跑 22 次全过（含故意改回旧 prompt）。
  · 靠真链路「碰运气」去覆盖一条异常分支，等于交付没跑过的代码。
  => 这里直接构造上游返回形态，精确验证兜底的三条分支。

覆盖：
  1. tool_calls 空 + content 是合法 JSON      -> 解析复用，**不抛错**，且打印通道说明
  2. tool_calls 空 + content 是围栏/带废话    -> 同样能解析
  3. tool_calls 空 + content 不是 JSON        -> **如实抛错**（绝不返回空壳）
  4. tool_calls 空 + content 为空             -> 单独报错（空响应）
  5. tool_calls 有值                          -> 走正常通道，不误报
"""
from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_client(content: str | None, tool_calls: list | None):
    """构造一个假的 AsyncOpenAI client，返回指定形态的响应。"""
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]

    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=resp)
    return client


def _llm():
    from framework.shared.llm_compat import ChatOpenAICompatible
    return ChatOpenAICompatible(model="glm-5.3-flash", api_key="dummy", base_url="http://x/v4")


def _run(llm, client, output_format):
    from browser_use.llm.messages import SystemMessage, UserMessage
    msgs = [SystemMessage(content="sys"), UserMessage(content="user")]
    with patch.object(llm, "_client", return_value=client):
        return asyncio.run(llm._invoke_with_content_fallback(msgs, output_format, stop=None))


def test_content_channel_json_is_recovered(capsys) -> None:
    """① content 里是合法 JSON -> 解析复用，并**出声**说明走了哪条通道。"""
    from framework.features.f02_semantic.explorer_explore import _PlanModel

    payload = {"steps": [{"order": 1, "op": "fill", "desc": "填账号",
                          "semantic_name": "账号", "value": "super"}]}
    client = _make_client(json.dumps(payload, ensure_ascii=False), None)
    r = _run(_llm(), client, _PlanModel)

    assert r is not None
    assert len(r.completion.steps) == 1
    assert r.completion.steps[0].op == "fill"
    out = capsys.readouterr().out
    assert "content 通道" in out, "兜底命中时必须打印通道说明（静默改变行为等同造假）"


def test_content_channel_tolerates_fence_and_chatter() -> None:
    """② 围栏 / 前后废话都要能吃下。"""
    from framework.features.f02_semantic.explorer_explore import _PlanModel

    body = json.dumps({"steps": [{"order": 1, "op": "click", "desc": "点登录",
                                  "semantic_name": "登_录"}]}, ensure_ascii=False)
    client = _make_client(f"好的，结果如下：\n```json\n{body}\n```\n以上。", None)
    r = _run(_llm(), client, _PlanModel)
    assert len(r.completion.steps) == 1
    assert r.completion.steps[0].op == "click"


def test_content_not_json_raises_not_fakes_success() -> None:
    """③ content 不是 JSON -> **如实抛错**，绝不编一个空壳假装成功。"""
    from browser_use.llm.exceptions import ModelProviderError
    from framework.features.f02_semantic.explorer_explore import _PlanModel

    client = _make_client("我觉得这个页面应该先登录，然后再搜索订单。", None)
    with pytest.raises(ModelProviderError) as ei:
        _run(_llm(), client, _PlanModel)
    assert "不是可解析的 JSON" in str(ei.value)


def test_empty_response_raises_clearly() -> None:
    """④ 既没 tool_calls 也没 content -> 单独报错，别混进「解析失败」。"""
    from browser_use.llm.exceptions import ModelProviderError
    from framework.features.f02_semantic.explorer_explore import _PlanModel

    client = _make_client(None, None)
    with pytest.raises(ModelProviderError) as ei:
        _run(_llm(), client, _PlanModel)
    assert "既没有 tool_calls 也没有 content" in str(ei.value)


def test_tool_calls_path_does_not_print_content_notice(capsys) -> None:
    """⑤ 正常 tool_calls 通道**不许**误报「走了 content 通道」。"""
    from framework.features.f02_semantic.explorer_explore import _PlanModel

    tc = MagicMock()
    tc.function.arguments = json.dumps(
        {"steps": [{"order": 1, "op": "click", "desc": "点", "semantic_name": "登_录"}]},
        ensure_ascii=False)
    client = _make_client(None, [tc])
    r = _run(_llm(), client, _PlanModel)
    assert len(r.completion.steps) == 1
    out = capsys.readouterr().out
    assert "content 通道" not in out, "走 tool_calls 时不该打印 content 通道提示（会误导排查）"
