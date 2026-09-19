"""hybrid_gui_qa 命令行入口 —— 一键流水线。

典型用法（先起被测应用：python -m demo.app）:
    python -m framework.cli probe            # 1) 探测页面交互元素
    python -m framework.cli generate         # 2) 读 cases/*.json → 生成 scripts/（按操作类型翻译 + 抽离数据）
    python -m framework.cli run --workers 2  # 3) pytest 并发执行用例 + 日志整合 + 报告
                                             #    跑前资源预检：内存不够会自动降并发，--force-workers 可强制
    python -m framework.cli all              # 1→2→3 全链路
    python -m framework.cli explore --ai --scenario "…"        # 内联自然语言（原样保留）
    python -m framework.cli explore --ai --scenario-file scenarios/x.yml   # 单场景文件
    python -m framework.cli explore --ai --scenario-dir scenarios/ --tag smoke  # 目录批量
                                             # AI 语义识别 → ElementMap + cases/ai_*.json
                                             # 默认做 --verify 试跑校验（实测不过 → exit 3；--no-verify 跳过）
    python -m framework.cli prune --keep 20   # 归档保留：快照各留最近 N 个（--dry-run 预演，不删）
    python -m framework.cli run --debug        # 调试开关（别名 --headed）：有屏幕→弹浏览器；没屏幕→录视频+逐步截图
    python -m framework.cli run --debug --case contracts_search_by_no   # 只跑一条用例
    python -m framework.cli run --debug --slowmo 500                    # 动作放慢 500ms，肉眼跟步

目录职责：
    cases/       手写自然语言用例（写死数据 + asserts[] 断言）
    scripts/     generate 产物（playwright 脚本 + scripts/datasets 抽离数据，分离）
    output/      probe/element_map/plan/heals/trace（运行时证据）
"""
from __future__ import annotations
import sys
from typing import NoReturn

from . import config
from .config import ensure_dirs, TARGET_URL, LOG_DIR
from .probe import probe_page
from .browser import launch_opts
from .limits import safe_workers
from .retention import DEFAULT_KEEP as KEEP_SNAPSHOTS, prune_snapshots
from .text_io import force_stdio, fs_encoding_warning, run_capture, utf8_env


def _now() -> str:
    import datetime as _dt
    return _dt.datetime.now().strftime("%Y%m%d_%H%M%S")


def _worker_from(rest: list[str]) -> int | None:
    """解析 --workers N；缺省 None（pytest -n auto）。"""
    if "--workers" in rest:
        i = rest.index("--workers")
        if i + 1 < len(rest) and rest[i + 1].isdigit():
            return int(rest[i + 1])
    return None


_TRUE_WORDS = {"true", "1", "yes", "y", "on"}
_FALSE_WORDS = {"false", "0", "no", "n", "off"}


def _debug_from(rest: list[str]) -> bool:
    """解析【调试开关】`--debug`（别名 `--headed`，兼容 Playwright 叫法）。

    **布尔开关**：写了 = 开（调试模式），不写 = 关（默认）。也支持显式写法 `--debug true|false`
    （方便脚本里当可配置项）。开了就是"我要看得见这次执行"：
      · 有图形显示 → 弹出 Chromium 窗口，看它一步步执行到用例结束；
      · 无图形显示 → 自动改为录制（视频 + 逐步截图 + trace），照样看得见，不报错。
    """
    for flag in ("--debug", "--headed"):
        if flag in rest:
            i = rest.index(flag)
            if i + 1 < len(rest):
                v = rest[i + 1].strip().lower()
                if v in _TRUE_WORDS:
                    return True
                if v in _FALSE_WORDS:
                    return False
            return True
    return False


def _headed_from(rest: list[str]) -> bool:
    """兼容旧名：等价于 `_debug_from`。"""
    return _debug_from(rest)


def _has_display() -> bool:
    """本机有没有图形显示（决定调试开关走"开窗"还是"录制"）。"""
    import os
    if sys.platform == "win32":
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def _force_from(rest: list[str]) -> bool:
    """解析 --force-workers（绕过内存预检，强行使用请求的并发数）。"""
    return "--force-workers" in rest


def _isolated_from(rest: list[str]) -> bool:
    """解析 --isolated-target（显式声明：目标已按 worker 隔离数据，可以放心并发）。"""
    return "--isolated-target" in rest


def _arg_values(rest: list[str], flag: str) -> list[str]:
    """取可重复出现的 `--flag <value>`（此处用于 --case a --case b）。"""
    out: list[str] = []
    for i, a in enumerate(rest):
        if a == flag and i + 1 < len(rest) and not rest[i + 1].startswith("--"):
            out.append(rest[i + 1])
    return out


def _slowmo_from(rest: list[str]) -> int | None:
    """解析 --slowmo <毫秒>（放慢每个动作，肉眼 debug 用；0/缺省=不放慢）。"""
    if "--slowmo" in rest:
        i = rest.index("--slowmo")
        if i + 1 < len(rest) and rest[i + 1].isdigit():
            return int(rest[i + 1])
    return None


def cmd_probe():
    """探测页面交互元素 → output/element_maps/probe_*.json。

    除了基础页面，还会点开「新建类」弹窗、**并钻进弹窗里嵌的 picker 层**（如客户列表），
    把层内控件一并探测出来（2026-09-14）—— 否则「从列表里选一行」这类 UI 对 AI/人都是盲区。
    层内元素在输出里带 🔸 标记，JSON 里带 `"source": "layer"`。
    """
    ensure_dirs()
    # ---- 目标可达性预检（V7.5.1）：先回答「活没活」，别让 Playwright 甩一屏 traceback ----
    # 2026-09-15 实测：demo 没起时 `pg.goto()` 抛 `net::ERR_CONNECTION_REFUSED` + exit 1，
    # 现象像「框架坏了」，其实是一句「demo 没启动」。环境问题要给动作，不是给栈。
    from .target_probe import reachability
    ok, why = reachability(TARGET_URL)
    if not ok:
        print(f"\n[probe] ❌ 探测没跑：{why}")
        print("[probe]    目标地址可用 TARGET_URL / HYBRID_BASE_URL 覆盖（两者等效）；"
              "demo 起好后重跑 `python -m framework.cli probe`（或 all）")
        raise SystemExit(2)
    from playwright.sync_api import sync_playwright
    import json
    from .explorer import _try_collect_modal_items, _merge_items
    with sync_playwright() as p:
        b = p.chromium.launch(**launch_opts(headless=True))
        pg = b.new_page()
        pg.goto(TARGET_URL)
        items = probe_page(pg)
        layer_items = _try_collect_modal_items(pg, items)      # 弹窗 + 嵌套弹层
        for it in layer_items:
            it["source"] = "layer"
        items = _merge_items(items, layer_items)
        b.close()
    out = config.ELEMENT_MAP_DIR / f"probe_{_now()}.json"
    out.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    prune_snapshots(quiet_if_none=True)          # 归档保留策略（静默：无可清理就不打印）
    n_layer = sum(1 for it in items if it.get("source") == "layer")
    print(f"[probe] 探测到 {len(items)} 个交互元素（其中弹窗/弹层内 {n_layer} 个）→ {out}")
    for it in items:
        mark = "🔸" if it.get("source") == "layer" else "  "
        print(f"      {mark} - {it['semantic_name']:<20} [{it['role']:<8}] "
              f"name={it['name']!r} ph={it['placeholder']!r} test_id={it['test_id']!r}")


