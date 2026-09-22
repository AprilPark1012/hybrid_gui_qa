#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""录像体检 —— 「哪些场景没有可用录像 / 录像过期」（**零成本**：不联网、不要 key、不起浏览器）。

现场问题（2026-09-22 使用者反馈 + 本机复现）：录像的键包含**场景文案**，而场景文件在
V7.8「数据参数化真展开」后把字面值写成占位符（`'1005'` → `'{关键词}'`）⇒ 结构键逐字比对就整份不命中
⇒ 无外网机器上跑场景1 直接报「没有这一份」，而**这个包已经被发出去了**（打包时没人验过回放能否命中）。
⇒ 本工具就是那道缺失的闸门：**不跑链路、不花钱，先告诉你哪个场景的录像对不上**。

用法：
    python build_tools/check_cassettes.py                 # 体检（默认录像目录 output/llm_cassettes）
    python build_tools/check_cassettes.py --dir <目录>     # 指定录像目录（例：解开录像包后）
    python build_tools/check_cassettes.py --list          # 只列录像文件，不做场景比对
    python build_tools/check_cassettes.py --json          # 机器可读（给验收入口/脚本调用）

退出码：**0** 全覆盖 · **1** 有场景缺录像（= 那些场景回放必失败）· **2** 用法/环境错 · **3** 跳过（没有场景文件或没有录像）

⚠️ 口径与边界（如实说明，别当成万能的）：
  · 本工具是**轻口径**：比对「场景文案（值归一化 + 去空白后）」是否与某份录像 prompt 里的场景段落一致 ——
    它精准回答「换数据 / 参数化 / 改场景文字之后，录像还认不认」；
  · 它**不**校验「控件骨架 / 页面结构」是否变过（那类变化只能靠真跑发现，由场景1 的离线链抽验覆盖，
    见 `tests/verify_e2e_scenario1_offline.py`）；
  · 值归一化口径来自 `llm_cassette.normalize_values()` —— 与真实回放**同一份实现**，不另写一套。
  · ⚠️ 两个实测坑（都踩过，写在这里防复发）：场景文案是**多行**嵌进 prompt 的（逐行抠只能拿到第一行片段，
    会误报「所有场景都缺录像」）；中文引号开闭是不同字符，比对/归一化不能用「字符类 + 反向引用」的写法。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from framework.tools.explore.llm_cassette import default_dir, normalize_values   # noqa: E402

OK, FAIL, USAGE, SKIP = 0, 1, 2, 3
# ⚠️ 2026-09-22 实测修的坑：原来是非贪婪 `([\s\S]*?)[」』”"]` ⇒ 场景文案里**自带内层引号**
# （「返回列表」「查看订单」「新建订单」…）时，抠取会在**第一个内层闭引号**处截断
# ⇒ 长场景永远匹配不上，体检误报「没有录像」（实测：录制明明成功、prompt 里那句完整存在）。
# 现在改成**取到段落边界**（下一个已知小节标题或空行），引号只做首尾剥离，不再当终止符。
_SCEN_HEAD = re.compile(r"自然语言测试场景[:：]?\s*")
_SCEN_END = re.compile(r"\n\s*\n|\n\s*(?:页面已探测出|跨页规则|可交互控件|可用控件|注意事项)")
_SCEN_BLOCK_RE = re.compile(
    r"自然语言测试场景[:：]?\s*[「『“\"]([\s\S]*?)[」』”\"]"
    r"(?=\n\s*\n|\n\s*(?:页面已探测出|跨页规则|可交互控件|可用控件|注意事项)|$)")


def _force_stdio() -> None:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")          # type: ignore[union-attr]
        except Exception:
            pass


def _flatten(text: str) -> str:
    """去掉所有空白（含换行）。

    ⚠️ 必须做：录像里的场景文案是**多行嵌进 prompt** 的，场景文件侧也是多行字符串 ⇒
    不压平就会「两边看着一样、字符串却不相等」，体检直接误报全缺（2026-09-22 实测）。
    """
    return re.sub(r"\s+", "", text or "")


def scenario_text_of(yml: Path) -> str | None:
    """取场景文件里的 `scenario:` 正文（缺字段 / 读不动 ⇒ None）。"""
    try:
        import yaml
        data = yaml.safe_load(yml.read_text(encoding="utf-8")) or {}
    except Exception:
        return None
    text = data.get("scenario") if isinstance(data, dict) else None
    return str(text).strip() if text else None


def scenario_block_in_prompt(prompt: str) -> str:
    """从录像 prompt 里抠出「自然语言测试场景: 「…」」的**完整段落**（跨行）。"""
    text = prompt or ""
    # ① 首选：抠到段落边界（长场景/含内层引号都稳）
    i = _SCEN_HEAD.search(text)
    if i:
        rest = text[i.end():]
        if rest[:1] in ("「", "『", "“", '"'):
            rest = rest[1:]
        m2 = _SCEN_END.search(rest)
        block = rest[:m2.start()] if m2 else rest
        block = block.strip()
        for q in ("」", "』", "”", '"'):
            if block.endswith(q):
                block = block[:-1].rstrip()
        if block:
            return block
    # ② 兜底：老正则（结构异常时至少别返回空）
    m = _SCEN_BLOCK_RE.search(text)
    return m.group(1).strip() if m else ""


def load_cassettes(cassette_dir: Path) -> list[dict]:
    """读录像目录 ⇒ [{file, scenario, normalized, framework_version, created_at}]。"""
    out: list[dict] = []
    for f in sorted(cassette_dir.glob("*.json")):
        try:
            rec = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:                       # 坏文件明确指出，不静默跳过
            out.append({"file": f.name, "broken": f"{type(e).__name__}: {e}"})
            continue
        block = scenario_block_in_prompt(rec.get("prompt") or "")
        out.append({"file": f.name, "scenario": block,
                    "normalized": _flatten(normalize_values(block)),
                    "framework_version": rec.get("framework_version") or "unknown",
                    "created_at": rec.get("created_at") or ""})
    return out


