# -*- coding: utf-8 -*-
"""文档真值契约 —— 文档说的必须和代码做的是同一回事。

背景（2026-10-12 审计）：README / training.html 里查出 21 处与框架代码不一致
（错的命令、错的目录结构、错的数字、错的默认值、自相矛盾的陈述）。
已有的 5 个文档判据只守**格式**（章节齐不齐）与**同步**（生成器改了产物跟着变），
没有一条守**内容真值** —— 这就是那些漂移能长期存活的原因。本文件补这一层。

边界（为什么这样划，可审计）：
  · 指导性文档（README / scenarios README / requirements / feature_map）**零容忍**：
    它们是「教人怎么用」的，出现不存在的路径或过时命令必是漂移。
  · changelog 历史条目**允许**引用旧路径，但**必须同行标注**（如「此文件现已不在仓库」）
    —— 否则读者会把历史当现状。CHANGELOG 段按 `CHANGELOG = [` 机械定位后跳过。
  · 判据不 import 框架私有名（`_` 开头），断言种类数从源码文本提取、可调项数走
    `cli config`（它是可调项的**唯一权威入口**，不在这里维护第二份）。
"""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# ---- 文档分类 ----
GUIDE_DOCS = [
    "README.md",
    "scenarios/README.md",
    "docs/feature_map.md",
    "requirements.txt",
    "requirements-ai.txt",
]
GENERATOR = "build_tools/build_html.py"

# 不存在的路径必须同行带这类标注（changelog 语境）
LEGACY_MARKS = ("此文件现已不在仓库", "已作废", "已废弃", "已移除", "已删除", "历史条目")

# 路径形态：带目录前缀 + 已知扩展名。占位符（含 < >）天然不匹配。
PATH_RE = re.compile(
    r"(?<![A-Za-z0-9_./\-])"
    r"(?:framework|tests|build_tools|scripts|demo|scenarios|cases)"
    r"/[A-Za-z0-9_/.\-]+\.(?:py|md|json|yml)"
)

# 「可照敲」的 AI 链路命令（要求 cli / framework.cli 前缀）。
# 描述式写法（`explore --ai -> generate -> run`）不带前缀，天然不匹配 —— 那是合法的。
BAD_AI_CMD_RE = re.compile(r"(?:framework\.cli\s+|cli\s+)explore\s+--ai")


def _read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def _changelog_span(src):
    """返回 build_html.py 里 CHANGELOG 列表的 [起, 止) 字符区间。

    用「行首顶格的 ]」定位结束 —— 不能用括号配平：changelog 正文里有 `[ai]`、
    `[V8.5.1 已作废]` 这类方括号，配平会提前收尾。找不到就返回 None，
    判据随后按「全文都算指导性」处理（更严，不会放水）。
    """
    i = src.find("CHANGELOG = [")
    if i < 0:
        return None
    m = re.search(r"(?m)^\]", src[i:])
    return (i, i + m.end()) if m else None


def _changelog_entries(src):
    """把 CHANGELOG 段按条目切开（每条以顶格注释下的 `dict(` 开头）。"""
    span = _changelog_span(src)
    body = src[span[0]:span[1]] if span else src
    parts = re.split(r"(?m)^(?=\s{4}dict\()", body)
    return [p for p in parts if 'version="' in p]


def _iter_paths(text):
    """逐处产出 (路径, 该行文本)。"""
    line_start = 0
    for m in PATH_RE.finditer(text):
        s = text.rfind("\n", line_start, m.start()) + 1
        e = text.find("\n", m.end())
        if e < 0:
            e = len(text)
        yield m.group(0), text[s:e]


# ==========================================================================
# J1 文档引用的文件路径必须存在
# ==========================================================================
def test_j1_guide_docs_referenced_paths_exist():
    """指导性文档里引用的每个文件路径都必须真的在仓库里（零容忍）。"""
    missing = []
    for rel in GUIDE_DOCS:
        for path, _line in _iter_paths(_read(rel)):
            if not (ROOT / path).exists():
                missing.append(f"{rel}: {path}")
    assert not missing, (
        "指导性文档引用了不存在的路径（教人照着用，必须准确）：\n  " + "\n  ".join(missing)
    )


def test_j1_changelog_legacy_paths_must_be_marked():
    """changelog 条目引用「现已不在仓库」的路径时，该条目必须有作废/历史标注。

    粒度按**条目**（不是按行）：一个历史条目统一标一次就够，读者不会把整条当现状。
    没标注的条目，读者会把历史路径当现存路径 —— 这正是本次审计里 `_auth.json`
    那类误导的来源（它教人「包里必须补上这个文件」，而现状正好相反）。
    """
    src = _read(GENERATOR)
    bad = []
    for entry in _changelog_entries(src):
        missing = sorted({p for p, _line in _iter_paths(entry) if not (ROOT / p).exists()})
        if not missing:
            continue
        if any(mark in entry for mark in LEGACY_MARKS):
            continue
        ver = re.search(r'version="([^"]+)"', entry)
        bad.append(f"v{ver.group(1) if ver else '?'}: {missing}")
    assert not bad, (
        "这些 changelog 条目引用了不存在的路径却没标注（读者会以为文件还在）"
        "—— 请在条目里加「已作废 / 已移除 / 此文件现已不在仓库」之类标注：\n  "
        + "\n  ".join(bad)
    )


