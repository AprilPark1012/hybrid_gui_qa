"""生成物健康度闸门（V7.5.1，配套 2026-09-15 交付事故）。

事故链条：现场 probe 不可用 → `generate` 只警告一句就落盘 → 产出一份
「16 个用例、每步都是 `pytest.fail(元素未映射)` 存根」的生成产物 →
**没人检查包内产物** → 提交 + 打包 + 交付 → 数天后在慢目标闸门炸成 50 条失败。

⇒ 生成期有质量闸（见 tests/frameworkTest/test_generate_quality_gate.py），**生成之后**还要有一道
「产物本身健不健康」的闸门：本文件就是它。秒级、不需要 demo、不需要浏览器，能进 CI。

P20（2026-09-24）布局变更：产物从「单个 `scripts/test_cases.py` + `scripts/conftest.py`」改成
    scripts/generated/<scenario_id>/<case_id>.py   ← 一个用例一个脚本（AI 用例）
    scripts/generated/manual/<case_id>.py          ← 手搓用例（无场景的）
    scripts/generated/_harness.py                  ← 共享辅助（原 conftest 内容原样搬来）
    scripts/generated/conftest.py                  ← 只做转发（sys.path + from _harness import …
    scripts/generated/index.json                   ← case_id → {script_path, 各种指纹}
⇒ 本文件的**判据语义一律不变**（守的还是那些交付事故），只是「在哪读产物」跟着布局走：
   「一个文件」→「generated/ 下的全部用例模块」，`conftest.py` 的接线 → `_harness.py`。
   旧路径 scripts/test_cases.py / scripts/conftest.py 已删除（不留兼容壳 ✗），不再是允许名单成员。

跑法：
    cd ~/hybrid_gui_qa && source .venv/bin/activate
    python -m pytest tests/frameworkTest/test_artifacts_health.py -v
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))        # 同目录测试工具

import artifacts                                              # noqa: E402

SCRIPTS = REPO / "scripts"
CASES = REPO / "cases"

# 生成物必须带的接线（少一个都说明「产物与代码/靠契约不同步」）：
#   _goto            = F1 页面就绪契约（等数据渲染完再动作，防慢目标假红）
#   _reset_target_data = demo 数据搬到服务端后的「用例间复位」
#   四个断言辅助     = 11 种断言的 render 产物（V7.2）
# P20：这些 `def` 现在住在 scripts/generated/_harness.py（原 conftest 内容原样搬过来），
#      conftest.py 退化成转发 ⇒ 判据改读 _harness.py（判的事没变：产物必须带齐接线）。
REQUIRED_CONFTEST = ("_act", "_goto", "_data", "_log", "_reset_target_data",
                     "_assert_text", "_assert_url", "_assert_value", "_assert_count")

# 脚本（conftest.py / _harness.py）不算「用例模块」—— 它们是共享运行时，不是产物里的一条用例
_SHARED_MODULES = ("conftest.py", "_harness.py")

_NO_MODULES = ("generated/ 下一个用例模块都没有（应为 scripts/generated/<场景>/<用例>.py）"
               "⇒ 产物还没产出。先确认被测目标起着（另开一个窗口 `python -m demo.app`），"
               "再跑 `python -m framework.cli generate`（或 `cli all` 一条龙）。")


def _gen_dir() -> Path:
    """P20 产物根 `scripts/generated/`。

    ⚠️ 每次现算而不做模块级常量：判据的沙箱会把 `SCRIPTS` 指到临时目录
    （见 test_env_adaptation.test_contract_gates_now_report_actionable_message），
    模块级常量不会跟着变 ⇒ 会读到真实仓库的产物，沙箱用例失去意义。
    """
    return SCRIPTS / "generated"


def _rel(p: Path) -> str:
    """报告里用仓库相对路径（沙箱路径相对不了就用绝对）。"""
    try:
        return str(p.relative_to(REPO))
    except ValueError:
        return str(p)


def _case_modules() -> list[Path]:
    """`generated/` 下的全部**用例模块** = 原 `test_cases.py` 的全部内容（一个用例一个文件）。

    排除 conftest.py / _harness.py：前者只做转发，后者是共享辅助 —— `_harness.py` 里的
    `page.goto()` 正是**就绪契约 `_goto` 的实现本体**，不是「产物绕过契约」。
    """
    d = _gen_dir()
    if not d.is_dir():
        return []
    return sorted(p for p in d.rglob("*.py") if p.name not in _SHARED_MODULES)


def test_generated_test_cases_has_no_unmapped_stubs():
    """生成物用例脚本绝不允许含「元素未映射」存根 —— 那就是交付事故本体。"""
    mods = _case_modules()
    assert mods, _NO_MODULES
    hits: dict[str, int] = {}
    for p in mods:
        txt = artifacts.read_artifact(p, role=f"生成物 {_rel(p)}")
        if (n := txt.count("元素未映射")):
            hits[_rel(p)] = n
    n = sum(hits.values())
    assert n == 0, (f"生成物里有 {n} 处「元素未映射」存根 ⇒ 这份产物是探测失败时落盘的垃圾，"
                    f"别提交/打包/交付；重新在目标可用的前提下跑 `python -m framework.cli generate`\n"
                    + "\n".join(f"   {f}: {c} 处" for f, c in sorted(hits.items())))


def test_generated_test_cases_uses_ready_contract():
    """每个用例脚本的 goto 都必须走 `_goto`（就绪契约），而不是裸 `page.goto`。"""
    mods = _case_modules()
    assert mods, _NO_MODULES
    texts = {p: artifacts.read_artifact(p, role=f"生成物 {_rel(p)}") for p in mods}
    no_goto = sorted(_rel(p) for p, t in texts.items() if "_goto(" not in t)
    assert not no_goto, f"这些用例脚本没走就绪契约 _goto（慢目标下会假红）：{no_goto}"
    bare = sorted(_rel(p) for p, t in texts.items() if "page.goto(" in t)
    assert not bare, f"这些用例脚本里出现裸 page.goto —— 绕过了就绪契约：{bare}"


def test_generated_conftest_has_contract_helpers():
    """生成物必须带齐辅助函数（浏览器池/复位/断言/数据注入），且转发层不许断。

    P20：辅助函数全在 `_harness.py`，`conftest.py` 只做转发 ⇒ 两件事都要判：
    ① `_harness.py` 里 `def` 齐不齐（少了就是产物与代码不同步）；② `conftest.py` 有没有
       真的从 `_harness` 转发（断了 ⇒ 夹具/辅助暴露不出去，用例跑到那一步才炸）。
    """
    gen = _gen_dir()
    hf = artifacts.read_artifact(gen / "_harness.py", role="生成物 scripts/generated/_harness.py")
    cf = artifacts.read_artifact(gen / "conftest.py", role="生成物 scripts/generated/conftest.py")
    missing = [f"def {name}" for name in REQUIRED_CONFTEST if f"def {name}" not in hf]
    assert not missing, f"_harness.py 缺这些接线：{missing}"
    assert "from _harness import" in cf, ("conftest.py 没转发 _harness 的接线"
                                          "（应为 `from _harness import *` + 显式列出夹具名）"
                                          "⇒ 用例 import 不到，跑到那一步就 NameError")


def test_case_ids_and_datasets_are_one_to_one():
    """cases/*.json 的 case_id 与 scripts/datasets/*.json 必须一一对应（缺 = 没生成；多 = 陈旧残留）。

    2026-09-21（V7.8 数据参数化）扩展：`<cid>.sets.json`（多组数据的**伴生件**，可选）不算基础数据集，
    但**必须**有对应用例 —— 否则就是场景改了 / 用例删了之后留下的陈旧组数据，
    用例会继续拿上一版数据跑（「改了没生效」的静默坑，比报错更难查）。

    P20：cases/ 分目录了（cases/<场景>/<cid>.json + cases/manual/<cid>.json）⇒ 用 rglob 收全；
    datasets/ 口径未变。
    """
    case_ids = {json.loads(f.read_text(encoding="utf-8"))["case_id"] for f in CASES.rglob("*.json")}
    all_files = list((SCRIPTS / "datasets").glob("*.json"))
    sets_files = [f for f in all_files if f.name.endswith(".sets.json")]
    datasets = {f.stem for f in all_files if not f.name.endswith(".sets.json")}
    set_ids = {f.name[: -len(".sets.json")] for f in sets_files}
    assert case_ids - datasets == set(), f"这些用例没有数据集（重新 generate）：{sorted(case_ids - datasets)}"
    assert datasets - case_ids == set(), f"这些数据集是陈旧残留（用例已不存在）：{sorted(datasets - case_ids)}"
    assert set_ids - case_ids == set(), \
        f"这些数据组文件是陈旧残留（对应用例已不存在 ⇒ generate 该清掉它们）：{sorted(set_ids - case_ids)}"


def test_generated_artifacts_reference_only_existing_datasets():
    """★缺口判据（2026-09-22 实测补）：生成物**嵌进去的 case_id**，其数据集必须真实存在。

    为什么不能只查 `cases/`：上面那条「cases ⇄ datasets 一一对应」查的是**清单**。
    这次翻车的是「两边清单都干净，生成物里却留着上一个窗口的 case_id」——
    录制/负向验证期间会出现**临时用例**（id 带时间戳 / `neg_tmp_`），那个窗口里跑过的 generate
    会把临时 case_id 写进产物；临时用例随后被清掉 ⇒ 产物**死引用**
    ⇒ 谁跑那个产物谁红，而且 pytest 报的是 FileNotFoundError + 退出码 2
    （= 执行环境问题）⇒ 极易被当成"环境/偶发"绕过（实测我误判成 flaky 绕了一圈）。

    ⚠️ 不能靠静态扫 `datasets/xxx.json` 字面量：辅助层是 `datasets / f"{case_id}.json"` **运行期拼**的
    （第一版判据就是这么写错的，注入死引用都抓不住 —— 负向证明当场拆穿了它）。
    P20：扫描面从「那一个 test_cases.py + conftest.py」扩到「generated/ 下全部模块 + _harness.py」
    （一个用例一个文件之后，死引用可能落在任何一个模块里）。
    """
    import re as _re
    gen = _gen_dir()
    mods = _case_modules()
    assert mods, _NO_MODULES
    srcs = {p: artifacts.read_artifact(p, role=f"生成物 {_rel(p)}")
            for p in [gen / "_harness.py", gen / "conftest.py", *mods]}
    used: set[str] = set()
    for text in srcs.values():
        for m in _re.finditer(r"^def test_([A-Za-z0-9_]+)\(", text, _re.M):
            used.add(m.group(1))
    for text in srcs.values():
        for m in _re.finditer(r"_ds_params\(\s*[\"\']([A-Za-z0-9_]+)[\"\']", text):
            used.add(m.group(1))
    dead = sorted(c for c in used if not (SCRIPTS / "datasets" / f"{c}.json").exists())
    assert not dead, (f"生成物引用了不存在的数据集 ⇒ 产物是坏的（重跑 `python -m framework.cli generate`）：{dead}")


def test_no_unexpected_files_in_scripts():
    """scripts/ 只应有 generate 的产物 —— 别把临时文件/日志留在里面一起发出去。

    P20 允许名单：`generated/`（用例脚本 + conftest + _harness + index.json）与 `datasets/`。
    旧的 test_cases.py / conftest.py 已随 P20 删除 ⇒ **不再允许**（它们再出现就是陈旧残留，必须红）。
    """
    allowed = {"generated", "datasets"}
    actual = {p.name for p in SCRIPTS.iterdir() if p.name != "__pycache__"}
    assert actual <= allowed, f"scripts/ 里有非产物文件：{sorted(actual - allowed)}"


def test_test_cases_imports_every_conftest_helper():
    """生成物用例脚本用到的共享辅助**必须**在它自己的 import 名单里。

    2026-09-17 实测踩到：跨 tab 用的 `_Tabs` 已经被渲染进用例，却忘了加进
    `from conftest import (...)` ⇒ verify 跑第一条跨 tab 用例就
    `NameError: name '_Tabs' is not defined`（生成期无声，**运行期才炸**）。

    判据（结构可查、不靠人记）：辅助层（P20 起 = `_harness.py`）顶层定义的 `_` 前缀名字
    ∩ 每个用例模块里真实 load 的 Name ⊆ 该模块的 import 名单。
    这类「模板渲染了、import 没跟上」的缺口以后都拦在这里 —— 现在**逐模块**判（一个用例一个文件）。
    """
    import ast
    gen = _gen_dir()
    hf = artifacts.read_artifact(gen / "_harness.py", role="生成物 scripts/generated/_harness.py")
    cf_tree = ast.parse(hf, filename=str(gen / "_harness.py"))

    defined = {n.name for n in cf_tree.body
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
    defined |= {t.id for n in cf_tree.body if isinstance(n, ast.Assign)
                for t in n.targets if isinstance(t, ast.Name)}
    defined = {n for n in defined if n.startswith("_")}

    mods = _case_modules()
    assert mods, _NO_MODULES
    missing_all: dict[str, list[str]] = {}
    for p in mods:
        tc_tree = ast.parse(artifacts.read_artifact(p, role=f"生成物 {_rel(p)}"), filename=str(p))
        imported: set[str] = set()
        for node in ast.walk(tc_tree):
            if isinstance(node, ast.ImportFrom) and node.module == "_harness":
                imported |= {a.name for a in node.names}
            elif isinstance(node, ast.Import):
                imported |= {a.name for a in node.names}
        used = {n.id for n in ast.walk(tc_tree)
                if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
        if (missing := sorted((used & defined) - imported)):
            missing_all[_rel(p)] = missing

    assert not missing_all, (
        "这些用例脚本用了辅助层里的名字却没 import（跑到那一步就 NameError）\n"
        + "\n".join(f"   {f}: {names}" for f, names in sorted(missing_all.items()))
        + "\n⇒ 把这些名字加进 generator 的 `from _harness import (...)` 模板")


def test_generated_artifacts_are_syntactically_valid():
    """生成产物必须能 compile —— 语法/缩进错了要在这里就炸，不能等跑用例才发现。

    2026-09-21 实测踩到（V7.8 L1 开发中）：改 `generator.py` 里**模板字符串内部**的代码时，
    patch 的模糊匹配把模板缝合出「for 头被换成赋值 + 缩进错乱 + 引用未定义变量」的坏版本；
    而生成阶段只写文本、**不校验语法** ⇒ 一路写盘，直到 pytest 收集才 SyntaxError。
    更坏的是：磁盘产物还是旧的（能跑），所以「跑了没报错」不等于「模板是好的」。

    ⇒ 两类哨兵：① 模板**渲染结果**（不依赖磁盘、改完模板立刻能炸）——
       P20 后 `_render_conftest()` 一分为二：`_render_harness()`（辅助）+ `_render_generated_conftest()`
       （转发层），两个都判；② 磁盘产物本身（共享层 + 每一条用例模块）。
    """
    import ast
    from framework.tools.generate import generator as G
    ast.parse(G._render_harness(), filename="<渲染出的 _harness>")
    ast.parse(G._render_generated_conftest(), filename="<渲染出的 conftest>")
    gen = _gen_dir()
    for p in (gen / "conftest.py", gen / "_harness.py"):
        ast.parse(artifacts.read_artifact(p, role=f"生成物 {_rel(p)}"), filename=str(p))
    mods = _case_modules()
    assert mods, _NO_MODULES
    for p in mods:
        ast.parse(artifacts.read_artifact(p, role=f"生成物 {_rel(p)}"), filename=str(p))


def test_no_transient_temp_artifacts_left_behind():
    """★临时产物绝不许留在仓库里（2026-09-24 被它带偏过一次）。

    `verify_data_expand` 会造 `cases/zz_verify_data_expand_tmp.json` + 对应 dataset 来验证
    "多套数据真展开"，跑完必须清干净。一旦残留：
      · 一类 test_generated_test_cases_has_no_unmapped_stubs 会因它报"有未映射存根"
      · test_case_ids_and_datasets_are_one_to_one 会因它报"用例与数据集对不上"
    ⇒ 两条失败都**指不到真因**（真因是"上次 data_expand 没清干净" ✗）
    ⇒ 这里单列一条，把信号说清楚：看到它就知道去清临时产物，而不是去查产物生成器。

    P20：cases/ 分目录了 ⇒ 用 rglob（临时产物可能落在 cases/<场景>/ 下）。
    """
    import glob
    leftovers = sorted(glob.glob(str(REPO / "cases" / "**" / "zz_*.json"), recursive=True)) + \
                sorted(glob.glob(str(REPO / "scripts" / "datasets" / "zz_*.json")))
    assert not leftovers, (
        "✗ 仓库里有临时产物残留 ⇒ 多半是上次 verify_data_expand 中途失败没清干净。\n"
        "   清掉它们再重跑（rm cases/**/zz_*.json scripts/datasets/zz_*.json），不要把它们当正常产物。\n"
        + "\n".join("   " + p for p in leftovers))
