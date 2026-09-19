"""交付打包自检的「测试的测试」（V7.5.1）。

`tools/pack_release.py` 的 `check_zip()` 是**唯一**会在打包时看包内产物的闸门；
它自己必须被证明「坏包能抓、好包不误伤」——否则又是一次假绿（2026-09-15 那次
`unzip` 缺失导致 `grep -c` 数到空输入、误判「包是干净的」就是反例）。

跑法（秒级）：
    cd ~/hybrid_gui_qa && source .venv/bin/activate
    python -m pytest tests/test_pack_release.py -v
"""
from __future__ import annotations

import importlib.util
import json
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

_spec = importlib.util.spec_from_file_location("pack_release", REPO / "tools" / "pack_release.py")
assert _spec is not None and _spec.loader is not None
pack_release = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pack_release)

GOOD_TESTS = '''"""生成物（正例）。"""
def test_ok(page, ctx):
    _goto(page, "http://localhost:8000/")
    _act(page, "click", semantic='搜索', primary=lambda p: p.get_by_test_id("btn-search"))
'''
BAD_TESTS = GOOD_TESTS + '''\n\ndef test_broken(page, ctx):
    pytest.fail("元素未映射：语义名 '新建合同' 不在探测清单/快照里", pytrace=False)
'''
GOOD_CONFTEST = """
def _act(page, action, semantic=None, primary=None, value=None): ...
def _goto(page, url): ...
def _reset_target_data(): ...
def _assert_text(page, text, desc=""): ...
def _assert_value(page, element, expect): ...
"""


def _make_zip(tmp_path: Path, tests_src: str, *, notes: bool = True,
              unmapped_extra: str = "", skip_case: bool = False,
              notes_path: str = "pkg/releases/RELEASE_NOTES_V9.9.md",
              extra_notes: tuple[str, ...] = (),
              legacy_layout: bool = False,
              drop: tuple[str, ...] = ()) -> Path:
    """造一个「结构完整」的最小交付包，只让被测判据不同。

    升级日志默认放 `pkg/releases/` 下（2026-09-18 起的落点）；`notes_path` 可改成包根（历史形态）。
    `legacy_layout=True`：按 2026-09-19 结构调整**之前**的形态造包（`build_html.py` 在包根、
    `training.html` 在包根）—— 用来证明「审计历史包不会误报」。
    `drop`：故意去掉某些条目（造真缺项，验负向）。
    """
    tmp_path.mkdir(parents=True, exist_ok=True)
    zp = tmp_path / "pkg.zip"
    entries = {
        "pkg/README.md": "# x\n",
        "pkg/tools/build_html.py": 'VERSION = "9.9"\n',
        "pkg/docs/training.html": "<html></html>",
        "pkg/framework/cli.py": "\n",
        "pkg/framework/text_io.py": "\n",
        "pkg/scripts/test_cases.py": tests_src + unmapped_extra,
        "pkg/scripts/conftest.py": GOOD_CONFTEST,
        "pkg/tests/test_x.py": "\n",
        "pkg/demo/x.py": "\n",
        "pkg/scenarios/x.yml": "scenario: x\n",
    }
    if not skip_case:
        entries["pkg/cases/x.json"] = '{"case_id": "x", "steps": []}'
    if legacy_layout:
        entries.pop("pkg/tools/build_html.py", None)
        entries.pop("pkg/docs/training.html", None)
        entries["pkg/build_html.py"] = 'VERSION = "9.9"\n'
        entries["pkg/training.html"] = "<html></html>"
    for k in drop:
        entries.pop(k, None)
    if notes:
        entries[notes_path] = "# 9.9\n"
    for n in extra_notes:
        entries[f"pkg/releases/{n}"] = "# 旧版升级日志\n"
    with zipfile.ZipFile(zp, "w") as z:
        for name, content in entries.items():
            z.writestr(name, content)
    return zp


def test_broken_artifact_is_caught(tmp_path):
    """★ 核心判据：包内是「元素未映射」存根 ⇒ 必须报出来（这就是 V7.5 交付事故本体）。"""
    zp = _make_zip(tmp_path, BAD_TESTS)
    problems = pack_release.check_zip(zp, expect_cases=1, require_notes_for="9.9")
    assert any("元素未映射" in p for p in problems), f"坏产物没被抓住：{problems}"


def test_good_package_passes(tmp_path):
    """好包不许误伤（否则闸门会被绕过/关掉）。"""
    zp = _make_zip(tmp_path, GOOD_TESTS)
    assert pack_release.check_zip(zp, expect_cases=1, require_notes_for="9.9") == []


