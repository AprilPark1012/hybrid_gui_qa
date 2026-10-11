# -*- coding: utf-8 -*-
"""特性2 · 场景级探测前置 `probe_pre`（2026-10-10 · A 方案 S1）。

背景（实测链条）：探测期若没切到业务身份，详情页「编辑」是置灰(aria-disabled) ->
    `[explore] [!] [订单详情页] 前置动作「编辑」执行失败（TimeoutError ...）`
    -> 编辑态控件采不到 -> AI 拿不到行内字段语义名 -> 行必填填不了 -> 保存无效
    -> 提交被前端静默拒绝 -> 订单永远到不了「已关闭」（等待给多大都白等）。
所以必须有「**探测期一开始就要处的状态**」这一层声明；它与页面级 `pages[].pre`
是**两个层级、同一个执行引擎**（`_run_pre_actions`）—— 不是第二套机制。
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

REPO = Path(__file__).resolve().parents[2]
ORDERS = REPO / "scenarios" / "orders" / "orders_invoice_full_lifecycle.yml"


def _scenario_from_text(tmp_path: Path, extra: str):
    from framework.features.f02_semantic.scenario_generate import load_scenario_file
    f = tmp_path / "s.yml"
    f.write_text("id: t" + chr(10) + "title: t" + chr(10) + extra + chr(10)
                 + "scenario: |" + chr(10) + "  打开列表页看订单。" + chr(10), encoding="utf-8")
    return load_scenario_file(f)


def test_probe_pre_is_parsed(tmp_path):
    # P25 片 6（D10）：声明了 probe_pre 就必须同时声明 **probe_pre_host**（这批前置在哪一页执行，
    # 引用 pages[].name）—— 缺了在加载期就硬红。所以这条判据的用例也要带上它，
    # 否则测到的不是"解析"而是"新校验拦下了"（判据与实现的口径必须一起动）。
    sc = _scenario_from_text(tmp_path, "probe_pre:" + chr(10) + "  - 切换为订单管理员"
                             + chr(10) + "probe_pre_host: 列表页")
    assert sc.probe_pre == ["切换为订单管理员"], f"probe_pre 没解析出来：{sc.probe_pre!r}"
    assert sc.probe_pre_host == "列表页", (
        f"probe_pre_host 没解析出来：{sc.probe_pre_host!r}（D10 要求它随 probe_pre 一起声明）")


def test_probe_pre_absent_is_empty(tmp_path):
    sc = _scenario_from_text(tmp_path, "notes: 无前置")
    assert sc.probe_pre == [], "没声明时必须是空列表（缺省行为与改造前一致）"


def test_probe_pre_must_be_list(tmp_path):
    from framework.features.f02_semantic.scenario_generate import ScenarioError
    try:
        _scenario_from_text(tmp_path, "probe_pre: 切换为订单管理员")
    except ScenarioError:
        return
    raise AssertionError("probe_pre 不是列表时应当报错（否则会静默当字符串逐字符处理）")


def test_orders_scenario_declares_probe_pre():
    """守门：本条业务链要靠它才能采到编辑态控件 —— 谁把它删了必须立刻红。"""
    from framework.features.f02_semantic.scenario_generate import load_scenario_file
    sc = load_scenario_file(ORDERS)
    assert any("订单管理员" in str(x) for x in sc.probe_pre), (
        f"orders 场景没有声明切身份的探测前置：{sc.probe_pre!r}")


def test_probe_pre_is_threaded_to_ai_explore():
    """接线锁：字段必须一路透传到探测入口（少接一处 -> 静默失效，零报错）。"""
    from framework.features.f02_semantic.explorer_explore import ai_explore
    assert "probe_pre" in inspect.signature(ai_explore).parameters


def test_probe_pre_runs_before_scan_in_both_paths():
    """接线锁（源码契约）：场景级前置必须跑在**页面级前置**与 **scan** 之前。

    顺序错了 -> 扫到的是旧权限上下文（置灰态），编辑态控件照样采不到。
    """
    # [!] 片 3c（2026-10-12，B1 三合一）：**多页路径的这段顺序契约跟着骨架搬到了
    #   `probe/scan_pages.py`**（explorer 侧只剩单页）。判据跟着搬，**要求一字不变**：
    #   场景级前置必须在**页面级前置**与 **scan_page** 之前。
    src = (REPO / "framework" / "features" / "f03_locate" / "scan_pages_probe.py").read_text(encoding="utf-8")
    code = chr(10).join(l for l in src.splitlines() if not l.strip().startswith("#"))
    i_pp = code.index("_run_pre(pg, _pp_pending")
    i_page = code.index('_run_pre(pg, _field(spec, "pre"')
    i_scan = code.index("_sc = scan_page(pg")
    assert i_pp < i_page < i_scan, "多页路径顺序不对：场景级前置必须在页面级前置与 scan 之前"
    src = (REPO / "framework" / "features" / "f02_semantic" / "explorer_explore.py").read_text(encoding="utf-8")
    code = chr(10).join(l for l in src.splitlines() if not l.strip().startswith("#"))
    # 单页路径同款
    i_spp = code.index("_run_pre_actions(pg, probe_pre")
    i_sscan = code.index("_sc = scan_page(pg)", i_spp)
    assert i_spp < i_sscan, "单页路径：场景级前置没跑在 scan 之前"


# ============================================================================
# 2026-10-10 A 方案（项目定案）：**身份前置在执行期同样要跑** —— 探/执同一引擎
#
# 事故（干净环境 E2E）：场景声明 `probe_pre: [超, 切换为订单管理员]`，探测期照跑没事；
#   执行期没人跑 -> AI 生成的用例只写了第 2 步（漏掉点开头像菜单的「超」）->
#   `Locator.click: Element is not visible`（菜单项在 DOM 里、未展开时不可见）-> 整条用例白跑。
# 病根：同一个「怎么到达这个身份」的知识**只活在探测侧** —— 一个能力两个入口（本项目明令禁止）。
# ============================================================================

def test_engine_is_the_single_source_for_pre_actions():
    """唯一引擎：探测期入口只许**委托**（`framework/shared/pre_actions_run.py`），不许再留实现。"""
    exp = (REPO / "framework" / "features" / "f02_semantic" / "explorer_explore.py").read_text(encoding="utf-8")
    i = exp.index("def _run_pre_actions(")
    wrapper = exp[i:i + 2600]
    assert "from framework.shared.pre_actions_run import run_pre_actions" in wrapper, \
        "探测期入口没委托给唯一引擎"
    assert "全不可见 -> 改用 force 点一次" not in exp, \
        "探测期还留着第二份实现（两套口径会漂）"
    eng = (REPO / "framework" / "shared" / "pre_actions_run.py").read_text(encoding="utf-8")
    assert "def run_pre_actions(" in eng and "require_all_resolvable" in eng, \
        "引擎缺整组语义（只跑半个序列会假成功）"


def test_execution_harness_runs_declared_identity_pre():
    """接线锁：产物侧 harness 读 `_pre.json`，并在**首次导航之后**跑一次身份前置。"""
    gen = (REPO / "framework" / "features" / "f02_semantic" / "generator_generate.py").read_text(encoding="utf-8")
    assert '"_pre.json"' in gen, "harness 没读身份前置表（声明了也白声明）"
    assert "def _maybe_scene_pre(page):" in gen, "harness 没有执行期身份前置的实现"
    assert "    page.goto(target)\n    _wait_ready(page, target)\n    _maybe_scene_pre(page)" in gen, \
        "身份前置没接在「首次导航 + 等就绪」之后"
    assert 'run_pre_actions(page, steps, "场景身份前置"' in gen, \
        "执行期没调**同一引擎**（自己另写一套 = 又分岔）"
    # [!] 执行期必须给预检**有界等待**：首次导航后立刻查 count 必然 0（菜单是异步注入的），
    #   不给等待就一步都不跑（2026-10-10 两个用例都因此当场抛）。
    assert "resolvable_wait_ms=15000" in gen, "执行期预检没有等待 -> 首次导航后必然判定「解析不到」"
    # 收尾闸：整条用例都没跑全身份前置时必须红（抛点从 `_maybe_scene_pre` 挪到 fixture 收尾 ——
    # 因为产物脚本第一次导航可能是登录页，在那里抛会把「还没到业务页」误判成「声明失效」）
    assert "身份前置整条用例都没能执行" in gen, "缺收尾闸：身份前置整条没跑全也不会红"
    # 主路径：**用例体之前**先导航到声明的那一页把身份建立好（不依赖用例自己的路线 ——
    # AI 的「等价直达 order_new.html」路线可能全程不过带导航的页，实测那页连头像节点都没有）
    assert "def _pre_steps_of(" in gen, "没有取「前置步骤 + host」的唯一入口"
    assert "身份前置已建立" in gen and "pg.goto(_host)" in gen, \
        "fixture 里没有『用例体之前先建立身份』这条主路径"
    assert '{"steps": _pp, "url": _host}' in gen, "_pre.json 没写 host（前置该在哪页跑）"
    # 生成器侧：按 source_scenario 回读声明并写表
    assert "def _scenario_probe_pre_of(" in gen and '_pre_path.write_text' in gen, \
        "生成器没把场景声明的 probe_pre 写进产物"


def test_generator_reads_declared_probe_pre_from_scenario():
    """行为判据（真值）：生成器回读函数必须取出场景真声明的序列。"""
    from framework.features.f02_semantic.generator_generate import _scenario_probe_pre_of
    got = _scenario_probe_pre_of("scenarios/orders/orders_invoice_full_lifecycle.yml")
    assert got == ["超", "切换为订单管理员"], f"回读到的 probe_pre 不对：{got!r}"


def test_declared_pre_steps_are_dropped_from_ai_output():
    """行为判据：AI 产出里**重复声明**的身份步骤被移除；不声明时一步不动（负向自证）。"""
    from framework.features.f02_semantic.explorer_explore import _drop_declared_pre_steps
    from framework.features.f03_locate.element_map import ElementRef, TestStep
    steps = [
        TestStep(1, "goto"),
        TestStep(2, "click", element=ElementRef(semantic_name="切换为订单管理员@合同列表页"),
                 description="切角色（AI 常只写这一步、漏了点开头像菜单）"),
        TestStep(3, "click", element=ElementRef(semantic_name="保存@新建订单页"), description="保存"),
    ]
    # 正向：按**基名**匹配（AI 写的是带页名后缀的那个），重复步骤被移除
    assert [s.order for s in _drop_declared_pre_steps(steps, ["超", "切换为订单管理员"])] == [1, 3]
    # 负向 1：场景没声明 -> 原样返回（行为与改造前一致，零影响）
    assert [s.order for s in _drop_declared_pre_steps(steps, [])] == [1, 2, 3]
    # 负向 2：声明的是别的名字 -> 不许误伤真步骤
    assert [s.order for s in _drop_declared_pre_steps(steps, ["超"])] == [1, 2, 3]


def test_prompt_tells_ai_the_declared_identity_pre():
    """行为判据：提示词要告诉 AI「身份前置已自动做，不要重复写」；未声明则**不许出现**该块。"""
    import framework.features.f02_semantic.explorer_explore as ex
    try:
        ex._CURRENT_PROBE_PRE = ["超", "切换为订单管理员"]
        p = ex._build_planner_prompt("场景原文", [], "http://localhost:8000/orders.html")
        assert "身份前置" in p, "没把已声明的身份前置告诉 AI -> 它还会重写一遍"
        assert "超" in p and "切换为订单管理员" in p, "提示词里没列出声明的序列"
        ex._CURRENT_PROBE_PRE = []
        p2 = ex._build_planner_prompt("场景原文", [], "http://localhost:8000/orders.html")
        assert "身份前置" not in p2, "没声明却在提示词里编了一段（会误导 AI）"
    finally:
        ex._CURRENT_PROBE_PRE = []


def test_declared_pre_host_is_the_first_business_page():
    """行为判据：前置的 host = 场景 `pages` 里第一个**业务页**（不是登录页）。

    为什么必须判（2026-10-10 实测）：第一版按 dict 取 `p.get("url")` —— 而 `pages` 是
    `ScenarioPage` **dataclass**，静默拿到空串 => `url` 全空 => 前置主路径整体不生效
    （用例照红，但红得莫名其妙）。这条判据直接对**真场景**取真值，能当场抓住这类静默空值。
    """
    from framework.features.f02_semantic.generator_generate import _scenario_pre_host_of

    host = _scenario_pre_host_of("scenarios/orders/orders_invoice_full_lifecycle.yml")
    assert host == "http://localhost:8000/", f"前置 host 取错了：{host!r}（登录页？还是空？）"
    assert "login" not in host.lower(), "host 落在登录页上（那页没有业务导航，前置解析不到）"
    assert _scenario_pre_host_of("scenarios/does_not_exist.yml") == "", "文件不存在应返回空串（不许抛）"


def test_scene_pre_done_is_initialized_before_use():
    """源码契约：`_pp_done` 必须**在 if 之前**初始化。

    2026-10-10 抓到的真 bug（同类第二个）：`_pp_done` 只在 `if _pp_pending:` 内赋值，
    下一行却无条件读 —— 没声明 `probe_pre` 的**任何跨页场景**在第一个页面就
    `UnboundLocalError`（被兜住 = 探测静默退化）；有声明时则每页复用上一页的陈旧值，
    把陈旧名字当成"本页已点击"（假证据，实测让「切换为订单管理员」在两个页面上都成了合成条目）。
    """
    # [!] 片 3c（2026-10-12）：`_pp_done` 的初始化契约跟着骨架搬到了 `probe/scan_pages.py`。
    src = (REPO / "framework" / "features" / "f03_locate" / "scan_pages_probe.py").read_text(encoding="utf-8")
    i_init = src.index("_pp_done: list = []")
    i_if = src.index("if _pp_pending:", i_init)
    i_use = src.index("list(_pp_done)", i_init)
    assert i_init < i_if < i_use, \
        "`_pp_done` 必须在 `if _pp_pending:` **之前**初始化（否则没声明 probe_pre 时必炸）"


def test_generate_live_probe_applies_declared_probe_pre():
    """`generate` 的两条**现场探测**路径都必须应用场景声明的 `probe_pre`。

    为什么（2026-10-11 实测复现）：全新环境（没有 element_map 落盘）跑 `cli all --workers 2`
    -> 现场探测**没切角色** -> 详情页「编辑/新增行」是置灰态 -> 常规点击被拒、只 force 点一下
    （只弹提示、不变状态）-> **编辑态控件根本没渲染** -> 7 个语义名探不到 ->
    `映射质量闸拦下：7 个语义名映射不上 -> 拒绝产出任何产物`。
    explore 侧 2026-10-10 就修了这条链条（见模块 docstring），**generate 的现场探测漏了** ——
    同一个能力有两条实现路径却没逐条对齐（本项目铁律 13）。
    """
    src = (REPO / "framework" / "features" / "f02_semantic" / "generator_generate.py").read_text(encoding="utf-8")
    # [!] 片 3c（2026-10-12）：**声明页现场探测**的 probe_pre 应用跟着骨架搬到了 scan_pages
    #   （generator 只把 `pre` 传进去）。所以"清单页那两条断言"改查 scan_pages；
    #   "回到 generator 侧"的三条（回读场景 probe_pre / 形参 / 传参）**不变**。
    sp = (REPO / "framework" / "features" / "f03_locate" / "scan_pages_probe.py").read_text(encoding="utf-8")
    # [!] 片 3c 后的实际形态：scan_pages 里经 `_run_pre(...)` 转发（`_run_pre` 只做委托，
    #   真正引擎仍是 `run.pre_actions.run_pre_actions`）。断言"声明页前置被应用 + 转发到唯一引擎"。
    assert '_run_pre(pg, _field(spec, "pre"' in sp, \
        "声明页现场探测没应用 probe_pre（骨架侧）-> 探测到的是只读态 -> 编辑态控件采集不到"
    assert "from framework.shared.pre_actions_run import run_pre_actions" in sp, \
        "scan_pages 里的前置没转发到唯一引擎 run.pre_actions（会漂成第二套点击逻辑）"
    assert "_scenario_probe_pre_of(" in src, "generate 没有回读场景的 probe_pre"
    assert "_decl_pre" in src, "generate 没有解析身份前置（_decl_pre）"
    assert 'run_pre_actions(pg, _decl_pre, "场景探测前置"' in src, \
        "单页现场探测没应用 probe_pre -> 探测到的是只读态 -> 编辑态控件采集不到"
    assert "pre: list | None = None" in src, "_probe_declared_pages 没接收 pre 形参"
    assert "pre=_decl_pre" in src, "调用声明页探测时没把 _decl_pre 传进去"


def test_generate_probe_pre_priority_matches_auth():
    """优先级口径与 auth 一致：**用例自带优先，其次场景回读**（手搓用例的常见形态）。"""
    src = (REPO / "framework" / "features" / "f02_semantic" / "generator_generate.py").read_text(encoding="utf-8")
    i = src.index("_decl_pre: list = []")
    blk = src[i:i + 700]
    assert 'list(_c0.get("probe_pre") or [])' in blk, "没先认用例自带的 probe_pre"
    assert "_scenario_probe_pre_of(" in blk, "没有回退到场景 yml 的 probe_pre"
