#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""直接用**框架真链路**复刻 explore 的调用，看能不能复现 `got none`。

为什么必须这一步：
  前面用 curl 裸调 API 测了 100+ 次（强制 tool_choice / 真实 _PlanModel schema /
  不同 system prompt / 0~2 轮 history），**全部 100% 成功**。
  但用户框架真实跑 `explore --ai` 时，登录页那一步**几乎必现**
  `ModelProviderError: Expected tool_calls in response but got none`。

  差异只可能在**封装层**（框架走 ChatOpenAICompatible.ainvoke，不是裸 curl）：
    · reasoning_effort 怎么塞进请求体
    · tool_choice 的降级判断 rejects_named_tool_choice
    · SystemMessage/UserMessage -> dict 的转换
    · 内部 AsyncOpenAI 客户端的参数

  这条对应记忆里的教训：「手工 new 一个对象做实验 != 真链路拿到的对象」。

做法：完全照 explorer_explore.py:938-957 的写法调用，跑 N 次统计复现率。
"""
import asyncio
import collections
import json
import os
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# 用项目 .env 的配置（和框架真实跑完全一致）
from dotenv import load_dotenv  # type: ignore[import-not-found]
load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=True)

from framework.shared.config import llm_from_env, llm_vendor_of
from framework.features.f02_semantic.explorer_explore import (
    _PlanModel, _PLANNER_SYSTEM, _plan_to_steps,
)
from browser_use.llm.messages import SystemMessage, UserMessage

N = int(os.environ.get("PROBE_N", "10"))

# 与用户日志第 6-8 行一致的登录页场景
PROMPT = (
    "在登录页填写账号 super、密码 super@123（两个输入框各填一个）\n"
    "DOM 事实：7 条记录（0 条带非默认状态），已并入清单 3 条（其中带状态 0 条）：\n"
    "- '账号' 输入框\n- '密码' 输入框\n- '登_录' 按钮\n"
)


async def main() -> None:
    print("=== 配置（来自 .env，与框架真实跑一致）===", flush=True)
    for k in ("LLM_MODEL", "LLM_BASE_URL", "LLM_REASONING_EFFORT", "HYBRID_LLM_TIMEOUT"):
        print(f"  {k}={os.environ.get(k) or '(未设)'}", flush=True)
    obj = llm_from_env()
    print(f"  实际客户端类: {type(obj).__name__}", flush=True)
    try:
        print(f"  vendor: {llm_vendor_of(obj)}", flush=True)
    except Exception:
        pass
    print(f"  timeout 属性: {getattr(obj, 'timeout', '(无)')}", flush=True)
    print(f"\n=== 复刻 explore 调用 {N} 次 ===\n", flush=True)

    stats = collections.Counter()
    times = []
    fails = []

    for i in range(1, N + 1):
        msgs = [SystemMessage(content=_PLANNER_SYSTEM), UserMessage(content=PROMPT)]
        t0 = time.time()
        try:
            r = await obj.ainvoke(msgs, output_format=_PlanModel)
            el = time.time() - t0
            times.append(el)
            # 不调 _plan_to_steps（它需要真实 page_items，传 None 会 TypeError 混淆统计）；
            # 这里只验证「有没有拿到结构化 completion」
            comp = getattr(r, "completion", None)
            n_steps = len(getattr(comp, "steps", []) or []) if comp is not None else 0
            stats["OK"] += 1
            print(f"  [{i}/{N}] OK  {el:6.1f}s  结构化步骤数={n_steps}", flush=True)
        except Exception as e:
            el = time.time() - t0
            times.append(el)
            msg = f"{type(e).__name__}: {str(e)[:150]}"
            if "tool_calls" in msg.lower():
                stats["got_none"] += 1
                tag = "*** got none 复现 ***"
            else:
                stats["其他异常"] += 1
                tag = "其他异常"
            fails.append(msg)
            print(f"  [{i}/{N}] {tag}  {el:6.1f}s  {msg}", flush=True)
        await asyncio.sleep(1.5)

    print("\n" + "=" * 70, flush=True)
    print(f"结果: {dict(stats)}", flush=True)
    if times:
        print(f"平均耗时 {sum(times)/len(times):.1f}s  范围 {min(times):.1f}~{max(times):.1f}s", flush=True)
    if fails:
        print("\n失败样本（前 3 条）:", flush=True)
        for f in fails[:3]:
            print(f"  - {f}", flush=True)
    rate = stats.get("got_none", 0) / N
    print()
    if rate > 0:
        print(f"[结论] **真链路复现成功**：got none 出现 {stats['got_none']}/{N}（{rate:.0%}）"
              f" --> 问题在框架封装层，与 curl 层无关", flush=True)
    else:
        print(f"[结论] 真链路 {N} 次**未复现** got none —— 说明还需要更多变量"
              f"（真实 DOM 探针 / 更长 prompt / 并发）", flush=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        traceback.print_exc()
        sys.exit(1)
