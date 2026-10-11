# -*- coding: utf-8 -*-
"""特性8 · 同结构键**多份**录像时，必须取**最新录制**的那份（P25 片 2 · 2026-10-11）

## 为什么（实测事故，0 token 修复）

结构键刻意**剥掉 `@页名` 后缀**（`element_fingerprint`：`@页名` 是「这次探到几页」的观测）。
副作用：**用旧上下文名录的**（`物料编码@详细信息`）与**用新上下文名录的**
（`物料编码@订单详情页`）算出来**是同一把结构键**，两份都会命中。

原实现 `for f in sorted(glob): ... return` = **命中即返回**，与录制时间无关
（文件名字典序第一个）=> 可能选中旧录像，而它里面的语义名与**当前**清单对不上 =>
解析期名字对不上的步骤 element 被清空 => 生成期 G2「必定位步骤空 element」拦下。
实测：8 步 element 为空、`generate EXIT=2`、run 因无脚本退出 5。

口径：同键多份时取 **created_at 最大**者 —— 新录像代表更近的页面/命名状态。
排序口径必须简单可解释；「猜哪份更配当前清单」属于拿实测值当地基，不做。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from framework.tools.explore.llm_cassette import Cassette, MODE_REPLAY


def _write(root: Path, fname: str, completion: str, created: str, key_struct: str = "SK-TIE"):
    (root / fname).write_text(json.dumps({
        "key": fname.replace(".json", ""),
        "key_struct": key_struct,
        "created_at": created,
        "responses": [{"kind": "text", "completion": completion}],
        "prompt": "",
    }, ensure_ascii=False), encoding="utf-8")


def test_picks_latest_when_struct_key_ties(tmp_path):
    """文件名字典序与时间**相反**时，仍必须按时间取最新（证明不是靠文件名排序）。"""
    root = tmp_path / "cas"
    root.mkdir()
    _write(root, "zzz_old.json", "OLD", "2026-10-10T21:00:00+08:00")
    _write(root, "aaa_new.json", "NEW", "2026-10-10T22:00:00+08:00")
    c = Cassette(MODE_REPLAY, root)
    rec = c.lookup("no-such-prompt-xyz", system="s", struct_key_value="SK-TIE")
    assert rec is not None, "结构键应当命中"
    assert rec["responses"][0]["completion"] == "NEW", (
        "同结构键多份时必须取最新录制的；取到 OLD 说明又按文件名字典序选了")
    assert rec.get("_match") == "struct"


def test_reports_which_one_it_picked(tmp_path, capsys):
    """多份时必须在日志里说明「命中了几份、取了哪份」（可审计，不静默）。"""
    root = tmp_path / "cas2"
    root.mkdir()
    _write(root, "a.json", "A", "2026-10-10T20:00:00+08:00")
    _write(root, "b.json", "B", "2026-10-10T23:00:00+08:00")
    c = Cassette(MODE_REPLAY, root)
    c.lookup("no-such-prompt-abc", system="s", struct_key_value="SK-TIE")
    out = capsys.readouterr().out
    assert "2 份" in out and "最新录制" in out, f"没有说明选择理由，实际输出：{out!r}"


def test_single_hit_stays_quiet(tmp_path, capsys):
    """只有一份命中时不该打多余噪音。"""
    root = tmp_path / "cas3"
    root.mkdir()
    _write(root, "only.json", "ONLY", "2026-10-10T20:00:00+08:00")
    c = Cassette(MODE_REPLAY, root)
    rec = c.lookup("no-such-prompt-1", system="s", struct_key_value="SK-TIE")
    assert rec["responses"][0]["completion"] == "ONLY"
    assert "份录像" not in capsys.readouterr().out


def test_strict_key_still_wins(tmp_path):
    """严格键（prompt 逐字相同）仍优先于结构键 —— 别把这条改坏。"""
    from framework.tools.explore.llm_cassette import cassette_key
    root = tmp_path / "cas4"
    root.mkdir()
    prompt = "P" * 20
    key = cassette_key(prompt, "s")
    (root / f"{key}.json").write_text(json.dumps({
        "key": key, "key_struct": "SK-TIE", "created_at": "2026-10-10T01:00:00+08:00",
        "responses": [{"kind": "text", "completion": "STRICT"}], "prompt": prompt,
    }, ensure_ascii=False), encoding="utf-8")
    _write(root, "zzz_newer.json", "STRUCT", "2026-10-10T23:00:00+08:00")
    c = Cassette(MODE_REPLAY, root)
    rec = c.lookup(prompt, system="s", struct_key_value="SK-TIE")
    assert rec["responses"][0]["completion"] == "STRICT", "严格键必须优先（逐字相同的那份最可信）"
    assert rec.get("_match") == "strict"
