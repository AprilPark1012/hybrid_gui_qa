# -*- coding: utf-8 -*-
"""L35 · 登录链路 AI 化 —— **契约判据**（取代 V8.5.1 的 `by` 选择器口径）。

## 改造前后（判据守的就是这条线）

    BEFORE（三套 schema）:
        scenarios/*.yml  login.steps[] = {op, by, value}     ← 人写选择器
        ElementMap.steps[]              = {op, element, value} ← AI 写语义名
        生成物 harness                   = `_login_do(page, op, by)` ← 第三套执行器
    AFTER（一套）:
        scenarios/*.yml  login = {url, scenario: <自然语言>, wait}
        → 同一个规划器在登录页产出普通 TestStep（op/desc/element/value）
        → 同一套定位栈（`resolve_locator`）执行
        → 步骤**固化进用例**（`case["login"]`），执行期零 AI

## 判据清单（一类，秒级、不需 demo）

  J1  声明了自然语言登录 -> 生成期渲染出 `_login_flow(...)`，且步骤是**普通步骤**（无 by）
  J2  负向：没声明 login -> 零前导；**声明了但用例里没有登录步骤 -> 大声报错**（提示重跑 explore）
  J3  负向：login 段三种非法形态（写 steps / 缺 scenario / wait 无可观测条件）-> 加载期即报错
  J4  出厂闸门：运行期要读的生成物不许被 .gitignore 忽略（不进包却运行必需的旧事故）
  J5  机制移除守门：`by` 那套（`_BY_KEY` / `locator_of` / `perform_login` / `_login_do`）不许回来
  J6  卡在登录页时报错要直说（不许把方向带向"异步取数/弹层未渲染"）
  J7  执行期**零 AI**：`_login_flow` 走 `resolve_locator`，不 import 任何 LLM 入口
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
FRAMEWORK = REPO / "framework"
SCENARIO = REPO / "scenarios" / "orders" / "orders_invoice_full_lifecycle.yml"

sys.path.insert(0, str(REPO))


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def _gen():
    from framework.features.f02_semantic import generator_generate as G
    return G


# ---- 一份"已固化登录步骤"的用例（执行期的真实形状）----
CASE_WITH_LOGIN = {
    "case_id": "l35_probe",
    "login": {
        "login_url": "http://h/login.html",
        "wait": {"url_not": "login.html"},
        "steps": [
            {"op": "goto", "desc": "打开登录页", "value": "http://h/login.html"},
            {"op": "fill", "desc": "填账号",
             "element": {"semantic_name": "账号", "role": "textbox", "name": "账号"},
             "value": "u1"},
            {"op": "click", "desc": "点登录",
             "element": {"semantic_name": "登_录", "role": "button", "name": "登录"}},
        ],
    },
}


# ============================ J1：渲染 ============================

def test_j1_login_steps_rendered_as_one_login_flow_call():
    """声明了登录 -> 渲染成**一次** `_login_flow(steps, wait, url)`，且步骤是普通 op/element。"""
    G = _gen()
    lines = G._login_lines_for(CASE_WITH_LOGIN, "http://h")
    joined = "\n".join(lines)
    assert "_login_flow(page," in joined, (
        "生成期没有渲染 `_login_flow(...)` —— 登录不在用例里，跑挂了看不出卡在登录")
    assert "'op': 'fill'" in joined or '"op": "fill"' in joined, (
        "渲染出来的登录步骤不是**普通步骤**（op/element/value）—— 那又变成第二套形状了")
    assert "by" not in joined.replace("bypass", ""), (
        "登录步骤里还带 `by`（V8.5.1 的选择器口径）—— L35 已删除，必须走语义定位")
    assert "login.html" in joined, "登录地址没渲染进去"


# ============================ J2：有无 / 缺产物 ============================

def test_j2_no_login_declaration_means_no_leading_steps():
    """负向：没有登录声明的用例，生成结果与改造前**完全一致**（零前导步骤）。"""
    G = _gen()
    assert G._login_lines_for({}, "http://localhost:8000") == [], \
        "无场景信息的用例被插入了登录步骤 -> 会改掉所有用例（破坏向后兼容）"
    assert G._login_lines_for(
        {"scenario_id": "__not_exist_scenario__"}, "http://localhost:8000") == [], \
        "拿不到场景时也必须是零步骤（不许猜、不许降级）"


def test_j2b_declared_login_but_case_has_none_fails_loudly():
    """[!] 关键：场景声明了 login、但用例里没有登录步骤 -> **硬红**（提示重跑 explore）。

    为什么这条必须有：L35 起登录步骤是 explore 的产物。若某天有人只改了场景、没重跑
    explore，generate 若静默跳过登录，整条用例会跑在登录页上 —— 报错却指向"元素未找到"。
    """
    G = _gen()
    with pytest.raises(RuntimeError) as ei:
        G._login_lines_for({"case_id": "no_login_field",
                            "scenario_id": "orders_invoice_full_lifecycle"},
                           "http://localhost:8000")
    msg = str(ei.value)
    assert "登录" in msg and "explore" in msg, f"报错没说清怎么修：{msg}"


# ============================ J3：声明非法要当场报 ============================

def _scenario_with_login_block(login_block: str, tmp_path: Path) -> Path:
    """把真实场景的 login 段换成给定块，写到 tmp 再加载（保持场景其它部分真实）。"""
    text = _read(SCENARIO)
    start = text.index("\nlogin:")
    end = text.index("\nassert_guard:", start)
    out = text[:start] + "\n" + login_block + "\n" + text[end:]
    p = tmp_path / "probe.yml"
    p.write_text(out, encoding="utf-8")
    return p


@pytest.mark.parametrize("block, fragment", [
    # ① 老口径：还写 steps/by
    ("login:\n  url: /login.html\n  steps:\n    - {op: fill, by: {id: u}, value: a}\n"
     "  wait: {url_not: login.html}", "steps"),
    # ② 缺自然语言
    ("login:\n  url: /login.html\n  wait: {url_not: login.html}", "scenario"),
    # ③ wait 没有可观测条件
    ("login:\n  url: /login.html\n  scenario: 填账号密码然后点登录\n  wait: {}", "可观测"),
])
def test_j3_malformed_login_declaration_fails_at_load(block, fragment, tmp_path):
    """三种非法形态 -> **加载期**报错（不许留到运行期才炸，更不许静默跳过）。"""
    from framework.features.f02_semantic.scenario_generate import ScenarioError, load_scenario_file

    p = _scenario_with_login_block(block, tmp_path)
    with pytest.raises(ScenarioError) as ei:
        load_scenario_file(p)
    assert fragment in str(ei.value), f"报错没点出问题（期望含 {fragment!r}）：{ei.value}"


# ============================ J4：出厂闸门（沿用）============================

def test_j4_runtime_required_files_are_subset_of_package_manifest():
    """运行期要读的生成物必须都在打包清单里（防"不入包却运行必需"复发）。"""
    from framework.shared.text_io import run_capture
    r = run_capture(["git", "ls-files", "--others", "--ignored", "--exclude-standard",
                     "scripts/"], cwd=REPO)
    ignored = [x for x in (getattr(r, "stdout", "") or "").split("\n") if x.strip()]
    gen = _read(FRAMEWORK / "features" / "f02_semantic" / "generator_generate.py")
    written = set(re.findall(r'["\'](_[a-z_]+\.json)["\']', gen))
    clash = [f for f in written if any(x.endswith(f) for x in ignored)]
    assert not clash, ("生成期写出、运行期要读的文件被 .gitignore 忽略 -> 不进包 -> "
                       "收包方静默失效：\n" + "\n".join(clash))


# ============================ J5：机制移除守门 ============================

def test_j5_no_selector_based_login_schema_anywhere():
    """`by` 那套（第二套 schema + 第三套执行器）不许回来。"""
    offenders: list[str] = []
    # ① 框架源码：登录模块不许再有 by 解析 / perform_login
    login_py = _read(FRAMEWORK / "shared" / "login.py")
    for tok in ("_BY_KEY", "def locator_of(", "def perform_login("):
        if tok in login_py:
            offenders.append(f"framework/shared/login.py 含 {tok}")
    # ② 生成物 harness：不许再有 _login_do/_login_wait/_LOGIN_BY
    harness = _read(REPO / "scripts" / "generated" / "_harness.py")
    for tok in ("_LOGIN_BY", "def _login_do(", "def _login_wait(", "def _login_locator("):
        if tok in harness:
            offenders.append(f"scripts/generated/_harness.py 含 {tok}")
    # ③ 场景文件：login 段不许写 steps/by
    sc_text = _read(SCENARIO)
    block = sc_text[sc_text.index("\nlogin:"):sc_text.index("\nassert_guard:")]
    # [!] 只看**结构**（YAML 键），注释行不算：本段注释里就会出现 "by: {id: ...}"
    #   这种「反例说明」——文本匹配会把说明文字判成违规（判据自己写错，比没有更糟）。
    for line in block.splitlines():
        code = line.split("#", 1)[0]
        if re.match(r"^\s+steps:\s*$", code) or re.match(r"^\s+by:\s*", code):
            offenders.append(f"场景 login 段含 {code.strip()[:40]}")
    assert not offenders, (
        "登录的第二套 schema / 执行器又出现了（L35 明确要求「不要搞 2 套」）：\n"
        + "\n".join(f"  - {o}" for o in offenders)
    )


# ============================ J6：报错文案（沿用）============================

def test_j6_error_message_names_login_page_when_stuck():
    """跑到登录页上时，报错必须直指登录（不许把方向带向"异步取数/弹层未渲染"）。"""
    hits = []
    for p in (FRAMEWORK / "features").rglob("*.py"):
        if "__pycache__" in str(p):
            continue
        s = _read(p)
        if "login_failure_hint" in s and "def login_failure_hint" not in s:
            hits.append(p.relative_to(REPO).as_posix())
    assert hits, ("没有任何地方使用 `login_failure_hint()` —— "
                  "「卡在登录页」的报错文案又会被『元素未找到』盖掉")


# ============================ J7：执行期零 AI ============================

def test_j7_runtime_login_executor_uses_same_locator_stack_and_no_ai():
    """执行期登录：走 `resolve_locator`（同一套定位栈），且**不** import 任何 LLM 入口。"""
    harness = _read(REPO / "scripts" / "generated" / "_harness.py")
    i = harness.find("def _login_flow(")
    assert i > 0, "生成物 harness 里没有 `_login_flow`（登录执行入口）"
    body = harness[i:i + 4000]
    assert "resolve_locator" in body, (
        "登录执行没走 `resolve_locator` —— 那就是又开了一套定位（L35 的核心要求是同一套）")
    for tok in ("ai_explore", "llm_from_env", "_ai_explore_async", "ChatDeepSeek"):
        assert tok not in body, f"执行期登录里出现了 {tok} —— 执行期必须零 AI（离线要能跑）"
