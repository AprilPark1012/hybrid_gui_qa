# -*- coding: utf-8 -*-
"""特性10 · 文档口径：**真 AI 链路是唯一链路**（V8.6）。

背景：
  · 2026-10-08 用户定方向 C：「把『手搓用例』降级为调试/回归辅助，主推路径改成 AI 链路」。
  · 2026-10-13 用户进一步定（V8.6）：**手搓链路整体删除**，框架只剩真 AI 链路一条 ——
    所以「AI 主推 / 手搓辅助」这个对比本身也不复存在，本文档口径判据随之升级为
    「文档里不许再把手搓链路写成可用入口」。

判据口径：
  · 只查**主推路径的表述**（README / CLI 提示 / 培训页）；
  · **不碰历史版本记录**（那是历史事实，改了才是造假）；
  · **允许**在「已删除」的说明语境里提到手搓（那是必要的变更交代，不是把它当活入口）。
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
README = REPO / "README.md"
CLI = REPO / "framework" / "features" / "f10_cli" / "cli.py"
HTML_GEN = REPO / "build_tools" / "build_html.py"


# ---------------------------------------------------------------- CLI 提示

def test_cli_error_suggests_ai_path():
    """`generate` 在 cases 为空时的提示，必须指向 **真 AI 链路**（`explore --ai`）。"""
    src = CLI.read_text(encoding="utf-8")
    i = src.index("cases/ 里一个用例都没有")
    seg = src[i: i + 400]
    assert "explore --ai" in seg, (
        "提示里没有指向真 AI 路径（explore --ai）—— V8.6 起它是唯一链路"
    )
    assert "cli probe" not in seg, "提示里仍在教人跑已删除的 probe 子命令"


def test_cli_module_docstring_says_cases_come_from_ai():
    """`cli.py` 顶部对 `cases/` 的说明，必须写明用例来自 **AI 产出**。"""
    src = CLI.read_text(encoding="utf-8")
    head = src[:2000]
    assert "cases/" in head, "cli.py 顶部没有 cases/ 说明"
    assert "AI" in head, "cli.py 顶部说明里没提 AI 链路"
    assert "手写" not in head and "手搓" not in head, (
        "cli.py 顶部还在把 cases/ 说成「手写/手搓」—— V8.6 起用例只有 AI 一个来源"
    )


# ---------------------------------------------------------------- README

def test_readme_single_track_no_handcraft():
    """README 必须只讲**一条链路**，且不许把 probe/手搓写成可用入口。"""
    src = README.read_text(encoding="utf-8")
    assert "两条链路" not in src, (
        "README 仍在讲「两条链路」—— V8.6 起只剩真 AI 链路一条"
    )
    assert "python -m framework.cli all --ai" in src, "README 没有给出真 AI 链路的入口命令"
    # 允许出现「已删除」交代，但不许出现可照跑的 probe 子命令
    assert "cli probe" not in src, "README 仍在教人跑已删除的 probe 子命令"


def test_readme_ai_is_recommended():
    """README 必须明确说明入口是 `all --ai`。"""
    src = README.read_text(encoding="utf-8")
    assert "all --ai" in src, "README 没有写明主入口是 all --ai"
    assert any(w in src for w in ("推荐", "主推", "唯一")), (
        "README 没有说明入口关系（推荐/主推/唯一）"
    )


# ---------------------------------------------------------------- 培训页（生成器模板）

def test_training_chapter4_is_ai_centered():
    """培训页第 4 章不许再以「手搓」为主题；须以「写场景 / AI 出用例」为主语。"""
    src = HTML_GEN.read_text(encoding="utf-8")
    assert "先让 AI 出题，再按需手搓" not in src, (
        "培训页第 4 章标题仍是《先让 AI 出题，再按需手搓》—— 手搓链路已删，标题须改"
    )
    assert "写场景" in src and "AI 出用例" in src, (
        "培训页第 4 章没有改成「写场景 -> AI 出用例」的表述"
    )
    assert '<h3 style="margin:26px 0 6px">4.1 一条链路' in src, (
        "培训页 4.1 没有改成「一条链路」（原来是与手搓的两条链路对比表）"
    )


def test_training_history_chapters_untouched():
    """**负向的另一面**：历史版本章节里的「手写用例」字样**必须保留** —— 那是历史事实。

    判据用意：防止有人为了「口径统一」把历史记录也一并改掉（那等于篡改版本史）。
    """
    src = HTML_GEN.read_text(encoding="utf-8")
    assert "10 条手写" in src or "12 条手写" in src or "6 条手写" in src, (
        "历史版本章节里的「N 条手写」记录被改掉了 —— 历史事实不许动"
    )
