"""R8「三方同步」的判据 —— 代码 / README / 培训页（docs/training.html）必须一致。

**为什么需要**（2026-09-23 AprilPark1012现场发现）：培训页第 2 章的目录树**停在旧版**，
比代码少了整整一批文件 —— P16 新增的三个定位模块（`anchor.py` / `scope_locate.py` /
`semantic_locate.py`）、`build_tools/` 的录像工具（`check_cassettes.py` / `record_cassettes.py`）、
`demo/` 的订单两页 + todo 页、`tests/_runner/` 的两个入口（`run_verifications.py` / `run_acceptance.py`）
与判据公共件、`releases/` 整节、仓库根配置文件全没写。
根因：那棵树是 `build_html.py` 里**硬编码的字符串**，改动代码时没人回头改它
-> 「看着正常、其实没在干活」的老毛病（同 R9 搬家协议打的是同一类病）。

判据三条（含负向自证 —— R7：只跑正向不算验证过）：
  (1) **关键入口/模块必须在培训页里出现**（新增模块忘了补文档 -> 红）
  (2) **培训页正文引用的仓库路径必须存在**；版本史附录（`A 版本与更新记录`）属**冻结历史**，
     按 R9 口径原样保留 -> 那片区域不查（否则会逼着人去改历史记录）
  (3) **实际顶层目录必须被 README 提到**（新增顶层目录不能悄悄加）

跑法（秒级，不需要 demo/key/git）：
    python -m pytest tests/特性8-质量闸门体系/test_docs_sync.py -v
"""
from __future__ import annotations

import html as html_mod
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import repo_files  # noqa: E402

README = REPO / "README.md"
HTML = REPO / "docs" / "training.html"

# (1) 这些「入口 / 框架模块 / 开发期工具 / 判据公共件」必须能在培训页里找到
MUST_BE_DOCUMENTED = (
    # 运行期（framework/）
    "cli.py", "config.py", "text_io.py", "browser.py", "limits.py", "retention.py", "target_probe.py",
    "probe.py", "element_map.py", "locator_bridge.py",
    "anchor.py", "scope_locate.py", "semantic_locate.py",
    "explorer.py", "llm_cassette.py",
    "generator.py", "case_builder.py", "scenario.py", "data_driven.py",
    "runner.py", "healer.py",
    # 开发期（build_tools/）
    "pack_release.py", "build_html.py", "check_cassettes.py", "record_cassettes.py", "offline_explore_chain.py",
    # 判据与验证入口（tests/_helpers/ + tests/_runner/）
    "run_verifications.py", "run_acceptance.py", "demo_freshness.py",
    "repo_files.py", "artifacts.py", "testid_policy.py",
)

# (2) 路径引用：只认「带目录前缀 + 带扩展名」
_PATH = re.compile(
    r"(?<![\w/.-])((?:cases|tests|docs|build_tools|framework|scenarios|demo|scripts|releases)"
    r"/[\w./-]+\.(?:py|md|json|html|yml|yaml|sh))")
# 教程里的占位示例（指「你自己的文件」，不是真路径）
_PLACEHOLDER = ("xxx", "用例.json", "你的")
# 运行期目录：交付包解压目录里可能不存在 -> 不查（一类判据必须与「在不在包里」无关）
_RUNTIME_PREFIXES = ("output/", "log/")

# 版本史附录（冻结历史：里面的旧文档引用按 R9 原样保留，不逼人改历史）
_CHANGELOG_ANCHOR = re.compile(r'<span class="n">A</span>版本与更新记录')


def live_body(text: str) -> str:
    """返回「需要检查」的部分：版本史附录之前的正文。"""
    m = _CHANGELOG_ANCHOR.search(text)
    return text[:m.start()] if m else text