def _report_unmapped(e) -> NoReturn:
    """映射质量闸触发时的交代：缺什么 / 为什么 / 下一步 —— **绝不落产物**，exit 2。"""
    print(f"\n[generate] ❌ 映射质量闸拦下：{len(e.missing)} 个语义名映射不上 → 拒绝产出任何产物")
    print(f"[generate]    locator 来源：{e.sources}")
    if e.probe_error:
        print(f"[generate]    现场 probe 失败：{e.probe_error}")
        # 先把「活没活」查清楚再给结论（旧版本这里只会猜「多半是目标没起」）
        try:
            from .target_probe import reachability
            ok, why = reachability(TARGET_URL)
        except Exception as _e:                       # 预检本身失败不该盖住原始错误
            ok, why = True, f"(可达性预检失败: {_e})"
        if not ok:
            print(f"[generate]    真因：{why}")
        else:
            print(f"[generate]    目标可达（{why}）⇒ 失败不是「没起」，查上面那条 probe 报错"
                  f"（权限/超时/页面结构变了）；`--debug` 可留截图与 trace")
    shown = e.missing[:20]
    print(f"[generate]    缺失项（共 {len(e.missing)} 个，最多列 20）：{shown}")
    if len(e.missing) > len(shown):
        print(f"[generate]    … 其余 {len(e.missing) - len(shown)} 个已省略")
    conflicts = getattr(e, "conflicts", None) or {}
    if conflicts:
        # 批次 2（S1/S2）：这一档缺失不是「名字拼错」，而是**同名歧义**——页面上有 ≥2 个控件
        # 争同一个基础名，探测已把它们全部唯一化（`base@上下文`），所以裸名不再存在。
        # 直接给候选，别让人去猜（历史事故就是含糊报错把人绕了半天）。
        print(f"[generate]    ⚠️ 其中 {len(conflicts)} 个是**同名歧义**（不是拼写错误）："
              f"该名字在页面上对应 ≥2 个控件，探测已全部唯一化 ⇒ 裸名不存在了。请改用下列候选之一：")
        for base, names in sorted(conflicts.items()):
            print(f"[generate]      · {base!r} → 候选：{'、'.join(names)}")
        print("[generate]    下一步：挑一个候选写进用例的 element（上下文后缀来自该控件所在区域/行），"
              "或给该控件补 data-testid 让它有稳定唯一名。")
    print("[generate]    （旧行为：只打一句警告就照样落盘 ⇒ 产出「每步都是 pytest.fail 存根」的垃圾产物；"
          "2026-09-15 的 V7.5 交付事故就是它进包的）")
    print("[generate]    仅调试时可显式加 --allow-unmapped 放行；那样的产物永不允许进交付。")
    raise SystemExit(2)


def _report_case_quality(e) -> NoReturn:
    """假绿红线触发时的交代：哪条用例 / 什么证据没牙 / 怎么改 —— **绝不落产物**，exit 2。"""
    print(f"\n[质量闸] ❌ 假绿红线拦下：{len(e.entries)} 条用例、共 {e.total} 处 → 拒绝产出任何产物")
    for cid, errs in e.entries:
        print(f"[质量闸]   用例 {cid}:")
        for m in errs:
            print(f"[质量闸]     · {m}")
    print("[质量闸]    真因：换页证据（kind=url 的 expect）若在**多个页面**的 URL 里都出现，"
          "换页前后都能通过 ⇒ 用例照样绿，但「确实换页了」这件事根本没被验到。")
    print("[质量闸]    下一步：① 换成只出现在目标页的片段（详情页 → contract_detail）；"
          "② 目标页没有独有 URL 片段（列表页就是根路径 /）→ 改对该页独有文案做 text 断言；"
          "③ 顺带确认用例的页面清单 pages[].url 填全了。")
    print("[质量闸]    （旧行为：这条假绿一路跑到报告里，靠人工复核才发现 —— 2026-09-14 就是。）")
    raise SystemExit(2)


