# -*- coding: utf-8 -*-
"""特性2 · 上游不支持 `tool_choice`（thinking mode）时要**跳过结构化路径并降噪**（V8.4.1）。

事故（AprilPark1012 2026-10-09 Windows 实录 · 每一轮都出现一次）：
    [explore] 第 1/3 次结构化输出失败 -> 结构化输出路径 ModelProviderError:
      Error code: 400 - {'error': {'message': 'Thinking mode does not support this tool_choice',
       'type': 'invalid_request_error'}}

    4 轮实测里 **4 次**出现（每轮 1 次）。它有重试兜底（第 2 次能成），所以不致命；
    但代价是：① 白烧一次 LLM 调用；② 用户看到一行 `ModelProviderError` 红字会以为框架坏了。

口径：这是**上游能力差异**（不是抖动）—— 抖动该重试，能力缺失该**记住并换路**。
      识别到「不支持 tool_choice」-> 本轮及后续**直接走纯文本路径**，日志降为 `[info]`。
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
EXPLORER = REPO / "framework" / "tools" / "explore" / "explorer.py"


def _src() -> str:
    return EXPLORER.read_text(encoding="utf-8")


def test_tool_choice_error_is_recognized():
    """必须能识别「不支持 tool_choice / thinking mode」这类**能力差异**错误。"""
    src = _src()
    assert "tool_choice" in src, "没有针对 tool_choice 不支持的识别"
    low = src.lower()
    assert ("thinking" in low) or ("不支持" in src and "tool_choice" in src), (
        "没识别 DeepSeek thinking mode 这条具体报错（实测原文含 'Thinking mode does not support'）"
    )


def test_unsupported_short_circuits_to_text_path():
    """识别到之后必须**跳过结构化路径**（不再每轮白试一次）。"""
    src = _src()
    assert "_no_structured" in src, (
        "没有「本会话禁用结构化输出」的开关 -> 每轮都会重蹈覆辙（白烧一次调用）"
    )
    # 开关必须真的被用在「进入结构化路径」的判断上
    assert "not _no_structured" in src, (
        "开关声明了但没接在结构化路径的判断上 -> 等于没写"
    )
    # 且必须**在识别到能力差异的分支里**被置位。
    # [!] 别用 `src.index("tool_choice")` 取窗口 —— 文件里 tool_choice 出现多处，
    #     第一次可能在别处（第一版判据这么写就误判了）-> 直接看置位语句本身在不在。
    assert "_no_structured = True" in src, (
        "识别到 tool_choice 不支持后没有置位开关 -> 每轮都会重蹈覆辙"
    )
    i = src.index("_no_structured = True")
    window = src[max(0, i - 700): i + 200]
    assert "tool_choice" in window or "thinking mode" in window, (
        "开关置位点不在「识别 tool_choice / thinking mode」的判定分支里"
    )


def test_log_is_downgraded_to_info():
    """降噪：能力差异不是错误，日志该是 `[info]` 而不是 `ModelProviderError` 红字。"""
    src = _src()
    assert "[info]" in src, "没有把这类情况降级成 [info] 打印"
    i = src.find("tool_choice")
    assert i > 0, "找不到 tool_choice 处理处"
    window = src[max(0, i - 1500): i + 1500]
    assert "[info]" in window, (
        "tool_choice 处理处附近没有 [info] 降噪打印 -> 用户还是会看到红字"
    )
