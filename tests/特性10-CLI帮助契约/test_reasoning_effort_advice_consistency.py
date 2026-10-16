# -*- coding: utf-8 -*-
"""特性10 · 思考档位的**推荐口径**必须一致：cli 的 TUNABLE_CATALOG 与 README（V8.6.3 新增）。

为什么（防再次静默漂移）：V8.6.2 把口径定成
    · `LLM_REASONING_EFFORT` 的**取值合法性由端点决定**（GLM-5.3 / 5.3-Flash 只接受 low / high / max）；
    · **别拿 `low` 当省钱解** —— 实测在 8.9 万 token 的大 prompt 上会让模型**完全不返回 tool_calls**
      （`finish_reason=stop`），结构化输出路径直接失效；
    · **本框架实测推荐 `high`**。
README 与 `.env.example` 已按这套口径更新，但 `cli config` 的 TUNABLE_CATALOG 里**还留着旧口径
「建议设 low」** —— 同一个旋钮在两处给出**相反建议**，用户照 CLI 的建议做就会撞上结构化输出失效。

判据（源码级，秒级，不需要 demo / key）：
  (1) `TUNABLE_CATALOG` 里 LLM_REASONING_EFFORT 的说明**不许**出现「建议设 low」这类旧口径；
  (2) README 的档位段落同样不许出现；
  (3) 两处都要同口径（都点明可用档位 / 推荐 `high`）；
  (4) 负向自证：喂一段含旧口径的文本，检查函数必须判红（判据不许空转）。

跑法：
    python -m pytest tests/特性10-CLI帮助契约/test_reasoning_effort_advice_consistency.py -v
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CLI = REPO / "framework" / "features" / "f10_cli" / "cli.py"
README = REPO / "README.md"

#: 旧口径（与真实实测相反：把探索阶段的最贵档当成「该压低」的理由）
_BAD_PHRASES = ("建议设 low", "建议设 `low`", "建议 low", "建议设为 low", "建议设为 `low`")


def catalog_effort_entry(src: str) -> str:
    """从 cli.py 源码里取出 TUNABLE_CATALOG 中 `LLM_REASONING_EFFORT` 那一条（含说明文案）。"""
    i = src.find('"LLM_REASONING_EFFORT"')
    assert i > 0, "TUNABLE_CATALOG 里找不到 LLM_REASONING_EFFORT 条目（旋钮被删了？）"
    return src[i: i + 700]


def readme_effort_paragraph(src: str) -> str:
    """README 里讲 `LLM_REASONING_EFFORT` 的那一段。"""
    i = src.find("LLM_REASONING_EFFORT")
    assert i > 0, "README 里找不到 LLM_REASONING_EFFORT（档位口径段落被删了？）"
    return src[max(0, i - 400): i + 1400]


def advice_problems(catalog: str, readme: str) -> list[str]:
    """两处档位推荐口径的一致性检查（返回问题清单，空 = 一致）。纯函数 -> 可负向自证。"""
    bad: list[str] = []
    for where, text in (("cli.TUNABLE_CATALOG", catalog), ("README", readme)):
        for phrase in _BAD_PHRASES:
            if phrase in text:
                bad.append(f"{where} 仍写着旧口径「{phrase}」—— 与实测相反"
                           f"（`low` 会让大 prompt 完全不返回 tool_calls）")
    if "high" not in catalog:
        bad.append("cli.TUNABLE_CATALOG 的档位说明没有点明可用/推荐档位（应含 `high`）")
    if "high" not in readme:
        bad.append("README 的档位说明没有点明推荐 `high`")
    return bad


def test_catalog_and_readme_advice_are_consistent():
    """`cli config` 与 README 必须给同一个建议 —— 否则用户照 CLI 的建议就会被坑。"""
    problems = advice_problems(catalog_effort_entry(CLI.read_text(encoding="utf-8")),
                               readme_effort_paragraph(README.read_text(encoding="utf-8")))
    assert not problems, "思考档位推荐口径不一致：\n  - " + "\n  - ".join(problems)


def test_negative_old_advice_is_caught():
    """负向自证：塞一段旧口径必须判红（判据不许空转 —— 「判据绿」不等于「判据有效」）。"""
    assert advice_problems("只接受 low/high/max，推荐 high ... 建议设 `low`", "推荐 high") != [], \
        "cli 侧写旧口径居然没被抓到"
    assert advice_problems("只接受 low/high/max，推荐 high", "... 探索阶段每步都跑最贵档，建议设 low ...") != [], \
        "README 侧写旧口径居然没被抓到"
    assert advice_problems("只接受 low/high/max，推荐 high", "推荐 high") == [], \
        "合规样例被误伤（假红与假绿一样会摧毁闸门）"