def cmd_generate(rest: list[str] = None, allow_unmapped: bool = False):
    """读 cases/*.json → 生成 scripts/（playwright 脚本 + scripts/datasets 抽离数据）。

    定位来源（P1 起）：默认优先读【probe 产出的 element.map 快照】；缺失才现场补探测。
      --element-map <path>  指定用某个 element_map_*.json（explore 产物）
      --live-probe          强制现场重新 probe（忽略快照，最准但最慢）
      --allow-unmapped      【调试用】放行「有语义名映射不上」的情况，仍然产出产物（含 pytest.fail 存根）；
                            默认**拒绝落盘并 exit 2**（防止产出/交付一份全是 fail 存根的假脚本）

    无法获得定位时**不产出产物**：宁可生成阶段就红，也不给出一份「看着合法、跑起来 50 条失败」的东西。
    """
    ensure_dirs()
    from pathlib import Path as _P
    from .case_builder import CaseQualityError
    from .generator import UnmappedElementsError, generate_scripts
    rest = rest or []
    map_path = None
    if "--element-map" in rest:
        i = rest.index("--element-map")
        if i + 1 < len(rest):
            map_path = _P(rest[i + 1])
    try:
        res = generate_scripts(element_map_path=map_path, live_probe="--live-probe" in rest,
                               allow_unmapped=allow_unmapped or ("--allow-unmapped" in rest))
    except CaseQualityError as e:
        _report_case_quality(e)
    except UnmappedElementsError as e:
        _report_unmapped(e)
    print(f"[generate] 读 cases/ → 生成 {res['count']} 个用例到 scripts/:")
    print(f"          tests: {res['tests']}")
    print(f"          datasets: {len(res['datasets'])} 个（脚本数据分离）")
    for d in res["datasets"]:
        print(f"            - {d}")
    print(f"          locator 来源: {res.get('locator_sources', '(未统计)')}")
    # 0 个用例 = 什么都没生成（2026-09-13 修）：以前照打一行"生成 0 个用例"就 exit 0，
    # 脚本/CI 会把空用例集当成功 ⇒ 明确失败并给下一步动作。
    if res["count"] == 0:
        print("[generate] ❌ cases/ 里一个用例都没有 → 没有生成任何可执行测试。"
              "先写 cases/*.json，或用 explore --ai 让 AI 出题")
        raise SystemExit(2)


def _arg_value(rest: list[str], flag: str) -> str | None:
    """取 `--flag <value>` 的值（下一个 token 以 -- 开头视为缺值 → None）。

    也认 `--flag=value`（2026-09-18）：`_validate_args` 本来就放行等号写法，
    但本函数以前只认分离写法 ⇒ `--llm-record=/tmp/x` 这种会**静默退回默认目录**
    （用户明给的路径被丢掉，属于「说了不听」）。两种写法现在等价。
    """
    for i, a in enumerate(rest):
        if a == flag:
            if i + 1 < len(rest) and not rest[i + 1].startswith("--"):
                return rest[i + 1]
            return None
        if a.startswith(flag + "="):
            return a.split("=", 1)[1]
    return None


def _rel(p) -> str:
    """相对项目根显示路径（失败则原样返回）。"""
    from pathlib import Path
    try:
        return str(Path(p).resolve().relative_to(config.BASE))
    except Exception:
        return str(p)


def _explore_one(scenario_text: str, url: str, *, label: str = "", page_bg: str = "",
                 guard_text: str = "", guard_spec: dict | None = None,
                 case_id: str | None = None, extra: dict | None = None,
                 to_cases: bool = True, mock_fallback: bool = False,
                 pages: list[dict] | None = None, cassette=None, cassette_strict: bool = False):
    """跑一次 AI 语义识别（+ 可选落 cases/）。返回 (emap, case_path | None, warns)。

    pages（P3 跨页）：[{"name","url","page"}, ...]；给了 ≥2 页就按跨页模式探测与规划，
    `url` 此时应为第一页地址（explore 的 goto 起点）。
    """
    from .explorer import ai_explore
    prefix = f"【{label}】" if label else ""
    # 刻意不在外面探测：ai_explore 内部会探测（且会打开弹窗补表单控件）。
    # 2026-09-11 修复：旧写法先探一次再交给 ai_explore ⇒ 连开两个 Chromium，内存吃紧时
    # 第二次探测失败，叠加 ai_explore 里的静默兜底 ⇒ AI 只能看到基础控件（弹窗字段全丢）。
    emap = ai_explore(scenario_text, [], url, allow_mock_fallback=mock_fallback,
                      page_bg=page_bg, guard=guard_text, pages=pages, llm_cassette=cassette,
                      cassette_strict=cassette_strict)
    print(f"{prefix}[explore] 生成 ElementMap: {len(emap.steps)} 步")
    for st in emap.steps:
        el = st.element
        print(f"  - {st.order}. {st.action:8s} → {el.semantic_name if el else '(无)'} "
              f"| {st.value or ''} | assert={st.assertion or ''} | {st.description}")

    out = config.ELEMENT_MAP_DIR / f"element_map_{_now()}.json"
    n = 2
    while out.exists():                       # 批量跑时同秒不撞名
        out = config.ELEMENT_MAP_DIR / f"element_map_{_now()}-{n}.json"
        n += 1
    emap.to_json(out)
    print(f"          → {out}")

    cpath = None
    warns: list[str] = []
    if cassette is not None:
        # 溯源：把「这条用例是录像回放出来的、还是当场问的 AI」写进用例文件 ——
        # 复核的人不用回忆当时敲了什么命令（回放 ≠ 实时 AI，必须看得见）。
        extra = {**(extra or {}), "llm_source": cassette.source_tag()}
    if to_cases and not mock_fallback:
        from .case_builder import CaseQualityError as _CaseQE
        from .case_builder import elementmap_to_cases_file
        try:
            cpath, warns = elementmap_to_cases_file(emap, case_id=case_id, extra=extra, guard=guard_spec)
        except _CaseQE as e:
            # 假绿红线（如换页证据只写 localhost）⇒ 拒绝落盘，绝不产出「看着绿、其实没验」的用例
            _report_case_quality(e)
        print(f"          → 用例: {cpath}  （AI 用例，ai_ 前缀）")
        for w in warns:
            print(f"          ⚠️ 质量警告: {w}")
    return emap, cpath, warns