def referenced_paths(html: str) -> list[str]:
    out = []
    for m in _PATH.finditer(html):
        s = m.group(1).rstrip(".,;:)")
        if "*" in s or "{" in s or "<" in s:
            continue
        if any(p in s for p in _PLACEHOLDER) or s.startswith(_RUNTIME_PREFIXES):
            continue
        out.append(s)
    return sorted(set(out))


def missing_paths(html: str, repo: Path = REPO) -> list[str]:
    return [s for s in referenced_paths(html) if not (repo / s).exists()]


def undocumented_modules(html: str) -> list[str]:
    return [m for m in MUST_BE_DOCUMENTED if m not in html]


def repo_top_level_dirs(repo: Path = REPO) -> list[str]:
    rels, _src = repo_files.file_list(repo)
    return sorted({r.split("/")[0] for r in rels if "/" in r})


# ---------------- (1) 关键模块必须在培训页里 ----------------

def test_training_html_documents_key_modules():
    html = HTML.read_text(encoding="utf-8")
    missing = undocumented_modules(html)
    assert not missing, (
        "培训页没提到这些入口 / 模块（新增了就要在培训页第 2 章目录树里补上，改完重跑 "
        "`python build_tools/build_html.py`）：\n  - " + "\n  - ".join(missing))


# ---------------- (2) 培训页引用的路径必须存在 ----------------

def test_training_html_referenced_paths_exist():
    html = HTML.read_text(encoding="utf-8")
    miss = missing_paths(live_body(html))
    assert not miss, (
        "培训页引用了不存在的仓库路径（改结构 / 改名后记得同步；改完重跑 "
        "`python build_tools/build_html.py`）：\n  - " + "\n  - ".join(miss))


# ---------------- (3) 顶层目录必须被 README 覆盖 ----------------

def test_every_repo_top_level_dir_is_documented():
    readme = README.read_text(encoding="utf-8")
    tops = repo_top_level_dirs()
    assert tops, "拿不到仓库文件清单（清单来源异常）"
    missing = [t for t in tops if f"{t}/" not in readme]
    assert not missing, (
        "这些顶层目录在 README 里完全没提（新增顶层目录不能悄悄加）：\n  - " + "\n  - ".join(missing))


# ---------------- 负向自证（判据自身必须抓得住坏输入）----------------

def test_negative_missing_path_is_detected():
    assert missing_paths("见 <code>tests/_helpers/definitely_missing_xyz.py</code>") == \
        ["tests/_helpers/definitely_missing_xyz.py"]
    assert missing_paths("见 <code>build_tools/nope_xyz.py</code> 与 <code>docs/training.html</code>") == \
        ["build_tools/nope_xyz.py"]


def test_negative_placeholder_and_runtime_paths_are_ignored():
    """占位示例与运行期目录不许误伤（假红与假绿一样会摧毁闸门）。"""
    assert missing_paths("见 <code>cases/xxx.json</code> · <code>scripts/datasets/xxx.json</code>") == []
    assert missing_paths("证据在 <code>output/element_maps/</code> 与 <code>log/latest/report.html</code>") == []


# r9-legacy-block:begin —— 负向样例区：这里**必须**写出「已移出仓库的旧设计文档路径」，
#   否则测不到「版本史附录该被跳过」这件事。它只作为字符串出现在测试里、不渲染进任何对外产物。
def test_negative_changelog_area_is_excluded():
    """版本史附录里的旧文档引用（冻结历史）不该让判据变红。"""
    # 正文区的路径必须是**真实存在**的 —— 本判据只验「历史区被跳过」，
    # 不能因为样例文件被 R7-f 清掉而假红（2026-09-30：原用 search_mixed.json，已随三目录重建清除）。
    body = '<h2>正文</h2><p>见 <code>cases/orders_invoice_full_lifecycle/ai_orders_invoice_full_lifecycle_140528.json</code></p>'
    hist = '<span class="n">A</span>版本与更新记录</h2><p>见 <code>docs/P4-慢目标与并发-修复方案.md</code></p>'
    assert missing_paths(live_body(body + hist)) == []
