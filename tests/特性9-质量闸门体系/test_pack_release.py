"""交付打包自检的「测试的测试」（V7.5.1）。

`build_tools/pack_release.py` 的 `check_zip()` 是**唯一**会在打包时看包内产物的闸门；
它自己必须被证明「坏包能抓、好包不误伤」——否则又是一次假绿（2026-09-15 那次
`unzip` 缺失导致 `grep -c` 数到空输入、误判「包是干净的」就是反例）。

跑法（秒级）：
    cd ~/hybrid_gui_qa && source .venv/bin/activate
    python -m pytest tests/特性9-质量闸门体系/test_pack_release.py -v
"""
from __future__ import annotations

import importlib.util
import json
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

_spec = importlib.util.spec_from_file_location("pack_release", REPO / "build_tools" / "pack_release.py")
assert _spec is not None and _spec.loader is not None
pack_release = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pack_release)


# ---------------- 录像随包交付的闸门（2026-10-14 口径变更：只有一个 zip）----------------
# 背景（实测）：录像曾经「发出去之后才发现 5 个场景只有 1 个有可用录像」-> 无网机器上那 4 个场景
# 必失败，而打包环节**没有任何检查**会告诉你这件事。
# [!] 2026-10-14（用户口径纠正）：`llm_cassettes` 本来就住在工程 `output/` 下，
#   「整个工程打包」自然要把它带进**同一个** zip —— 旧的「两件套 / 独立录像包」**已废弃**。
#   闸门因此从「打录像包前体检」改成「**打代码包时默认体检**」。下面钉四件事：
#   (1) 接线必须在，且**不能藏在 --with-cassettes 后面**（源码级锁）；
#   (2) 覆盖不全 **必须拦**（不留半成品包）；
#   (3) 显式逃生口必须有效（否则现场要临时绕过时只能改代码 —— 那更糟）；
#   (4) 录像**必须真的在包里**（按份数核对，而不是「看着像打进去了」）。

def _make_cassette_json(name: str, scenario_line: str) -> dict:
    return {
        "key": "deadbeef00000000", "key_struct": "feedface00000000",
        "prompt": f"系统提示\n自然语言测试场景: 「{scenario_line}」\n控件清单…",
        "system": "sys", "model": "m",
        "responses": [{"kind": "text", "completion": "{}"}],
        "framework_version": "0.0", "created_at": "2026-01-01T00:00:00+08:00",
    }


def test_cassette_gate_is_wired_into_default_pack():
    """源码级接线锁：**默认**打包路径就要过录像体检（不复用一份口径 = 迟早漂）。"""
    src = (REPO / "build_tools" / "pack_release.py").read_text(encoding="utf-8")
    assert "cassette_coverage_problems()" in src, "默认打包没接录像体检 -> 坏包照样出厂"
    assert "check_cassettes.py" in src, "体检必须复用同一份口径（build_tools/check_cassettes.py）"
    assert "--allow-missing-cassettes" in src, "缺逃生口 -> 需要临时绕过时只能改代码"
    # 反证：体检不能再躲在 `if a.with_cassettes:` 后面（那就是「只有显式要才查」）
    tail = src.split("if a.with_cassettes:", 1)[-1]
    assert "cassette_coverage_problems" not in tail, (
        "录像体检又躲回 --with-cassettes 后面了 -> 默认打包不做检查（交付可能带坏录像）")
    # 独立录像包机制应已删除（交付只有一个 zip）
    assert "def pack_cassettes(" not in src, "独立的录像包机制应已删除"


def _cov_dirs(tmp_path, *, covered: bool):
    """造一对 (scenarios, cassettes) 目录 —— 可控「场景有没有被录像覆盖」。"""
    cass = tmp_path / "cass"
    cass.mkdir()
    scen = tmp_path / "scen"
    scen.mkdir()
    (scen / "a.yml").write_text("scenario: 现在这个场景\n", encoding="utf-8")
    line = "现在这个场景" if covered else "某个早就改过的老场景（录像里根本没有）"
    rec = _make_cassette_json("deadbeef00000000.json", line)
    (cass / "deadbeef00000000.json").write_text(
        json.dumps(rec, ensure_ascii=False), encoding="utf-8")
    return scen, cass