def cmd_explore(rest: list[str] = None):
    """【AI 语义识别】自然语言场景（内联 或 scenario 文件）+ probe 清单 + DOM 上下文
    → ElementMap（默认同步落 cases/ai_*.json）。

    需 .env 配 DeepSeek key（config.llm_from_env 走 ChatDeepSeek）。

    三种入口（**互斥**，只给一个；都不给用内置默认场景）：
      --scenario "…"                     内联自然语言（原样保留）
      --scenario-file scenarios/x.yml    单个场景文件（见 framework/scenario.py）
      --scenario-dir scenarios/          目录批量（可配 --tag / --limit）

    开关：
      --no-cases                是否落 cases/ai_*.json（**默认落**；没有 --to-cases 这个开关）
      --verify / --no-verify    落盘后是否试跑校验（**默认试跑**；实测失败 → exit 3）
      --mock-fallback           LLM 不可用时显式降级为确定性 mock（默认【拒绝】，且不写 cases/）
      --tag <t>（可重复）        目录批量时按 tag 过滤（OR 语义）
      --limit N                 目录批量时最多跑 N 条
      --llm-record [DIR]        【录制】真调 LLM，成功后把「prompt → 回答」落盘
                                （DIR 可省，默认 output/llm_cassettes）
      --llm-cassette [DIR]      【回放】只读录像目录：命中即用（**不联网、不需要 key**）；
                                先按严格键（prompt 逐字一致）找，找不到再用**结构键**兜底
                                （同场景、同页面结构，但页面数据的值不同 —— 换台机器就是这样）
                                ⇒ 结构键命中会**大声告警**，请核对后再用
      --llm-cassette-strict     回放只认严格键（不要结构键兜底）
      · 两者互斥；都不给 = 实时调用（与以前逐字一致，行为不变）
      · 无外网的机器怎么用：先在**有外网**的机器上 --llm-record 录一次 → 把整个录像目录
        拷过去 → 那台机器用 --llm-cassette，就能跑完整 explore（含默认 --verify 试跑）
    """
    ensure_dirs()
    rest = rest or []
    if "--ai" not in rest:
        print("[explore] ❌ 缺 --ai：explore 只做真 AI 语义识别（不提供隐式降级 —— 静默兜底=造假）。")
        print("          要跑确定性链路请用： python -m framework.cli probe → generate → run")
        raise SystemExit(2)

    mock_fallback = "--mock-fallback" in rest
    to_cases = "--no-cases" not in rest
    do_verify = "--no-verify" not in rest

    # ---------- LLM 录像：录制 / 回放（2026-09-18）----------
    # **只在显式给参数时启用** —— 默认一个字节都不变（实时调用），绝不自动切换模式。
    from .llm_cassette import MODE_RECORD, MODE_REPLAY, Cassette, CassetteError
    has_rec = "--llm-record" in rest or any(a.startswith("--llm-record=") for a in rest)
    has_rep = "--llm-cassette" in rest or any(a.startswith("--llm-cassette=") for a in rest)
    if has_rec and has_rep:
        print("[explore] ❌ --llm-record 与 --llm-cassette 互斥：一次只能「录」或「放」"
              "（要边录边放请分两次跑）")
        raise SystemExit(2)
    if (has_rec or has_rep) and mock_fallback:
        print("[explore] ❌ --mock-fallback 与录像模式互斥：mock 是确定性假产物、录像里存的是"
              "真 AI 回答 —— 混用没有意义")
        raise SystemExit(2)
    cassette = None
    try:
        if has_rec:
            cassette = Cassette(MODE_RECORD, _arg_value(rest, "--llm-record"))
        elif has_rep:
            cassette = Cassette(MODE_REPLAY, _arg_value(rest, "--llm-cassette"))
    except CassetteError as e:
        print(f"[explore] ❌ {e}")
        raise SystemExit(2) from None
    cassette_strict = "--llm-cassette-strict" in rest
    if cassette_strict and not has_rep:
        print("[explore] ❌ --llm-cassette-strict 只与 --llm-cassette 搭配使用"
              "（它的意思是「回放只认逐字一致的录像」）")
        raise SystemExit(2)
    if cassette is not None:
        print(f"[explore] {cassette.banner()}"
              + ("　· 只认严格键" if cassette_strict else ""))

    inline = _arg_value(rest, "--scenario")
    sfile = _arg_value(rest, "--scenario-file")
    sdir = _arg_value(rest, "--scenario-dir")
    given = [(f, v) for f, v in (("--scenario", inline), ("--scenario-file", sfile),
                                 ("--scenario-dir", sdir)) if v]
    if len(given) > 1:
        print(f"[explore] ❌ 参数互斥：{'、'.join(g[0] for g in given)} 只能给一个（不猜你的意图）")
        raise SystemExit(2)

    from .case_builder import make_case_id_from_scenario_id

    def _job_from_scenario(sc, scenario_text: str) -> dict:
        pgs = [p.to_dict() for p in sc.all_pages()]
        return dict(
            label=sc.id, text=scenario_text,
            url=(pgs[0]["url"] if pgs else (sc.url or TARGET_URL)),
            pages=(pgs if len(pgs) > 1 else None),
            page_bg=sc.page_bg(), guard_text=sc.guard_text(), guard_spec=sc.guard_spec(),
            case_id=make_case_id_from_scenario_id(sc.id), extra=sc.case_extra(),
        )

    # ---------- 收集作业（一条 = 一个场景）----------
    jobs: list[dict] = []
    if sdir:
        from pathlib import Path
        from .scenario import ScenarioError, discover_scenarios
        tags = _arg_values(rest, "--tag")
        lim = _arg_value(rest, "--limit")
        try:
            scs = discover_scenarios(Path(sdir), tags=tags, limit=int(lim) if lim else None)
        except ScenarioError as e:
            print(f"[explore] ❌ {e}")
            raise SystemExit(2) from None
        print(f"[explore] 场景目录: {sdir} → 命中 {len(scs)} 个场景"
              + (f"（tag={','.join(tags)}）" if tags else ""))
        for sc in scs:
            for w in sc.warnings:
                print(f"  ⚠️ [{sc.id}] {w}")
            jobs.append(_job_from_scenario(sc, sc.scenario))
    elif sfile:
        from pathlib import Path
        from .scenario import ScenarioError, load_scenario_file
        try:
            sc = load_scenario_file(Path(sfile))
        except ScenarioError as e:
            print(f"[explore] ❌ {e}")
            raise SystemExit(2) from None
        for w in sc.warnings:
            print(f"  ⚠️ [{sc.id}] {w}")
        print(f"[explore] 场景文件: {sfile}（id={sc.id}"
              + (f", tags={','.join(sc.tags)}" if sc.tags else "")
              + (f", priority={sc.priority}" if sc.priority else "") + "）")
        jobs.append(_job_from_scenario(sc, sc.scenario))
    else:
        jobs.append(dict(
            label="", text=inline or "在合同列表页面的搜索框输入'合同1'，然后点击搜索按钮查看结果。",
            url=TARGET_URL, page_bg="", guard_text="", guard_spec=None, case_id=None, extra=None,
        ))

    # ---------- 逐条跑 ----------
    from .explorer import AiExploreError
    done: list[tuple[str, str]] = []
    last_emap = None
    for idx, job in enumerate(jobs, 1):
        if len(jobs) > 1:
            print(f"\n[explore] === 场景 {idx}/{len(jobs)}：{job['label']} ===")
        try:
            emap, cpath, _ = _explore_one(
                job["text"], job["url"], label=job["label"], page_bg=job["page_bg"],
                guard_text=job["guard_text"], guard_spec=job["guard_spec"],
                case_id=job["case_id"], extra=job["extra"],
                to_cases=to_cases, mock_fallback=mock_fallback, pages=job.get("pages"),
                cassette=cassette, cassette_strict=cassette_strict)
        except AiExploreError as e:
            print(f"[explore] ❌ 【{job['label'] or '内联'}】{e}")
            raise SystemExit(2) from None
        last_emap = emap
        if cpath:
            done.append((job["label"], cpath.stem))
        if mock_fallback:
            print("          ⚠️ mock 兜底产物 → 按约定【不落 cases/】（避免假 AI 用例污染用例库）")

    prune_snapshots(quiet_if_none=True)          # 归档保留策略：快照各留最近 N 个

    if cassette is not None and cassette.is_replay:
        print(f"[explore] ⚠️ 本次 AI 判断来自**录像回放**（{cassette.root}）："
              f"是录制那一刻问出来的，不是现在实时问的 —— 用例里的 llm_source 字段已标注来源")

    if done and do_verify:
        if _verify_cases(done) is False:
            print("[explore] ❌ 有 AI 用例【实测未通过】→ 不可当可用用例（请修正场景/断言后重来；"
                  "坏用例仍在 cases/ 里，确认后可删）")
            raise SystemExit(3)
    elif done:
        print("          ℹ️ 按 --no-verify 跳过试跑校验（这些用例未经实测验证）")

    return last_emap


