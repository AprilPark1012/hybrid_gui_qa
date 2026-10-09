# -*- coding: utf-8 -*-
"""特性10 · 文档口径：**AI 链路是主推路径，手搓用例降级为调试/回归辅助**（V8.4）。

背景（用户 2026-10-08 定的方向 C，原话）：
    「把『手搓用例』明确降级为调试/回归辅助，文档与培训页里的主推路径改成 AI 链路。」
    并强调「我的本意是真 AI 生成 cases，cli all 就是跑完整的 AI 链路端到端……请务必按照这个
    要求来改，而不是只是适配手搓用例。」

判据口径：
  · 只查**主推路径的表述顺序与措辞**（README / CLI 提示 / 培训页主推章节）；
  · **不碰历史版本记录**（那是历史事实，改了才是造假）；
  · **不碰判据/代码里的「手写」技术术语**（如 `test_assert_kinds_render.py` 里的用例名）。
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
README = REPO / "README.md"
CLI = REPO / "framework" / "cli.py"
HTML_GEN = REPO / "build_tools" / "build_html.py"


# ---------------------------------------------------------------- CLI 提示

def test_cli_error_suggests_ai_first():
    """`generate` 在 cases 为空时的提示，必须**先推 AI**（`explore --ai`），再提手写。

    事故口径：原文是「先写 cases/*.json，或用 explore --ai 让 AI 出题」—— 把**手搓排在前面**，
    而现任主推路径是 AI。用户按提示走会先撞上手搓那条（还要自己写用例）。
    """
    src = CLI.read_text(encoding="utf-8")
    i = src.index("cases/ 里一个用例都没有")
    seg = src[i: i + 400]
    ai = seg.find("explore --ai")
    manual = seg.find("cases/*.json")
    assert ai != -1, "提示里没有提到 AI 路径（explore --ai）"
    assert manual != -1, "提示里没有提到手写用例路径"
    assert ai < manual, (
        "CLI 提示里手搓路径排在 AI 路径**前面** —— 与「主推 AI 链路」的口径不符"
    )


def test_cli_module_docstring_marks_manual_as_auxiliary():
    """`cli.py` 顶部对 `cases/` 的说明，必须把「手写」标注为辅助定位（而不是默认形态）。"""
    src = CLI.read_text(encoding="utf-8")
    head = src[:2000]
    assert "cases/" in head, "cli.py 顶部没有 cases/ 说明"
    # 必须出现「AI」+「辅助/调试/回归」这类限定词，不能只写「手写自然语言用例」
    assert "AI" in head, "cli.py 顶部说明里没提 AI 链路"
    assert any(w in head for w in ("辅助", "调试", "回归")), (
        "cli.py 顶部把 cases/ 只说成「手写自然语言用例」，没有标注手写是辅助形态"
    )


# ---------------------------------------------------------------- README

def test_readme_two_tracks_puts_ai_first():
    """README 的「两条链路」表格里，**AI 链路必须是 ①**。"""
    src = README.read_text(encoding="utf-8")
    i = src.index("两条链路")
    seg = src[i: i + 1200]
    ai = seg.find("AI")
    manual = seg.find("手搓")
    assert ai != -1 and manual != -1, "README 的链路表结构变了，判据需同步更新"
    assert ai < manual, "README 链路表里手搓排在 AI 前面 —— 主推路径应当 AI 在前"


def test_readme_ai_is_recommended():
    """README 必须明确说明「AI 是推荐入口、手搓是辅助」。"""
    src = README.read_text(encoding="utf-8")
    assert any(w in src for w in ("推荐", "主推")) and "AI" in src, (
        "README 没有说明推荐的入口是哪一个"
    )
    i = src.find("推荐")
    if i == -1:
        i = src.find("主推")
    seg = src[max(0, i - 200): i + 400]
    assert "AI" in seg, "README 的「推荐/主推」字样附近没有提到 AI 链路"


# ---------------------------------------------------------------- 培训页（生成器模板）

def test_training_chapter4_not_headlined_by_handcraft():
    """培训页第 4 章标题不许再以「手搓」开头 —— 它是主推路径章节，应以 AI 为主语。"""
    src = HTML_GEN.read_text(encoding="utf-8")
    assert "场景文件与用例文件：怎么手搓" not in src, (
        "培训页第 4 章标题仍是《场景文件与用例文件：怎么手搓》—— 主推路径没有改成 AI"
    )
    assert "先让 AI 出题" in src or "AI 出题" in src, (
        "培训页第 4 章没有改成「AI 为主、手搓为辅」的表述"
    )


def test_training_history_chapters_untouched():
    """**负向的另一面**：历史版本章节里的「手写用例」字样**必须保留** —— 那是历史事实。

    判据用意：防止有人为了「口径统一」把历史记录也一并改掉（那等于篡改版本史）。
    """
    src = HTML_GEN.read_text(encoding="utf-8")
    # 历史章节里的典型句子（V8.1 时期：13 用例全绿 = 10 手写 + 3 AI）
    assert "10 条手写" in src or "12 条手写" in src or "6 条手写" in src, (
        "历史版本章节里的「N 条手写」记录被改掉了 —— 历史事实不许动"
    )