def test_cassette_coverage_reports_uncovered_scenario(tmp_path):
    """★ 行为：录像目录**有文件**、但场景没被覆盖 -> 必须报问题。

    这是最容易被漏掉的形态：「有录像」不等于「场景被覆盖」——
    包看着有内容，到无网机器上那些场景**直接跑不了**。
    """
    scen, cass = _cov_dirs(tmp_path, covered=False)
    problems = pack_release.cassette_coverage_problems(scen, cass)
    assert problems, "覆盖不全却没报问题 -> 坏包会照样出厂"


def test_cassette_coverage_passes_when_covered(tmp_path):
    """反向自证：覆盖完整时必须**零问题**（闸门误拦 = 人就会去绕过它）。"""
    scen, cass = _cov_dirs(tmp_path, covered=True)
    problems = pack_release.cassette_coverage_problems(scen, cass)
    assert problems == [], f"覆盖完整却报问题（误拦）：{problems}"


def test_pack_blocks_when_coverage_incomplete(tmp_path, monkeypatch):
    """★ 端到端接线：覆盖不全时 `main()` 必须 exit 2，且**不留半成品包**。

    用 monkeypatch 把「收集哪些文件 / 包内自检」换成最小值 —— 本条要验的是
    **录像闸门在默认打包路径上真的会拦**，不是整个工程打包能不能过。
    """
    monkeypatch.setattr(pack_release, "cassette_coverage_problems",
                        lambda *a, **k: ["[NG] 场景 a.yml 缺可用录像"])
    monkeypatch.setattr(pack_release, "collect_files", lambda: [REPO / "README.md"])
    monkeypatch.setattr(pack_release, "check_zip", lambda *a, **k: [])
    monkeypatch.setattr(sys, "argv", ["pack_release.py", "--out", str(tmp_path)])

    rc = pack_release.main()

    assert rc == 2, f"覆盖不全却没拦住（rc={rc}）-> 坏包会出厂"
    assert not list(tmp_path.glob("*.zip")), \
        f"拦下后不该留下半成品包：{[p.name for p in tmp_path.glob('*.zip')]}"


def test_pack_escape_hatch_allows_incomplete_coverage(tmp_path, monkeypatch):
    """负向自证：显式给逃生口时必须**放过**（逃生口失效 = 现场只能改代码绕过，那更糟）。"""
    monkeypatch.setattr(pack_release, "cassette_coverage_problems",
                        lambda *a, **k: ["[NG] 场景 a.yml 缺可用录像"])
    monkeypatch.setattr(pack_release, "collect_files", lambda: [REPO / "README.md"])
    monkeypatch.setattr(pack_release, "check_zip", lambda *a, **k: [])
    monkeypatch.setattr(sys, "argv", ["pack_release.py", "--out", str(tmp_path),
                                      "--allow-missing-cassettes"])

    rc = pack_release.main()

    assert rc == 0, f"给了逃生口却没放过（rc={rc}）"
    assert list(tmp_path.glob("*.zip")), "逃生口生效却没产包"


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
        "pkg/build_tools/build_html.py": 'VERSION = "9.9"\n',
        "pkg/docs/training.html": "<html></html>",
        "pkg/framework/features/f10_cli/cli.py": "\n",
        "pkg/framework/shared/text_io.py": "\n",
        # P20：产物 = scripts/generated/<场景>/<用例>.py（一个用例一个文件）
        #   -> "坏产物"注入点仍在"用例脚本"这一层（产物检查拼读全部生成模块）
        "pkg/scripts/generated/demo/x.py": tests_src + unmapped_extra,
        "pkg/scripts/generated/_harness.py": GOOD_CONFTEST,
        "pkg/scripts/generated/conftest.py": "from _harness import *\n",
        "pkg/scripts/generated/index.json": '{"x": {}}',
        "pkg/tests/_helpers/test_x.py": "\n",
        "pkg/tests/_runner/verify_x.py": "import sys\n",
        "pkg/demo/x.py": "\n",
        "pkg/scenarios/x.yml": "scenario: x\n",
    }
    if not skip_case:
        entries["pkg/cases/x.json"] = '{"case_id": "x", "steps": []}'
    if legacy_layout:
        entries.pop("pkg/build_tools/build_html.py", None)
        entries.pop("pkg/docs/training.html", None)
        entries.pop("pkg/framework/shared/text_io.py", None)
        entries["pkg/build_html.py"] = 'VERSION = "9.9"\n'
        entries["pkg/training.html"] = "<html></html>"
        entries["pkg/framework/text_io.py"] = "\n"
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
    """★ 核心判据：包内是「元素未映射」存根 -> 必须报出来（这就是 V7.5 交付事故本体）。"""
    zp = _make_zip(tmp_path, BAD_TESTS)
    problems = pack_release.check_zip(zp, expect_cases=1, require_notes_for="9.9")
    assert any("元素未映射" in p for p in problems), f"坏产物没被抓住：{problems}"


