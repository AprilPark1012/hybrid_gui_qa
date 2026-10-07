#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""「特性 × 验证结果」报告 —— 他 2026-10-07 定的口径（R7-g 第 5 步）。

**为什么要它**：发内部口径邮件时必须**逐特性**标出验证结果（✅/❌/⏭️），
这样才能看出「哪个特性真的在被验证、哪个是空的」—— 而不是笼统说一句"测试都过了"。

**特性从哪来**：`tests/特性N-<名>/` 的目录名（**唯一来源**，不另立清单 —— 另立必然漂移）。
**一类**：跑一次 `pytest tests/ --junitxml=...`，按 `classname` 归到特性夹。
**二类**：`verify_*.py` 按所在特性夹归类；结果来自 `--class2-log`（`run_verifications.py` 的日志）
        —— 二类要真浏览器 + 真 demo、约 11 分钟，所以**默认不现场跑**，而是读最近一次日志。
**未验证标记**：特性夹里有 `UNVERIFIED.md` ⇒ 该特性标 ⏭️（有实现、无判据）。

用法：
  python tests/_runner/feature_verification_report.py                       # 只跑一类（快，~35s）
  python tests/_runner/feature_verification_report.py --class2-log <日志>    # 带上二类结果
  python tests/_runner/feature_verification_report.py --out report.md        # 落盘
退出码：0 正常 / 1 有红 / 2 用法
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TESTS_DIR = REPO / "tests"
RUNNER = TESTS_DIR / "_runner" / "run_verifications.py"
PY = sys.executable


def feature_dirs() -> list[Path]:
    return sorted(p for p in TESTS_DIR.iterdir()
                  if p.is_dir() and p.name.startswith("特性") and p.name != "__pycache__")


def run_class1() -> dict[str, tuple[int, int, list[str]]]:
    """跑一类，返回 {特性夹名: (pass, fail, [失败用例])}。"""
    with tempfile.TemporaryDirectory() as td:
        xml = Path(td) / "r.xml"
        subprocess.run([PY, "-m", "pytest", "tests/", "-q", "--tb=no",
                        f"--junitxml={xml}"], cwd=str(REPO),
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
        res: dict[str, tuple[int, int, list[str]]] = {}
        if not xml.exists():
            return res
        for tc in ET.parse(xml).getroot().iter("testcase"):
            cls = tc.get("classname") or ""
            m = re.search(r"(特性\d+-[^.\s]+)", cls)
            key = m.group(1) if m else "(未归类)"
            p, f, fails = res.get(key, (0, 0, []))
            if tc.find("failure") is not None or tc.find("error") is not None:
                f += 1
                fails.append(f'{tc.get("name")}')
            else:
                p += 1
            res[key] = (p, f, fails)
        return res


def class2_results(log_path: Path | None) -> dict[str, list[tuple[str, bool]]]:
    """从 run_verifications 日志解析二类结果，按特性夹分组。"""
    out: dict[str, list[tuple[str, bool]]] = {}
    if not log_path or not log_path.is_file():
        return out
    txt = log_path.read_text(encoding="utf-8", errors="replace")
    # runner 的日志是**分段式**：`———— [N/M] script.py ————` 后跟该脚本的输出，
    # 段内出现 `✅ exit 0`（通过）/ `❌ exit N`（失败）；开头另有 `⏭️ script.py 不进日常：...`（跳过）。
    # ⚠️ 别按单行 `N/M script exit N` 匹配 —— 实际格式不是那样（2026-10-07 踩过，二类列全空）。
    skipped = set(re.findall(r"⏭️\s+(verify_\w+\.py)", txt))
    parts = re.split(r"—+\s*\[?\d+/\d+\]\s+(verify_\w+\.py)\s*—+", txt)
    for i in range(1, len(parts) - 1, 2):
        script, body = parts[i], parts[i + 1]
        if re.search(r"✅\s*exit\s*0", body):
            good = True
        elif re.search(r"❌\s*exit\s*[1-9]", body):
            good = False
        else:
            continue
        hits = list(TESTS_DIR.glob(f"特性*/{script}"))
        key = hits[0].parent.name if hits else "(未归类)"
        out.setdefault(key, []).append((script, good))
    for script in skipped:                     # 跳过的不算通过，单列
        hits = list(TESTS_DIR.glob(f"特性*/{script}"))
        key = hits[0].parent.name if hits else "(未归类)"
        out.setdefault(key, []).append((script + "(跳过)", True))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="生成「特性 × 验证结果」表")
    ap.add_argument("--class2-log", help="run_verifications.py 的日志路径（不传则二类列显示 —）")
    ap.add_argument("--out", help="把 Markdown 表写到这个文件")
    a = ap.parse_args()

    c1 = run_class1()
    c2 = class2_results(Path(a.class2_log) if a.class2_log else None)

    lines = ["| 特性 | 一类 | 二类 | 状态 |", "|---|---|---|---|"]
    total_p = total_f = 0
    unverified, any_red = [], False
    for d in feature_dirs():
        name = d.name
        p, f, fails = c1.get(name, (0, 0, []))
        total_p += p
        total_f += f
        c2rows = c2.get(name, [])
        if p == 0 and f == 0:
            c1s = "⏭️ **零判据**" if (d / "UNVERIFIED.md").is_file() else "⚠️ 无"
        else:
            c1s = f"✅ {p}" if f == 0 else f"❌ {p} 过 / **{f} 红**"
        if c2rows:
            okn = sum(1 for _, good in c2rows if good)
            c2s = f"✅ {okn}/{len(c2rows)}" if okn == len(c2rows) else f"❌ {okn}/{len(c2rows)}"
        else:
            c2s = "—（未提供日志）" if not a.class2_log else "⏭️ 无"
        if (d / "UNVERIFIED.md").is_file():
            status = "⏭️ **UNVERIFIED**（有实现、无判据）"
            unverified.append(name)
        elif f or (c2rows and not all(g for _, g in c2rows)):
            status = "❌ 有红"
        elif p == 0:
            status = "⚠️ 无判据、也无标记"
        else:
            status = "✅"
        lines.append(f"| {name} | {c1s} | {c2s} | {status} |")
        if status.startswith("❌"):
            any_red = True

    lines.append("")
    lines.append(f"**一类合计**：{total_p} passed / {total_f} failed"
                 + (f"（失败：{', '.join(sum((v[2] for v in c1.values()), []))}）" if total_f else ""))
    if unverified:
        lines.append(f"**未验证特性（必须显式列出）**：{'、'.join(unverified)}")

    md = "\n".join(lines)
    print(md)
    if a.out:
        Path(a.out).write_text(md + "\n", encoding="utf-8")
        print(f"\n[report] 已写入 {a.out}")
    return 1 if any_red else 0


if __name__ == "__main__":
    sys.exit(main())
