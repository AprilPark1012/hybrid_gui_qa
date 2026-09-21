"""LLM 抖动退避重试的回归测试（2026-09-13 冷启动排查时挖出的真 bug）。

背景：`_ai_explore_async` 里 `await asyncio.sleep(...)`（重试退避）用的是**函数内局部** import，
只有 `ai_explore` / `_get_llm_text` 那两个函数里 import 了 asyncio ⇒ 重试路径一触发就
`NameError: name 'asyncio' is not defined` 崩溃。后果很严重：
  ① 我们最依赖的「DeepSeek function calling 间歇抖动 → 重试恢复」**从来没生效过**；
  ② LLM 401/抖动时抛的是 traceback（exit 1），而不是干净的「AI 不可用 → exit 2」，防假 AI 闸门也被绕了。

注意每次尝试里其实有**两条路径**：先结构化输出（ainvoke + output_format），失败再走纯文本兜底
（ainvoke 无 output_format）⇒ 一次 attempt 最多 2 次 ainvoke。

跑法（不需要 key、不需要 demo、秒级）：
    cd ~/hybrid_gui_qa && source .venv/bin/activate && python -m pytest tests/test_llm_retry.py -q
"""
from __future__ import annotations

import asyncio

import pytest

from framework.tools.common import config
from framework.tools.explore import explorer
from framework.tools.explore.explorer import AiExploreError, _ai_explore_async

ITEMS = [{"semantic_name": "搜索", "role": "button", "name": "搜索", "test_id": "btn-search"}]


def _plan_once(action="click", sn="搜索", desc="点搜索"):
    return explorer._PlanModel(steps=[
        explorer._StepModel(order=1, action=action, semantic_name=sn,
                            value=None, assertion=None, description=desc),
    ])


class _Completion:
    def __init__(self, payload):
        self.completion = payload


def test_retry_loop_actually_retries(monkeypatch):
    """重试 N 次后必须抛 AiExploreError（而不是 NameError 崩在退避那行）。"""

    class _AlwaysFailLLM:
        def __init__(self):
            self.calls = 0

        async def ainvoke(self, msgs, output_format=None):
            self.calls += 1
            raise RuntimeError("boom: 上游抖动")

    fake = _AlwaysFailLLM()
    monkeypatch.setattr(config, "llm_from_env", lambda: fake)
    monkeypatch.setenv("HYBRID_LLM_ATTEMPTS", "3")

    slept: list[float] = []

    async def _no_sleep(sec):
        slept.append(sec)          # 不真等，但记录"退避确实被调用过"

    monkeypatch.setattr(asyncio, "sleep", _no_sleep)

    with pytest.raises(AiExploreError) as e:
        asyncio.run(_ai_explore_async("在搜索框输入 1005 点搜索", ITEMS, "http://localhost:8000"))

    assert fake.calls >= 3, f"应当至少尝试 3 轮，实际 ainvoke 调用 {fake.calls} 次"
    assert slept == [1.5, 3.0], f"退避应当按 1.5×attempt 递增，实际 {slept}"
    assert "重试 3 次" in str(e.value)   # 报错信息要能看出"试过了、不是一次就放弃"


def test_retry_then_success_returns_elementmap(monkeypatch):
    """第 1 轮抖动、第 2 轮成功 → 必须正常拿到 ElementMap（这才是重试的意义）。"""

    class _FlakyLLM:
        def __init__(self):
            self.calls = 0

        async def ainvoke(self, msgs, output_format=None):
            self.calls += 1
            if self.calls <= 2:            # 第 1 轮：结构化失败 + 文本兜底也失败
                raise RuntimeError("boom: 第一次抖动")
            return _Completion(_plan_once())   # 第 2 轮：结构化成功

    fake = _FlakyLLM()
    monkeypatch.setattr(config, "llm_from_env", lambda: fake)
    monkeypatch.setenv("HYBRID_LLM_ATTEMPTS", "3")

    async def _no_sleep(sec):
        return None

    monkeypatch.setattr(asyncio, "sleep", _no_sleep)

    m = asyncio.run(_ai_explore_async("点搜索", ITEMS, "http://localhost:8000"))
    assert fake.calls == 3, "应当抖动一轮后重试成功（第 3 次调用拿到步骤）"
    assert m.url == "http://localhost:8000"
    assert m.steps[0].action == "goto"       # _finalize_map 会补首步 goto
    assert any(s.action == "click" for s in m.steps)


def test_asyncio_is_imported_at_module_level():
    """源码级防复发：模块顶部必须有 asyncio（协程里用 asyncio.sleep 靠它）。"""
    src = open(explorer.__file__, encoding="utf-8").read()
    head = src.split("class _StepModel", 1)[0]
    assert "import asyncio" in head, "explorer.py 顶部必须 import asyncio（否则重试退避会 NameError）"
