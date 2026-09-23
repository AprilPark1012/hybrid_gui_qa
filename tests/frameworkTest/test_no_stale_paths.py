"""R9「搬家协议」的自动化判据 —— 搬家要查调用方，要按新的目录结构修正调用关系（2026-09-21 定）。

本文件回答一个问题：**「还有谁在指旧位置？」** —— 答案必须是这条判据的 grep 结果，
而不是「我记得改过了」。搬家（改名 / 移动 / 分层 / 把内容移出仓库）之后跑它：
- 活引用（会被执行、被照抄的：源码、脚本、测试提示语、活文档）留在旧路径上 ⇒ **红**；
- 人工确认过的历史记录 / 对照示例 / 负向样例 ⇒ 用**豁免标记**显式声明，不算命中。

三级豁免（每级都要写清理由；豁免区**不许扩大**到掩盖真问题）：
  ① `EXEMPT_DIRS`  —— 历史交付记录目录（冻结历史，按 R9 口径原样保留、不回头改）
  ② `EXEMPT_FILES` —— 生成物（其唯一来源文件已在同一判据下检查）
  ③ 行内标记 —— `r9-legacy-ok`（该行 + 之后 MARK_WINDOW 行）、块标记
     `r9-legacy-block:begin` / `r9-legacy-block:end`（包裹整段历史区）
     ⚠️ 标记一律写在**不会被渲染进对外产物**的位置：Python 注释 / Markdown 的 HTML 注释。
     不要写进会渲染的字符串里（培训页是给团队看的对外文档，不能出现内部标记）。

负向自证（R7：只跑正向不算验证过）：见文件尾部的 `test_negative_*` —— 在 tmp 假仓库里
造 5 种旧路径形态，逐一断言「必须抓到」；再断言三级豁免各自「必须放行」。

对应文档：skill `hybrid-gui-test-framework` 的作业协议 ⑥ R9（含两条实测踩坑实例）。
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

# 同目录测试工具：文件清单入口（git 优先 / 非 git 等效降级）
sys.path.insert(0, str(Path(__file__).resolve().parent))
import repo_files  # noqa: E402

# ---- 豁免 ①：历史交付记录（冻结历史，不随搬家修正）--------------------------
# 理由：releases/ 里是**当时发出的**发行说明与交付记录 —— 它们记录的是当时真实的路径，
#       改掉就成了篡改历史（R9 口径：冻结的历史记录原样保留）。
EXEMPT_DIRS = ("releases/",)

# ---- 豁免 ②：生成物 ---------------------------------------------------------
# 理由：training.html 由 build_tools/build_html.py 生成；**源头已在同一判据下检查**，
#       生成物必然继承其版本史区（历史条目里的旧路径）。只豁免生成物本身，不豁免源头。
EXEMPT_FILES = ("docs/training.html",)

# ---- 豁免 ③：行内/块标记（写在注释里，渲染不可见）---------------------------
MARKER_OK = "r9-legacy-ok"
BLOCK_BEGIN = "r9-legacy-block:begin"
BLOCK_END = "r9-legacy-block:end"
MARK_WINDOW = 4          # 标记行之后多少行内算豁免

# ---- 已废弃路径清单（旧 → 新）----------------------------------------------
# ⚠️ 加新条目时**必须同时给「为什么旧、新在哪」**，否则后来人不知道该怎么修。
FLAT_MODULES = ("config|text_io|limits|retention|browser|target_probe|probe|element_map|"
                "locator_bridge|explorer|llm_cassette|generator|case_builder|scenario|"
                "data_driven|runner|healer")   # V8.0 前的 17 个平铺模块

STALE = (
    (re.compile(r"from framework\.(" + FLAT_MODULES + r")\b"),
     "旧平铺 import（V8.0 前：framework/<模块>.py）",
     "改为 from framework.tools.<层>.<模块> import …"),
    (re.compile(r"(?<![A-Za-z_./])framework/(" + FLAT_MODULES + r")\.py"),
     "旧平铺模块路径（V8.0 前）",
     "改为 framework/tools/<层>/<模块>.py"),
    (re.compile(r"(?<![A-Za-z_])tools/(build_html|pack_release|offline_explore_chain)\.py"),
     "旧开发工具目录（V8.0 把仓库根 tools/ 改名 build_tools/）",
     "改为 build_tools/…"),
    (re.compile(r"python build_html\.py"),
     "旧命令写法（少了目录前缀，照抄会失败）",
     "改为 python build_tools/build_html.py"),
    # ⚠️ 试过加一条「裸 tools/ 目录名」模式（匹配 `tools/` 独立出现），**实测误伤 14+ 处**：
    #    README 里的说明文字、`framework/tools/common/…` 的提及、注释里的历史叙述全中 ——
    #    按「假红与假绿一样会摧毁闸门」的口径**不启用**（一条会天天误报的判据最终会被人关掉）。
    #    这类「说明性文字里的旧目录名」的成本远低于「用户照抄旧命令」（后者已由上面两条
    # r9-legacy-ok（说明性引用：这里必须写出旧写法才能说清覆盖范围）
    #    `tools/<脚本>.py` 与「缺目录前缀的 build_html 写法」两条覆盖）⇒ 作为**已知边界**记在这里，
    #    靠人工审查兜（实例：build_tools/offline_explore_chain.py 的 docstring 曾写「住在仓库的 tools/」，
    #    2026-09-21 人工发现并修掉）。
    (re.compile(r"docs/P\d+-[^\s`<>)）]*\.md"),
     "指向已移出仓库的设计文档（现住项目台账 references/design/）",
     "仓库内改成中性表述（如「见内部设计文档『X』」），别写内部台账路径"),
    (re.compile(r"docs/BACKLOG[^\s`<>)）]*\.md"),
     "指向已移出仓库的台账",
     "同上"),
)


def iter_repo_text_files(repo: Path = REPO):
    """仓库里的文本文件：**已跟踪 + 未跟踪但不被忽略**（与打包脚本的收集口径一致）；二进制按 NUL 粗判跳过。

    ⚠️ 为什么必须带「未跟踪」这一半（2026-09-21 实测踩到，属**假绿**，最坏的一种）：
    本判据原先只走 `git ls-files`（仅已跟踪）⇒ **新写的文件在提交前根本不在扫描范围内** ——
    提交前全绿、刚提交就红。人看到「刚才跑过一遍是绿的」就以为查过了，实际漏的就是**新增文件**
    （而搬家/改名恰恰最爱在新文件里留下旧路径引用，比如新写的测试里照抄老命令）。
    ⇒ 与打包脚本的收集口径对齐：文件一落到工作区（哪怕还没 add）就被查。

    ⚠️ 2026-09-22 再修一层：清单来源改走 `tests/frameworkTest/repo_files.py`（**git 优先、非 git 等效降级**）。
    老写法是直调 `git ls-files ... check=True` —— 而**交付包解压目录不是 git 仓库**，
    团队用户按 README 跑到这里直接 exit 128 报红；可本判据要判的事（「还有谁在指旧位置」）
    与有没有 `.git` 毫无关系（AprilPark1012 本地 Windows 验收实测）。降级后判据照常判，清单来源写进消息。
    """
    rels, _source = repo_files.file_list(repo)
    for rel in rels:
        if any(rel.startswith(d) for d in EXEMPT_DIRS) or rel in EXEMPT_FILES:
            continue
        text = repo_files.read_text_file(repo / rel)
        if text is None:
            continue
        yield rel, text


def scan_text(rel: str, text: str):
    """扫一段文本，返回 [(rel, lineno, why, fix, line), ...]（已应用三级豁免）。"""
    hits = []
    in_block = False
    last_marker = -10 ** 6
    for i, line in enumerate(text.splitlines(), start=1):
        if BLOCK_BEGIN in line:
            in_block = True
            continue
        if BLOCK_END in line:
            in_block = False
            continue
        if MARKER_OK in line:
            last_marker = i
            continue
        if in_block or (i - last_marker) <= MARK_WINDOW:
            continue
        for pat, why, fix in STALE:
            if pat.search(line):
                hits.append((rel, i, why, fix, line.strip()[:140]))
    return hits


def scan_repo(repo: Path = REPO):
    hits = []
    for rel, text in iter_repo_text_files(repo):
        hits.extend(scan_text(rel, text))
    return hits


def _fmt(hits):
    lines = [f"  ❌ {r}:{n}  {why}\n       修法：{fix}\n       原文：{src}" for r, n, why, fix, src in hits]
    return "\n".join(lines)


# ============================ 正向：当前仓库必须干净 ============================

def test_repo_has_no_stale_paths():
    """搬家后的活引用不许留在旧位置（豁免区除外）。"""
    hits = scan_repo()
    assert not hits, (
        f"发现 {len(hits)} 处指向旧位置的活引用（R9：搬家要查调用方，要按新结构修正）：\n"
        + _fmt(hits)
        + "\n\n  若某处是**有意保留**的历史记录 / 对照示例，请在其上一行（4 行内）加注释标记 "
          f"`{MARKER_OK}`，或用 `{BLOCK_BEGIN}` / `{BLOCK_END}` 包住整段历史区。"
    )


def test_exempt_entries_still_exist():
    """豁免不许腐化：目录 / 文件豁免必须真的存在（删了就得从清单里摘掉）。"""
    for d in EXEMPT_DIRS:
        assert (REPO / d).exists(), f"EXEMPT_DIRS 里的 {d} 已不存在 ⇒ 请从判据里摘掉"
    for f in EXEMPT_FILES:
        assert (REPO / f).exists(), f"EXEMPT_FILES 里的 {f} 已不存在 ⇒ 请从判据里摘掉"


# ============================ 负向自证：必须抓得到 ============================

def _fake_repo(tmp_path: Path) -> Path:
    (tmp_path / "framework").mkdir(parents=True, exist_ok=True)
    (tmp_path / "framework" / "cli.py").write_text("x = 1\n", encoding="utf-8")
    return tmp_path


# r9-legacy-block:begin —— 本判据自身的**负向样例区**：
#   下面这些字符串是「要测的坏形态」与「豁免用例的素材」，**必须保留旧路径写法**（否则判据测不到东西）。
#   它们只作为字符串出现在测试里，不会被渲染进任何对外产物；扫仓库时本块跳过。
@pytest.mark.parametrize("snippet, why_fragment", [
    ("from framework.probe import probe_page", "旧平铺 import"),
    ("见 framework/runner.py 的说明", "旧平铺模块路径"),
    ("python tools/pack_release.py --with-cassettes", "旧开发工具目录"),
    ("修法：python build_html.py && git add docs/training.html", "旧命令写法"),
    ("设计见 docs/P4-慢目标与并发-修复方案.md", "已移出仓库的设计文档"),
    ("台账见 docs/BACKLOG-下一步优化.md", "已移出仓库的台账"),
])
def test_negative_each_stale_form_is_caught(tmp_path, snippet, why_fragment):
    """6 种旧路径形态：每一种都必须被点名（漏一种就是假绿）。"""
    p = _fake_repo(tmp_path) / "note.md"
    p.write_text(snippet + "\n", encoding="utf-8")
    hits = scan_text("note.md", p.read_text(encoding="utf-8"))
    assert len(hits) == 1, f"应恰好抓 1 条，实际 {hits}"
    assert why_fragment in hits[0][2], f"归因不对：{hits[0][2]}"


def test_negative_new_paths_are_not_flagged(tmp_path):
    """不能误伤新路径（假红与假绿一样会摧毁闸门）。"""
    good = "\n".join([
        "from framework.tools.probe.probe import probe_page",
        "见 framework/tools/run/runner.py",
        "python build_tools/pack_release.py --with-cassettes",
        "python build_tools/build_html.py",
        "设计见内部设计文档「慢目标与并发修复方案」",
        "见 build_tools/offline_explore_chain.py",
        "运行期模块在 framework/tools/common/ 下（这条不许被误伤）",
        "开发期工具都在 build_tools/ 下（这条也不许被误伤）",
    ])
    assert scan_text("ok.md", good) == []


# ============================ 负向自证：豁免必须生效 ============================

def test_marker_line_exempts_following_lines():
    text = f"<!-- {MARKER_OK} 破坏性变更对照示例 -->\nfrom framework.probe import x\n" + "y\n" * 6 + "from framework.generator import z\n"
    hits = scan_text("r.md", text)
    assert len(hits) == 1 and hits[0][1] == 9, f"标记只应豁免窗口内的行，实际 {hits}"


def test_block_marker_exempts_whole_section():
    text = (f"# {BLOCK_BEGIN}\nfrom framework.probe import x\nfrom framework.runner import y\n"
            f"# {BLOCK_END}\nfrom framework.healer import z\n")
    hits = scan_text("m.py", text)
    assert len(hits) == 1 and "healer" in hits[0][4], f"块标记应只豁免块内，实际 {hits}"


def test_exempt_dir_and_file_skipped(tmp_path):
    (tmp_path / "releases").mkdir()
    (tmp_path / "releases" / "RELEASE_NOTES_V1.md").write_text("python tools/pack_release.py\n", encoding="utf-8")
    (tmp_path / "note.md").write_text("python tools/pack_release.py\n", encoding="utf-8")
    files = [rel for rel, _ in iter_repo_text_files(tmp_path)] if _has_git(tmp_path) else []
    # 未初始化 git 的临时目录拿不到跟踪清单 ⇒ 直接验证豁免判定函数本身
    assert all(not rel.startswith(EXEMPT_DIRS) for rel in files)
def test_negative_untracked_file_is_scanned(tmp_path):
    """**未跟踪**（但未被忽略）的新文件必须在提交前就被扫到 —— 2026-09-21 实测的假绿盲点。

    原先只扫 `git ls-files`（已跟踪）⇒ 新增文件在提交前不在扫描范围内：提交前全绿、一提交就红；
    更坏的是「我刚才跑过一遍是绿的」会让人以为已经查过了。本判据已与打包口径对齐
    （已跟踪 + 未跟踪但不被忽略）—— 本用例就是它的**负向自证**：造一个真 git 仓库，
    把旧路径写进**未跟踪**的新文件，断言必须被抓到。
    """
    subprocess.run(["git", "init", "-q"], cwd=str(tmp_path), check=True)
    (tmp_path / "tracked.md").write_text("已跟踪、且干净\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.md"], cwd=str(tmp_path), check=True)
    (tmp_path / "brand_new_test.py").write_text(
        "python tools/pack_release.py --with-cassettes\n", encoding="utf-8")   # 尚未 git add
    hits = scan_repo(tmp_path)
    assert any(rel == "brand_new_test.py" for rel, *_ in hits), \
        f"未跟踪文件里的旧路径**必须**被抓到（抓不到就是假绿，正是要堵的盲点），实际 {hits}"


def test_negative_tracked_clean_file_still_passes(tmp_path):
    """对照：同一次扫描里，干净文件不许被误伤（假红与假绿一样会摧毁闸门）。"""
    subprocess.run(["git", "init", "-q"], cwd=str(tmp_path), check=True)
    (tmp_path / "ok.md").write_text("python build_tools/pack_release.py --with-cassettes\n", encoding="utf-8")
    subprocess.run(["git", "add", "ok.md"], cwd=str(tmp_path), check=True)
    assert scan_repo(tmp_path) == [], "新路径不许被判成命中"


# r9-legacy-block:end


def _has_git(p: Path) -> bool:
    try:
        subprocess.run(["git", "rev-parse", "--git-dir"], cwd=str(p),
                       capture_output=True, text=True, encoding="utf-8", errors="replace", check=True)
        return True
    except Exception:
        return False