def _verify_cases(entries: list[tuple[str, str]]) -> bool | None:
    """新用例试跑校验：generate 一次 + 逐条 pytest 单跑（explore 的「交付即验证」闸门）。

    entries: [(label, case_name)] —— label 用于批量时标明是哪条场景。
    返回 True=全部实测通过 / False=有失败 / None=校验没能执行（环境问题，不判死刑）。
    """
    from .config import SCRIPTS_DIR

    if not entries:
        return None
    tests = SCRIPTS_DIR / "test_cases.py"
    print(f"[explore] --verify：先 generate 一次，再逐条试跑 {len(entries)} 条新用例…")
    # ⚠️ 必须用 run_capture（显式 UTF-8 解码）：以前是裸 `subprocess.run(..., text=True)`，
    # 父进程按系统默认编码（中文 Windows = cp936/gbk）解码子进程的 UTF-8 中文输出 ⇒
    # `UnicodeDecodeError: 'gbk' codec can't decode byte 0xbb in position 13`（2026-09-13 AprilPark1012实测）。
    gen = run_capture([sys.executable, "-m", "framework.cli", "generate"], cwd=str(config.BASE))
    if gen.returncode != 0:
        print("  ⚠️ 校验未执行：generate 失败（多半是「映射质量闸」拦下：目标没起 / 探测不可用）"
              "→ scripts/ **未更新**，新用例【未经实测验证】，别把它当成已验证")
        tail = ((gen.stdout or "") + (gen.stderr or ""))[-400:]
        print("  " + tail.replace("\n", "\n  "))
        return None

    vdir = config.OUTPUT_DIR / "verify"
    vdir.mkdir(parents=True, exist_ok=True)
    all_ok = True
    for label, name in entries:
        node = f"{tests}::test_{name}"
        r = run_capture([sys.executable, "-m", "pytest", node, "-v", "-s"],
                        cwd=str(config.BASE))
        text = (r.stdout or "") + (r.stderr or "")
        log = vdir / f"{name}_{_now()}.log"
        log.write_text(text, encoding="utf-8")
        tag = f"【{label}】" if label else ""
        if r.returncode == 0:
            print(f"  ✅ {tag}校验通过：该用例实测 PASSED（校验日志 {log}）")
        else:
            all_ok = False
            print(f"  ❌ {tag}校验失败：该用例实测 FAILED（断言是猜的？页面结构变了？）校验日志 {log}")
            for line in text.splitlines():
                s = line.strip()
                if s.startswith("E ") or "TimeoutError" in s or "not found" in s:
                    print(f"     {s[:160]}")
    return all_ok


def _verify_case(case_name: str) -> bool | None:
    """单条校验（薄封装，保留原有调用形状）。"""
    return _verify_cases([("", case_name)])


def cmd_prune(rest: list[str] = None):
    """归档保留策略：output/element_maps/ 的 element_map_*.json / probe_*.json 各留最近 N 个。

    用法: python -m framework.cli prune [--keep 20] [--dry-run]
    默认保留数可用环境变量 HYBRID_KEEP_SNAPSHOTS 覆盖；--dry-run 只预演不删。
    """
    ensure_dirs()
    rest = rest or []
    keep = KEEP_SNAPSHOTS
    if "--keep" in rest:
        i = rest.index("--keep")
        if i + 1 < len(rest) and rest[i + 1].isdigit():
            keep = int(rest[i + 1])
    dry = "--dry-run" in rest
    print(f"[prune] 快照保留策略：每类保留最近 {keep} 个（{'dry-run 预演，不删' if dry else '实际清理'}）")
    removed = prune_snapshots(keep=keep, dry_run=dry, quiet_if_none=False)
    print(f"[prune] {'将清理' if dry else '已清理'} {len(removed)} 个快照文件")
    if dry and removed:
        for f in removed[:5]:
            print(f"          - {f.name}")
        if len(removed) > 5:
            print(f"          … 其余 {len(removed) - 5} 个")


