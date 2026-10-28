"""V8.7.5 判据：llm-doctor 的「厂商显示」与「大 prompt 实探」。

事故背景（2026-10-27 用户实测）：
  ① `llm-doctor` 打印 `provider deepseek`，但端点明明是智谱 GLM ——
     因为 `ChatOpenAICompatible` 继承 `ChatDeepSeek`，带着实现类里写死的 provider 字段。
     用户看到就以为配错了。教训：**「实现出处」不等于「端点归属」**，体检必须报后者。
  ② `llm-doctor` 原本只发 2 次极小 schema 请求，都通过 -> 结论「可以用」；
     但真实 explore 的 prompt 是 11 万字符级别，GLM-5.3 + high 档要 312 秒，
     默认 180 秒超时 -> 真跑必然失败。**体检给了假保证**，所以加第 3 项大 prompt 实探。
  ③ 结构化路径报「Expected tool_calls in response but got none」时，用户会以为是
     「模型不稳定」去换模型；其实几乎必然是 `reasoning_effort` 太低（实测 low 档
     在 11.6 万字符 prompt 上完全不返回 tool_calls）。必须在报错当场点破。
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

BASE = Path(__file__).resolve().parents[2]
CLI_SRC = BASE / "framework/features/f10_cli/cli.py"
EXPLORE_SRC = BASE / "framework/features/f02_semantic/explorer_explore.py"


def _cli() -> str:
    return CLI_SRC.read_text(encoding="utf-8")


def _explore() -> str:
    return EXPLORE_SRC.read_text(encoding="utf-8")


# ---------- ① 厂商显示：报端点归属，不报实现类的 provider 字段 ----------

def test_doctor_reports_vendor_not_implementation_provider() -> None:
    """`llm-doctor` 的 provider 行必须按**实际端点**认厂商。"""
    src = _cli()
    assert "llm_vendor_of(" in src, "doctor 必须用 llm_vendor_of 认厂商（按端点，不按实现类）"
    # 不许再直接把实现类的 provider 字段当结论打印
    assert 'print(f"[llm-doctor] provider  {prov}")' not in src, (
        "provider 行不能再直接打印实现类的 provider 字段"
        "（ChatDeepSeek 写死 'deepseek'，配 GLM 时会误导）")


def test_doctor_labels_implementation_class_separately() -> None:
    """实现类要单独标注 —— 排查时「厂商」和「哪个客户端类」是两件事。"""
    src = _cli()
    assert "客户端实现类" in src, "必须标注客户端实现类，便于区分厂商与实现出处"
    assert "type(obj).__name__" in src


def test_doctor_reports_config_source() -> None:
    """要说清配置来自哪一组变量（LLM_* / DEEPSEEK_*）—— 变量名与实际端点可能不一致。"""
    assert "配置来源" in _cli()
    assert "llm_source_env(" in _cli()


@pytest.mark.parametrize("base_url,expect", [
    ("https://open.bigmodel.cn/api/paas/v4", "智谱 GLM"),
    ("https://open.bigmodel.cn/api/coding/paas/v4", "智谱 GLM"),
    ("https://api.deepseek.com/v1", "DeepSeek"),
])
def test_vendor_mapping_is_by_endpoint(base_url: str, expect: str) -> None:
    """厂商判定走真入口（endpoint -> vendor），不靠变量名推断。"""
    from framework.shared.config import llm_vendor_of
    assert expect in llm_vendor_of(base_url)


def test_vendor_says_unknown_instead_of_guessing() -> None:
    """认不出的端点必须直说，不许瞎猜一个厂商。"""
    from framework.shared.config import llm_vendor_of
    assert "未识别" in llm_vendor_of("https://some-unknown-proxy.example.com/v9")


# ---------- ② 大 prompt 实探：不能只跑极小 schema 就给「可以用」 ----------

def test_doctor_has_big_prompt_probe() -> None:
    """doctor 必须有第 3 项大 prompt 实探，且复用框架自己的 prompt 构造器。"""
    src = _cli()
    assert 'out["big"]' in src, "必须有大 prompt 实探结果（out['big']）"
    assert "_build_planner_prompt(" in src, "大 prompt 必须用框架自己的构造器（真链路同源）"
    assert "_PLANNER_SYSTEM" in src, "大 prompt 必须带真实的系统提示词"


def test_big_probe_uses_configured_timeout_not_hardcoded() -> None:
    """实探超时必须取 `llm_timeout_s()` —— 否则测的不是用户真实配置。"""
    src = _cli()
    m = re.search(r"out\[\"big\"\][\s\S]{0,1200}", src)
    assert m, "找不到 out['big'] 相关代码"
    seg = _cli()
    assert "llm_timeout_s()" in seg, "实探必须用 llm_timeout_s() 取超时"
    assert "timeout=to_s" in seg, "实探的 wait_for 必须用取到的超时值"


def test_big_probe_failure_blocks_positive_conclusion() -> None:
    """实探失败/超时时，结论**不许**说「可以用」—— 这是防假保证的核心。"""
    src = _cli()
    assert "big_ok" in src, "必须有 big_ok 标志参与结论判定"
    assert "真实规模跑不动" in src, "实探失败时结论必须明确说真实规模跑不动"


def test_big_probe_falls_back_to_synthetic_when_no_map() -> None:
    """本机没有 element_map 时要有合成清单兜底，不能直接跳过实探。"""
    src = _cli()
    assert "合成清单" in src, "无 element_map 时应有合成清单兜底并注明来源"


# ---------- ③ 结构化失败时点破真因 ----------

def test_explore_warns_reasoning_effort_when_no_tool_calls() -> None:
    """报 tool_calls 缺失时必须提示 reasoning_effort 太低，别让用户去换模型。"""
    src = _explore()
    assert "reasoning_effort 太低" in src, "缺 tool_calls 的报错处必须给出 effort 提示"
    assert "HYBRID_LLM_TIMEOUT 提到 400+" in src, "必须同时给出超时值建议"
    # 判定条件要认准这条报文（否则提示挂不上去）
    assert '"tool_calls" in _low' in src


def test_env_example_documents_timeout_and_effort() -> None:
    """可调项必须可发现：.env.example 要登记超时/重试/预算，不能只活在源码里。"""
    ex = (BASE / ".env.example").read_text(encoding="utf-8")
    for key in ("HYBRID_LLM_TIMEOUT", "HYBRID_AI_RETRY", "HYBRID_LLM_ATTEMPTS",
                "HYBRID_PROMPT_LIST_CHARS"):
        assert key in ex, f".env.example 必须登记 {key}（否则用户不知道能调）"
    assert "312" in ex, ".env.example 要写明 high 档实测耗时，作为调大超时的依据"
