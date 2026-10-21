"""`docs/ARCHITECTURE.md` 的**契约判据**（L34-b）：文档写的东西必须真实存在。

为什么需要它（而不是"写完就算"）：
  L33 的原始诉求是「四段契约要有单一权威文档」，可**文档最容易变成愿望清单** ——
  某段被删了、某个产物改了名，文档里还写着，下一个人就照着它去找一个不存在的东西
  （本项目已经踩过：`cli probe` 早删了，文档里还留着它的产物 `probe_*.json`）。

三条判据（都对着**代码**查，不对着文档自己查）：
  1. **四段 + 数据流 + 产物归属 + 模块边界** 四个必备章节都在，且文档不是空壳；
  2. 文档里点名的每个**产物名**，都能在源码里找到写入点（没人产出的产物 = 文档在说谎）；
  3. 文档点名的**段**必须与 `cli.py` 的分发表一致；**已删除的段**（`probe`/手搓链路）
     在文档里只能作为"已删除"出现，不能作为可执行入口出现。

[!] 刻意**不**逐字钉住文档正文：钉死正文会让每次措辞修订都要改判据，
    最后一定被人关掉；这里只钉"事实有没有对应物"。
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DOC = REPO / "docs" / "ARCHITECTURE.md"
CLI = REPO / "framework" / "features" / "f10_cli" / "cli.py"

# ---- 必备章节（标题里必须出现这些词）----
REQUIRED_SECTIONS = ("四段契约", "数据流", "谁的产物是谁的输入", "模块边界", "依赖方向")

# ---- 文档点名的产物 -> 源码里必须出现的写入点字面量 ----
#   只查"有没有人写它"，不查路径拼装细节（路径由 config 决定）。
ARTIFACTS = {
    "element_map_": "element_map_",
    "_harness.py": "_harness.py",
    "conftest.py": "conftest.py",
    "index.json": "index.json",
    "_probe_snapshot.json": "_probe_snapshot.json",
    "_pre.json": "_pre.json",
    "report.html": "report.html",
    "llm_cassettes": "llm_cassettes",
    "scripts/datasets": "datasets",
}

# ---- 段名 -> cli.py 里的处理函数（文档必须点名，代码必须有）----
SEGMENTS = {
    "explore": "cmd_explore",
    "generate": "cmd_generate",
    "run": "cmd_run",
    "all": "cmd_all",
}


def _doc() -> str:
    assert DOC.is_file(), f"缺 {DOC.relative_to(REPO)}（L34-b 要求：四段契约的单一权威文档）"
    return DOC.read_text(encoding="utf-8")


def _sources() -> str:
    out = []
    for p in sorted((REPO / "framework").rglob("*.py")):
        if "__pycache__" in p.parts:
            continue
        out.append(p.read_text(encoding="utf-8", errors="replace"))
    for p in sorted((REPO / "build_tools").glob("*.py")):
        out.append(p.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(out)


def test_doc_has_required_sections_and_is_not_a_stub():
    """四个必备章节都在，且文档有实质内容（防空转假绿）。"""
    text = _doc()
    assert len(text) > 2000, f"文档只有 {len(text)} 字符 —— 像是占位符而不是契约"
    missing = [s for s in REQUIRED_SECTIONS if s not in text]
    assert not missing, (
        f"docs/ARCHITECTURE.md 缺章节：{missing}\n"
        f"  L33/L34 的诉求是「四段契约表 + 数据流图 + 谁的产物是谁的输入」+ 模块边界，缺一个就是不完整。"
    )


def test_every_named_artifact_has_a_writer_in_code():
    """文档点名的产物，源码里必须有人写它 —— 否则文档在指一个不存在的产物。"""
    text = _doc()
    src = _sources()
    named = [name for name in ARTIFACTS if name in text]
    missing = [n for n in named if ARTIFACTS[n] not in src]
    assert not missing, (
        "文档里写了这些产物，但源码里找不到任何写入点（文档说了谎）：\n"
        + "\n".join(f"  - {n}" for n in missing)
    )
    # 防空转：至少要点名一半以上的关键产物，否则这条判据等于没查
    assert len(named) >= 7, (
        f"文档只点名了 {len(named)} 个产物（{sorted(named)}），"
        f"少于 7 个 -> 要么文档缩水了，要么这条判据在空转"
    )


def test_segments_in_doc_match_cli_dispatch():
    """文档点名的段必须与 cli.py 分发表一致；已删除的段不许再作为入口出现。"""
    doc = _doc()
    cli = CLI.read_text(encoding="utf-8")
    for seg, fn in SEGMENTS.items():
        assert f"cli {seg}" in doc, f"文档没写 `cli {seg}` 这一段（四段契约必须点名叫得出来）"
        assert f"def {fn}(" in cli, f"文档写了 `cli {seg}`，但 cli.py 里没有 {fn}()"
    # 反向：已删除的 probe 段只能作为「已删除」被提及（同一句/下一句里有"删除"）
    assert "def cmd_probe(" not in cli, "cli probe 已删除，若它又回来了：先改本判据与文档"
    bad = []
    lines = doc.splitlines()
    for i, line in enumerate(lines):
        if "cli probe" not in line:
            continue
        ctx = line + "\n" + "\n".join(lines[i + 1:i + 2])
        if "删除" not in ctx:
            bad.append((i + 1, line.strip()[:90]))
    assert not bad, (
        "文档把已删除的 `cli probe` 当成可执行入口（同句/下一句没说『删除』）：\n"
        + "\n".join(f"  - L{n}: {s}" for n, s in bad)
        + "\n  V8.6 已随整条手搓链路删掉它，只能写成『已删除』。"
    )


def test_doc_step_field_contract_matches_dataclass():
    """文档里的步骤字段口径必须与 `TestStep` 的真实字段一致（防文档写旧名）。"""
    from framework.features.f03_locate.element_map import TestStep

    doc = _doc()
    fields = set(TestStep.__dataclass_fields__)
    assert "op" in doc and "desc" in doc, "文档没写清步骤字段口径（op / desc）"
    for f in ("op", "desc", "cell_by", "row_index"):
        assert f in fields, f"TestStep 少了字段 {f}（文档却写着它）"
        assert f in doc, f"文档的字段清单漏了 {f}"