def cmd_run(workers: int | None = None, debug: bool = False, force_workers: bool = False,
            cases: list[str] | None = None, slowmo: int | None = None,
            isolated_target: bool = False):
    """用 pytest 执行 scripts/test_cases.py + 日志整合 + HTML 报告。

    debug=True（`--debug`，别名 `--headed`）＝ **调试开关**（默认关，只在调试时用）。
      开了 = "我要看得见这次执行"：单浏览器、顺序跑、动作放慢（默认 200ms，`--slowmo N` 可改），
      然后分两种情况（都不报错）：
        · 有图形显示（Windows 桌面 / 带 X 的 Linux）→ `headless=False`，**Chromium 窗口弹出来**，
          看着它一步步执行到用例结束；
        · 无图形显示（服务器）→ **不改需求，改成录下来**：整条用例录成 `log/<run_id>/videos/<case_id>.webm`，
          并且每一步存一张图 `log/<run_id>/shots/<case_id>/01_*.png`（直接打开就能看），另有 trace 可交互回放。
      ⚠️ 调试模式刻意**不带 `-n`**：`pytest -n 1` 也会设 `PYTEST_XDIST_WORKER=gw0`，而 conftest 判定
      "在 worker 里 ⇒ 无头" ⇒ 旧版 `--headed` 因此是空操作（2026-09-11 修复）。

    默认（不写 `--debug`）＝ 无头并发跑，按内存预检裁并发（防 OOM 杀 Hermes 网关），不录像不截图。
    cases=[...]（`--case <case_id>`，可重复）：只跑指定用例（透传 pytest `-k`）；不传=整包跑。
    产物落在 log/<run_id>/（run-id 隔离 ⇒ 天然"本次运行干净"）。
    """
    ensure_dirs()
    import os
    import subprocess
    from .config import SCRIPTS_DIR
    tests = SCRIPTS_DIR / "test_cases.py"
    if not tests.exists():
        print("[run] ❌ scripts/test_cases.py 不存在 → 没有可跑的东西（先跑 generate）")
        print("      （2026-09-13 修：这里以前只提示一句就 return，**exit 0** —— "
              "CI/脚本调用方会把\"什么都没跑\"误判成成功）")
        raise SystemExit(2)

    # ---- 资源预检：按可用内存裁定并发（本次 OOM 事故的根治点）----
    n, why = safe_workers(workers)
    print(f"[run] 资源预检: {why}")
    if workers and n < workers:
        if force_workers:
            n = workers
            print(f"[run] ⚠️ --force-workers 生效：无视预检，强行用 {n} 并发"
                  f"（内存不足时有 OOM 风险，可能连带影响 Hermes 网关）")
        else:
            print(f"[run] ⚠️ 请求并发 {workers} 超出安全值 → 已降级为 {n}"
                  f"（确有把握可加 --force-workers 覆盖；预算可用 "
                  f"HYBRID_MB_PER_WORKER / HYBRID_RESERVE_MB 调整）")

    # ---- 并发安全闸（F6b）：目标是否"声明可并发隔离"？没声明就保守串行 ----
    # 为什么（2026-09-14 团队演示实测）：并发的前提是**每个 worker 读写自己的数据分区**。
    # 目标没这个能力时，多 worker 共享一份状态会让精确计数断言互相踩（实测：期望 20 行实得 23、
    # 期望 4 条实得 6），而且失败原因会指向错误的地方——比"跑得慢"危险得多。
    if not debug and n > 1:
        if isolated_target or os.environ.get("HYBRID_ISOLATED_TARGET", "") == "1":
            print(f"[run] 并发隔离：已显式声明（--isolated-target / HYBRID_ISOLATED_TARGET=1）"
                  f" → 保持 {n} worker")
        else:
            from .target_probe import probe_partitioned
            capable, why_p = probe_partitioned()
            if capable:
                print(f"[run] 并发隔离：{why_p} → 保持 {n} worker（框架会给每个 worker 注入独立数据分区）")
            else:
                print(f"[run] ⚠️ 并发隔离：{why_p}")
                print(f"[run] ⚠️ 目标未声明可并发隔离 → 并发由 {n} 保守降级为 1")
                print(f"[run]    多 worker 共享一份状态时，精确计数断言会随机红、且失败原因指向错误的地方；"
                      f"要并发请让目标支持按 worker 分区（/api/health 返回 partitioned=true），"
                      f"或确知已隔离时加 --isolated-target")

    # ---- 调试开关（--debug / --headed）：开了就"看得见"（有屏幕开窗；没屏幕录制）----
    if debug:
        if n != 1:
            print(f"[run] 🐞 调试模式 → 并发由 {n} 强制降为 1（单浏览器顺序跑，才看得清）")
        n = 1
        os.environ["HYBRID_DEBUG"] = "1"
        if _has_display():
            os.environ["HYBRID_HEADED"] = "1"
            print("[run] 🐞 调试模式：有图形显示 → 弹出 Chromium 窗口，看它一步步执行到用例结束")
        else:
            os.environ["HYBRID_VIDEO"] = "1"
            os.environ["HYBRID_SHOTS"] = "1"
            print("[run] 🐞 调试模式：本机没有图形显示（DISPLAY/WAYLAND_DISPLAY 未设置）")
            print("[run]       → 不改需求，这次执行【录下来给你看】：视频 + 每一步截图 + trace")
            print("[run]       → 换到带屏幕的机器（如 Windows 桌面）跑同一个开关，就直接弹出浏览器窗口")
        if not slowmo:
            slowmo = 200
            print("[run] 🐞 调试模式默认放慢 200ms/动作（--slowmo N 覆盖，0 = 不放慢）")

    # ---- run-id 隔离的产物目录 ----
    run_id = _now()
    run_dir = LOG_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    os.environ["HYBRID_RUN_ID"] = run_id
    if slowmo:
        os.environ["HYBRID_SLOWMO"] = str(slowmo)

    cmd = [sys.executable, "-m", "pytest", str(tests), "-v",
           f"--html={run_dir / 'report.html'}", "-s"]
    if not debug:
        # 调试模式绝不能带 -n：xdist 会起 worker 进程，worker 里带 PYTEST_XDIST_WORKER
        # ⇒ conftest 判定"在 worker 里 ⇒ 无头"，调试开关就白传了（旧版实测 bug）
        cmd += ["-n", str(n)]
    if cases:
        # 只跑指定用例：test_<case_id> or test_<case_id>...（pytest -k 表达式）
        expr = " or ".join(f"test_{c}" for c in cases)
        cmd += ["-k", expr]
        print(f"[run] 只跑指定用例（{len(cases)} 条）：{', '.join(cases)}")
    mode = "调试模式：单浏览器、不用 xdist" if debug else f"无头 ×{n} worker"
    if slowmo:
        mode += f"，slow_mo={slowmo}ms"
    print(f"[run] 执行 → {' '.join(cmd)}  ({mode})")
    print(f"[run] 本次运行产物 → {run_dir}（逐用例 .log + report.html）")
    # env=utf8_env()：让 pytest 子进程按 UTF-8 输出（否则 Windows cp936 控制台下
    # conftest 里的 ✓ / ⚠️ 会 UnicodeEncodeError，跑到一半崩）；父进程已 force_stdio()
    # 把 Windows 控制台代码页设成 65001，所以中文在控制台照样显示正常。
    r = subprocess.run(cmd, cwd=str(config.BASE), env=utf8_env())
    print(f"[run] pytest 退出码 {r.returncode}")
    if debug:
        vids = sorted((run_dir / "videos").glob("*.webm")) if (run_dir / "videos").exists() else []
        shots = sorted((run_dir / "shots").glob("*/*.png")) if (run_dir / "shots").exists() else []
        traces = sorted((run_dir / "traces").glob("*.zip")) if (run_dir / "traces").exists() else []
        print(f"[run] 🐞 调试产物：视频 {len(vids)} 个 / 逐步截图 {len(shots)} 张 / trace {len(traces)} 个")
        for p in (vids[:1] + shots[:3]):
            print(f"        - {p}")
        if len(shots) > 3:
            print(f"        … 其余截图在 {run_dir / 'shots'}（按 01/02/03… 就是执行顺序）")
        if traces:
            print(f"        trace 交互回放：playwright show-trace {traces[0]}")
    if r.returncode == 5:
        print("[run] ℹ️ 退出码 5 = 没有匹配到任何用例（--case 的名字对不上？已生成的用例见 "
              "scripts/test_cases.py 里的 def test_* ）")
    # 退出码必须**如实传递**（2026-09-13 修）：以前 cmd_run 跑完就返回 ⇒ cli 永远 exit 0，
    # 用例失败(1)/没匹配到用例(5)/collect error(2) 全被吞掉 ⇒ CI 与脚本调用方一律误判成功。
    if r.returncode != 0:
        print(f"[run] ❌ 以 pytest 退出码 {r.returncode} 结束（1=有用例失败 / 5=没匹配到用例 / "
              f"其它=执行环境问题）→ cli 同样返回该退出码，别把它当成功")
        raise SystemExit(r.returncode)