# ==========================================================================
# J2 主线命令必须是 `all --ai`（不另开命令）
# ==========================================================================
def test_j2_no_explore_ai_as_runnable_command():
    """文档里不许再出现「可照敲」的 `explore --ai` —— 主线一律 `all --ai`。

    由来：2026-10-11 要求 4「两条链路统一成 python -m framework.cli all，
    真 AI 链路用 --ai 区分，不另开命令」。描述式写法不受影响。
    """
    offenders = []
    for rel in GUIDE_DOCS:
        for m in BAD_AI_CMD_RE.finditer(_read(rel)):
            offenders.append(f"{rel}: {m.group(0)}")
    # 生成器：跳过 changelog 段（历史条目里出现旧命令属正常）
    src = _read(GENERATOR)
    span = _changelog_span(src)
    head = src[:span[0]] if span else src
    tail = src[span[1]:] if span else ""
    for m in BAD_AI_CMD_RE.finditer(head + tail):
        offenders.append(f"{GENERATOR}: {m.group(0)}")
    assert not offenders, (
        "文档里仍把 explore --ai 当可照敲的命令（应统一为 all --ai）：\n  " + "\n  ".join(offenders)
    )


def test_j2_all_ai_is_documented():
    """正向：`all --ai` 必须被文档提及（否则新同学找不到统一入口）。"""
    hits = [rel for rel in GUIDE_DOCS if "all --ai" in _read(rel)]
    assert hits, "没有任何指导性文档提到 `all --ai` —— 统一入口没被写出来"


# ==========================================================================
# J3 环境变量表：声称「列全」就必须真的列全
# ==========================================================================
def _config_registry_count():
    """跑 `cli config` 数可调项条数（它是可调项的唯一权威入口，不在此维护第二份）。"""
    r = subprocess.run(
        [sys.executable, "-m", "framework.cli", "config"],
        cwd=str(ROOT), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=120,
    )
    out = r.stdout + r.stderr
    names = set(re.findall(r"(?m)^\s{2,}(HYBRID_[A-Z0-9_]+)\s", out))
    assert names, f"cli config 没解析出可调项，输出头部：\n{out[:500]}"
    return len(names)


def test_j3_env_table_claim_matches_config_count():
    """环境变量表要么别声称「列全」，要么条数真的等于 `cli config`。"""
    src = _read(GENERATOR)
    i = src.find("环境变量与运行开关")
    assert i > 0, "生成器里找不到「环境变量与运行开关」章节（判据需同步更新）"
    seg = src[i:i + 20000]

    # 表头文案（取章节开头到第一个 <table> 之间）
    head_end = seg.find("<table")
    head = seg[:head_end] if head_end > 0 else seg[:3000]

    rows = set(re.findall(r"HYBRID_[A-Z0-9_]+", seg))
    total = _config_registry_count()

    if re.search(r"列全|全部列出|完整清单", head):
        assert len(rows) == total, (
            f"环境变量表声称「列全」但列了 {len(rows)} 项，cli config 有 {total} 项。"
            "要么补全，要么改成「列常用项」并指向 cli config。"
        )
    else:
        assert re.search(r"常用项|常用", head), (
            "环境变量表既没声称「列全」也没说明是「常用项」—— 读者无从判断是否完整"
        )
        assert "framework.cli config" in seg, (
            "环境变量表是「常用项」时，必须给出唯一权威入口 python -m framework.cli config"
        )


# ==========================================================================
# J4 文档里的关键数字 = 代码真值
# ==========================================================================
ASSERT_KINDS_RE = re.compile(r"_ASSERT_KINDS\s*=\s*\{(.*?)\}", re.S)


def test_j4_readme_assert_kind_count_matches_code():
    """README 写的「断言 N 种」必须等于代码里的断言种类数。"""
    m = ASSERT_KINDS_RE.search(_read("framework/features/f02_semantic/generator_generate.py"))
    assert m, "generator_generate.py 里找不到 _ASSERT_KINDS（判据需同步更新）"
    kinds = set(re.findall(r"\"([a-z_]+)\"", m.group(1)))
    assert kinds, "_ASSERT_KINDS 没解析出种类名"

    md = _read("README.md")
    hit = re.search(r"断言\s*\*{0,2}(\d+)\s*\*{0,2}\s*种", md)
    assert hit, "README 里找不到「断言 N 种」这句话（判据需同步更新）"
    assert int(hit.group(1)) == len(kinds), (
        f"README 说断言 {hit.group(1)} 种，代码里是 {len(kinds)} 种：{sorted(kinds)}"
    )


def test_j4_readme_pitfall_count_matches_items():
    """README 写的「最容易踩的 N 条」必须等于该节实际条目数。"""
    md = _read("README.md")
    hit = re.search(r"最容易踩的\s*\*{0,2}(\d+)\s*\*{0,2}\s*条", md)
    assert hit, "README 里找不到「最容易踩的 N 条」（判据需同步更新）"
    claimed = int(hit.group(1))

    # 从该句之后数到下一个二级标题，统计有序列表项 (1. / 2. ...)
    seg = md[hit.end():]
    nxt = re.search(r"\n#{1,3} ", seg)
    if nxt:
        seg = seg[:nxt.start()]
    items = re.findall(r"(?m)^\s*\d+\.\s+\S", seg)
    assert items, "该节里没数到条目（判据需同步更新）"
    assert claimed == len(items), (
        f"README 说「最容易踩的 {claimed} 条」，实际列了 {len(items)} 条"
    )
