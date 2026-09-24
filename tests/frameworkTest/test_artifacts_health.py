"""生成物健康度闸门（V7.5.1，配套 2026-09-15 交付事故）。

事故链条：现场 probe 不可用 → `generate` 只警告一句就落盘 → 产出一份
「16 个用例、每步都是 `pytest.fail(元素未映射)` 存根」的 `scripts/test_cases.py` →
**没人检查包内产物** → 提交 + 打包 + 交付 → 数天后在慢目标闸门炸成 50 条失败。

⇒ 生成期有质量闸（见 tests/frameworkTest/test_generate_quality_gate.py），**生成之后**还要有一道
「产物本身健不健康」的闸门：本文件就是它。秒级、不需要 demo、不需要浏览器，能进 CI。

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
REQUIRED_CONFTEST = ("_act", "_goto", "_data", "_log", "_reset_target_data",
                     "_assert_text", "_assert_url", "_assert_value", "_assert_count")


def test_generated_test_cases_has_no_unmapped_stubs():
    """`scripts/test_cases.py` 绝不允许含「元素未映射」存根 —— 那就是交付事故本体。"""
    tc = artifacts.read_artifact(SCRIPTS / "test_cases.py", role="生成物 scripts/test_cases.py")
    n = tc.count("元素未映射")
    assert n == 0, (f"生成物里有 {n} 处「元素未映射」存根 ⇒ 这份产物是探测失败时落盘的垃圾，"
                    f"别提交/打包/交付；重新在目标可用的前提下跑 `python -m framework.cli generate`")


def test_generated_test_cases_uses_ready_contract():
    """每个 goto 都必须走 `_goto`（就绪契约），而不是裸 `page.goto`。"""
    tc = artifacts.read_artifact(SCRIPTS / "test_cases.py", role="生成物 scripts/test_cases.py")
    assert "_goto(" in tc, "生成物没走就绪契约 _goto（慢目标下会假红）"
    assert "page.goto(" not in tc, "生成物里出现裸 page.goto —— 绕过了就绪契约"


def test_generated_conftest_has_contract_helpers():
    """`scripts/conftest.py` 必须带齐辅助函数（浏览器池/复位/断言/数据注入）。"""
    cf = artifacts.read_artifact(SCRIPTS / "conftest.py", role="生成物 scripts/conftest.py")
    missing = [f"def {name}" for name in REQUIRED_CONFTEST if f"def {name}" not in cf]
    assert not missing, f"conftest 缺这些接线：{missing}"


def test_case_ids_and_datasets_are_one_to_one():
    """cases/*.json 的 case_id 与 scripts/datasets/*.json 必须一一对应（缺 = 没生成；多 = 陈旧残留）。

    2026-09-21（V7.8 数据参数化）扩展：`<cid>.sets.json`（多组数据的**伴生件**，可选）不算基础数据集，
    但**必须**有对应用例 —— 否则就是场景改了 / 用例删了之后留下的陈旧组数据，
    用例会继续拿上一版数据跑（「改了没生效」的静默坑，比报错更难查）。
    """
    case_ids = {json.loads(f.read_text(encoding="utf-8"))["case_id"] for f in CASES.glob("*.json")}
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
    ⇒ 谁跑 `scripts/test_cases.py` 谁红，而且 pytest 报的是 FileNotFoundError + 退出码 2
    （= 执行环境问题）⇒ 极易被当成"环境/偶发"绕过（实测我误判成 flaky 绕了一圈）。

    ⚠️ 不能靠静态扫 `datasets/xxx.json` 字面量：conftest 是 `datasets / f"{case_id}.json"` **运行期拼**的
    （第一版判据就是这么写错的，注入死引用都抓不住 —— 负向证明当场拆穿了它）。
    """
    import re as _re
    tc = (SCRIPTS / "test_cases.py").read_text(encoding="utf-8")
    cf = (SCRIPTS / "conftest.py").read_text(encoding="utf-8")
    used: set[str] = set()
    for m in _re.finditer(r"^def test_([A-Za-z0-9_]+)\(", tc, _re.M):
        used.add(m.group(1))
    for m in _re.finditer(r"_ds_params\(\s*[\"\']([A-Za-z0-9_]+)[\"\']", cf + tc):
        used.add(m.group(1))
    dead = sorted(c for c in used if not (SCRIPTS / "datasets" / f"{c}.json").exists())
    assert not dead, (f"生成物引用了不存在的数据集 ⇒ 产物是坏的（重跑 `python -m framework.cli generate`）：{dead}")


def test_no_unexpected_files_in_scripts():
    """scripts/ 只应有 generate 的产物 —— 别把临时文件/日志留在里面一起发出去。"""
    allowed = {"test_cases.py", "conftest.py", "datasets"}
    actual = {p.name for p in SCRIPTS.iterdir() if p.name != "__pycache__"}
    assert actual <= allowed, f"scripts/ 里有非产物文件：{sorted(actual - allowed)}"


def test_test_cases_imports_every_conftest_helper():
    """`test_cases.py` 用到的 conftest 辅助**必须**在它的 import 名单里。

    2026-09-17 实测踩到：跨 tab 用的 `_Tabs` 已经被渲染进用例，却忘了加进
    `from conftest import (...)` ⇒ verify 跑第一条跨 tab 用例就
    `NameError: name '_Tabs' is not defined`（生成期无声，**运行期才炸**）。

    判据（结构可查、不靠人记）：conftest 顶层定义的 `_` 前缀名字 ∩ test_cases 里真实 load 的 Name
    ⊆ test_cases 的 import 名单。这类「模板渲染了、import 没跟上」的缺口以后都拦在这里。
    """
    import ast
    cf_tree = ast.parse((SCRIPTS / "conftest.py").read_text(encoding="utf-8"))
    tc_tree = ast.parse((SCRIPTS / "test_cases.py").read_text(encoding="utf-8"))

    defined = {n.name for n in cf_tree.body
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
    defined |= {t.id for n in cf_tree.body if isinstance(n, ast.Assign)
                for t in n.targets if isinstance(t, ast.Name)}
    defined = {n for n in defined if n.startswith("_")}

    imported: set[str] = set()
    for node in ast.walk(tc_tree):
        if isinstance(node, ast.ImportFrom) and node.module == "conftest":
            imported |= {a.name for a in node.names}
        elif isinstance(node, ast.Import):
            imported |= {a.name for a in node.names}
    used = {n.id for n in ast.walk(tc_tree)
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}

    missing = sorted((used & defined) - imported)
    assert not missing, (f"test_cases.py 用了 conftest 里的 {missing} 却没 import（跑到那一步就 NameError）"
                         f"⇒ 把这些名字加进 generator 的 `from conftest import (...)` 模板")

def test_generated_artifacts_are_syntactically_valid():
    """生成产物必须能 compile —— 语法/缩进错了要在这里就炸，不能等跑用例才发现。

    2026-09-21 实测踩到（V7.8 L1 开发中）：改 `generator.py` 里**模板字符串内部**的代码时，
    patch 的模糊匹配把模板缝合出「for 头被换成赋值 + 缩进错乱 + 引用未定义变量」的坏版本；
    而生成阶段只写文本、**不校验语法** ⇒ 一路写盘，直到 pytest 收集才 SyntaxError。
    更坏的是：磁盘产物还是旧的（能跑），所以「跑了没报错」不等于「模板是好的」。

    ⇒ 两道哨兵：① 模板**渲染结果**（不依赖磁盘、改完模板立刻能炸）；② 磁盘产物本身。
    """
    import ast
    from framework.tools.generate import generator as G
    ast.parse(G._render_conftest(), filename="<渲染出的 conftest>")
    for name in ("conftest.py", "test_cases.py"):
        p = SCRIPTS / name
        ast.parse(p.read_text(encoding="utf-8"), filename=str(p))

def test_no_transient_temp_artifacts_left_behind():
    """★临时产物绝不许留在仓库里（2026-09-24 被它带偏过一次）。

    `verify_data_expand` 会造 `cases/zz_verify_data_expand_tmp.json` + 对应 dataset 来验证
    "多套数据真展开"，跑完必须清干净。一旦残留：
      · 一类 test_generated_test_cases_has_no_unmapped_stubs 会因它报"有未映射存根"
      · test_case_ids_and_datasets_are_one_to_one 会因它报"用例与数据集对不上"
    ⇒ 两条失败都**指不到真因**（真因是"上次 data_expand 没清干净" ✗）
    ⇒ 这里单列一条，把信号说清楚：看到它就知道去清临时产物，而不是去查产物生成器。
    """
    import glob
    leftovers = sorted(glob.glob(str(REPO / "cases" / "zz_*.json"))) + \
                sorted(glob.glob(str(REPO / "scripts" / "datasets" / "zz_*.json")))
    assert not leftovers, (
        "✗ 仓库里有临时产物残留 ⇒ 多半是上次 verify_data_expand 中途失败没清干净。\n"
        "   清掉它们再重跑（rm cases/zz_*.json scripts/datasets/zz_*.json），不要把它们当正常产物。\n"
        + "\n".join("   " + p for p in leftovers))
