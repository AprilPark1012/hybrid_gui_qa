# -*- coding: utf-8 -*-
"""特性10 · 思考模式端点兼容：`tool_choice` 拒绝时的**有界降级**（V8.6.1）。

背景（2026-10-14 实测，不是推断）：出厂配置的 `deepseek-flash` 报
    400 Thinking mode does not support this tool_choice
=> 框架的**结构化输出路径一直失败、一直走文本兜底**。逐步实验定位：

    tool_choice 传什么        结果
    ----------------------    --------------------------------------
    不传 / "auto"             OK，正常返回 tool_calls
    "required" / 指名函数      400（上游 `ChatDeepSeek` 发的正是「指名函数」）

修法：撞到该错误时，**改用 tool_choice=auto 自己发一次请求**。
（为什么不用上游「只给 tools」那条分支：实测它自己有 bug —— 把 dict 塞进
 `ChatInvokeCompletion(completion=<dict>)`，pydantic 按 TypeVar 上界 `BaseModel`
 校验，报 `BaseModel cannot be instantiated directly`。）

本文件钉住的是**兜底的边界**，不只是"能用"：
  · 只认特征明确的错（别的错必须照抛，误吞 = 拿兜底盖真故障）；
  · 只重试一次、且记住端点特性（不每次白试）；
  · 降级**必须真发 tool_choice=auto**、且不能把 reasoning_effort 弄丢；
  · 拿不到 tool_calls 要**如实抛错**，不许返回"看起来成功"的空壳；
  · 降级发生要**有痕迹**（不静默）。
"""

from __future__ import annotations

import asyncio
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from framework.shared.llm_compat import (  # noqa: E402
    ChatOpenAICompatible,
    _REJECTED_ENDPOINTS,
    rejects_named_tool_choice,
)

REJECT_MSG = "Thinking mode does not support this tool_choice"
TOOL = "Ping"


class Ping(BaseModel):
    ok: bool


