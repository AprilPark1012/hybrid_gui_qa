#!/usr/bin/env python3
"""V8.3.6 tests/ 目录重组：特性2 一分为二 + 原 3~9 顺延为 4~10。

用法：
    .venv/bin/python build_tools/reorg_tests_v836.py --dry-run   # 只打印计划
    .venv/bin/python build_tools/reorg_tests_v836.py --apply     # 执行（git mv，保留历史）

设计原则：
  * 用 `git mv` 移动，保留文件历史（不删了重建）。
  * 目录名 = `特性<N>-<名称>`，与 `framework/feature_spec.py` 的 `dir` 字段一致。
  * 一个文件的物理位置取「它所属的大特性」；spec 里允许跨子特性引用。
  * 只动目录与文件位置，**不改任何文件内容**（内容侧引用由 reorg 后统一复扫修）。
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TESTS = REPO / "tests"

# 目标目录（与 feature_spec.py 的 dir 字段一一对应）
D1 = "特性1-混合链路"
D2 = "特性2-语义识别与步骤编排"
D3 = "特性3-分层定位与控件识别"
D4 = "特性4-选错控件兜底"
D5 = "特性5-用例脚本数据三层分离"
D6 = "特性6-自愈闭环Healer"
D7 = "特性7-并发与资源安全"
D8 = "特性8-离线回放"
D9 = "特性9-质量闸门体系"
D10 = "特性10-CLI帮助契约"

# 源目录
S1 = "特性1-混合链路"
S2 = "特性2-语义识别与分层定位"
S3 = "特性3-选错控件兜底"
S4 = "特性4-用例脚本数据三层分离"
S5 = "特性5-自愈闭环Healer"
S6 = "特性6-并发与资源安全"
S7 = "特性7-离线回放"
S8 = "特性8-质量闸门体系"
S9 = "特性9-CLI帮助契约"

# 特性2 拆分：文件 -> 目标目录
SPLIT_2 = {
    # -> 特性2 语义识别与步骤编排
    "test_name_alignment.py": D2,
    "test_step_direct_locator.py": D2,
    "test_scope_locate_expr.py": D2,
    "test_locate_by_title.py": D2,
    "test_scenario_auth_spec.py": D2,
    "test_page_pre_actions.py": D2,
    "test_probe_url_and_occurrence.py": D2,
    "test_login_priming_coverage.py": D2,
    "verify_role_switch_click.py": D2,
    "verify_login_priming.py": D2,
    "verify_page_pre_actions.py": D2,
    # -> 特性3 分层定位与控件识别
    "test_element_anchor_path.py": D3,
    "test_expandable_menu_discovery.py": D3,
    "verify_scope_locate.py": D3,
    "verify_cross_page.py": D3,
    "verify_expandable_menu.py": D3,
    "verify_select_index_skips_placeholder.py": D3,
}

# 整目录顺延（源 -> 目标）
DIR_RENAMES = {
    S3: D4,
    S4: D5,
    S5: D6,
    S6: D7,
    S7: D8,
    S8: D9,
    S9: D10,
}

# 跨目录归位（源目录/文件 -> 目标目录）
MOVES = [
    (S4, "test_row_cell_col_by.py", D3),   # 行内单元格定位 -> 分层定位（原归类偏「三层分离」）
    (S4, "test_row_cell_ops.py", D3),
    (S8, "test_select_by_index.py", D3),   # select index 语义 -> 分层定位（原归类偏「质量闸门」）
]


def run(cmd: list[str], dry: bool) -> None:
    print("   $", " ".join(cmd))
    if dry:
        return
    r = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        print(f"   !! 失败: {r.stderr.strip()}", file=sys.stderr)
        raise SystemExit(1)


def main() -> int:
    ap = argparse.ArgumentParser(description="V8.3.6 tests/ 目录重组")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    if not (a.dry_run or a.apply):
        print("请显式指定 --dry-run 或 --apply", file=sys.stderr)
        return 2
    dry = a.dry_run

    print(f"[reorg] {'干跑' if dry else '执行'}  tests/ 重组 (V8.3.6)\n")

    # 0) 建目标目录
    for d in (D2, D3):
        p = TESTS / d
        print(f"[0] 建目录 {d}")
        if not dry:
            p.mkdir(parents=True, exist_ok=True)

    # 1) 特性2 拆分
    print(f"\n[1] 拆分 {S2} -> {D2} / {D3}")
    for fn, dst in sorted(SPLIT_2.items()):
        src = TESTS / S2 / fn
        if not src.exists():
            print(f"   !! 缺文件 {src}", file=sys.stderr)
            return 1
        run(["git", "mv", str(src.relative_to(REPO)), str((TESTS / dst / fn).relative_to(REPO))], dry)

    # 2) 特性2 源目录此时应为空 -> 删除
    print(f"\n[2] 删除已空的 {S2}")
    if not dry:
        left = list((TESTS / S2).iterdir())
        if left:
            print(f"   !! 目录非空，剩余 {len(left)} 项，停止", file=sys.stderr)
            return 1
        (TESTS / S2).rmdir()
        print("   OK 已删")
    else:
        print("   (干跑)")

    # 3) 跨目录归位
    print("\n[3] 跨目录归位")
    for srcdir, fn, dstdir in MOVES:
        src = TESTS / srcdir / fn
        if not src.exists():
            print(f"   !! 缺文件 {src}", file=sys.stderr)
            return 1
        run(["git", "mv", str(src.relative_to(REPO)), str((TESTS / dstdir / fn).relative_to(REPO))], dry)

    # 4) 整目录顺延
    print("\n[4] 目录顺延")
    for src, dst in DIR_RENAMES.items():
        if not (TESTS / src).exists():
            print(f"   !! 缺目录 {src}", file=sys.stderr)
            return 1
        run(["git", "mv", str((TESTS / src).relative_to(REPO)), str((TESTS / dst).relative_to(REPO))], dry)

    print("\n[reorg] 完成。下一步：")
    print("   1) 复扫 tests/ 内对旧目录名的引用（含 conftest/_runner/_helpers、判据、文档）")
    print("   2) python build_tools/build_feature_map.py")
    print("   3) python -m pytest tests/ -q")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
