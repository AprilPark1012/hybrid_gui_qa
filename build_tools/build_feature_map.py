"""从 framework/feature_spec.py 生成特性映射文档。

用法：
    python build_tools/build_feature_map.py            # 写 docs/feature_map.md
    python build_tools/build_feature_map.py --check     # 只校验，不写（判据用）

单一来源纪律：特性/子特性/归属只在 framework/feature_spec.py 里定义，
本脚本只负责渲染 + 统计。文档与规格不一致时 --check 会非 0 退出。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from framework.tools.spec.feature_spec import FEATURES, all_subfeatures  # noqa: E402


def _count_tests(repo: Path, name: str) -> int:
    """数一个 test 文件里的用例函数数（只数 def test_，参数化不展开）。"""
    for d in (repo / "tests").iterdir():
        if d.is_dir() and not d.name.startswith("_"):
            f = d / name
            if f.exists():
                import re
                return len(re.findall(r"^def test_\w+", f.read_text(encoding="utf-8"), re.M))
    return 0


def render(repo: Path) -> str:
    lines: list[str] = []
    lines.append("# 框架特性与子特性映射表")
    lines.append("")
    lines.append("> 本文件由 `build_tools/build_feature_map.py` 从 `framework/feature_spec.py` **自动生成**，请勿手改。")
    lines.append("> 加特性 / 子特性：改规格文件后重跑生成器。")
    lines.append("")

    total_feat = len(FEATURES)
    subs = list(all_subfeatures())
    total_sub = len(subs)
    c1_files = {f for _n, _fn, s, _f in subs for f in (s.get("class1") or [])}
    c2_files = {f for _n, _fn, s, _f in subs for f in (s.get("class2") or [])}
    c1_cases = sum(_count_tests(repo, f) for f in c1_files)

    lines.append("## 总览")
    lines.append("")
    lines.append(f"- 大特性 **{total_feat}** 个 · 子特性 **{total_sub}** 条")
    lines.append(f"- 一类用例文件 **{len(c1_files)}** 个 / 用例函数 **{c1_cases}** 条")
    lines.append(f"- 二类验证文件 **{len(c2_files)}** 个")
    lines.append("")
    lines.append("| 特性 | 名称 | 子特性数 | 一类文件 | 二类文件 |")
    lines.append("|---|---|---:|---:|---:|")
    for f in FEATURES:
        s1 = {x for s in f.get("subs", []) for x in (s.get("class1") or [])}
        s2 = {x for s in f.get("subs", []) for x in (s.get("class2") or [])}
        lines.append(f"| {f['no']} | {f['name']} | {len(f.get('subs', []))} | {len(s1)} | {len(s2)} |")
    lines.append("")

    for f in FEATURES:
        tag = f" `[{f['status']}]`" if f.get("status") else ""
        lines.append(f"## 特性 {f['no']} · {f['name']}{tag}")
        lines.append("")
        lines.append(f"**目标**：{f['goal']}")
        lines.append("")
        lines.append(f"**目录**：`tests/{f['dir']}/`")
        lines.append("")
        lines.append("| 子特性 | 名称 | 目标 | 一类（用例数）| 二类 |")
        lines.append("|---|---|---|---|---|")
        for s in f.get("subs", []):
            c1 = s.get("class1") or []
            c2 = s.get("class2") or []
            c1s = "、".join(f"`{x}`({_count_tests(repo, x)})" for x in c1) or "-"
            c2s = "、".join(f"`{x}`" for x in c2) or "-"
            st = f" `[{s['status']}]`" if s.get("status") else ""
            lines.append(f"| {s['no']}{st} | {s['name']} | {s['goal']} | {c1s} | {c2s} |")
        lines.append("")

    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="生成特性映射文档")
    ap.add_argument("--check", action="store_true", help="只校验不写（不一致则非 0 退出）")
    args = ap.parse_args()

    content = render(REPO)
    out = REPO / "docs" / "feature_map.md"

    if args.check:
        if not out.exists():
            print("[feature_map] 文档不存在，需生成", file=sys.stderr)
            return 1
        if out.read_text(encoding="utf-8") != content:
            print("[feature_map] 文档与规格不一致，请重跑生成器", file=sys.stderr)
            return 1
        print("[feature_map] [OK] 与规格一致")
        return 0

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content, encoding="utf-8")
    n = sum(len(f.get("subs", [])) for f in FEATURES)
    print(f"[feature_map] [OK] 已写出 {out.relative_to(REPO)}（{len(FEATURES)} 特性 / {n} 子特性）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