def _resp(name: str, args: dict) -> dict:
    return {
        "id": "x", "object": "chat.completion", "created": 0, "model": "m",
        "choices": [{"index": 0, "finish_reason": "tool_calls",
                     "message": {"role": "assistant", "content": None,
                                 "tool_calls": [{"id": "c1", "type": "function",
                                                 "function": {"name": name,
                                                              "arguments": json.dumps(args)}}]}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


class _FakeEndpoint:
    """模拟「思考模式」端点：**只拒指名函数**，接受 auto / 不传。

    reject_mode:
        "named"  -> 指名函数 400，其余 200（= DeepSeek thinking 的真实行为）
        "all"    -> 任何带 tool_choice 的请求都 400（极端端点，用来验边界）
        "no_tool"-> 一律 200 但不返回 tool_calls（验「不许假装成功」）
        "other"  -> 一律 500（验「别的错不许被吞」）
    """

    def __init__(self, reject_mode: str = "named"):
        self.reject_mode = reject_mode
        self.hits: list[dict] = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n) or b"{}")
                outer.hits.append(body)
                tc = body.get("tool_choice")
                named = isinstance(tc, dict)
                if outer.reject_mode == "other":
                    raw, code = json.dumps({"error": {"message": "internal"}}).encode(), 500
                elif outer.reject_mode == "no_tool":
                    raw = json.dumps({
                        "id": "x", "object": "chat.completion", "created": 0, "model": "m",
                        "choices": [{"index": 0, "finish_reason": "stop",
                                     "message": {"role": "assistant", "content": "好的"}}],
                        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                    }).encode()
                    code = 200
                elif named and outer.reject_mode in ("named", "all"):
                    raw = json.dumps({"error": {"message": REJECT_MSG,
                                                "type": "invalid_request_error"}}).encode()
                    code = 400
                elif tc is not None and outer.reject_mode == "all":
                    raw = json.dumps({"error": {"message": REJECT_MSG}}).encode()
                    code = 400
                else:
                    raw = json.dumps(_resp(TOOL, {"ok": True})).encode()
                    code = 200
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def log_message(self, format, *args):
                pass

        self.srv = HTTPServer(("127.0.0.1", 0), H)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/v1"

    def stop(self):
        self.srv.shutdown()
        self.srv.server_close()


@pytest.fixture(autouse=True)
def _clear_cache():
    """每个用例前清掉「已知拒指名函数端点」缓存 —— 否则用例之间会互相污染。"""
    _REJECTED_ENDPOINTS.clear()
    yield
    _REJECTED_ENDPOINTS.clear()


def _client(endpoint: _FakeEndpoint, **kw) -> ChatOpenAICompatible:
    return ChatOpenAICompatible(api_key="sk-test", base_url=endpoint.base_url,
                                model="deepseek-flash", temperature=0.0, **kw)


def _run(coro):
    return asyncio.run(coro)


def _msgs():
    from browser_use.llm.messages import UserMessage
    return [UserMessage(content="把 ok 设 True")]


# ==========================================================================
# 一、特征识别必须「窄」（误吞 = 拿兜底盖真故障）
# ==========================================================================
@pytest.mark.parametrize("text,expect", [
    ("400 Thinking mode does not support this tool_choice", True),
    ("tool_choice is not supported by this model", True),
    ("unsupported value for tool_choice", True),
    ("500 Internal Server Error", False),
    ("401 invalid_api_key", False),
    ("context length exceeded", False),
    ("Rate limit reached", False),
])
def test_detection_is_narrow(text, expect):
    assert rejects_named_tool_choice(RuntimeError(text)) is expect, (
        f"特征判定错了：{text!r} 判成 {not expect}"
    )


def test_detection_sees_through_wrapping():
    """上游把 APIStatusError 包成 ModelProviderError —— 原文在内层，只看外层会漏。"""
    inner = RuntimeError(REJECT_MSG)
    outer = RuntimeError("ModelProviderError: 400 Bad Request")
    outer.__cause__ = inner
    assert rejects_named_tool_choice(outer) is True, (
        "没穿透异常链 —— 真实链路里上游就是这么包一层的，会漏判"
    )


# ==========================================================================
# 二、降级：真的救回结构化输出，且发出的是 auto
# ==========================================================================
def test_fallback_recovers_structured_output():
    ep = _FakeEndpoint("named")
    try:
        r = _run(_client(ep).ainvoke(_msgs(), output_format=Ping))
        assert isinstance(r.completion, Ping) and r.completion.ok is True, (
            f"降级没救回结构化输出，拿到的是 {type(r.completion).__name__}"
        )
    finally:
        ep.stop()


def test_fallback_sends_tool_choice_auto():
    """必须**真发 auto**（不是省略、更不是继续发指名函数）。"""
    ep = _FakeEndpoint("named")
    try:
        _run(_client(ep).ainvoke(_msgs(), output_format=Ping))
        sent = [h for h in ep.hits if "tools" in h]
        assert sent, "没有带 tools 的请求"
        assert sent[-1].get("tool_choice") == "auto", (
            f"降级那次发的 tool_choice = {sent[-1].get('tool_choice')!r}，应为 'auto'"
        )
        assert isinstance(sent[0].get("tool_choice"), dict), (
            "第一次没发「指名函数」—— 那说明我们没走原始路径，兜底就是空转"
        )
    finally:
        ep.stop()


def test_fallback_keeps_reasoning_effort():
    """降级不能把 reasoning_effort 弄丢（两条路径的可调项必须一致）。"""
    ep = _FakeEndpoint("named")
    try:
        _run(_client(ep, reasoning_effort="low").ainvoke(_msgs(), output_format=Ping))
        last = [h for h in ep.hits if "tools" in h][-1]
        assert last.get("reasoning_effort") == "low", (
            "降级路径丢了 reasoning_effort —— 用户设的低档在最需要省的那条路上失效了"
        )
    finally:
        ep.stop()


# ==========================================================================
# 三、有界：只重试一次；端点特性记住后不再白试
# ==========================================================================
def test_fallback_is_bounded_and_then_remembered():
    ep = _FakeEndpoint("named")
    try:
        c = _client(ep)
        _run(c.ainvoke(_msgs(), output_format=Ping))
        first = len(ep.hits)
        _run(c.ainvoke(_msgs(), output_format=Ping))
        second = len(ep.hits) - first
        # 第一次：指名函数(400) + auto(200) = 2 次；第二次：直接 auto = 1 次
        assert first == 2, f"第一次发了 {first} 次请求（应为 2：试探 + 降级）"
        assert second == 1, (
            f"第二次发了 {second} 次请求（应为 1）—— 没记住端点特性，每次都在白试，"
            f"一次端到端十几二十次调用就是十几次浪费"
        )
    finally:
        ep.stop()


def test_fallback_has_visible_trace(capsys):
    """兜底必须留痕（静默兜底 = 造假）。"""
    ep = _FakeEndpoint("named")
    try:
        _run(_client(ep).ainvoke(_msgs(), output_format=Ping))
        out = capsys.readouterr().out
        assert "[!]" in out and "tool_choice" in out, (
            "降级没打印任何痕迹 —— 用户会以为一切正常"
        )
    finally:
        ep.stop()


# ==========================================================================
# 四、边界：不许假装成功，也不许吞掉别的错
# ==========================================================================
def test_other_errors_are_not_swallowed():
    """非 tool_choice 的错（这里用 500）必须照抛，不能被兜底盖住。

    [!] 别拿「请求次数」当判据：OpenAI SDK 自己对 5xx **有内建重试**（默认 3 次尝试），
        所以 500 那条路本来就可能发多次 —— 那跟我们的兜底无关。
        真正要钉的是「**我们有没有发 auto**」：发了就等于把真故障当 tool_choice 问题兜了。
    """
    ep = _FakeEndpoint("other")
    try:
        with pytest.raises(Exception) as ei:
            _run(_client(ep).ainvoke(_msgs(), output_format=Ping))
        assert not rejects_named_tool_choice(ei.value), (
            "把一个 500 误判成了 tool_choice 问题 —— 会拿兜底盖住真故障"
        )
        assert ep.hits, "请求都没发出去，这个用例没验到东西"
        assert not any(h.get("tool_choice") == "auto" for h in ep.hits), (
            "对 500 触发了降级（发了 tool_choice=auto）—— 兜底越界了"
        )
        assert _REJECTED_ENDPOINTS == set(), (
            "把 500 的端点误记成「拒指名函数」—— 后续所有请求都会走降级形态"
        )
    finally:
        ep.stop()


def test_no_tool_calls_raises_not_fake_success():
    """降级后模型没给 tool_calls：要如实抛错，不许返回空壳。"""
    ep = _FakeEndpoint("no_tool")
    try:
        with pytest.raises(Exception) as ei:
            _run(_client(ep).ainvoke(_msgs(), output_format=Ping))
        assert "tool_calls" in str(ei.value), (
            f"错误信息没说清是「没返回 tool_calls」，上层无法判断该退到文本路径：{ei.value}"
        )
    finally:
        ep.stop()


def test_no_output_format_takes_original_path():
    """纯文本调用（不带 output_format）不该被这层兜底动到。"""
    ep = _FakeEndpoint("named")
    try:
        c = _client(ep)
        assert not hasattr(None, "model_json_schema")
        _run(c.ainvoke(_msgs()))   # 不传 output_format
        assert len(ep.hits) == 1, "纯文本调用被兜底逻辑多发了请求"
        assert _REJECTED_ENDPOINTS == set(), "纯文本调用不该往端点缓存里写东西"
    finally:
        ep.stop()