def test_good_package_passes(tmp_path):
    """好包不许误伤（否则闸门会被绕过/关掉）。"""
    zp = _make_zip(tmp_path, GOOD_TESTS)
    assert pack_release.check_zip(zp, expect_cases=1, require_notes_for="9.9") == []


def test_missing_release_notes_for_current_version_is_caught(tmp_path):
    """版本号改了但发版说明没写 -> 报出来（交付物完整性）。"""
    zp = _make_zip(tmp_path, GOOD_TESTS, notes=False)
    problems = pack_release.check_zip(zp, expect_cases=1, require_notes_for="9.9")
    assert any("RELEASE_NOTES" in p for p in problems), problems


def test_legacy_layout_audited_without_false_alarm(tmp_path):
    """结构变更前的历史包：用当前必需项清单审计**不许误报**，但要如实标出历史形态。

    背景（2026-09-19）：`build_html.py` 挪进 tools/、`training.html` 归位 docs/ 之后，
    用新代码审计老的 V7.7 包会报「缺 build_tools/build_html.py / docs/training.html」—— 那是**误报**，
    历史包本来就按当时结构打的。误报会诱发人绕过工具，所以按「两种落点都认」的先例修掉。
    """
    zp = _make_zip(tmp_path, GOOD_TESTS, legacy_layout=True)
    legacy: list[str] = []
    problems = pack_release.check_zip(zp, expect_cases=1, require_notes_for="9.9",
                                      legacy_notes=legacy)
    assert problems == [], f"历史形态包被误报：{problems}"
    assert len(legacy) == 3, f"历史形态命中没被标出来（应 3 条：build_html / training.html / text_io）：{legacy}"


def test_really_missing_required_is_still_caught(tmp_path):
    """★ 负向：两个位置都没有（真缺项）-> 必须照样报 —— 别名不许放过真问题。"""
    zp = _make_zip(tmp_path, GOOD_TESTS, legacy_layout=True, drop=("pkg/build_html.py",))
    problems = pack_release.check_zip(zp, expect_cases=1, require_notes_for="9.9")
    assert any("build_tools/build_html.py" in p for p in problems), problems


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
    """包内 cases 数量与仓库不一致 -> 报出来（打包漏文件/多余文件）。"""
    zp = _make_zip(tmp_path, GOOD_TESTS, skip_case=True)
    problems = pack_release.check_zip(zp, expect_cases=1, require_notes_for="9.9")
    assert any("cases/**/*.json 数量" in p or "没有任何 cases" in p for p in problems), problems