def cmd_all(workers: int | None = None, debug: bool = False, force_workers: bool = False,
            cases: list[str] | None = None, slowmo: int | None = None,
            isolated_target: bool = False, allow_unmapped: bool = False):
    """probe → generate → run 一条龙。

    ⚠️ 需要被测目标在跑（`python -m demo.app`）：任一步拿不到目标都会**在生成期就红**，
    不会产出「全是 pytest.fail 存根」的假脚本（--allow-unmapped 是调试逃生口，别用于交付）。
    """
    cmd_probe()
    cmd_generate(allow_unmapped=allow_unmapped)
    cmd_run(workers, debug, force_workers, cases=cases, slowmo=slowmo,
            isolated_target=isolated_target)


# ============================ CLI 参数契约 ============================
# 原则（2026-09-13 定）：**未知 / 错位参数一律报错 + 非 0 退出，绝不静默忽略**。
# 起因（实测三个真问题）：
#   ① `prune --dry-run --workres 1`（--workers 拼错）→ 静默按默认跑完、exit 0；
#   ② 未知子命令 `frobnicate` → 只打 __doc__、**exit 0** ⇒ 脚本调用方误判成功；
#   ③ `_arg_values` 曾重复定义（后者静默覆盖前者）。
# 值含义: "value" = 必须带值； "opt" = 可带可不带值（如 --debug true|false）； None = 纯开关
FLAG_SPECS: dict[str, str | None] = {
    "--workers": "value", "--debug": "opt", "--headed": None, "--force-workers": None,
    "--isolated-target": None,
    "--case": "value", "--slowmo": "value",
    "--element-map": "value", "--live-probe": None,
    "--allow-unmapped": None,
    "--ai": None, "--mock-fallback": None, "--no-cases": None,
    "--verify": None, "--no-verify": None,
    "--scenario": "value", "--scenario-file": "value", "--scenario-dir": "value",
    "--tag": "value", "--limit": "value",
    # LLM 录像录制 / 回放（2026-09-18）：opt = 值可省（省了就用默认目录 output/llm_cassettes）
    "--llm-cassette": "opt", "--llm-record": "opt", "--llm-cassette-strict": None,
    "--keep": "value", "--dry-run": None,
}
# 对 run/all 生效的通用参数（main 统一解析）
_COMMON_FLAGS = {"--workers", "--debug", "--headed", "--force-workers", "--isolated-target",
                "--case", "--slowmo"}
CMD_FLAGS: dict[str, set[str]] = {
    "probe": set(),
    "generate": {"--element-map", "--live-probe", "--allow-unmapped"},
    "explore": {"--ai", "--mock-fallback", "--no-cases", "--no-verify", "--verify",
                "--scenario", "--scenario-file", "--scenario-dir", "--tag", "--limit",
                "--llm-cassette", "--llm-record", "--llm-cassette-strict"},
    "run": set(_COMMON_FLAGS),
    "all": set(_COMMON_FLAGS) | {"--allow-unmapped"},
    "prune": {"--keep", "--dry-run"},
}
# 已移除的参数：给"为什么没了 + 该用什么"，而不是笼统的"不认识"
REMOVED_FLAGS = {
    "--to-cases": "落 cases/ai_*.json 已是默认行为；要关掉用 --no-cases",
}


def _usage(cmd: str) -> str:
    fs = sorted(CMD_FLAGS.get(cmd, set()))
    return " ".join(fs) if fs else "(无参数)"


def _fail(msg: str, hint: str = "") -> None:
    """参数错误：明确报错 + 非 0 退出（脚本调用方必须能察觉）。"""
    print(f"\n[cli] ❌ {msg}", file=sys.stderr)
    if hint:
        print(f"        {hint}", file=sys.stderr)
    print("        （本项目约定：看不懂的参数一律报错，不静默忽略；"
          "总览见 python -m framework.cli --help）", file=sys.stderr)
    raise SystemExit(2)