# r9-legacy-block:end


def test_negative_undocumented_module_is_detected():
    assert undocumented_modules("clients: cli.py")  # 缺一大批 -> 非空
    assert undocumented_modules(" · ".join(MUST_BE_DOCUMENTED)) == []


# ---------------- (4) 目录树的「父子归属」（L20 · 2026-09-28 新增） ----------------
# 起因：第 2 章目录树里，6 个**一类**条目（test_*.py / demo_freshness.py / repo_files.py · artifacts.py /
# testid_policy.py / fixtures/*.html）被挂在 `tests/_runner/` 父节点下，而它们实际住在
# `tests/_helpers/` -> 对外培训页把两类目录的职责讲反了。
# 为什么以前的判据抓不到：(1)「关键模块名出现过」只查名字在不在页面里，不查**挂在谁下面**；
# (2) 引用路径判据只看路径存在性。-> 这条判据看的是**树的结构**。

_TREE_BLOCK = re.compile(r'<pre class="tree">(.*?)</pre>', re.S)
_TREE_ENTRY = re.compile(r"^([\s│]*)(?:├──|└──)\s*(.+)$")

# 该住 `_helpers/`（公共模块）与该住 `_runner/`（入口与工具）的条目（2026-10-07 按 9 特性重组后）
_HELPERS_ONLY = ("repo_files.py", "artifacts.py", "testid_policy.py", "demo_freshness.py", "_gen_layout.py")
_RUNNER_ONLY = ("run_verifications.py", "run_acceptance.py", "rerecord_cassettes.py", "fixtures/")


def tree_entries(html_text: str) -> list[tuple[int, str, str]]:
    """把「含 tests/_helpers/ 的那棵目录树」解析成 [(深度, 条目名, 父条目名)]。

    只认 `├──` / `└──` 这一种画法 —— 换画法 -> 解析不出 -> 判据会红（有意的：目录树的结构必须机器可读，
    否则「谁挂在谁下面」这件事没法钉）。
    """
    # 2026-10-07：目录树改成 `tests/` → 特性夹 + `_helpers/` + `_runner/` 两级 ->
    # 不能再找 "tests/_helpers/" 这一整串（重组后树里没这串），改判「同时含 _helpers/ 与特性夹」。
    block = next((b for b in _TREE_BLOCK.findall(html_text)
                  if "_helpers/" in b and "特性1-混合链路" in b), None)
    if block is None:
        return []
    text = html_mod.unescape(re.sub(r"<[^>]+>", "", block))
    stack: list[tuple[int, str]] = [(-1, "hybrid_gui_qa/")]
    out: list[tuple[int, str, str]] = []
    for line in text.splitlines():
        m = _TREE_ENTRY.match(line)
        if not m:
            continue
        depth = len(m.group(1)) // 4
        name = m.group(2).strip()
        while stack and stack[-1][0] >= depth:
            stack.pop()
        out.append((depth, name, stack[-1][1] if stack else ""))
        stack.append((depth, name))
    return out