def test_missing_release_notes_for_current_version_is_caught(tmp_path):
    """版本号改了但发版说明没写 ⇒ 报出来（交付物完整性）。"""
    zp = _make_zip(tmp_path, GOOD_TESTS, notes=False)
    problems = pack_release.check_zip(zp, expect_cases=1, require_notes_for="9.9")
    assert any("RELEASE_NOTES" in p for p in problems), problems


def test_legacy_layout_audited_without_false_alarm(tmp_path):
    """结构变更前的历史包：用当前必需项清单审计**不许误报**，但要如实标出历史形态。

    背景（2026-09-19）：`build_html.py` 挪进 tools/、`training.html` 归位 docs/ 之后，
    用新代码审计老的 V7.7 包会报「缺 tools/build_html.py / docs/training.html」—— 那是**误报**，
    历史包本来就按当时结构打的。误报会诱发人绕过工具，所以按「两种落点都认」的先例修掉。
    """
    zp = _make_zip(tmp_path, GOOD_TESTS, legacy_layout=True)
    legacy: list[str] = []
    problems = pack_release.check_zip(zp, expect_cases=1, require_notes_for="9.9",
                                      legacy_notes=legacy)
    assert problems == [], f"历史形态包被误报：{problems}"
    assert len(legacy) == 2, f"历史形态命中没被标出来（应 2 条）：{legacy}"


def test_really_missing_required_is_still_caught(tmp_path):
    """★ 负向：两个位置都没有（真缺项）⇒ 必须照样报 —— 别名不许放过真问题。"""
    zp = _make_zip(tmp_path, GOOD_TESTS, legacy_layout=True, drop=("pkg/build_html.py",))
    problems = pack_release.check_zip(zp, expect_cases=1, require_notes_for="9.9")
    assert any("tools/build_html.py" in p for p in problems), problems


def test_release_notes_recognized_in_both_layouts(tmp_path):
    """升级日志在 releases/ 下（新落点）与在包根（历史包）都要认得出来。"""
    zp = _make_zip(tmp_path, GOOD_TESTS)                       # pkg/releases/RELEASE_NOTES_V9.9.md
    assert pack_release.check_zip(zp, expect_cases=1, require_notes_for="9.9") == []
    zp2 = _make_zip(tmp_path / "old", GOOD_TESTS, notes_path="pkg/RELEASE_NOTES_V9.9.md")
    assert pack_release.check_zip(zp2, expect_cases=1, require_notes_for="9.9") == []


def test_missing_history_release_notes_is_caught(tmp_path):
    """★ 交付包要带**全部**历史升级日志（AprilPark1012 2026-09-18 要求）：只带当前版本那份要报出来。"""
    zp = _make_zip(tmp_path, GOOD_TESTS)
    problems = pack_release.check_zip(zp, expect_cases=1, require_notes_for="9.9", expect_notes=3)
    assert any("升级日志" in p for p in problems), problems
    zp2 = _make_zip(tmp_path / "full", GOOD_TESTS,
                    extra_notes=("RELEASE_NOTES_V9.8.md", "RELEASE_NOTES_V9.7.md"))
    assert pack_release.check_zip(zp2, expect_cases=1, require_notes_for="9.9", expect_notes=3) == []


def test_case_count_mismatch_is_caught(tmp_path):
    """包内 cases 数量与仓库不一致 ⇒ 报出来（打包漏文件/多余文件）。"""
    zp = _make_zip(tmp_path, GOOD_TESTS, skip_case=True)
    problems = pack_release.check_zip(zp, expect_cases=1, require_notes_for="9.9")
    assert any("cases/*.json 数量" in p or "没有任何 cases" in p for p in problems), problems


def test_cassette_pack_contains_recordings_readme_and_helper(tmp_path, monkeypatch):
    """★ 交付「两件套」的第二件：录像包必须含 录像 + 用法说明 + 一键脚本。

    背景（2026-09-19）：此前录像包由一个**仓库外的独立脚本**打（~/deliver_scripts/pack_cassettes.py），
    没有任何判据、路径还漂了（里面残留 build_html.py 的老路径）⇒ 收进打包器并钉住内容。
    """
    src = tmp_path / "llm_cassettes"
    src.mkdir()
    (src / "abc123.json").write_text(json.dumps(
        {"created_at": "2026-09-18T13:05:21+08:00", "model": "deepseek-chat",
         "responses": [{"kind": "plan"}]}), encoding="utf-8")
    helper = tmp_path / "offline_explore_chain.py"
    helper.write_text("# helper\n", encoding="utf-8")
    monkeypatch.setattr(pack_release, "CASSETTE_SRC", src)
    monkeypatch.setattr(pack_release, "CASSETTE_HELPER", helper)
    out = tmp_path / "out"
    out.mkdir()

    zp = pack_release.pack_cassettes(out, "9.9")
    assert zp is not None and zp.exists()
    with zipfile.ZipFile(zp) as z:
        names = z.namelist()
        readme = z.read("llm_cassettes_README.md").decode("utf-8")
    assert "llm_cassettes/abc123.json" in names, names
    assert "llm_cassettes_README.md" in names, names
    assert "tools/offline_explore_chain.py" in names, names
    assert "V9.9" in readme and "abc123.json" in readme, "用法说明里要有版本与录像清单"
    assert "127.0.0.1:9" in readme, "必须写清「端点指黑洞」这条可证伪性"


