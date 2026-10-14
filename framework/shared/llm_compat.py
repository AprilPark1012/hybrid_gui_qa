# -*- coding: utf-8 -*-
"""通用 OpenAI 兼容 LLM 客户端（V8.6.1）。

**为什么需要它**：browser_use 自带的 `ChatDeepSeek` 已能满足「任意 OpenAI 兼容端点」
的基本要求（发 `tools` + `tool_choice`，走 function calling），但它的请求参数是
**写死的** —— 只有 temperature / max_tokens / top_p / seed，外加一个只在
`deepseek-v4` 模型名上才会发的 `thinking` 开关。

而 2026 年这一代国产旗舰正在集体**取消「关闭思考」的选项**：
  - **GLM-5.3**：官方文档明确「从 GLM-5.3 起，完全关闭推理的选项不再存在」，
    思考强度分 low / high / max 三档，**默认 max**；
  - **MiniMax-M3.1-Flash-Preview**：不允许 `thinking.type=disabled`（报 2013）。
框架的探索阶段**每一步都要调一次 LLM**（一次端到端十几二十次调用），走服务端默认档
就等于每次都跑最贵的推理级别 —— 又慢又贵。所以需要能把强度**压下来**。

**实现方式**：**子类 + 覆盖 `_request_kwargs()`**，不 fork 第三方代码。

    [!] 已知风险：`_request_kwargs` 是 browser_use 的**私有方法**，上游改签名我们会
    被静默忽略（参数发不出去、用户以为压下来了其实没压）。
    -> 对策：判据**直接断言 `_request_kwargs()` 的产出**（而不是断言「我们调用了它」），
       上游一变立刻红。见 tests/特性10-CLI帮助契约/test_llm_doctor.py

**参数落点**：`extra_body` —— OpenAI SDK 会把它 merge 进请求体，最终成为**顶层**
`reasoning_effort` 字段。实测三家的 `reasoning_effort` 都是顶层字段，所以这样发是对的。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from browser_use.llm.deepseek.chat import ChatDeepSeek
from browser_use.llm.messages import BaseMessage
from browser_use.llm.schema import SchemaOptimizer
from browser_use.llm.views import ChatInvokeCompletion

__all__ = ["ChatOpenAICompatible", "REASONING_EFFORT_EXAMPLES"]

#: 帮助文案里举例用的取值。**刻意不做白名单校验** —— 各家的档位名一直在变
#: （OpenAI 是 low/medium/high，GLM-5.3 是 low/high/max），写死白名单会挡住
#: 用户试新档位；而且这个值最终是发给远端端点的，合不合法该由端点说了算。
REASONING_EFFORT_EXAMPLES = ("low", "medium", "high", "max")

#: 「端点不接受这种 tool_choice」的错误特征。实测样本（DeepSeek thinking 模式）：
#:     400 Thinking mode does not support this tool_choice
#: 写得**窄一点**：必须同时出现 tool_choice 与「不支持」语义，否则会把别的 400 也吞掉
#: （误吞 = 拿错兜底盖住真故障，属于静默兜底）。
_TOOL_CHOICE_REJECTED = re.compile(
    r"tool_choice[^.]{0,80}(does\s*n[o']?t\s+support|not\s+support|unsupported|unrecognized|invalid)"
    r"|(does\s*n[o']?t\s+support|not\s+support|unsupported|unrecognized|invalid)[^.]{0,80}tool_choice",
    re.I | re.S,
)

#: 已知「拒指名函数」的端点（base_url + model）。记下来后**后续请求直接走降级形态**，
#: 不再每次白试一次（一次端到端十几二十次调用，白试就是十几次浪费）。
#: 为什么不用实例属性：`ChatDeepSeek` 是 dataclass，实例上赋值的行为不可靠；
#: 而且这个是「端点特性」不是「客户端状态」，放在模块级语义更准。
_REJECTED_ENDPOINTS: set[tuple[str, str]] = set()


def _endpoint_key(obj: Any) -> tuple[str, str]:
    return (str(getattr(obj, "base_url", "") or ""), str(getattr(obj, "model", "") or ""))


def _unwrap_chain(err: BaseException) -> list[str]:
    """异常可能被包了好几层（ModelProviderError from APIStatusError）—— 逐层取文案。

    只看最外层会漏：上游把 `APIStatusError` 包成 `ModelProviderError`，
    而带 "tool_choice" 字样的原文在**内层**。
    """
    out: list[str] = []
    cur: BaseException | None = err
    for _ in range(6):
        if cur is None:
            break
        out.append(str(cur))
        cur = cur.__cause__ or cur.__context__
    return out


def rejects_named_tool_choice(err: BaseException) -> bool:
    """这个异常是不是「端点不接受指名函数形式的 tool_choice」。"""
    return any(_TOOL_CHOICE_REJECTED.search(s) for s in _unwrap_chain(err))


@dataclass
class ChatOpenAICompatible(ChatDeepSeek):
    """任何 OpenAI 兼容端点都能用的客户端（结构化输出走 `tools` / function calling）。

    比 `ChatDeepSeek` 多做两件事：
        1. 把 `reasoning_effort` 塞进请求体（压思考强度）；
        2. **tool_choice 兜底**：端点若不接受「指名函数」形式，自动降级重试一次。

    字段说明：
        reasoning_effort: 思考强度（`None` = **不发这个字段**，保持各端服务端默认）。
            想省钱省时间就设 `low` —— 探索阶段要的是「看懂页面」，不需要 max 档推理。
    """

    reasoning_effort: str | None = None

    def _request_kwargs(self) -> dict[str, Any]:
        common = super()._request_kwargs()
        if self.reasoning_effort:
            # 必须**合并**而不是覆盖：deepseek-v4 的 thinking 开关也住在 extra_body 里，
            # 直接赋值会把那个开关吃掉 —— 静默改变行为等同造假，这里宁可多写三行。
            extra = dict(common.get("extra_body") or {})
            extra["reasoning_effort"] = self.reasoning_effort
            common["extra_body"] = extra
        return common

    async def ainvoke(  # type: ignore[override]
        self,
        messages: list[BaseMessage],
        output_format: Any = None,
        tools: list[dict[str, Any]] | None = None,
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> Any:
        """结构化输出调用，带「指名函数被拒」的**有界降级**。

        为什么要这一层（2026-10-14 实测）：上游 `ainvoke` 在给了 `output_format` 时会发
            tool_choice = {'type': 'function', 'function': {'name': <模型类名>}}
        而**思考模式的端点拒这种取值**（出厂配置的 `deepseek-flash` 就报
        400 `Thinking mode does not support this tool_choice`）。实测该端点：

            不传 tool_choice / "auto"  -> OK，正常返回 tool_calls
            "required" / 指名函数      -> 400

        -> 撞上就**改用 `tool_choice=auto` 自己发一次请求**，把结构化输出路径救回来。

        边界（兜底必须有边界、可审计）：
            · **只重试一次**，不循环；
            · 只认特征明确的错误（tool_choice + 不支持语义），别的错照抛；
            · 端点特性记进 `_REJECTED_ENDPOINTS`，后续直接走降级形态，不再白试；
            · 降级发生时会打印一行，**不静默**；
            · 若降级后模型仍没返回 tool_calls，异常照抛 —— 由上层（explorer）决定
              退到纯文本路径，不在这一层假装成功。
        """
        has_schema = output_format is not None and hasattr(output_format, "model_json_schema")
        if not has_schema:
            return await super().ainvoke(messages, output_format=output_format,
                                         tools=tools, stop=stop, **kwargs)

        key = _endpoint_key(self)
        if key in _REJECTED_ENDPOINTS:
            return await self._invoke_without_tool_choice(messages, output_format,
                                                          stop=stop, **kwargs)
        try:
            return await super().ainvoke(messages, output_format=output_format,
                                         tools=tools, stop=stop, **kwargs)
        except Exception as e:
            if not rejects_named_tool_choice(e):
                raise
            _REJECTED_ENDPOINTS.add(key)
            print(f"      [llm] [!] 端点不接受「指名函数」形式的 tool_choice（{key[1]}）"
                  f" -> 自动降级改用 tool_choice=auto 重试（本进程内后续直接走降级形态）")
            return await self._invoke_without_tool_choice(messages, output_format,
                                                          stop=stop, **kwargs)

    async def _invoke_without_tool_choice(
        self,
        messages: list[BaseMessage],
        output_format: Any,
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> Any:
        """降级形态：**自己发请求，不发 `tool_choice`**。

        为什么不借道上游的「只给 tools、不给 output_format」那条分支：
        实测它自己有 bug —— 那条分支把原始 dict 塞进
        `ChatInvokeCompletion(completion=<dict>)`，pydantic 按 TypeVar 上界 `BaseModel`
        去校验，直接报 `BaseModel cannot be instantiated directly`。
        （= 上游那条分支在当前版本是走不通的死路；我们只能自己发。）

        边界：拿不到 tool_calls 就**如实抛错**，绝不返回一个"看起来成功"的空壳 ——
        由上层（explorer）决定退到纯文本路径。
        """
        import json

        from browser_use.llm.deepseek.serializer import DeepSeekMessageSerializer
        from browser_use.llm.exceptions import ModelProviderError

        name = getattr(output_format, "__name__", "result")
        try:
            schema = SchemaOptimizer.create_optimized_json_schema(output_format)
        except Exception:
            # 优化器是上游私有实现，它变了不该让整条链路挂掉 —— 退回 pydantic 原生 schema
            schema = output_format.model_json_schema()
        schema = dict(schema or {})
        schema.pop("title", None)
        call_tools = [{
            "type": "function",
            "function": {
                "name": name,
                "description": f"Return a JSON object of type {name}",
                "parameters": schema,
            },
        }]

        common = self._request_kwargs()
        if stop:
            common["stop"] = stop
        client = self._client()
        try:
            resp = await client.chat.completions.create(  # type: ignore
                model=self.model,
                messages=DeepSeekMessageSerializer.serialize_messages(messages),  # type: ignore
                tools=call_tools,  # type: ignore
                # ★ 关键：tool_choice 发 **auto**（= 让模型自己决定要不要调工具）。
                #   实测这类端点拒的是「指名函数」与 required，接受 auto / 不传；
                #   这里显式发 auto 而不是省略 —— 省略等于赌「服务端默认就是 auto」，
                #   显式写出来才能被判据钉住、也便于出问题时一眼看出我们发了什么。
                tool_choice="auto",  # type: ignore
                **common,
            )
        except Exception as e:
            raise ModelProviderError(str(e), model=self.name) from e

        msg = resp.choices[0].message
        if not msg.tool_calls:
            raise ModelProviderError(
                "降级（tool_choice=auto）后模型没有返回 tool_calls —— "
                "这类端点在 auto 下可能直接给自然语言；上层会退到纯文本路径",
                model=self.name)
        raw = msg.tool_calls[0].function.arguments
        parsed = json.loads(raw) if isinstance(raw, str) else raw
        return ChatInvokeCompletion(completion=output_format.model_validate(parsed), usage=None)
