# -*- coding: utf-8 -*-
"""特性2 · 规划提示词里**不许出现 demo 实测出来的字面名**（2026-10-10 血泪教训）。

事故：提示词模板里硬编码了 `选择客户@订单系统` / `HT_1001@合同列表页` / `选择销售员@新建订单`
这类**某次探测偶然得到**的名字当"教学范例"。AI 照着范例的**形状**学会了 `@订单系统` 这个后缀，
而清单里根本没有这个名字 -> 映射质量闸报缺失项 -> generate 拒绝产出 -> 整条链卡死。
排查代价：跨了 3 轮验收（每轮 10~19 分钟）才定位。

口径（AprilPark1012定的原则）：**不拿"观测到的具体值"当地基** —— 范例只能用通用形状（甲@乙），
并明写"示例只是形状，名字必须逐字来自本次清单"。
=> 本判据用机器盯住这条：**静态规则段**里出现 demo 专属名就红。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

REPO = Path(__file__).resolve().parents[2]
EXPLORER = REPO / "framework" / "tools" / "explore" / "explorer.py"

# demo（场景）里真实存在的具体名 —— 它们只能来自数据，不许写进提示词模板
DEMO_LITERALS = ["订单系统", "HT_1001", "SO_2301", "新建订单页", "合同列表页",
                 "订单列表页", "发票列表页", "订单详情页", "开票页"]


def _static_rule_block() -> str:
    """取"规则:"那一段静态提示词（不含动态注入的清单）。"""
    src = EXPLORER.read_text(encoding="utf-8")
    i = src.index("规则:")
    seg = src[i:i + 9000]
    # 截到该 prompt +=(...) 块的结尾（下一个不含 f"   的行）
    out = []
    for line in seg.splitlines():
        if out and not (line.strip().startswith('f"') or line.strip().startswith(")")):
            break
        out.append(line)
    return chr(10).join(out)


def test_static_prompt_has_no_demo_literal_names():
    blk = _static_rule_block()
    assert len(blk) > 500, f"没取到静态规则段（{len(blk)} 字符）—— 判据前提失效，先修取法"
    bad = [n for n in DEMO_LITERALS if n in blk]
    assert not bad, (
        "提示词静态规则段里出现了 demo 实测出来的字面名：" + "、".join(bad)
        + "。范例必须用通用形状（如 甲@乙），否则 AI 会照形状自造后缀（2026-10-10 卡链事故）"
    )


def test_prompt_states_examples_are_only_shapes():
    """光删范例不够，还要**明写**："示例只是形状"。否则 AI 仍可能把同类形状当范式。"""
    blk = _static_rule_block()
    assert "形状" in blk and "逐字来自" in blk, (
        "规则段缺少「示例只是形状、名字必须逐字来自本次清单」这条明文约束"
    )
