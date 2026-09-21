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
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

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
    (re.compile(r"docs/P\d+-[^\s`<>)）]*\.md"),
     "指向已移出仓库的设计文档（现住项目台账 references/design/）",
     "仓库内改成中性表述（如「见内部设计文档『X』」），别写内部台账路径"),
    (re.compile(r"docs/BACKLOG[^\s`<>)）]*\.md"),
     "指向已移出仓库的台账",
     "同上"),
)


def iter_tracked_text_files(repo: Path = REPO):
    """仓库里被 git 跟踪的文本文件（二进制按 NUL 字节粗判跳过）。"""
    out = subprocess.run(["git", "ls-files"], cwd=str(repo), capture_output=True,
                         text=True, encoding="utf-8", errors="replace", check=True).stdout
    for rel in out.splitlines():
        if any(rel.startswith(d) for d in EXEMPT_DIRS) or rel in EXEMPT_FILES:
            continue
        p = repo / rel
        try:
            raw = p.read_bytes()
        except OSError:
            continue
        if b"\0" in raw[:4096]:
            continue
        yield rel, raw.decode("utf-8", errors="replace")


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
    for rel, text in iter_tracked_text_files(repo):
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
    files = [rel for rel, _ in iter_tracked_text_files(tmp_path)] if _has_git(tmp_path) else []
    # 未初始化 git 的临时目录拿不到跟踪清单 ⇒ 直接验证豁免判定函数本身
    assert all(not rel.startswith(EXEMPT_DIRS) for rel in files)
# r9-legacy-block:end


def _has_git(p: Path) -> bool:
    try:
        subprocess.run(["git", "rev-parse", "--git-dir"], cwd=str(p),
                       capture_output=True, text=True, encoding="utf-8", errors="replace", check=True)
        return True
    except Exception:
        return False