def test_cassette_readme_text_carries_listing_and_falsifiability(tmp_path):
    """★ 包内用法说明：收包人得知道「这是什么 / 怎么用 / 怎么证明没联网」。

    为什么留这份 README：录像现在是**随包交付**的一份数据，光有 json 说不清用途；
    说明里必须写清「端点指黑洞 127.0.0.1:9」——那是**可证伪**的（证明真没联网）。
    """
    src = tmp_path / "llm_cassettes"
    src.mkdir()
    (src / "abc123.json").write_text(json.dumps(
        {"created_at": "2026-09-18T13:05:21+08:00", "model": "deepseek-chat",
         "responses": [{"kind": "plan"}]}), encoding="utf-8")

    text = pack_release.cassette_readme_text(sorted(src.glob("*.json")), "9.9")

    assert "V9.9" in text and "abc123.json" in text, "用法说明里要有版本与录像清单"
    assert "127.0.0.1:9" in text, "必须写清「端点指黑洞」这条可证伪性"
    assert "output/llm_cassettes/" in text, "要说清录像就在本包哪个位置（收包人不用找第二个包）"
    assert "两件套" not in text, "说明里不该再出现已废弃的「两件套」说法"


def test_zip_check_catches_missing_or_wrong_cassette_count(tmp_path):
    """★ 负向：录像**必须真的在包里** —— 按份数核对，不靠「看着像打进去了」。

    背景：录像漏打时，无外网的机器上 `explore --ai --llm-cassette` 直接跑不了，
    而包本身「看着是完整的」—— 正是那种发出去才发现的坏包。
    """
    zp = tmp_path / "x.zip"
    with zipfile.ZipFile(zp, "w") as z:
        z.writestr("tag/README.md", "hi")

    none_at_all = pack_release.check_zip(zp, expect_cassettes=1)
    assert any("没有任何 output/llm_cassettes" in p for p in none_at_all), none_at_all

    with zipfile.ZipFile(zp, "a") as z:
        z.writestr("tag/output/llm_cassettes/a.json", "{}")
    # [!] 只滤**录像类**问题：这个最小 zip 本来就会缺一堆必需项（那不在本条射程内），
    #     拿全部问题判「误拦」会自己绊自己。
    cas_problems = [p for p in pack_release.check_zip(zp, expect_cassettes=1)
                    if "llm_cassettes" in p]
    assert cas_problems == [], f"有 1 份却报录像问题（误拦）：{cas_problems}"

    wrong = [p for p in pack_release.check_zip(zp, expect_cassettes=2) if "期望 2 份" in p]
    assert wrong, "份数不对却没报"

    # 默认不传 -> 不查（最小包构造的判据只塞几个文件，不该被录像要求误报一片）
    assert not [p for p in pack_release.check_zip(zp) if "llm_cassettes" in p]


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
    for must in ("README.md", "build_tools/build_html.py", "framework/features/f10_cli/cli.py", "framework/shared/text_io.py",
                 "scripts/generated", "scripts/generated/index.json", "demo/app.py",
                 "tests/特性9-质量闸门体系/test_artifacts_health.py", "tests/特性9-质量闸门体系/verify_html_sync.py", "cases", "scenarios"):
        assert any(r == must or r.startswith(must + "/") for r in rel), f"漏了 {must}"
    # 2026-10-13（用户第 ④ 条）：`output/` 放行 element_maps（交付生成物之一）。
    # 2026-10-14（用户口径纠正）：`output/llm_cassettes/` **也要放行** ——
    #   它本就在工程 output/ 下，整个工程打包自然带进**同一个** zip（旧的「两件套」已废弃）。
    #   log/ 与其它 output 子目录（traces / verify / archived_* / *_shots）仍不得进包。
    bad = [r for r in rel
           if r.startswith(("log/", ".venv/"))
           or (r.startswith("output/")
               and not r.startswith(("output/element_maps/", "output/llm_cassettes/")))
           or "__pycache__" in r or r.endswith((".zip", ".tar.gz", ".env"))]
    assert not bad, f"包里有不该发的内容：{bad[:5]}"
    # 录像必须在包里（按用户口径与代码包同一个 zip）
    cas = [r for r in rel if r.startswith("output/llm_cassettes/") and r.endswith(".json")]
    assert cas, "录像（output/llm_cassettes/*.json）没被收进包 -> 无网机器上回放直接跑不了"
    # elementMap 必须随包交付，且**只带最新 1 份**（42 份历史快照会让包从 ~2M 涨到 20M+）
    emaps = [r for r in rel if r.startswith("output/element_maps/")]
    assert len(emaps) == 1, f"element_maps 应只收最新 1 份，实收 {len(emaps)} 份：{emaps[:3]}"
    # 升级日志必须进包；releases/ 下其它东西（交付包本体 / 内部记录）不得进包（2026-09-18 口径）
    notes = [r for r in rel if r.startswith("releases/")
             and r.rsplit("/", 1)[-1].startswith("RELEASE_NOTES")]
    assert notes, "升级日志（releases/RELEASE_NOTES_*.md）没被收进包"
    leaked = [r for r in rel if r.startswith("releases/") and r not in notes]
    assert not leaked, f"releases/ 下不该进包的内容混进来了：{leaked[:5]}"

