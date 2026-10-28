"""V8.7.12 判据：`got none` 的诊断必须**先读当前 effort**，不许无脑甩「档位太低」。

由来（2026-10-28 用户实测纠正）：
  用户 `LLM_REASONING_EFFORT=high`，在**登录页只有 3 条清单**（极小 prompt）时也报
  `Expected tool_calls in response but got none`，且第 2 次重试就成功。
  但框架旧版硬编码断言：
      「这多半不是模型不稳定，而是 reasoning_effort 太低」
      「实测 GLM-5.3 在 low 档 + 大 prompt 下完全不返回 tool_calls」
  => 三层全错：① 就是模型不稳 ② 与 prompt 大小无关（3 条也失败）③ 用户已经是 high。
  => 实际后果：把排查方向带偏整整一轮（去查大 prompt / 端点 / max_tokens，全白跑）。

判据口径：
  · 诊断必须 **读 `LLM_REASONING_EFFORT` 再分流**（effort 偏低 / 已经够高 两套话术）
  · effort 已高时，**不许**再出现「档位太低 / 改 high」这类误导性结论
  · 必须给出**偶发不调工具 → 靠重试兜住**这条正确处置
"""
from __future__ import annotations

import re
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
SRC = BASE / "framework/features/f02_semantic/explorer_explore.py"


def _diagnose_block() -> str:
    """按结构定位诊断块（不用魔法行号：从 tool_calls 判断起，到路径2注释止）。"""
    src = SRC.read_text(encoding="utf-8")
    i = src.find('if "tool_calls" in _low')
    assert i != -1, "找不到 got-none 诊断分支（判断条件改动了？）"
    j = src.find("# 路径2：纯文本 + 宽松解析", i)
    assert j != -1, "找不到诊断块的结束锚点"
    return src[i:j]


def test_diagnosis_reads_effort_before_advising() -> None:
    """必须先读 LLM_REASONING_EFFORT —— 这是本次修复的核心。"""
    blk = _diagnose_block()
    assert 'os.environ.get("LLM_REASONING_EFFORT")' in blk, (
        "诊断块没有读取 LLM_REASONING_EFFORT —— 又回到「不管档位、直接断言太低」的老毛病"
    )
    assert 'if _eff in ("", "low", "minimal"):' in blk, (
        "没有按 effort 分流：偏低与已经够高必须给不同话术"
    )


def test_high_effort_does_not_blame_the_knob() -> None:
    """effort 已高时，不许再出现「档位太低 / 改 high」的误导结论。"""
    blk = _diagnose_block()
    # 找到 else 分支（effort 已经够高 那支）
    k = blk.find("else:")
    assert k != -1, "缺失 else 分支（effort 已够高的情况没处理）"
    else_branch = blk[k:]
    for bad in ("而是 reasoning_effort 太低", "LLM_REASONING_EFFORT=high，"):
        assert bad not in else_branch, (
            f"effort 已高的分支里仍出现误导表述 {bad!r} —— 这句只能出现在 effort 偏低的那个分支"
        )
    assert "偶发不调工具" in else_branch, "effort 已高时必须点明「偶发不调工具」"
    assert "HYBRID_LLM_ATTEMPTS" in else_branch, "必须给出处置：靠重试兜住（HYBRID_LLM_ATTEMPTS）"


def test_old_misleading_phrase_is_gone() -> None:
    """那句「这多半不是模型不稳定」不许出现在**实际话术**里（它把根因判断反了）。

    [!] 只检查非注释代码：本次修复的注释里**引用**了这句作为「原来错在哪」的说明，
    那是刻意的反面教材，不该被判红。
    """
    src = SRC.read_text(encoding="utf-8")
    no_comment = "\n".join(
        line.split("#")[0] for line in src.splitlines()
    )
    assert "这多半不是模型不稳定" not in no_comment, (
        "旧措辞「这多半不是模型不稳定」仍出现在实际话术里 —— 实证恰好相反：就是模型偶发不稳定"
    )


def test_both_branches_are_reachable_in_source() -> None:
    """正向自证：两支话术都真实存在于源码（不是只写了个 if 没有 else 内容）。"""
    blk = _diagnose_block()
    assert "档位偏低是**主要嫌疑**" in blk, "effort 偏低分支缺少话术"
    assert "**所以不是档位太低**" in blk, "effort 已高分支缺少澄清话术"
