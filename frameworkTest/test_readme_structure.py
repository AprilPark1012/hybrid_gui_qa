"""README 结构的「测试的测试」（2026-09-23 · README 重排批次）。

**为什么需要**（实测真值，重排前）：README 934 行 / 82.8 KB —— 是业界使用型测试框架
（robotframework 151 行 · cypress 94 行 · puppeteer 78 行）的 **15~24 倍**字节；其中
**15 章「变更要点」共约 389 行 = 全文 42%** 被夹在「架构」和「快速上手」之间（新人从"这是什么"
滚到"怎么跑"要越过 389 行往期新闻）；全文**没有目录**；`cli prune` 用法重复 3 处；
4 处写死「当前 16 条」（实际当时已 19 条）；且与培训页大面积重复（目录结构 / 链路 / 常见坑 / 装环境）。

重排口径（AprilPark1012 2026-09-23 拍板）：**简洁优先 —— 7 节 ≤ 250 行**，只讲「背景 / 项目结构 /
快速上手 / 常见的坑」；变更日志归 `releases/RELEASE_NOTES_V*.md`（README 只指路）；
环境变量表与关键技术细节**下沉培训页**。本判据负责**守住新结构**，防止几个月后漂回原样。

判据清单（含负向自证 —— R7 硬要求：只跑正向不算验证过）：
  ① README 存在且文件名为 `README.md`（打包 `pack_release.REQUIRED` 依赖它，不能改名）
  ② 必需章节按约定顺序出现（只认「关键锚点词」，不绑死整条标题文字 ⇒ 允许润色）
  ③ README 里不得再有「变更要点」章（`## 2026-…`）—— 历史归发行说明
  ④ 目录（TOC）与正文 H2 标题**双向一致**（少一项 / 多一项 / 顺序不同都要报）
  ⑤ 不得写死「当前 N 条」这类状态性数字（会随用例增删漂移）
  ⑥ 头部版本号 == 版本单一来源（`framework/tools/common/config.py::read_version`）
  ⑦ README 必须**指路**发行说明，且 `releases/` 下必须有**当前版本**的说明
  ⑧ **体量预算**：README ≤ 250 行（简洁是硬要求；细节下沉培训页 / 发行说明）
  ⑨ README 里引用到的**仓库内路径必须真实存在**（防「文档指了个不存在的东西」）

**取舍说明**：⑤ 只抓「当前 N 条/个」这种**状态性**数字；`11 种断言 kind`、`3 个库` 这类**契约性**
数字不在禁令内（契约变了本来就要改文档，不算漂移源）。

跑法（秒级，不需要 demo / key / git）：
    python -m pytest frameworkTest/test_readme_structure.py -v
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
README = REPO / "README.md"
RELEASE_NOTES_DIR = REPO / "releases"

# ② 约定章节顺序（关键锚点词；README 里必须按这个先后出现）
REQUIRED_SECTIONS = (
    "目录",                 # TOC（正文第一屏；不参与 ④ 的比对）
    "它解决什么问题",
    "快速上手",
    "项目结构与链路",
    "常见坑",
    "文档与资源",
    "许可",
)
TOC_HEADING = "目录"
MAX_LINES = 250             # ⑧ 体量预算（他的口径：简洁是硬要求）

_FENCE = re.compile(r"^\s*(```|~~~)")
_H2 = re.compile(r"^##\s+(?!#)(.+?)\s*$")
# ⑤ 状态性数字：`当前 16 条` / `当前 4 个`
_HARDCODED_COUNT = re.compile(r"当前\s*\d+\s*[条个]")
# ③ 「变更要点」章（旧结构形态：`## 2026-09-23（第二次）变更要点 —— …`）
_CHANGELOG_SECTION = re.compile(r"^##\s+20\d\d-\d\d")
# ⑥ 版本号：头部第一个 `V8.2.3` 形态
_VERSION = re.compile(r"\bV(\d+\.\d+(?:\.\d+)?)\b")


# ---------------- 纯函数层（可秒级钉，负向自证直接钉这几个）----------------

def h2_headings(text: str) -> list[tuple[int, str]]:
    """返回 [(行号, 标题), ...]（1-based）。**跳过 fenced code block 内的行**。"""
    out: list[tuple[int, str]] = []
    in_fence = False
    for i, line in enumerate(text.splitlines(), start=1):
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = _H2.match(line)
        if m:
            out.append((i, m.group(1).strip()))
    return out


_SLUG_DROP = re.compile(r"[^\w\s\u4e00-\u9fff-]", re.UNICODE)


def slug(title: str) -> str:
    """GitHub 风格锚点：去 markdown 修饰 → 去标点 → 空白转 `-` → 小写。

    ⚠️ 与 GitHub 渲染规则对齐（标点删除、空白转连字符）；本项目标题刻意少用标点，
    锚点只应产出 `[a-z0-9\\u4e00-\\u9fff-]`（⑧ 判据守着这点，避免歧义锚点）。
    """
    t = re.sub(r"[`*]", "", title)
    t = _SLUG_DROP.sub("", t)
    # GitHub 口径：**逐个空格**替换为 `-`（连续空格不合并 ⇒ `a  b` → `a--b`）
    t = t.strip().lower().replace(" ", "-")
    return t


def toc_entries(text: str) -> list[str]:
    """取「目录」节里的锚点（按出现顺序）。没有目录 ⇒ 空列表。"""
    heads = h2_headings(text)
    start = end = None
    for idx, (ln, h) in enumerate(heads):
        if h.strip() == TOC_HEADING:
            start = ln
            end = heads[idx + 1][0] if idx + 1 < len(heads) else None
            break
    if start is None:
        return []
    lines = text.splitlines()
    body = "\n".join(lines[start:(end - 1 if end else len(lines))])
    return re.findall(r"^\s*[-*]\s+\[[^\]]*\]\(#([^)]+)\)", body, re.M)


def section_lines(text: str) -> dict[str, int]:
    """锚点词 ⇒ 该 H2 所在行号（找不到 = -1）。"""
    heads = h2_headings(text)
    out: dict[str, int] = {}
    for key in REQUIRED_SECTIONS:
        out[key] = next((ln for ln, h in heads if key in h), -1)
    return out


def order_violations(lines: dict[str, int]) -> list[str]:
    """按约定顺序检查单调递增；返回违规说明（空 = 合规）。"""
    bad: list[str] = []
    prev_key, prev_ln = None, -1
    for key in REQUIRED_SECTIONS:
        ln = lines.get(key, -1)
        if ln < 0:
            bad.append(f"缺章节：{key}")
            continue
        if ln < prev_ln:
            bad.append(f"顺序错：{key}(第{ln}行) 出现在 {prev_key}(第{prev_ln}行) 之前")
        prev_key, prev_ln = key, ln
    return bad


def toc_diff(headings: list[str], toc: list[str]) -> list[str]:
    """目录与正文标题的双向差异（空 = 一致）。`TOC_HEADING` 自身不参与比对。"""
    want = [slug(h) for h in headings if h.strip() != TOC_HEADING]
    bad: list[str] = []
    for s in want:
        if s not in toc:
            bad.append(f"目录缺项：#{s}")
    for s in toc:
        if s not in want:
            bad.append(f"目录多项（正文无此标题）：#{s}")
    if not bad and want != toc:
        bad.append(f"目录顺序与正文不一致：{toc} != {want}")
    return bad


def find_hardcoded_counts(text: str) -> list[str]:
    """状态性写死数字（`当前 16 条`）。空 = 合规。"""
    return _HARDCODED_COUNT.findall(text)


def changelog_sections(text: str) -> list[str]:
    """README 里残留的「变更要点」章标题（应为空 —— 已归 releases/RELEASE_NOTES_V*.md）。"""
    return [line for line in text.splitlines() if _CHANGELOG_SECTION.match(line)]


def framework_version() -> str:
    """版本单一来源：`framework/tools/common/config.py::read_version()`。"""
    spec = importlib.util.spec_from_file_location(
        "hybrid_config_for_readme_test", REPO / "framework" / "tools" / "common" / "config.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return str(mod.read_version()[0])


def _readme() -> str:
    return README.read_text(encoding="utf-8")


# ---------------- ① 文件与命名 ----------------

def test_readme_exists_and_named():
    """打包 `pack_release.REQUIRED` 依赖 `README.md` 这个名字 —— 不能改名。"""
    assert README.is_file(), f"缺 {README}"
    assert README.name == "README.md"


# ---------------- ② 章节顺序 ----------------

def test_required_sections_present_and_in_order():
    text = _readme()
    lines = section_lines(text)
    bad = order_violations(lines)
    assert not bad, "README 结构不合约定：\n  - " + "\n  - ".join(bad)


# ---------------- ③ 变更史必须已搬走 ----------------

def test_no_changelog_sections_left_in_readme():
    left = changelog_sections(_readme())
    assert not left, (
        "README 里还留着「变更要点」章（历史归 releases/RELEASE_NOTES_V*.md，README 只指路）：\n  - "
        + "\n  - ".join(left[:5]) + (f"\n  … 共 {len(left)} 章" if len(left) > 5 else ""))


# ---------------- ④ 目录与标题双向一致 ----------------

def test_toc_matches_h2_headings():
    text = _readme()
    toc = toc_entries(text)
    assert toc, "README 没有目录（`## 目录` + 锚点列表）"
    bad = toc_diff([h for _, h in h2_headings(text)], toc)
    assert not bad, "目录与正文标题不一致：\n  - " + "\n  - ".join(bad)


def test_toc_anchors_characters_are_safe():
    """锚点只允许 `[a-z0-9\\u4e00-\\u9fff-]`（避免 GitHub 锚点歧义）。"""
    text = _readme()
    toc = toc_entries(text)
    assert toc, "README 没有目录，锚点无从校验（别让这条在空目录上假绿）"
    bad = [s for s in toc if not re.fullmatch(r"[a-z0-9\u4e00-\u9fff-]+", s)]
    assert not bad, f"锚点字符不安全（含标点/大写）：{bad}"


# ---------------- ⑤ 写死数字 ----------------

def test_no_hardcoded_state_counts():
    found = find_hardcoded_counts(_readme())
    assert not found, (
        f"README 里还有状态性写死数字 {found} —— 改用抗腐烂写法（如「条数以实跑输出为准」）；"
        "契约性数字（11 种断言 kind）不在禁令内")


# ---------------- ⑥ 版本号与单一来源一致 ----------------

def test_version_matches_single_source():
    text = _readme()
    m = _VERSION.search(text)
    assert m, "README 头部没有版本号（形如 `**V8.2.3**`）"
    want = framework_version()
    assert m.group(1) == want, f"README 版本 {m.group(1)} != 版本单一来源 {want}"


# ---------------- ⑦ 变更日志归发行说明 ----------------

def test_readme_points_to_release_notes():
    """README 只**指路** `releases/RELEASE_NOTES_V*.md`（变更日志的家），且当前版本必须有说明。"""
    text = _readme()
    assert "RELEASE_NOTES" in text, "README 必须指路 releases/RELEASE_NOTES_V*.md（变更日志的家）"
    notes = sorted(RELEASE_NOTES_DIR.glob("RELEASE_NOTES_*.md"))
    assert len(notes) >= 15, f"releases/ 下发行说明偏少：{len(notes)} 份"
    cur = RELEASE_NOTES_DIR / f"RELEASE_NOTES_V{framework_version()}.md"
    assert cur.is_file(), f"当前版本缺发行说明：{cur.name}（发版必带）"


# ---------------- ⑧ 体量预算 ----------------

def test_readme_stays_concise():
    """**简洁是硬要求**：README 是门面 + 快速上手，不是手册（细节归培训页与发行说明）。"""
    lines = _readme().splitlines()
    assert len(lines) <= MAX_LINES, (
        f"README {len(lines)} 行 > 预算 {MAX_LINES} 行 —— 新增内容前先问：该放培训页还是发行说明？")


# ---------------- ⑨ 引用的仓库路径必须存在 ----------------

# 只查「源码 / 文档类」目录：运行期目录（output/ · log/）在交付包解压目录里可能不存在
# ⇒ 一并检查会制造跨环境假红（一类判据必须与「在不在包里」无关）。
_CHECKED_PREFIXES = ("framework/", "frameworkTest/", "featureTest/", "docs/", "build_tools/", "cases/",
                     "scenarios/", "demo/", "releases/", "scripts/")
# 必须含 `/` ⇒ 裸文件名（cli.py / report.html 这类上下文里的简称）不参与，避免误报
_PATH_LIKE = re.compile(r"(?<![\w/.-])((?:[\w.-]+/)+[\w.-]+\.(?:md|py|json|html|yml|yaml))")


def referenced_paths(text: str) -> list[str]:
    """README 里引用的「仓库内文件路径」（带目录前缀、带扩展名、不含通配符）。"""
    out = []
    for m in _PATH_LIKE.finditer(text):
        s = m.group(1).rstrip(".,;:)")
        if s.startswith(_CHECKED_PREFIXES) and "*" not in s:
            out.append(s)
    return sorted(set(out))


def missing_paths(text: str, repo: Path = REPO) -> list[str]:
    return [s for s in referenced_paths(text) if not (repo / s).exists()]


def test_referenced_repo_paths_exist():
    miss = missing_paths(_readme())
    assert not miss, "README 引用了不存在的仓库路径（改结构/改名后记得同步）：\n  - " + "\n  - ".join(miss)


# ---------------- 负向自证（判据自身必须抓得住坏输入）----------------

def test_negative_hardcoded_counts_are_detected():
    """坏输入必须被抓；合法表述不许误伤。"""
    assert find_hardcoded_counts("（当前 16 条；会话级浏览器复用）") == ["当前 16 条"]
    assert find_hardcoded_counts("当前 4 个 worker") == ["当前 4 个"]
    assert find_hardcoded_counts("条数以实跑输出为准") == []
    assert find_hardcoded_counts("11 种断言 kind") == []


def test_negative_section_order_is_detected():
    """顺序颠倒 / 缺章必须报出来（否则 ② 判据等于没写）。"""
    lines: dict[str, int] = dict.fromkeys(REQUIRED_SECTIONS, 100)
    lines["快速上手"] = 10
    lines["这个框架解决什么问题"] = 40        # 顺序故意颠倒
    bad = order_violations(lines)
    assert any("顺序错" in b for b in bad), bad
    missing: dict[str, int] = dict.fromkeys(REQUIRED_SECTIONS, 100)
    del missing["快速上手"]
    assert any("缺章节" in b for b in order_violations(missing))


def test_negative_toc_diff_is_detected():
    """目录少一项 / 多一项都必须报（双向比对，不做单向）。"""
    heads = ["这个框架解决什么问题", "快速上手", "许可"]
    assert toc_diff(heads, [slug(h) for h in heads]) == []
    assert any("缺项" in b for b in toc_diff(heads, [slug("快速上手")]))
    assert any("多项" in b for b in toc_diff(heads, [slug(h) for h in heads] + ["幽灵章节"]))
    assert any("顺序" in b for b in toc_diff(heads, [slug(h) for h in reversed(heads)]))


def test_negative_changelog_sections_are_detected():
    """"变更要点"章残留必须被抓（③ 判据的有效性自证）。"""
    sample = "# x\n\n## 2026-09-23 变更要点 —— 一条命令搞定环境（V8.2.3）\n\n正文\n"
    assert len(changelog_sections(sample)) == 1
    assert changelog_sections("## 快速上手\n\n## 版本与更新\n") == []


def test_slug_rule_is_pinned():
    """钉住锚点规则（否则 ④ 判据的期望值会随实现漂）。"""
    assert slug("## 快速上手") == "快速上手"
    assert slug("快速上手（Windows / Linux）") == "快速上手windows--linux"
    assert slug("目录结构 & 谁负责什么") == "目录结构--谁负责什么"
    assert slug("V8.2.3（2026-09-23）") == "v8232026-09-23"


def test_negative_missing_path_is_detected():
    """引用了不存在的路径必须被抓；裸文件名 / 运行期产物不许误伤。"""
    assert missing_paths("见 `frameworkTest/definitely_missing_xyz.py` 与 `docs/oops.md`") == \
        ["docs/oops.md", "frameworkTest/definitely_missing_xyz.py"]
    assert missing_paths("见 `README.md` 与 `cli.py`（裸文件名不参与比对）") == []
    assert missing_paths("见 `featureTest/run_acceptance.py`（真实存在 ⇒ 不许误伤）") == []