def belonging_problems(entries: list[tuple[int, str, str]]) -> list[str]:
    """口径（2026-10-07 按 9 个特性重组后 —— 判据与负向自证共用）：

    · 一类 `test_*.py` 与二类 `verify_*.py` **都必须挂在特性夹下**（`tests/特性N-<名>/`），
      **不许住** `_helpers/` / `_runner/`；
    · `_helpers/` 只许放**公共模块**（repo_files / artifacts / testid_policy / demo_freshness / _gen_layout）；
    · `_runner/` 只许放**入口与工具**（run_verifications / run_acceptance / rerecord_cassettes / fixtures）。

    [!] 旧版这条判据查的是「一类不挂 `_runner`、二类不挂 `_helpers`」—— 重组后两类都搬进特性夹，
    那两个目录里**再也不会出现** test_/verify_ -> 判据**恒真空转**（2026-10-07 审视时发现）。
    """
    # [!] 只按目录名匹配：重组后目录树是 `tests/` → `_helpers/`/`_runner/` 两级，
    # 父节点名里**没有** "tests/_helpers/" 这整串（旧版按它匹配 -> 永远空 -> 判据空转）。
    helpers = [n for _, n, p in entries if "_helpers" in p]
    runner = [n for _, n, p in entries if "_runner" in p]
    bad: list[str] = []
    for name in helpers + runner:
        if name.startswith("test_") or name.startswith("verify_"):
            bad.append(f"{name} 挂在 `_helpers/` 或 `_runner/` 下 -> "
                       f"一类/二类都**必须住特性夹**（`tests/特性N-<名>/`）")
    for name in _RUNNER_ONLY:
        if any(name in h for h in helpers):
            bad.append(f"{name} 挂在 `tests/_helpers/` 下 -> 入口/工具应住 `tests/_runner/`")
    for name in _HELPERS_ONLY:
        if any(name in r for r in runner):
            bad.append(f"{name} 挂在 `_runner/` 下 -> 公共模块应住 `_helpers/`")
    for name in _HELPERS_ONLY:            # 同一模块名出现在两类清单里也不许（防清单漂移）
        if any(name in h for h in helpers) and name in _RUNNER_ONLY:
            bad.append(f"{name} 同时出现在两类清单里 -> 清单漂移")
    return bad


def test_training_tree_parent_child_belonging():
    """第 2 章目录树里：一类 `test_*.py` / 二类 `verify_*.py` 都必须在**特性夹**下；
    `_helpers/` 只放公共模块、`_runner/` 只放入口与工具。"""
    html_text = HTML.read_text(encoding="utf-8")
    entries = tree_entries(html_text)
    assert entries, "解析不出第 2 章目录树（树画法变了 -> 本判据要同步）"
    bad = belonging_problems(entries)
    assert not bad, (
        "培训页目录树把两类文件挂错了父节点（改完重跑 `python build_tools/build_html.py`）：\n  - "
        + "\n  - ".join(bad))


_MISPLACED_TREE = """
<b>hybrid_gui_qa/</b>
├── <b>tests/</b>                     测试根：一个特性一个文件夹
│   ├── 特性1-混合链路/
│   │   └── verify_*.py              二类验证（← 挂对了）
│   ├── _helpers/                    公共模块
│   │   └── run_verifications.py     ★ 二类统一入口（← 故意错挂：runner 工具应住 _runner/）
│   └── _runner/                     入口与工具
│       ├── test_*.py                一类判据（← 故意错挂：一类应住特性夹）
│       └── demo_freshness.py        demo 新鲜度闸门（← 故意错挂：公共模块应住 _helpers/）
"""

_CORRECT_TREE = """
<b>hybrid_gui_qa/</b>
├── <b>tests/</b>                     测试根：一个特性一个文件夹
│   ├── 特性1-混合链路/
│   │   ├── test_*.py                一类判据
│   │   └── verify_*.py              二类验证
│   ├── _helpers/                    公共模块
│   │   └── demo_freshness.py        demo 新鲜度闸门
│   └── _runner/                     入口与工具
│       └── run_verifications.py     ★ 二类统一入口
"""


def test_negative_misplaced_tree_is_caught():
    """负向自证：故意挂错的树必须被抓住（否则这条判据等于恒真）。"""
    bad = belonging_problems(tree_entries(f'<pre class="tree">{_MISPLACED_TREE}</pre>'))
    assert any("test_*.py" in b for b in bad), f"错挂的 test_*.py 没被抓：{bad}"
    assert any("demo_freshness.py" in b for b in bad), f"错挂的 demo_freshness.py 没被抓：{bad}"


def test_negative_correct_tree_passes():
    """负向自证：挂对的树不许被误报（防判据写成恒红、逼人绕过）。"""
    assert belonging_problems(tree_entries(f'<pre class="tree">{_CORRECT_TREE}</pre>')) == []