def check(scenario_files: list[Path], cassettes: list[dict]) -> tuple[list[dict], list[dict]]:
    """返回 (有录像的, 缺录像的)。口径：场景文案「归一化 + 压平」后是否被某份录像覆盖。"""
    norm_cass = [c for c in cassettes if c.get("normalized")]
    covered: list[dict] = []
    missing: list[dict] = []
    for yml in scenario_files:
        text = scenario_text_of(yml)
        # ⚠️ 别对仓库外路径硬做 relative_to（实测：调用方传 /tmp 下的临时场景 ⇒ ValueError 崩，
        # 而"体检"这种工具**不该被一个路径崩掉**）——能相对就相对，不能就如实用绝对路径。
        try:
            rel = str(yml.relative_to(REPO))
        except ValueError:
            rel = str(yml)
        if not text:
            missing.append({"scenario": rel, "why": "场景文件里没有 scenario 字段"})
            continue
        want = _flatten(normalize_values(text))
        # 覆盖口径：录像里的场景文案 == 场景文件，**或**完整包含它
        # （包含是精确判定，不是模糊相似度：录像记录的是当时真正发出去的 prompt，可能多带说明）
        hit = next((c for c in norm_cass
                    if c["normalized"] == want or want in c["normalized"]), None)
        row: dict[str, object] = {"scenario": rel, "scenario_text": text}
        if hit:
            row.update({"file": hit["file"], "framework_version": hit["framework_version"],
                        "created_at": hit["created_at"]})
            covered.append(row)
        else:
            best, best_ratio = None, 0.0             # 顺便找「最像」的一份，帮人判断改了哪几个字
            for c in norm_cass:
                a, b = set(want), set(str(c["normalized"]))
                ratio = len(a & b) / max(1, len(a | b))
                if ratio > best_ratio:
                    best, best_ratio = c, ratio
            row.update({"why": "录像里没有任何一份对得上该场景（回放会报「没有这一份」）",
                        "nearest": (best or {}).get("file", ""),
                        "nearest_ratio": round(best_ratio, 2)})
            missing.append(row)
    return covered, missing


def main(argv: list[str]) -> int:
    _force_stdio()
    ap = argparse.ArgumentParser(
        prog="check_cassettes.py",
        description="录像体检：哪些场景没有可用录像（零成本，不联网、不要 key、不起浏览器）",
    )
    ap.add_argument("--dir", default="", help=f"录像目录（默认 {default_dir()}）")
    ap.add_argument("--scenario-dir", default="scenarios", help="场景目录（默认 scenarios/）")
    ap.add_argument("--list", action="store_true", help="只列录像文件，不做场景比对")
    ap.add_argument("--json", action="store_true", help="输出 JSON（机器可读）")
    args = ap.parse_args(argv)

    cassette_dir = Path(args.dir).expanduser().resolve() if args.dir else default_dir()
    scen_root = REPO / args.scenario_dir
    scenario_files = sorted(scen_root.rglob("*.yml"))
    cassettes = load_cassettes(cassette_dir) if cassette_dir.is_dir() else []

    if args.list:
        for c in cassettes:
            print(f"  {c['file']}  v{c.get('framework_version','?')}  {c.get('created_at','')}")
        print(f"  共 {len(cassettes)} 份录像（目录 {cassette_dir}）")
        return OK

    if not cassette_dir.is_dir():
        print(f"⏭️  SKIP：录像目录不存在（{cassette_dir}）⇒ 先录或用 --dir 指定；**不算通过**")
        return SKIP
    if not scenario_files:
        print(f"⏭️  SKIP：{args.scenario_dir}/ 下没有场景文件；**不算通过**")
        return SKIP

    covered, missing = check(scenario_files, cassettes)
    broken = [c for c in cassettes if c.get("broken")]

    if args.json:
        print(json.dumps({"cassette_dir": str(cassette_dir), "cassettes": len(cassettes),
                          "covered": covered, "missing": missing, "broken": broken},
                         ensure_ascii=False, indent=2))
    else:
        print("=" * 66)
        print(" 录像体检（零成本：不联网 / 不要 key / 不起浏览器）")
        print(f" 录像目录: {cassette_dir}（{len(cassettes)} 份）")
        print(f" 场景目录: {args.scenario_dir}/（{len(scenario_files)} 个场景）")
        print("=" * 66)
        for row in covered:
            print(f"  ✅ {row['scenario']}")
            print(f"       录像 {row['file']}（框架 v{row['framework_version']}，{row['created_at']}）")
        for row in missing:
            print(f"  ❌ {row['scenario']}  —— {row.get('why','')}")
            if row.get("nearest"):
                print(f"       最像的是 {row['nearest']}（字符重合 {row.get('nearest_ratio')}）")
            print(f"       ⇒ 重录：python build_tools/record_cassettes.py "
                  f"--only {Path(str(row['scenario'])).stem}")
        for c in broken:
            print(f"  ⚠️ 坏录像文件 {c['file']}：{c['broken']} ⇒ 删掉重录")
        print("-" * 66)
        print(f" 汇总：覆盖 {len(covered)} / 缺 {len(missing)} / 坏文件 {len(broken)}")

    if missing or broken:
        print("❌ 有场景的录像对不上 ⇒ 那些场景在离线机器上回放必失败（发版前必须重录）")
        return FAIL
    print("✅ 所有场景都有可用录像（轻口径：值归一化 + 压平后的场景文案均能对上）")
    return OK


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