def test_cassette_pack_refuses_when_no_recordings(tmp_path, monkeypatch):
    """★ 负向：没有录像时必须**打不出包**（返回 None），绝不产出一个空包糊过去。"""
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setattr(pack_release, "CASSETTE_SRC", empty)
    out = tmp_path / "out"
    out.mkdir()
    assert pack_release.pack_cassettes(out, "9.9") is None
    assert not list(out.glob("*.zip")), "不许留下空包"


def test_refresh_sums_lists_existing_zips_and_keeps_ledger(tmp_path):
    """SHA256SUMS.txt：有效行 = 现存 zip（自算 sha256）；`#` 台账注释原样保留。"""
    import hashlib as _h
    d = tmp_path
    (d / "a.zip").write_bytes(b"AAA")
    (d / "b.zip").write_bytes(b"BBB")
    (d / "SHA256SUMS.txt").write_text(
        "# 台账：历史删除记录\n#   old.zip  deadbeef\n0000  a.zip\n", encoding="utf-8")

    pack_release.refresh_sums(d)
    txt = (d / "SHA256SUMS.txt").read_text(encoding="utf-8")
    assert "# 台账：历史删除记录" in txt and "old.zip  deadbeef" in txt, "注释台账不许被冲掉"
    lines = [l for l in txt.splitlines() if l.strip() and not l.startswith("#")]
    assert len(lines) == 2, lines
    assert f"{_h.sha256(b'AAA').hexdigest()}  a.zip" in lines
    assert f"{_h.sha256(b'BBB').hexdigest()}  b.zip" in lines
    assert "0000  a.zip" not in txt, "旧的有效行必须被真值取代（手抄的数不许留着）"


def test_refresh_sums_drops_line_of_deleted_package(tmp_path):
    """包删掉后，清单里那条有效行必须消失（注释里的留档照旧）。"""
    import hashlib as _h
    d = tmp_path
    (d / "gone.zip").write_bytes(b"X")
    pack_release.refresh_sums(d)
    assert f"{_h.sha256(b'X').hexdigest()}  gone.zip" in (d / "SHA256SUMS.txt").read_text(encoding="utf-8")
    (d / "gone.zip").unlink()
    pack_release.refresh_sums(d)
    txt = (d / "SHA256SUMS.txt").read_text(encoding="utf-8")
    assert not [l for l in txt.splitlines() if l.strip() and not l.startswith("#")], txt


def test_collect_files_keeps_sources_and_drops_runtime_cruft():
    """打包收集：源代码/用例/生成物要进包，运行时证据与虚拟环境不得进包。"""
    rel = {p.relative_to(REPO).as_posix() for p in pack_release.collect_files()}
    for must in ("README.md", "tools/build_html.py", "framework/cli.py", "framework/text_io.py",
                 "scripts/test_cases.py", "scripts/conftest.py", "demo/app.py",
                 "tests/test_artifacts_health.py", "cases", "scenarios"):
        assert any(r == must or r.startswith(must + "/") for r in rel), f"漏了 {must}"
    bad = [r for r in rel if r.startswith(("output/", "log/", ".venv/"))
           or "__pycache__" in r or r.endswith((".zip", ".tar.gz", ".env"))]
    assert not bad, f"包里有不该发的内容：{bad[:5]}"
    # 升级日志必须进包；releases/ 下其它东西（交付包本体 / 内部记录）不得进包（2026-09-18 口径）
    notes = [r for r in rel if r.startswith("releases/")
             and r.rsplit("/", 1)[-1].startswith("RELEASE_NOTES")]
    assert notes, "升级日志（releases/RELEASE_NOTES_*.md）没被收进包"
    leaked = [r for r in rel if r.startswith("releases/") and r not in notes]
    assert not leaked, f"releases/ 下不该进包的内容混进来了：{leaked[:5]}"
