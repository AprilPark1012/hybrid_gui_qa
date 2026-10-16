# -*- coding: utf-8 -*-
"""交付物**齐套**校验（P25 片 7 · AprilPark1012要求7）。

## 为什么需要它（AprilPark1012原话）

「*.case.json、*.scripts.py 必须和 elementMap、LLM_cassettes 保持版本齐套，避免出现误判」

不齐套的典型症状：**用新用例跑旧脚本** —— 报告里看起来像"代码 bug"，
实际是产物不配套（用例改了没重跑 generate）。这类误判最费人：查错方向从一开始就偏了。

## 口径

只做**可判定**的检查（不猜、不联网、不依赖浏览器）：

| 代号 | 检查 | 为什么 |
|---|---|---|
| K1 | 每条 AI 用例都有对应的生成脚本 | 没有脚本 = 这条用例根本没进执行链路 |
| K2 | 脚本不早于用例（`mtime` 不更旧） | 用例改了没重跑 generate -> 跑的是旧脚本（"误判"的主要来源） |
| K3 | 用例 `llm_source` 指向的录像仍在目录里 | 录像被清理掉 -> 这份产物**无法复现**，出问题查不回去 |
| K4 | AI 用例的 `probe_pre` 与场景声明一致（有场景时） | 与 D9 同源；这里只做"能不能对上"的粗判，细则以 `scenario.probe_pre_conflicts` 为准 |

返回**问题描述列表**（空 = 齐套）。调用方决定怎么处置（`verify` 把它计入判定）。
"""
from __future__ import annotations

import json
from pathlib import Path

from framework.shared.config import CASES_DIR, SCRIPTS_DIR


def _scripts_of(case_id: str, scripts_dir: Path) -> list[Path]:
    gen = scripts_dir / "generated"
    out = [p for p in gen.rglob(f"{case_id}.py")] if gen.is_dir() else []
    return out


def check_kit(cases_dir: Path | None = None, scripts_dir: Path | None = None,
              cassette_dir: Path | None = None) -> list[str]:
    """返回不齐套的问题清单（空列表 = 齐套）。

    [!] 只查 `ai_*.json`：本函数针对的是「真 AI 链路产出的那一套」（要求 2/7 的口径）。
    """
    cases_dir = Path(cases_dir or CASES_DIR)
    scripts_dir = Path(scripts_dir or SCRIPTS_DIR)
    if cassette_dir is None:
        try:
            from framework.features.f08_replay.llm_cassette_explore import default_dir
            cassette_dir = default_dir()
        except Exception:
            cassette_dir = None
    problems: list[str] = []
    if not cases_dir.is_dir():
        return problems                       # 还没产出过用例：不算"不齐套"
    for f in sorted(cases_dir.rglob("ai_*.json")):
        cid = f.stem
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:
            problems.append(f"K0 {cid}: 用例文件读不动（{type(e).__name__}: {e}）")
            continue
        # K1 有脚本
        scripts = _scripts_of(cid, scripts_dir)
        if not scripts:
            problems.append(f"K1 {cid}: 没有对应的生成脚本（先跑 generate；"
                            f"产物不齐时跑 run 只会得到「没匹配到用例」）")
            continue
        # K2 脚本不早于用例
        newest_case = max(p.stat().st_mtime for p in (f,))
        oldest_script = min(p.stat().st_mtime for p in scripts)
        if oldest_script < newest_case - 1:      # 1s 容差（同一批生成的落盘顺序）
            problems.append(f"K2 {cid}: 生成脚本比用例早（用例改了没重跑 generate -> "
                            f"跑的是旧脚本，报告会误导）")
        # K3 录像仍在
        src = str(d.get("llm_source") or "")
        if src.startswith("cassette:") and cassette_dir:
            key = src.split(":", 1)[1].strip()
            if key and not (Path(cassette_dir) / f"{key}.json").exists():
                problems.append(f"K3 {cid}: 产出的录像 {key}.json 已不在录像目录"
                                f"（{cassette_dir}）—— 这份用例无法复现")
        # K4 probe_pre 与场景对得上（粗判，细则见 scenario.probe_pre_conflicts）
        rel = str(d.get("source_scenario") or "")
        if rel and d.get("probe_pre"):
            try:
                from framework.features.f02_semantic.scenario_generate import load_scenario_file
                from framework.shared.config import SCENARIOS_DIR
                sc = load_scenario_file(SCENARIOS_DIR.resolve().parent / rel)
                want = list(getattr(sc, "probe_pre", None) or [])
                if want != list(d.get("probe_pre") or []):
                    problems.append(f"K4 {cid}: probe_pre 与场景声明不一致"
                                    f"（场景 {want!r} vs 用例 {d.get('probe_pre')!r}）")
            except Exception:
                pass                             # 场景读不到不在这里判（另有场景同步判据）
    return problems