def _validate_args(cmd: str, rest: list[str]) -> None:
    """校验参数：未知 flag / 用错子命令 / 缺取值 / 多余位置参数 → 报错退出 2。"""
    import difflib
    allowed = CMD_FLAGS.get(cmd, set())
    known = sorted(set(FLAG_SPECS) | set(REMOVED_FLAGS))
    i = 0
    while i < len(rest):
        a = rest[i]
        if not a.startswith("-"):
            _fail(f"多余的位置参数：{a}", f"{cmd} 不接受位置参数；可用参数：{_usage(cmd)}")
        name = a.split("=", 1)[0]
        if name in REMOVED_FLAGS:
            _fail(f"参数 {name} 已移除", f"替代做法：{REMOVED_FLAGS[name]}")
        if name not in FLAG_SPECS:
            close = difflib.get_close_matches(name, known, n=1, cutoff=0.6)
            _fail(f"不认识的参数：{name}",
                  f"是不是想写 {close[0]} ？" if close else f"{cmd} 可用参数：{_usage(cmd)}")
        if name not in allowed:
            owners = [c for c, fs in CMD_FLAGS.items() if name in fs]
            _fail(f"参数 {name} 对 {cmd} 无效",
                  f"它只用于 {'/'.join(owners)}；{cmd} 可用参数：{_usage(cmd)}")
        if "=" in a:                      # --key=value 形式
            i += 1
            continue
        spec = FLAG_SPECS[name]
        if spec == "value":
            if i + 1 >= len(rest) or rest[i + 1].startswith("-"):
                _fail(f"参数 {name} 缺少取值", f"用法：{name} <值>")
            i += 2
        elif spec == "opt":               # 如 --debug [true|false]
            i += 2 if (i + 1 < len(rest) and not rest[i + 1].startswith("-")) else 1
        else:
            i += 1
    return


def _print_help(cmd: str | None = None) -> None:
    """`--help` / `-h`：总览或单子命令帮助（**直接取函数 docstring**，文档与代码同源不会漂）。"""
    import inspect
    if cmd is None:
        print((__doc__ or "").strip())
        print("\n子命令：")
        for c in CMD_FLAGS:
            first = (inspect.getdoc(_CMD_FUNCS[c]) or "").strip().splitlines()[0]
            print(f"  {c:<9} {first}")
        print("\n查看单个子命令：python -m framework.cli <子命令> --help")
        print("run/all 通用参数：--workers N | --debug [true|false] | --headed | "
              "--force-workers | --isolated-target | --case <id>（可重复）| --slowmo <ms>")
        print("  说明：--force-workers  = 无视内存预检强行并发（有 OOM 风险）")
        print("        --isolated-target = 显式声明『目标已按 worker 隔离数据』，放行并发；")
        print("                            没声明时框架会探测目标 /api/health，未声明就保守降到 1 并发")
        return
    print(f"用法：python -m framework.cli {cmd} {_usage(cmd)}\n")
    print((inspect.getdoc(_CMD_FUNCS[cmd]) or "").strip())


def _version() -> str:
    """版本号读 `tools/build_html.py`（**版本单一来源**）；读不到就如实说 unknown，不编。"""
    try:
        import re
        src = config.VERSION_SOURCE.read_text(encoding="utf-8")
        v = re.search(r'^VERSION\s*=\s*"([^"]+)"', src, re.M)
        d = re.search(r'^VERSION_DATE\s*=\s*"([^"]+)"', src, re.M)
        if not v:
            return "unknown"
        return f"v{v.group(1)}" + (f" ({d.group(1)})" if d else "")
    except Exception:
        return "unknown"


def main():
    # ★ 统一 UTF-8（跨进程/落盘文本口径的唯一入口）——必须在任何 print / subprocess 之前跑：
    #   ① 自身 stdout/stderr 转 UTF-8（Windows cp936 下 ✓/❌/⚠️ 不再 UnicodeEncodeError）；
    #   ② PYTHONUTF8/PYTHONIOENCODING 写进 os.environ ⇒ 之后所有 Python 子进程按 UTF-8 输出；
    #   ③ Windows 控制台代码页 → 65001，中文显示不乱码。
    force_stdio()
    _fs_warn = fs_encoding_warning()
    if _fs_warn:
        # 文件系统编码不是 UTF-8 ⇒ 中文文件名会落成 GBK/其他字节名（仓库里就是乱码）。
        # 运行期改不了，只能大声提醒（不静默：静默的后果是留下一堆打不开的文件名）。
        print(_fs_warn, file=sys.stderr)
    ensure_dirs()
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        _print_help(); return
    if args[0] in ("-V", "--version"):
        print(f"hybrid_gui_qa {_version()}  ·  被测目标 {TARGET_URL}")
        return
    cmd, rest = args[0], args[1:]
    if cmd not in CMD_FLAGS:
        import difflib
        close = difflib.get_close_matches(cmd, list(CMD_FLAGS), n=1, cutoff=0.5)
        _fail(f"未知子命令：{cmd}",
              f"是不是想写 {close[0]} ？" if close else f"可用子命令：{' / '.join(CMD_FLAGS)}")
    if any(a in ("-h", "--help") for a in rest):
        _print_help(cmd); return
    _validate_args(cmd, rest)

    workers = _worker_from(rest)
    headed = _debug_from(rest)
    force_workers = _force_from(rest)
    isolated = _isolated_from(rest)
    cases = _arg_values(rest, "--case")
    slowmo = _slowmo_from(rest)
    allow_unmapped = "--allow-unmapped" in rest
    if cmd == "probe":
        cmd_probe()
    elif cmd == "generate":
        cmd_generate(rest, allow_unmapped=allow_unmapped)
    elif cmd == "explore":
        cmd_explore(rest)
    elif cmd == "run":
        cmd_run(workers, headed, force_workers, cases=cases, slowmo=slowmo, isolated_target=isolated)
    elif cmd == "all":
        cmd_all(workers, headed, force_workers, cases=cases, slowmo=slowmo, isolated_target=isolated,
                allow_unmapped=allow_unmapped)
    elif cmd == "prune":
        cmd_prune(rest)


_CMD_FUNCS = {"probe": cmd_probe, "generate": cmd_generate, "explore": cmd_explore,
              "run": cmd_run, "all": cmd_all, "prune": cmd_prune}


if __name__ == "__main__":
    main()