def test_auth_json_gate_behaves(tmp_path):
    """★ 守门（V8.5.1 语义反转）：`_auth.json` **已废弃**，包里出现它必须在**显式要求时**被抓住。

    **历史**（V8.3.4 时的正确行为，现已反转）：那时登录前置靠运行期读
    `scripts/generated/_auth.json` 注入 token，包里的 `scripts/generated/*.py` 是预生成产物、
    用户解包后直接 run，所以**必须带它**，否则业务页被重定向到登录页、报出来却是
    「元素语义未找到」，排查方向被带偏。当时判据锁的是「缺了必报」。

    **现在**（V8.5.1 登录步骤化后）：登录由场景 `login:` 段声明 -> 生成期展开成用例前导步骤
    -> 执行期真在页面上填账号点登录。`_auth.json` 那套**整体删除，没有任何代码读它**。
    它还留在包里就成了：① **没人用却含明文口令**的凭据暴露面；② 误导收包人以为还有隐藏前置。

    -> 判据语义**整体反转**，锁三件事（缺一不可）：
      (1) **默认不查** —— 本文件的判据都用**最小临时包**构造各种形态，若不区分地检查，
          会把这批判据**全部误报**（2026-10-07 实测 4 条被带红）；
      (2) **显式要求时，带了必报** —— 交付路径（CLI `--check` / 打包后自检）就是这么调的；
      (3) **没带不许报** —— 否则闸门会误伤正确的新包。

    [!] 必须能红：把 `expect_auth_json` 的反向拦截分支删掉 => 本判据立刻失败。
    """
    zp = _make_zip(tmp_path, GOOD_TESTS)

    # (1) 默认不查：最小包里没有 _auth.json，也不许报（防误伤）
    assert pack_release.check_zip(zp, expect_cases=1, require_notes_for="9.9") == [], \
        "默认不该检查 _auth.json —— 否则最小包构造的判据会被误报一片"

    # (2) 显式要求时，**没带**是正确的（不许报）
    assert pack_release.check_zip(zp, expect_cases=1, require_notes_for="9.9",
                                 expect_auth_json=False) == [], \
        "包里没有 _auth.json 是 V8.5.1 的正确形态，闸门不该报"


def test_auth_json_present_is_caught(tmp_path):
    """反向拦截（V8.5.1）：包里**带了**已废弃的 `_auth.json` => **必须报出来**。

    为什么必须能红：这条是防「打包脚本那段 V8.3.4 补丁回归」的唯一哨兵 ——
    该补丁当年是**正确的**（运行期要读），删机制时极容易被漏掉（V8.5.1 实际就这么漏了，
    把含明文口令的文件打进了交付包）。
    """
    base = _make_zip(tmp_path / "b", GOOD_TESTS)
    zp = tmp_path / "with_auth.zip"
    with zipfile.ZipFile(base) as src, zipfile.ZipFile(zp, "w") as dst:
        for n in src.namelist():
            dst.writestr(n, src.read(n))
        dst.writestr("pkg/scripts/generated/_auth.json", '{"x": {}}')
    problems = pack_release.check_zip(zp, expect_cases=1, require_notes_for="9.9")
    assert any("_auth.json" in p for p in problems), \
        f"包里带了已废弃的 _auth.json 却没被抓住：{problems}"
