# -*- coding: utf-8 -*-
"""特性8 · 回放的**第三级匹配**（相似度兜底）与它的红线（V8.4.2）。

背景：严格键（prompt 逐字）与结构键（页面骨架）都不中时，历史实现**直接报「没有这一份」**。
但实测的失配场景里，有一类是「同一场景、demo 数据/页面轻微变动」——
prompt 只差 0.5% 的行，结构键却没兜住（42 份录像里有 36 个互不相同的结构键）。
这时报错把人卡死在「重录 -> 还是不行」的循环里。

所以加第三级：**差异行占比 <= 阈值**（默认 3%）就命中。

红线（必须由判据守住，不许退化）：
  1. **不许静默** —— 用第三级命中必须在本会话里**明确说明**（这是回放、不是当场问的 AI；
     且步骤是**当时那批数据**下做的判断）。
  2. **差异大就是没有** —— 不同场景 / 页面结构真变了，必须照旧报「没有这一份」。
  3. **可关** —— `HYBRID_CASSETTE_FUZZY=0` 时行为退回到「只有严格键 + 结构键」。
"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from framework.tools.explore import llm_cassette as lc  # noqa: E402


def _mk(tmp_path: Path, prompt: str, key: str = "deadbeefdeadbeef") -> Path:
    d = tmp_path / "cass"
    d.mkdir(exist_ok=True)
    (d / f"{key}.json").write_text(json.dumps({
        "key": key, "key_struct": "whatever-not-matching", "framework_version": "8.4.1",
        "created_at": "2026-10-09T12:06:14+08:00", "model": "deepseek-chat",
        "system": "sys", "prompt": prompt,
        "responses": [{"kind": "structured", "completion": {"steps": []}}],
    }, ensure_ascii=False), encoding="utf-8")
    return d


# [!] fuzzy 只比**场景文案**（提示词模板占大头，整 prompt 相似度会让不同场景也像）。
#     所以判据里的 prompt 必须带**真实形态**的场景段，否则提取不到 -> 正确地不命中。
SCEN = "1. 打开合同列表页。\n2. 在搜索框输入 '1005'，点搜索。\n3. 确认结果列表出现该合同。"
BASE = ("你是 GUI 自动化测试规划师。目标页面: http://localhost:8000\n"
        f"自然语言测试场景: 「{SCEN}」\n\n"
        + "\n".join(f"第 {i} 行：控件清单与页面上下文" for i in range(200)))


def test_fuzzy_hits_when_prompt_almost_identical(tmp_path):
    """只差 2/200 行（1%）-> 第三级该命中，并标 `_match == "fuzzy"`。"""
    old = BASE
    new = BASE.replace("第 5 行：控件清单与页面上下文", "第 5 行：控件清单与页面上下文（改了一点）") \
              .replace("第 7 行：控件清单与页面上下文", "第 7 行：控件清单与页面上下文（也改了）")
    d = _mk(tmp_path, old)
    c = lc.Cassette(lc.MODE_REPLAY, d)
    rec = c.lookup(new, "sys", struct_key_value="not-a-match")
    assert rec is not None, "差异 1% 却没命中 -> 用户会被卡在「重录也白搭」"
    assert rec.get("_match") == "fuzzy"


def test_fuzzy_annotates_similarity(tmp_path):
    """命中要给得出「有多像」—— 这是让人核对的前提（不许静默）。"""
    new = BASE.replace("第 9 行：控件清单与页面上下文", "第 9 行：完全不同的一行")
    d = _mk(tmp_path, BASE)
    c = lc.Cassette(lc.MODE_REPLAY, d)
    rec = c.lookup(new, "sys", struct_key_value="not-a-match")
    assert rec is not None and "_fuzzy_similarity" in rec
    assert rec["_fuzzy_similarity"] >= 0.90


def test_fuzzy_survives_line_insertion(tmp_path):
    """**核心判据**：往提示词中间**插入十几行**（后面所有行整体错位）-> 仍该命中。

    [!] 历史实现用「差异行数 / 总行数」，实测这种情形会算出 1355 行不同（其实 95% 相同），
        把真正该救的场景判成「没有这一份」。改用相似度（最长公共子序列）才对。
    """
    inserted = "\n".join(["【新加的一段提示词约束】"] * 15)
    new = BASE.replace("第 100 行：控件清单与页面上下文",
                       inserted + "\n第 100 行：控件清单与页面上下文")
    d = _mk(tmp_path, BASE)
    c = lc.Cassette(lc.MODE_REPLAY, d)
    rec = c.lookup(new, "sys", struct_key_value="not-a-match")
    assert rec is not None, "只插了一段（内容 95% 相同）却报「没有这一份」-> 白卡住用户"


def test_fuzzy_does_not_hit_when_prompt_differs_a_lot(tmp_path):
    """**红线**：差异大（真换了场景 / 页面结构变了）-> 必须照旧「没有这一份」。"""
    other = ("你是 GUI 自动化测试规划师。目标页面: http://localhost:9999\n"
             "自然语言测试场景: 「完全另一套场景：删除发票并注销账号」\n\n"
             + "\n".join(f"另一套控件 {i}" for i in range(200)))
    d = _mk(tmp_path, other)
    c = lc.Cassette(lc.MODE_REPLAY, d)
    assert c.lookup(BASE, "sys", struct_key_value="not-a-match") is None, \
        "差异 100% 也命中了 -> 等于「随便拿一份旧结论套新场景」，红线破了"


def test_fuzzy_can_be_disabled(tmp_path, monkeypatch):
    """`HYBRID_CASSETTE_FUZZY=0` -> 行为退回「只有严格键 + 结构键」。"""
    new = BASE.replace("第 3 行：控件清单与页面上下文", "第 3 行：改过了")
    d = _mk(tmp_path, BASE)
    monkeypatch.setenv("HYBRID_CASSETTE_FUZZY", "0")
    c = lc.Cassette(lc.MODE_REPLAY, d)
    assert c.lookup(new, "sys", struct_key_value="not-a-match") is None


# 场景**改过**的版本：实测与 SCEN 的相似度约 0.82（默认阈值 0.90 接不住，放松能接住）
SCEN_EDITED = "1. 打开订单列表页。\n2. 在搜索框输入别的值，点搜索。\n3. 确认结果列表出现该合同（改过）。"


def _prompt_with(scen: str) -> str:
    return ("你是 GUI 自动化测试规划师。目标页面: http://localhost:8000\n"
            f"自然语言测试场景: 「{scen}」\n\n"
            + "\n".join(f"第 {i} 行：控件清单与页面上下文" for i in range(200)))


def test_default_threshold_rejects_edited_scenario(tmp_path):
    """默认阈值 0.90：场景被改过（相似度约 0.82）-> 不命中。"""
    d = _mk(tmp_path, BASE)
    c = lc.Cassette(lc.MODE_REPLAY, d)
    assert c.lookup(_prompt_with(SCEN_EDITED), "sys", struct_key_value="not-a-match") is None


def test_fuzzy_threshold_loosening_accepts_more(tmp_path, monkeypatch):
    """阈值放松到 0.75 就该接住 —— 说明阈值**真的在起作用**（不是摆设）。"""
    d = _mk(tmp_path, BASE)
    monkeypatch.setenv("HYBRID_CASSETTE_FUZZY_RATIO", "0.75")
    c = lc.Cassette(lc.MODE_REPLAY, d)
    rec = c.lookup(_prompt_with(SCEN_EDITED), "sys", struct_key_value="not-a-match")
    assert rec is not None, "阈值放松了仍不命中 -> 阈值没生效"


def test_fuzzy_threshold_1_rejects_anything_not_identical(tmp_path, monkeypatch):
    """阈值 = 1.0 -> 只有逐字相同的场景才接（此处场景改过，必不中）。"""
    d = _mk(tmp_path, BASE)
    monkeypatch.setenv("HYBRID_CASSETTE_FUZZY_RATIO", "1.0")
    c = lc.Cassette(lc.MODE_REPLAY, d)
    assert c.lookup(_prompt_with(SCEN_EDITED), "sys", struct_key_value="not-a-match") is None


def test_strict_key_still_wins_over_fuzzy(tmp_path):
    """严格键命中时**不许**走 fuzzy（逐字相同是最强证据，优先用它）。"""
    d = _mk(tmp_path, BASE, key=lc.cassette_key(BASE, "sys"))
    # 再放一份「很接近但不是逐字」的
    _mk(tmp_path, BASE.replace("第 1 行", "第 1 行(改)"), key="ffffffffffffffff")
    c = lc.Cassette(lc.MODE_REPLAY, d)
    rec = c.lookup(BASE, "sys", struct_key_value="not-a-match")
    assert rec is not None and rec.get("_match") == "strict", "严格键该优先"
