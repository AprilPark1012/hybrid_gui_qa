"""hybrid_gui_qa 命令行入口 —— 一键流水线。

典型用法（先起被测应用：python -m demo.app）:
    python -m framework.cli setup            # 0) 第一次跑先执行它：装依赖 + 装浏览器 + 自检
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
import json
import sys
from typing import NoReturn

from framework.tools.common import config
from framework.tools.common.config import ensure_dirs, TARGET_URL, LOG_DIR
from framework.tools.probe.probe import probe_page
from framework.tools.common.browser import launch_opts
from framework.tools.common.limits import safe_workers
from framework.tools.common.retention import (                  # noqa: E402
    DEFAULT_KEEP as KEEP_SNAPSHOTS, prune_snapshots,
    DEFAULT_KEEP_RUNS, DEFAULT_KEEP_RUN_DAYS, DEFAULT_MAX_DELETE,
    auto_prune_runs, prune_runs,
)
from framework.tools.common.text_io import force_stdio, fs_encoding_warning, run_capture, utf8_env


def _write_run_summary(run_dir: Path, run_id: str, exit_code: int) -> None:
    """给 run 目录落 `summary.json` —— 归档保留策略据此判「能否证明成功」。

    缺它 / 坏了 -> 策略一律只**瘦身**不整删（宁可少回收，也不赌一次运行是成功的），
    所以这个文件也承担"失败证据永远留得住"的责任。

    失败数从**用例日志**里数（`X` 是 runner 执行失败时打的、另有 Python traceback 兜底），
    不去解析 pytest 的文本输出：日志是框架自己的产物、口径稳定，pytest 输出格式会随版本变。
    误判方向是安全的（多算失败 -> 更保守）。
    """
    try:
        logs = [p for p in run_dir.rglob("*.log") if p.is_file()]
        failed = 0
        for p in logs:
            try:
                txt = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if "X" in txt or "Traceback (most recent call last)" in txt:
                failed += 1
        tdir = run_dir / "traces"
        traces = sum(p.stat().st_size for p in tdir.glob("*.zip")) if tdir.is_dir() else 0
        data = {
            "run_id": run_id,
            "ended": _now(),
            "exit_code": int(exit_code),
            "case_logs": len(logs),
            "failed_cases": failed,
            "traces_bytes": traces,
            "note": "failed_cases 由用例日志里的 X / Traceback 计数；exit_code = pytest 退出码",
        }
        (run_dir / "summary.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as e:
        print(f"  [run] [!] summary.json 写入失败（归档策略会因此保守：只瘦身不整删）：{e}")


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
    层内元素在输出里带 - 标记，JSON 里带 `"source": "layer"`。
    """
    ensure_dirs()
    # ---- 目标可达性预检（V7.5.1）：先回答「活没活」，别让 Playwright 甩一屏 traceback ----
    # 2026-09-15 实测：demo 没起时 `pg.goto()` 抛 `net::ERR_CONNECTION_REFUSED` + exit 1，
    # 现象像「框架坏了」，其实是一句「demo 没启动」。环境问题要给动作，不是给栈。
    from framework.tools.common.target_probe import reachability
    ok, why = reachability(TARGET_URL)
    if not ok:
        print(f"\n[probe] [NG] 探测没跑：{why}")
        print("[probe]    目标地址可用 TARGET_URL / HYBRID_BASE_URL 覆盖（两者等效）；"
              "demo 起好后重跑 `python -m framework.cli probe`（或 all）")
        raise SystemExit(2)
    from playwright.sync_api import sync_playwright
    import json
    from framework.tools.explore.explorer import _try_collect_modal_items, _merge_items
    from framework.tools.probe.expandable import expand_and_collect
    with sync_playwright() as p:
        b = p.chromium.launch(**launch_opts(headless=True))
        pg = b.new_page()
        pg.goto(TARGET_URL)
        from framework.tools.probe.page_scan import scan_page   # V8.3.7：探测步骤唯一入口
        _sc = scan_page(pg)          # 基础 + 可展开容器（隐藏菜单/下拉）+ 弹窗/弹层 + 合并
        # 标记来源（产物里保留这个字段，供人工核对哪些项来自展开/弹层）：
        #   menu_items / modal_items 与 items 里的项是同一批 dict（_merge_items 只做浅拷贝 + 统一重命名），
        #   所以这里原地打标记，最终落到 output/element_maps/probe_*.json 里。
        for it in _sc.menu_items:
            it["source"] = "menu"
        for it in _sc.modal_items:
            it["source"] = "layer"
        items = _sc.items
        b.close()
    out = config.ELEMENT_MAP_DIR / f"probe_{_now()}.json"
    out.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    prune_snapshots(quiet_if_none=True)          # 归档保留策略（静默：无可清理就不打印）
    n_layer = sum(1 for it in items if it.get("source") == "layer")
    n_menu = sum(1 for it in items if it.get("source") == "menu")
    print(f"[probe] 探测到 {len(items)} 个交互元素"
          f"（其中可展开菜单内 {n_menu} 个 · 弹窗/弹层内 {n_layer} 个）→ {out}")
    for it in items:
        mark = ("-" if it.get("source") == "menu"
                else ("-" if it.get("source") == "layer" else "  "))
        print(f"      {mark} - {it['semantic_name']:<20} [{it['role']:<8}] "
              f"name={it['name']!r} ph={it['placeholder']!r} test_id={it['test_id']!r}")


def _report_unmapped(e) -> NoReturn:
    """映射质量闸触发时的交代：缺什么 / 为什么 / 下一步 —— **绝不落产物**，exit 2。"""
    print(f"\n[generate] [NG] 映射质量闸拦下：{len(e.missing)} 个语义名映射不上 → 拒绝产出任何产物")
    print(f"[generate]    locator 来源：{e.sources}")
    if e.probe_error:
        print(f"[generate]    现场 probe 失败：{e.probe_error}")
        # 先把「活没活」查清楚再给结论（旧版本这里只会猜「多半是目标没起」）
        try:
            from framework.tools.common.target_probe import reachability
            ok, why = reachability(TARGET_URL)
        except Exception as _e:                       # 预检本身失败不该盖住原始错误
            ok, why = True, f"(可达性预检失败: {_e})"
        if not ok:
            print(f"[generate]    真因：{why}")
        else:
            print(f"[generate]    目标可达（{why}）-> 失败不是「没起」，查上面那条 probe 报错"
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
        print(f"[generate]    [!] 其中 {len(conflicts)} 个是**同名歧义**（不是拼写错误）："
              f"该名字在页面上对应 ≥2 个控件，探测已全部唯一化 -> 裸名不存在了。请改用下列候选之一：")
        for base, names in sorted(conflicts.items()):
            print(f"[generate]      · {base!r} → 候选：{'、'.join(names)}")
        print("[generate]    下一步：挑一个候选写进用例的 element（上下文后缀来自该控件所在区域/行），"
              "或行内/子元素改用「锚点 + 容器内相对语义」（anchor + path）；"
              "data-testid 只是可选优化 —— 框架不要求被测系统为测试埋点。")
    print("[generate]    （旧行为：只打一句警告就照样落盘 -> 产出「每步都是 pytest.fail 存根」的垃圾产物；"
          "2026-09-15 的 V7.5 交付事故就是它进包的）")
    print("[generate]    仅调试时可显式加 --allow-unmapped 放行；那样的产物永不允许进交付。")
    raise SystemExit(2)


def _report_data_sets(e) -> NoReturn:
    """数据组与占位符对不上时的交代：哪个用例 / 哪一组 / 差哪几个 —— **绝不落产物**，exit 2。"""
    print(f"\n[generate] [NG] 数据组校验拦下 → 拒绝产出任何产物（exit 2）")
    for line in str(e).splitlines():
        print(f"[generate]    {line}")
    print("[generate]    为什么拦：未解析的 {占位符} 会被**原样填进页面**（看着在跑、其实全错），"
          "写了不生效的组值则等于静默误导。")
    print("[generate]    → 改场景的 data: 或用例文案里的占位符，使两者一一对上；改完重跑 generate。")
    raise SystemExit(2)


# ---------------- AI 产出的「校验 -> 自动重试」闭环（V8.4 · 用户 2026-10-08 选 B）----------
# 为什么需要：AI 编排是**非确定性**的，同一场景逐轮暴露不同缺陷（编登录流程/编密码 ->
#   猜 select 的 value -> 拿 host 当换页证据）。提示词逐条堵能堵住每一条，但堵不完；
#   工程上是承认「一次生成就对」不可靠 —— 用**已有**的校验能力接成有界重试。
_AI_RETRY_MAX_CAP = 5     # 上界：防手滑写成 999 把 token 烧光


def _ai_retry_limit(env: dict | None = None) -> int:
    """读 `HYBRID_AI_RETRY`（默认 2，0 = 关闭重试退回旧行为）。

    [!] 脏值**回落到默认**而不是抛异常：这是人手敲的环境变量，敲错了不该让整条链路崩。
    [!] 必须有上界：一次 `explore` 最多 N 次 LLM 调用 + N 次实跑，写大了会很贵。
    """
    import os
    e = env if env is not None else os.environ
    raw = str(e.get("HYBRID_AI_RETRY", "")).strip()
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return 2
    return max(0, min(n, _AI_RETRY_MAX_CAP))


def _retry_reason_fingerprint(text: str) -> str:
    """把失败原因归一化成**可比对的指纹** —— 供「同因不重试」用。

    [!] 为什么要归一化（2026-10-09 干净环境 E2E 实测教训）：
        原因文本里**必然**带每轮都不同的东西 —— 校验日志路径自带时间戳：
            …/verify/ai_xxx_20261009_073944.log
            …/verify/ai_xxx_20261009_074246.log
        逐字比较 -> **永远判「不同因」** -> 永远重试 -> 白烧一轮 LLM + 一轮实跑。
        实测：三轮失败点其实是同一个（`get_by_text("订单系统")` 幻觉），却跑到第 3 轮才停。

    只抹掉**每轮必然变化**的部分（日志路径、时间戳、耗时、绝对路径前缀），
    **不碰真正的失败描述** —— 否则该重试的也不试了（判据里有反向自证守着这条）。
    """
    import re
    t = str(text or "")
    t = re.sub(r"[^\s]*[/\\][\w./\\-]*\.log\b", "<LOG>", t)      # 校验日志路径
    t = re.sub(r"\b\d{8}[_\-]\d{6}\b", "<TS>", t)                  # 20261009_073944
    t = re.sub(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[\w:.]*", "<TS>", t)
    t = re.sub(r"\b\d+(\.\d+)?\s*(ms|s)\b", "<DUR>", t)            # 5000ms / 1.5s
    t = re.sub(r"/tmp/[\w.-]+", "<TMP>", t)                          # 环境相关的临时目录
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _should_retry_again(*, prev: str, new: str, attempt: int, limit: int) -> bool:
    """还要不要再试一次？三条口径（任意一条不满足就停）。

    1. 次数没用尽（`attempt < limit`）；
    2. 这一轮**确实**产生了失败原因（`new` 非空）；
    3. **原因和上一轮不同** —— 原因没变说明再问也是同一个答案，白烧 token。
       （实测就是这个场景：假绿红线报了「换页证据用 index」，重试若还给同样产出，原因一模一样。）
       [!] 比较用 `_retry_reason_fingerprint` 归一化后的指纹 —— 见该函数的说明。
    """
    if attempt >= limit:
        return False
    if not new:
        return False
    if prev and _retry_reason_fingerprint(prev) == _retry_reason_fingerprint(new):
        return False
    return True


def _case_quality_reasons(e) -> str:
    """把假绿红线的失败原因**文本化** —— 两用：① 打印给人看；② 喂给 AI 做重试修正。

    [!] V8.4 拆出来的原因：以前 `_report_case_quality` 直接 `raise SystemExit(2)`，
        想重试都没机会。现在这里只负责「说清楚错在哪」，由调用方决定 exit 还是带着它重试。
    """
    lines = [f"假绿红线拦下：{len(e.entries)} 条用例、共 {e.total} 处"]
    for cid, errs in e.entries:
        for m in errs:
            lines.append(f"[{cid}] {m}")
    lines.append("真因：换页证据（kind=url 的 expect）若在多个页面的 URL 里都出现，"
                 "换页前后都能通过 -> 用例照样绿，但「确实换页了」这件事根本没被验到。")
    lines.append("改法：(1) 换成只出现在目标页的片段（详情页 -> contract_detail）；"
                 "(2) 目标页没有独有 URL 片段（列表页就是根路径 /）-> 改对该页独有文案做 text 断言；"
                 "(3) 确认用例的页面清单 pages[].url 填全了。")
    return "\n".join(lines)


def _report_case_quality(e) -> NoReturn:
    """假绿红线触发时的交代：哪条用例 / 什么证据没牙 / 怎么改 —— **绝不落产物**，exit 2。"""
    print(f"\n[质量闸] [NG] 假绿红线拦下：{len(e.entries)} 条用例、共 {e.total} 处 → 拒绝产出任何产物")
    for cid, errs in e.entries:
        print(f"[质量闸]   用例 {cid}:")
        for m in errs:
            print(f"[质量闸]     · {m}")
    print("[质量闸]    真因：换页证据（kind=url 的 expect）若在**多个页面**的 URL 里都出现，"
          "换页前后都能通过 -> 用例照样绿，但「确实换页了」这件事根本没被验到。")
    print("[质量闸]    下一步：(1) 换成只出现在目标页的片段（详情页 → contract_detail）；"
          "(2) 目标页没有独有 URL 片段（列表页就是根路径 /）→ 改对该页独有文案做 text 断言；"
          "(3) 顺带确认用例的页面清单 pages[].url 填全了。")
    print("[质量闸]    （旧行为：这条假绿一路跑到报告里，靠人工复核才发现 —— 2026-09-14 就是。）")
    raise SystemExit(2)


def cmd_generate(rest: list[str] = None, allow_unmapped: bool = False):
    """读 cases/*.json → 生成 scripts/（playwright 脚本 + scripts/datasets 抽离数据）。

    定位来源（P1 起）：默认优先读【probe 产出的 element.map 快照】；缺失才现场补探测。
      --element-map <path>  指定用某个 element_map_*.json（explore 产物）
      --live-probe          强制现场重新 probe（忽略快照，最准但最慢）
      --allow-unmapped      【调试用】放行「有语义名映射不上」的情况，仍然产出产物（含 pytest.fail 存根）；
                            默认**拒绝落盘并 exit 2**（防止产出/交付一份全是 fail 存根的假脚本）
      --changed             【默认】只重写**变了**的用例脚本（三指纹：用例 / 场景 / 探测结果）——
                            P20 起的增量生成：一个用例一个文件，没变的不动字节
      --force               全量重写所有用例脚本（发版/核对用；不看指纹）
      --only <id[,id...]>   只重生成指定的用例（其余一动不动，连 index 条目都保留）

    无法获得定位时**不产出产物**：宁可生成阶段就红，也不给出一份「看着合法、跑起来 50 条失败」的东西。
    """
    ensure_dirs()
    from pathlib import Path as _P
    from framework.tools.generate.case_builder import CaseQualityError
    from framework.tools.generate.generator import (DataSetsError, DanglingDatasetError,
                                                   UnmappedElementsError, generate_scripts)
    rest = rest or []
    map_path = None
    if "--element-map" in rest:
        i = rest.index("--element-map")
        if i + 1 < len(rest):
            map_path = _P(rest[i + 1])
    only_ids: list[str] = []
    if "--only" in rest:
        _i = rest.index("--only")
        if _i + 1 < len(rest):
            only_ids = [x.strip() for x in rest[_i + 1].split(",") if x.strip()]
        if not only_ids:
            print("[NG] --only 后面要跟用例 id（逗号分隔，可多个）", file=sys.stderr)
            return 2
    try:
        res = generate_scripts(element_map_path=map_path, live_probe="--live-probe" in rest,
                               allow_unmapped=allow_unmapped or ("--allow-unmapped" in rest),
                               changed_only="--force" not in rest,
                               only=only_ids or None)
    except CaseQualityError as e:
        _report_case_quality(e)
    except DanglingDatasetError as e:
        print(f"[NG] {e}", file=sys.stderr)
        print("   -> 产物已拒绝落盘（宁可报错，也不产出跑不通的产物）；重跑一次 generate 即可自愈。",
              file=sys.stderr)
        return 2
    except UnmappedElementsError as e:
        _report_unmapped(e)
    except DataSetsError as e:
        _report_data_sets(e)
    print(f"[generate] 读 cases/ → 生成 {res['count']} 个用例到 scripts/:")
    print(f"          tests: {res['tests']}")
    print(f"          datasets: {len(res['datasets'])} 个（脚本数据分离）")
    for d in res["datasets"]:
        print(f"            - {d}")
    print(f"          locator 来源: {res.get('locator_sources', '(未统计)')}")
    # 0 个用例 = 什么都没生成（2026-09-13 修）：以前照打一行"生成 0 个用例"就 exit 0，
    # 脚本/CI 会把空用例集当成功 -> 明确失败并给下一步动作。
    if res["count"] == 0:
        print("[generate] [NG] cases/ 里一个用例都没有 -> 没有生成任何可执行测试。"
              "推荐先跑 explore --ai --scenario-file <场景.yml> 让 AI 按场景生成用例（主推路径）；"
              "也可手写 cases/*.json（仅用于调试/回归辅助）")
        raise SystemExit(2)


def _arg_value(rest: list[str], flag: str) -> str | None:
    """取 `--flag <value>` 的值（下一个 token 以 -- 开头视为缺值 → None）。

    也认 `--flag=value`（2026-09-18）：`_validate_args` 本来就放行等号写法，
    但本函数以前只认分离写法 -> `--llm-record=/tmp/x` 这种会**静默退回默认目录**
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
                 pages: list[dict] | None = None, cassette=None, cassette_strict: bool = False,
                 auth: dict | None = None, retry_feedback: str = "",
                 probe_pre: list | None = None):
    """跑一次 AI 语义识别（+ 可选落 cases/）。返回 (emap, case_path | None, warns, qerr)。

    qerr（V8.4）：假绿红线拦下时的失败原因**文本**，通过= None。
      以前这里直接 exit 2；现在交给调用方 —— 它能决定「汇报退出」还是「带原因让 AI 重生成」。

    pages（P3 跨页）：[{"name","url","page"}, ...]；给了 ≥2 页就按跨页模式探测与规划，
    `url` 此时应为第一页地址（explore 的 goto 起点）。
    """
    from framework.tools.explore.explorer import ai_explore
    prefix = f"【{label}】" if label else ""
    # 刻意不在外面探测：ai_explore 内部会探测（且会打开弹窗补表单控件）。
    # 2026-09-11 修复：旧写法先探一次再交给 ai_explore -> 连开两个 Chromium，内存吃紧时
    # 第二次探测失败，叠加 ai_explore 里的静默兜底 -> AI 只能看到基础控件（弹窗字段全丢）。
    emap = ai_explore(scenario_text, [], url, allow_mock_fallback=mock_fallback,
                      page_bg=page_bg, guard=guard_text, pages=pages, llm_cassette=cassette,
                      cassette_strict=cassette_strict, auth=auth, retry_feedback=retry_feedback,
                      probe_pre=probe_pre)
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
    qerr = None          # 假绿红线原因（V8.4）：非 None 表示这次产出不合格
    if cassette is not None:
        # 溯源：把「这条用例是录像回放出来的、还是当场问的 AI」写进用例文件 ——
        # 复核的人不用回忆当时敲了什么命令（回放 ≠ 实时 AI，必须看得见）。
        extra = {**(extra or {}), "llm_source": cassette.source_tag()}
    if to_cases and not mock_fallback:
        from framework.tools.generate.case_builder import CaseQualityError as _CaseQE
        from framework.tools.generate.case_builder import elementmap_to_cases_file
        try:
            cpath, warns = elementmap_to_cases_file(emap, case_id=case_id, extra=extra, guard=guard_spec)
        except _CaseQE as e:
            # 假绿红线（如换页证据只写 localhost）-> 拒绝落盘，绝不产出「看着绿、其实没验」的用例
            qerr = _case_quality_reasons(e)      # 不再直接 exit：调用方可能带它重试（V8.4）
        if qerr is None:
            print(f"          → 用例: {cpath}  （AI 用例，ai_ 前缀）")
            for w in warns:
                print(f"          [!] 质量警告: {w}")
    return emap, cpath, warns, qerr


def cmd_explore(rest: list[str] = None):
    """【AI 语义识别】自然语言场景（内联 或 scenario 文件）+ probe 清单 + DOM 上下文
    → ElementMap（默认同步落 cases/ai_*.json）。

    需 .env 配 DeepSeek key（config.llm_from_env 走 ChatDeepSeek）。

    三种入口（**互斥**，只给一个；都不给用内置默认场景）：
      --scenario "…"                     内联自然语言（原样保留）
      --scenario-file scenarios/x.yml    单个场景文件（见 framework/tools/generate/scenario.py）
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
                                -> 结构键命中会**大声告警**，请核对后再用
      --llm-cassette-strict     回放只认严格键（不要结构键兜底）
      · 两者互斥；都不给 = 实时调用（与以前逐字一致，行为不变）
      · 无外网的机器怎么用：先在**有外网**的机器上 --llm-record 录一次 → 把整个录像目录
        拷过去 → 那台机器用 --llm-cassette，就能跑完整 explore（含默认 --verify 试跑）
    """
    ensure_dirs()
    rest = rest or []
    if "--ai" not in rest:
        print("[explore] [NG] 缺 --ai：explore 只做真 AI 语义识别（不提供隐式降级 —— 静默兜底=造假）。")
        print("          要跑确定性链路请用： python -m framework.cli probe → generate → run")
        raise SystemExit(2)

    mock_fallback = "--mock-fallback" in rest
    to_cases = "--no-cases" not in rest
    do_verify = "--no-verify" not in rest

    # ---------- LLM 录像：录制 / 回放（2026-09-18）----------
    # **只在显式给参数时启用** —— 默认一个字节都不变（实时调用），绝不自动切换模式。
    from framework.tools.explore.llm_cassette import MODE_RECORD, MODE_REPLAY, Cassette, CassetteError
    has_rec = "--llm-record" in rest or any(a.startswith("--llm-record=") for a in rest)
    has_rep = "--llm-cassette" in rest or any(a.startswith("--llm-cassette=") for a in rest)
    if has_rec and has_rep:
        print("[explore] [NG] --llm-record 与 --llm-cassette 互斥：一次只能「录」或「放」"
              "（要边录边放请分两次跑）")
        raise SystemExit(2)
    if (has_rec or has_rep) and mock_fallback:
        print("[explore] [NG] --mock-fallback 与录像模式互斥：mock 是确定性假产物、录像里存的是"
              "真 AI 回答 —— 混用没有意义")
        raise SystemExit(2)
    cassette = None
    try:
        if has_rec:
            cassette = Cassette(MODE_RECORD, _arg_value(rest, "--llm-record"))
        elif has_rep:
            cassette = Cassette(MODE_REPLAY, _arg_value(rest, "--llm-cassette"))
    except CassetteError as e:
        print(f"[explore] [NG] {e}")
        raise SystemExit(2) from None
    cassette_strict = "--llm-cassette-strict" in rest
    if cassette_strict and not has_rep:
        print("[explore] [NG] --llm-cassette-strict 只与 --llm-cassette 搭配使用"
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
        print(f"[explore] [NG] 参数互斥：{'、'.join(g[0] for g in given)} 只能给一个（不猜你的意图）")
        raise SystemExit(2)

    from framework.tools.generate.case_builder import make_case_id_from_scenario_id

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
        from framework.tools.generate.scenario import ScenarioError, discover_scenarios
        tags = _arg_values(rest, "--tag")
        lim = _arg_value(rest, "--limit")
        try:
            scs = discover_scenarios(Path(sdir), tags=tags, limit=int(lim) if lim else None)
        except ScenarioError as e:
            print(f"[explore] [NG] {e}")
            raise SystemExit(2) from None
        print(f"[explore] 场景目录: {sdir} → 命中 {len(scs)} 个场景"
              + (f"（tag={','.join(tags)}）" if tags else ""))
        for sc in scs:
            for w in sc.warnings:
                print(f"  [!] [{sc.id}] {w}")
            # P22 批 5：把场景的**登录前置声明**带进 job —— 不带的话跨页探测每页都只拿到登录页控件
        #（实测 2026-09-30：7 页全是 7 个控件 -> AI 的 31 个步骤 element 全为空）
        jobs.append({**_job_from_scenario(sc, sc.scenario), "auth": sc.auth_spec(),
                 "probe_pre": list(sc.probe_pre or [])})
    elif sfile:
        from pathlib import Path
        from framework.tools.generate.scenario import ScenarioError, load_scenario_file
        try:
            sc = load_scenario_file(Path(sfile))
        except ScenarioError as e:
            print(f"[explore] [NG] {e}")
            raise SystemExit(2) from None
        for w in sc.warnings:
            print(f"  [!] [{sc.id}] {w}")
        print(f"[explore] 场景文件: {sfile}（id={sc.id}"
              + (f", tags={','.join(sc.tags)}" if sc.tags else "")
              + (f", priority={sc.priority}" if sc.priority else "") + "）")
        # P22 批 5：把场景的**登录前置声明**带进 job —— 不带的话跨页探测每页都只拿到登录页控件
        #（实测 2026-09-30：7 页全是 7 个控件 -> AI 的 31 个步骤 element 全为空）
        jobs.append({**_job_from_scenario(sc, sc.scenario), "auth": sc.auth_spec(),
                 "probe_pre": list(sc.probe_pre or [])})
    else:
        jobs.append(dict(
            label="", text=inline or "在合同列表页面的搜索框输入'合同1'，然后点击搜索按钮查看结果。",
            url=TARGET_URL, page_bg="", guard_text="", guard_spec=None, case_id=None, extra=None,
        ))

    # ---------- 逐条跑 ----------
    from framework.tools.explore.explorer import AiExploreError
    done: list[tuple[str, str]] = []
    last_emap = None
    # ---------- V8.4：校验不合格 -> 带原因让 AI 重生成（有界）----------
    retry_limit = _ai_retry_limit()
    replay = bool(cassette is not None and getattr(cassette, "is_replay", False))
    if retry_limit:
        print(f"[explore] 产出校验不合格时最多重试 {retry_limit} 次"
              f"（HYBRID_AI_RETRY=0 可关闭）")
    # ---------- V8.4：L1 实跑校验失败 -> 带原因重跑整轮（有界）----------
    # 为什么 L1 只能在外层：实跑要先 generate（需要整轮产物齐了）才能跑，
    # 所以「生成所有 job -> verify -> 不合格就整轮重生成」是唯一顺序。
    l1_feedback = ""        # 实跑失败原因 -> 带给下一轮生成
    l1_attempt = 0
    while True:
        done = []           # 每轮重新收集（重跑时旧产物不该混进来）
        for idx, job in enumerate(jobs, 1):
            if len(jobs) > 1:
                print(f"\n[explore] === 场景 {idx}/{len(jobs)}：{job['label']} ===")
            emap = cpath = None
            qerr = None
            feedback = ""          # 本轮要带给 AI 的「上一轮失败原因」
            prev_reason = ""
            attempt = 0
            while True:
                try:
                    emap, cpath, _, qerr = _explore_one(
                        job["text"], job["url"], label=job["label"], page_bg=job["page_bg"],
                        guard_text=job["guard_text"], guard_spec=job["guard_spec"],
                        case_id=job["case_id"], extra=job["extra"],
                        to_cases=to_cases, mock_fallback=mock_fallback, pages=job.get("pages"),
                        cassette=cassette, cassette_strict=cassette_strict, auth=job.get("auth"),
                        retry_feedback=feedback, probe_pre=job.get("probe_pre"))
                except AiExploreError as e:
                    print(f"[explore] [NG] 【{job['label'] or '内联'}】{e}")
                    raise SystemExit(2) from None
                if qerr is None:
                    break                       # 合格 -> 收工
                print(f"[explore] [!] 第 {attempt + 1} 次产出**校验不合格**")
                if replay:
                    # 回放的是同一份录像，转 N 圈还是同一个坏产出 -> 不浪费轮次
                    print("[explore] [!] 录像回放模式：重试无意义（回放的是同一份录像）-> 直接汇报")
                    break
                if not _should_retry_again(prev=prev_reason, new=qerr,
                                           attempt=attempt, limit=retry_limit):
                    if prev_reason and prev_reason.strip() == qerr.strip():
                        print("[explore] [!] 失败原因与上一轮**相同** -> 停止重试"
                              "（再问也是同一个答案，不白烧 token）")
                    break
                prev_reason = qerr
                feedback = qerr
                attempt += 1
                print(f"[explore] -> 带着失败原因让 AI 重新生成"
                      f"（第 {attempt + 1}/{retry_limit + 1} 次尝试）")
            if qerr is not None:
                print(f"\n[explore] [NG] 重试用尽仍不合格（已尝试 {attempt + 1} 次 · "
                      f"上限 HYBRID_AI_RETRY={retry_limit}）→ 拒绝产出任何产物")
                print("[explore]    下面是框架校验给出的**具体失败原因**：")
                print(qerr)
                raise SystemExit(2)
            last_emap = emap
            if cpath:
                done.append((job["label"], cpath.stem))
            if mock_fallback:
                print("          [!] mock 兜底产物 → 按约定【不落 cases/】（避免假 AI 用例污染用例库）")

        # ---- L1：实跑校验（便宜的先跑已在 _explore_one 内做完 L0）----
        if not (done and do_verify):
            break
        ok, reasons = _verify_cases_detailed(done)
        if ok is not False:
            break                       # 全通过（或环境问题没跑成，不判死刑）
        if replay:
            print("[explore] [!] 录像回放模式：重试无意义（回放的是同一份录像）-> 直接汇报")
            raise SystemExit(3)
        if not _should_retry_again(prev=l1_feedback, new=reasons,
                                   attempt=l1_attempt, limit=retry_limit):
            print("[explore] [NG] 有 AI 用例【实测未通过】-> 不可当可用用例"
                  "（请修正场景/断言后重来；坏用例仍在 cases/ 里，确认后可删）")
            if reasons:
                print("[explore]    实跑给出的具体失败原因：")
                print(reasons)
            raise SystemExit(3)
        l1_attempt += 1
        l1_feedback = reasons
        print(f"[explore] -> 带着**实跑失败原因**让 AI 重新生成"
              f"（第 {l1_attempt + 1}/{retry_limit + 1} 轮）")

    if done and not do_verify:
        print("          [info] 按 --no-verify 跳过试跑校验（这些用例未经实测验证）")
    return last_emap


def _verify_cases(entries: list[tuple[str, str]]) -> bool | None:
    """新用例试跑校验（薄封装，保留原有调用形状）。"""
    ok, _ = _verify_cases_detailed(entries)
    return ok


def _verify_cases_detailed(entries: list[tuple[str, str]]) -> tuple[bool | None, str]:
    """新用例试跑校验：generate 一次 + 逐条 pytest 单跑（explore 的「交付即验证」闸门）。

    entries: [(label, case_name)] —— label 用于批量时标明是哪条场景。
    返回 `(ok, reasons)`：
      · `ok` = True 全部通过 / False 有失败 / None 校验没能执行（环境问题，不判死刑）；
      · `reasons`（V8.4）= **给 AI 看的失败原因文本**（通过时为空串）。
        为什么要它：重试若只说「失败了」AI 无从改起 —— 必须带上**具体哪条断言/哪一步炸了**。
    """
    from framework.tools.common.config import SCRIPTS_DIR

    reasons: list[str] = []
    if not entries:
        return None, ""
    # V8.4.2：**先看 explore 侧收集到的产出缺陷**（写死行数据 / 严重误选控件）。
    #   之前这两个清单只收集没人读 -> 等于白收集：这类用例**注定换个环境就崩或选错控件**，
    #   试跑它纯属浪费（而且跑过了也只证明"在这批数据上侥幸能过"）。
    #   处置：直接带原因返回 False，让重试闭环让 AI 重生成（不跑 generate / 不试跑）。
    try:
        from framework.tools.explore import explorer as _exp
        _prod: list[str] = []
        if getattr(_exp, "_HARDCODED_NOTES", None):
            _prod.append("产出里把**表格行数据的具体值写死**了"
                         "（换数据/换排序就会崩，必须改成行锚 / 首行断言 / {占位符}）：")
            _prod += ["  · " + x for x in _exp._HARDCODED_NOTES[:5]]
        if getattr(_exp, "SEMANTIC_MISMATCH_NOTES", None):
            _prod.append("产出里选中的控件与步骤描述**几乎无关**"
                         "（语义校准判为严重误选，实跑必然报「元素语义未找到」）：")
            _prod += ["  · " + x for x in _exp.SEMANTIC_MISMATCH_NOTES[:5]]
        # V8.4.3+：场景明写的**必填项** AI 漏编排 -> 保存会被前端校验拦下（实跑才炸）
        if getattr(_exp, "_REQUIRED_COVERAGE_NOTES", None):
            _prod.append("产出里**漏了场景要求填的必填项**"
                         "（页面标 * 的必填控件；不填就保存不了，后面的断言必然失败）：")
            _prod += ["  · " + x for x in _exp._REQUIRED_COVERAGE_NOTES[:5]]
        if _prod:
            print("  [NG] 校验不合格：AI 产出有**结构性缺陷** -> 不试跑，直接带原因重生成")
            for line in _prod:
                print(f"     {line[:170]}")
            print("  要求：① 行数据一律用声明式定位（row_text / expect_first_row / cell_field），"
                  "字面编号只允许出现在场景里逐字给出的情形；")
            print("        ② 每个步骤选的控件必须与步骤描述语义相符（不许拿业务数据当控件名）；")
            print("        ③ 场景里**逐字列出的每一个要填的字段**（尤其页面标 * 的必填项）都要有对应步骤，"
                  "一项都不许漏 —— 漏一项保存就会被前端拦下，后面的断言全部白给。")
            return False, "\n".join(_prod)
    except Exception as _e:      # 收集/读取出问题不该毁掉校验本身
        print(f"  [!] 产出缺陷清单读取失败（不影响校验）：{type(_e).__name__}: {_e}")

    gen_dir = SCRIPTS_DIR / "generated"
    print(f"[explore] --verify：先 generate 一次，再逐条试跑 {len(entries)} 条新用例…")
    # [!] 必须用 run_capture（显式 UTF-8 解码）：以前是裸 `subprocess.run(..., text=True)`，
    # 父进程按系统默认编码（中文 Windows = cp936/gbk）解码子进程的 UTF-8 中文输出 ->
    # `UnicodeDecodeError: 'gbk' codec can't decode byte 0xbb in position 13`（2026-09-13 AprilPark1012实测）。
    gen = run_capture([sys.executable, "-m", "framework.cli", "generate"], cwd=str(config.BASE))
    if gen.returncode != 0:
        tail = ((gen.stdout or "") + (gen.stderr or ""))[-2000:]
        # V8.4：**必须区分两类 generate 失败** —— 以前一律 `return None, ""`（当「未执行」），
        # 于是「AI 产出不完整」被当成「环境问题」溜过去，`explore` 还 exit=0（假绿）。
        # 实测事故：AI 有 4 步**只写 desc 没绑 element** -> 映射质量闸正确拦下 ->
        # 但 explore 报「校验未执行」-> exit=0，而 cases/ 里躺着一条根本生成不了脚本的产出。
        #   · 产出侧问题（映射不上 / 没给 element）-> **AI 能改** -> return False（触发重试）；
        #   · 环境侧问题（目标没起 / 探测不可用）-> AI 改不了 -> return None（重试纯属浪费）。
        _ai_fault = any(k in tail for k in (
            "映射不上", "映射质量闸", "没有 element", "allow-unmapped",
        ))
        if _ai_fault:
            print("  [NG] 校验不合格：AI 产出不完整 -> generate 拒绝产出脚本"
                  "（映射质量闸拦下，不是环境问题；带原因让 AI 重新生成）")
            reasons.append("AI 产出的用例没能生成脚本（generate 被映射质量闸拦下）：")
            for line in tail.splitlines():
                t = line.strip()
                if t.startswith("[generate]") or "没有 element" in t or "映射不上" in t:
                    print(f"     {t[:160]}")
                    break
            for line in tail.splitlines():
                t = line.strip()
                if "缺失项" in t or "没有 element" in t:
                    reasons.append("  " + t[:400])
            reasons.append("  要求：**每个 click/fill/select/check 步骤都必须给出 element**"
                           "（必须是探测清单里真实存在的语义名，不许自造，也不许留空）。")
            return False, "\n".join(reasons)
        print("  [!] 校验未执行：generate 失败（目标没起 / 探测不可用这类环境问题）"
              "→ scripts/ **未更新**，新用例【未经实测验证】，别把它当成已验证")
        print("  " + tail.replace("\n", "\n  "))
        return None, ""

    vdir = config.OUTPUT_DIR / "verify"
    vdir.mkdir(parents=True, exist_ok=True)
    all_ok = True
    for label, name in entries:
        # P20：一个用例一个脚本 -> 用 index.json（case_id → script_path）拿 node id
        try:
            _idx = json.loads((gen_dir / "index.json").read_text(encoding="utf-8"))
            _script = config.BASE / _idx[name]["script_path"]
        except Exception as _e:
            print(f"      [!] 取不到 {name} 的脚本路径（index.json 里没有？）：{_e}")
            continue
        node = f"{_script}::test_{name}"
        r = run_capture([sys.executable, "-m", "pytest", node, "-v", "-s"],
                        cwd=str(config.BASE))
        text = (r.stdout or "") + (r.stderr or "")
        log = vdir / f"{name}_{_now()}.log"
        log.write_text(text, encoding="utf-8")
        tag = f"【{label}】" if label else ""
        if r.returncode == 0:
            print(f"  [OK] {tag}校验通过：该用例实测 PASSED（校验日志 {log}）")
        else:
            all_ok = False
            print(f"  [NG] {tag}校验失败：该用例实测 FAILED（断言是猜的？页面结构变了？）校验日志 {log}")
            reasons.append(f"用例 {name} 实跑 FAILED（校验日志 {log}）：")
            for line in text.splitlines():
                s = line.strip()
                if s.startswith("E ") or "TimeoutError" in s or "not found" in s:
                    print(f"     {s[:160]}")
                    if len(reasons) < 40:                 # 有界：别把整份日志塞进提示词
                        reasons.append("  " + s[:200])
    return all_ok, "\n".join(reasons)


def _verify_case(case_name: str) -> bool | None:
    """单条校验（薄封装，保留原有调用形状）。"""
    return _verify_cases([("", case_name)])


def _int_flag(rest: list[str], name: str, default: int) -> int:
    """取 `--name v` / `--name=v` 的**整数**取值；没给返回默认值，取值不合法按参数错误处理（exit 2）。

    [!] 名字故意不叫 `_arg_value`：本文件早有一个 `_arg_value(rest, flag)`（返回字符串或 None，
    给 llm-cassette / scenario 用）。同名会**遮蔽**它 -> 那些 2 参数调用全部 TypeError（实测踩到，
    被一类 `test_arg_value_supports_equals_form` 抓出来）。
    """
    for i, a in enumerate(rest):
        if a == name and i + 1 < len(rest):
            raw = rest[i + 1]
        elif a.startswith(name + "="):
            raw = a.split("=", 1)[1]
        else:
            continue
        try:
            return cast(raw)
        except ValueError:
            _fail(f"参数 {name} 取值不合法：{raw}", f"用法：{name} <整数>")
    return default


def cmd_prune(rest: list[str] = None):
    """归档保留策略（两类目录）：

      (1) `output/element_maps/`：element_map_*.json / probe_*.json 各留最近 `--keep` 个；
      (2) `log/<run_id>/` 与 `output/verify/`（`--runs` / `--all` 才生效）：
         保留最近 `--keep-runs` 个 ∪ `--keep-days` 天（默认 30 个 / 7 天）；超龄的 run 里，
         **能证明成功**（有 summary.json 且全绿）的才整删，历史（无 summary）/失败 ->
         只**瘦身**（删掉 traces 录像，保留 .log + report.html + summary.json）。

    用法: python -m framework.cli prune [--keep 20] [--dry-run]
          python -m framework.cli prune --all [--keep-runs 30] [--keep-days 7] [--max-delete 20] [--dry-run]
    默认值可用环境变量覆盖：HYBRID_KEEP_SNAPSHOTS / HYBRID_KEEP_RUNS / HYBRID_KEEP_RUN_DAYS /
    HYBRID_MAX_DELETE_PER_PRUNE / HYBRID_MAX_FREE_MB；`--dry-run` 只预演不删。
    [!] 不带 `--runs/--all` 时行为同旧版（**只清快照，不碰 log/**）。
    """
    ensure_dirs()
    rest = rest or []
    keep = _int_flag(rest, "--keep", KEEP_SNAPSHOTS)
    keep_runs = _int_flag(rest, "--keep-runs", DEFAULT_KEEP_RUNS)
    keep_days = _int_flag(rest, "--keep-days", DEFAULT_KEEP_RUN_DAYS)
    max_delete = _int_flag(rest, "--max-delete", DEFAULT_MAX_DELETE)
    dry = "--dry-run" in rest
    do_runs = ("--all" in rest) or ("--runs" in rest)
    do_snaps = ("--all" in rest) or not do_runs          # 默认沿用旧行为：只清快照
    print(f"[prune] 快照保留策略：每类保留最近 {keep} 个（{'dry-run 预演，不删' if dry else '实际清理'}）")
    removed = prune_snapshots(keep=keep, dry_run=dry, quiet_if_none=False)
    print(f"[prune] {'将清理' if dry else '已清理'} {len(removed)} 个快照文件")
    if dry and removed:
        for f in removed[:5]:
            print(f"          - {f.name}")
        if len(removed) > 5:
            print(f"          … 其余 {len(removed) - 5} 个")

    if do_runs:
        print(f"[prune] run/verify 保留策略：最近 {keep_runs} 个 ∪ {keep_days} 天 · "
              f"单次上限 {max_delete} 个目录（{'dry-run 预演，不删' if dry else '实际清理'}）")
        res = prune_runs(keep=keep_runs, keep_days=keep_days, max_delete=max_delete,
                         dry_run=dry, quiet_if_none=False)
        print(f"[prune] {'将处理' if dry else '已处理'}：整删 {len(res['removed_dirs'])} 个目录 · "
              f"瘦身 {len(res['slimmed_dirs'])} 个目录（删录像 {len(res['slim_files'])} 个文件）· "
              f"清理 verify 日志 {len(res['verify_files'])} 个 · "
              f"释放 {res['freed_bytes'] / 1024 / 1024:.1f} MB"
              + ("（已达单次上限，余量留到下次）" if res["capped"] else "")
              + f"；显式保护跳过 {len(res['protected_skipped'])} 个 · "
                f"命名不认识跳过 {res['unknown_skipped']} 个")
        if dry and res["removed_dirs"]:
            for name in res["removed_dirs"][:5]:
                print(f"          - 整删 {name}")
            if len(res["removed_dirs"]) > 5:
                print(f"          … 其余 {len(res['removed_dirs']) - 5} 个")


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
      [!] 调试模式刻意**不带 `-n`**：`pytest -n 1` 也会设 `PYTEST_XDIST_WORKER=gw0`，而 conftest 判定
      "在 worker 里 -> 无头" -> 旧版 `--headed` 因此是空操作（2026-09-11 修复）。

    默认（不写 `--debug`）＝ 无头并发跑，按内存预检裁并发（防 OOM 杀 Hermes 网关），不录像不截图。
    cases=[...]（`--case <case_id>`，可重复）：只跑指定用例（透传 pytest `-k`）；不传=整包跑。
    产物落在 log/<run_id>/（run-id 隔离 -> 天然"本次运行干净"）。
    """
    ensure_dirs()
    import os
    import subprocess
    from framework.tools.common.config import SCRIPTS_DIR
    # P20：产物改成 scripts/generated/<场景>/<用例>.py（一个用例一个文件）-> 直接跑目录
    tests = SCRIPTS_DIR / "generated"
    if not (tests / "index.json").exists():
        print("[run] [NG] scripts/generated/index.json 不存在 → 没有可跑的东西（先跑 generate）")
        print("      （2026-09-13 修：这里以前只提示一句就 return，**exit 0** —— "
              "CI/脚本调用方会把\"什么都没跑\"误判成成功）")
        raise SystemExit(2)

    # ---- 资源预检：按可用内存裁定并发（本次 OOM 事故的根治点）----
    n, why = safe_workers(workers)
    print(f"[run] 资源预检: {why}")
    if workers and n < workers:
        if force_workers:
            n = workers
            print(f"[run] [!] --force-workers 生效：无视预检，强行用 {n} 并发"
                  f"（内存不足时有 OOM 风险，可能连带影响 Hermes 网关）")
        else:
            print(f"[run] [!] 请求并发 {workers} 超出安全值 → 已降级为 {n}"
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
            from framework.tools.common.target_probe import probe_partitioned
            capable, why_p = probe_partitioned()
            if capable:
                print(f"[run] 并发隔离：{why_p} → 保持 {n} worker（框架会给每个 worker 注入独立数据分区）")
            else:
                print(f"[run] [!] 并发隔离：{why_p}")
                print(f"[run] [!] 目标未声明可并发隔离 → 并发由 {n} 保守降级为 1")
                print(f"[run]    多 worker 共享一份状态时，精确计数断言会随机红、且失败原因指向错误的地方；"
                      f"要并发请让目标支持按 worker 分区（/api/health 返回 partitioned=true），"
                      f"或确知已隔离时加 --isolated-target")

    # ---- 调试开关（--debug / --headed）：开了就"看得见"（有屏幕开窗；没屏幕录制）----
    if debug:
        if n != 1:
            print(f"[run] [bug] 调试模式 → 并发由 {n} 强制降为 1（单浏览器顺序跑，才看得清）")
        n = 1
        os.environ["HYBRID_DEBUG"] = "1"
        if _has_display():
            os.environ["HYBRID_HEADED"] = "1"
            print("[run] [bug] 调试模式：有图形显示 → 弹出 Chromium 窗口，看它一步步执行到用例结束")
        else:
            os.environ["HYBRID_VIDEO"] = "1"
            os.environ["HYBRID_SHOTS"] = "1"
            print("[run] [bug] 调试模式：本机没有图形显示（DISPLAY/WAYLAND_DISPLAY 未设置）")
            print("[run]       → 不改需求，这次执行【录下来给你看】：视频 + 每一步截图 + trace")
            print("[run]       → 换到带屏幕的机器（如 Windows 桌面）跑同一个开关，就直接弹出浏览器窗口")
        if not slowmo:
            slowmo = 200
            print("[run] [bug] 调试模式默认放慢 200ms/动作（--slowmo N 覆盖，0 = 不放慢）")

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
        # -> conftest 判定"在 worker 里 -> 无头"，调试开关就白传了（旧版实测 bug）
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
    # conftest 里的 v / [!] 会 UnicodeEncodeError，跑到一半崩）；父进程已 force_stdio()
    # 把 Windows 控制台代码页设成 65001，所以中文在控制台照样显示正常。
    r = subprocess.run(cmd, cwd=str(config.BASE), env=utf8_env())
    print(f"[run] pytest 退出码 {r.returncode}")
    if debug:
        vids = sorted((run_dir / "videos").glob("*.webm")) if (run_dir / "videos").exists() else []
        shots = sorted((run_dir / "shots").glob("*/*.png")) if (run_dir / "shots").exists() else []
        traces = sorted((run_dir / "traces").glob("*.zip")) if (run_dir / "traces").exists() else []
        print(f"[run] [bug] 调试产物：视频 {len(vids)} 个 / 逐步截图 {len(shots)} 张 / trace {len(traces)} 个")
        for p in (vids[:1] + shots[:3]):
            print(f"        - {p}")
        if len(shots) > 3:
            print(f"        … 其余截图在 {run_dir / 'shots'}（按 01/02/03… 就是执行顺序）")
        if traces:
            print(f"        trace 交互回放：playwright show-trace {traces[0]}")
    if r.returncode == 5:
        print("[run] [info] 退出码 5 = 没有匹配到任何用例（--case 的名字对不上？已生成的用例见 "
              "scripts/test_cases.py 里的 def test_* ）")
    # 退出码必须**如实传递**（2026-09-13 修）：以前 cmd_run 跑完就返回 -> cli 永远 exit 0，
    # 用例失败(1)/没匹配到用例(5)/collect error(2) 全被吞掉 -> CI 与脚本调用方一律误判成功。
    # ---- 收尾（**必须在退出码判断之前**）：summary.json + 归档保留 ----
    # 为什么要在 raise 之前：失败 run 也要留下 summary.json —— 归档策略据此判「能否证明成功」
    # （失败/无 summary 一律只瘦身不整删），而且"最近一次全红"要靠它才保得住。
    _write_run_summary(run_dir, run_id, r.returncode)
    auto_prune_runs(quiet_if_none=True)

    if r.returncode != 0:
        print(f"[run] [NG] 以 pytest 退出码 {r.returncode} 结束（1=有用例失败 / 5=没匹配到用例 / "
              f"其它=执行环境问题）→ cli 同样返回该退出码，别把它当成功")
        raise SystemExit(r.returncode)


def cmd_all(workers: int | None = None, debug: bool = False, force_workers: bool = False,
            cases: list[str] | None = None, slowmo: int | None = None,
            isolated_target: bool = False, allow_unmapped: bool = False):
    """probe → generate → run 一条龙。

    [!] 需要被测目标在跑（`python -m demo.app`）：任一步拿不到目标都会**在生成期就红**，
    不会产出「全是 pytest.fail 存根」的假脚本（--allow-unmapped 是调试逃生口，别用于交付）。
    """
    cmd_probe()
    cmd_generate(allow_unmapped=allow_unmapped)
    cmd_run(workers, debug, force_workers, cases=cases, slowmo=slowmo,
            isolated_target=isolated_target)


# ============================ CLI 参数契约 ============================
# 原则（2026-09-13 定）：**未知 / 错位参数一律报错 + 非 0 退出，绝不静默忽略**。
# 起因（实测三个真问题）：
#   (1) `prune --dry-run --workres 1`（--workers 拼错）→ 静默按默认跑完、exit 0；
#   (2) 未知子命令 `frobnicate` → 只打 __doc__、**exit 0** -> 脚本调用方误判成功；
#   (3) `_arg_values` 曾重复定义（后者静默覆盖前者）。
# 值含义: "value" = 必须带值； "opt" = 可带可不带值（如 --debug true|false）； None = 纯开关
FLAG_SPECS: dict[str, str | None] = {
    "--workers": "value", "--debug": "opt", "--headed": None, "--force-workers": None,
    "--isolated-target": None,
    "--case": "value", "--slowmo": "value",
    "--element-map": "value", "--live-probe": None,
    "--allow-unmapped": None,
    "--only": "value", "--changed": None, "--force": None,
    "--ai": None, "--mock-fallback": None, "--no-cases": None,
    "--verify": None, "--no-verify": None,
    "--scenario": "value", "--scenario-file": "value", "--scenario-dir": "value",
    "--tag": "value", "--limit": "value",
    # LLM 录像录制 / 回放（2026-09-18）：opt = 值可省（省了就用默认目录 output/llm_cassettes）
    "--llm-cassette": "opt", "--llm-record": "opt", "--llm-cassette-strict": None,
    "--keep": "value", "--dry-run": None,
    # setup 子命令的开关（2026-09-23，V8.2.3）
    "--check": None, "--force-browser": None, "--with-ai": None,
    # L5 归档保留（2026-09-22）：run / verify 目录
    "--all": None, "--runs": None,
    "--keep-runs": "value", "--keep-days": "value", "--max-delete": "value",
    # V8.4：常用可调项开成 CLI 参数（用户 2026-10-08 定「方案 2」）——
    # 起因：41 个 HYBRID_* 环境变量全靠「翻源码才知道」，.env.example 里一个都没有，
    # 而项目 .env 不入库、现状压根不存在 -> 用户根本没处发现它们。
    "--ai-retry": "value", "--shots": None, "--video": None,
    "--timeout": "value", "--base-url": "value", "--strict-locate": None,
    }
# 对 run/all 生效的通用参数（main 统一解析）
_COMMON_FLAGS = {"--workers", "--debug", "--headed", "--force-workers", "--isolated-target",
                "--case", "--slowmo"}
CMD_FLAGS: dict[str, set[str]] = {
    "probe": {"--base-url"},
    "generate": {"--element-map", "--live-probe", "--allow-unmapped",
                  "--only", "--changed", "--force", "--base-url"},
    "explore": {"--ai", "--mock-fallback", "--no-cases", "--no-verify", "--verify",
                "--scenario", "--scenario-file", "--scenario-dir", "--tag", "--limit",
                "--llm-cassette", "--llm-record", "--llm-cassette-strict", "--ai-retry"},
    "run": set(_COMMON_FLAGS) | {"--shots", "--video", "--timeout", "--base-url",
                                 "--strict-locate"},
    "all": set(_COMMON_FLAGS) | {"--allow-unmapped", "--shots", "--video", "--timeout",
                                 "--base-url", "--strict-locate"},
    "prune": {"--keep", "--dry-run", "--all", "--runs",
              "--keep-runs", "--keep-days", "--max-delete"},
    "setup": {"--check", "--force-browser", "--with-ai"},
    "config": set(),
}
# 已移除的参数：给"为什么没了 + 该用什么"，而不是笼统的"不认识"
REMOVED_FLAGS = {
    "--to-cases": "落 cases/ai_*.json 已是默认行为；要关掉用 --no-cases",
}


#: 全部可调项清单（V8.4 `cli config` 用它展示）。
# 起因：41 个 HYBRID_* 全靠翻源码才能发现；`cli config` 让「有哪些旋钮、当前多少、从哪来的」
# 一屏可见。字段：(环境变量, 默认值, 一句话说明)。
# [!] 只登记**用户可能需要动**的项。框架运行期自设的（RUN_ID / PARTITION / W / CASSETTE_STRICT,
#     以及测试专用的 BAD_PY / DAILY_SKIP）**刻意不列** —— 列出来只会让用户误以为该去调它。
TUNABLE_CATALOG: list[tuple[str, str, str]] = [
    ("HYBRID_AI_RETRY", "2", "AI 产出校验不合格时的重试次数（0=关闭 · 上界 5）"),
    ("HYBRID_WAIT_DEFAULT_MS", "30000",
     "等待类断言的**有界默认**时长（毫秒）；场景声明了业务时长时以声明为准（见 declared_wait）"),
    ("HYBRID_PROMPT_LIST_CHARS", "90000",
     "喂给 AI 的**每条清单**（控件/行内列/DOM）的字符预算；超了按「场景提到+必填 全给，其余页间轮转」裁剪并明示条数"),
    ("HYBRID_BASE_URL", "http://localhost:8000", "被测应用地址（旧名 TARGET_URL 也认，它优先）"),
    ("HYBRID_EFFECT_CHECK", "1",
     "动作后置校验总开关：业务动词点击后判「动作是否真的生效（有导航/有写请求/无拒绝提示）」，默认只留痕"),
    ("HYBRID_STRICT_EFFECT", "0",
     "动作后置校验的严格模式（1=开）：页面出现**拒绝提示**时直接判失败（CI 零兜底）"),
    ("HYBRID_EDITABLE_PROBE", "1",
     "「编辑态/动态新增」补探开关：探测时点一次「编辑」「新增」再重采（有些控件只在编辑态才存在）"),
    ("HYBRID_EDIT_VERBS", "(空)",
     "追加「进编辑态」动词（逗号分隔）—— 框架内置表不含业务专有词"),
    ("HYBRID_ADD_VERBS", "(空)",
     "追加「动态新增」动词（逗号分隔）—— 点一下会**长出**新控件的那种"),
    ("HYBRID_REVERT_VERBS", "(空)",
     "追加「收尾复原」动词（逗号分隔）—— 优先用它退出编辑态，取不到就 reload"),
    ("HYBRID_HINT_SELECTORS", "(空)",
     "追加「提示区」选择器（分号分隔）：用于回读页面提示文案（默认候选见 harness）"),
    ("HYBRID_REFUSE_HINTS", "(空)",
     "追加「拒绝语义」词（逗号分隔）：提示文案命中即视为动作被拒绝"),
    ("HYBRID_BIZ_VERBS", "(空)",
     "追加「业务动词」（逗号分隔）：只有命中这些词的点击才做动作后置校验"),
    ("HYBRID_CASE_TIMEOUT", "600", "单条用例超时秒数（0/off = 不限）"),
    ("HYBRID_LOCATE_TIMEOUT", "5000", "单次定位等待毫秒（慢目标可调大）"),
    ("HYBRID_READY_TIMEOUT", "15000", "等页面就绪标记的毫秒上限"),
    ("HYBRID_READY_SELECTOR", "(空)", "自定义「页面就绪」选择器"),
    ("HYBRID_READY_REQUIRED", "0", "1=没等到就绪标记即判失败"),
    ("HYBRID_WAIT_READY", "1", "0=不等待就绪标记"),
    ("HYBRID_SELF_HEAL", "1", "0=关掉自愈（定位失败时不再走语义兜底，失败即报）"),
    ("HYBRID_STRICT_LOCATE", "(空)", "1=禁用模糊兜底（CI 语义：失败即报）"),
    ("HYBRID_HEADED", "(空)", "1=有头跑（肉眼看步骤；xdist worker 下强制无头）"),
    ("HYBRID_SLOWMO", "(空)", "每个动作放慢的毫秒数（配 --headed 看慢动作）"),
    ("HYBRID_SHOTS", "(空)", "1=每步存一张 PNG 截图"),
    ("HYBRID_VIDEO", "(空)", "1=整个用例录成 webm"),
    ("HYBRID_DEBUG", "(空)", "1=调试输出"),
    ("HYBRID_RESET_URL", "(空)", "用例间复位被测应用的接口；off/none = 不复位"),
    ("HYBRID_LAYER_CLICKS", "8", "探测时每层最多展开几个 picker（页面复杂可调大）"),
    ("HYBRID_LAYER_TRIES", "8", "探测时每层最多尝试几个候选"),
    ("HYBRID_LAYER_ROUNDS", "4", "探测时最多往下钻几层"),
    ("HYBRID_LLM_ATTEMPTS", "(内置)", "LLM 上游限流时的重试次数"),
    ("HYBRID_TAB_TIMEOUT", "8000", "等新 tab 出现的毫秒上限"),
    ("HYBRID_TAB_CLOSE_STRICT", "1", "关 tab 的严格校验"),
    ("HYBRID_JS_HEAP_MB", "(内置)", "Chromium JS 堆上限（内存吃紧时下调）"),
    ("HYBRID_MB_PER_WORKER", "550", "每个 worker 的内存预算（并发调度用）"),
    ("HYBRID_RESERVE_MB", "450", "留给网关与 OS 的内存余量"),
    ("HYBRID_MAX_FREE_MB", "(内置)", "内存低于此值就不再开新 worker"),
    ("HYBRID_KEEP_RUNS", "(内置)", "run 目录保留最近几个"),
    ("HYBRID_KEEP_RUN_DAYS", "(内置)", "run 目录保留几天"),
    ("HYBRID_KEEP_SNAPSHOTS", "(内置)", "快照保留最近几个"),
    ("HYBRID_MAX_DELETE_PER_PRUNE", "(内置)", "单次清理最多删几个"),
    ("HYBRID_NO_AUTO_PRUNE", "(空)", "1=关掉 run 结束后的自动清理"),
    ("HYBRID_SKIP_BROWSER_CHECK", "(空)", "1=跳过启动前的浏览器预检"),
    ("HYBRID_ISOLATED_TARGET", "(空)", "1=跑隔离目标（独立分区）"),
    ("HYBRID_PYTHON", "(内置)", "显式指定解释器（缺依赖时停手报错，不偷换）"),
]


def cmd_config(rest: list[str] = None) -> None:
    """列出全部可调项：**当前值 + 来源 + 怎么在命令行上调**（V8.4）。

    起因（用户 2026-10-08 提问引出）：框架有 41 个 `HYBRID_*`，但 `.env.example` 里一个都没有，
    项目 `.env` 又不入库、现状压根不存在 -> 用户**没处发现它们**，只能翻源码。
    本命令就是那个「一屏可见」的入口 —— **不引入第二套配置文件**（避免与 env 并存造成双入口）。
    """
    import os
    print("\n[config] 可调项一览（优先级：CLI 参数 > 环境变量 > 默认值）")
    print("[config] 用法：python -m framework.cli <子命令> <CLI参数> [值]")
    print("[config] 例：  python -m framework.cli explore --ai --scenario-file x.yml --ai-retry 3")
    print()
    print(f"  {'可调项':36s} {'当前值':22s} {'来源':10s} CLI 参数")
    print("  " + "-" * 104)
    for env, default, desc in TUNABLE_CATALOG:
        raw = os.environ.get(env)
        if raw is None or raw == "":
            cur, src = default, "默认"
        else:
            cur, src = raw, "环境变量"
        cur = (cur[:19] + "…") if len(cur) > 20 else cur
        flag = ENV_TO_FLAG.get(env, "—")
        print(f"  {env:36s} {cur:22s} {src:10s} {flag}")
        print(f"  {'':36s} {desc}")
    print()
    n_cli = len(ENV_TO_FLAG)
    print(f"[config] 共 {len(TUNABLE_CATALOG)} 项 · 其中 {n_cli} 项可直接用 CLI 参数给"
          f"（见上表最后一列）")
    print("[config] 框架运行期自设的变量（RUN_ID / PARTITION / W 等）刻意不列："
          "那些不该由用户去调")


#: 环境变量 -> CLI 参数 的映射（V8.4）。
# 用途：① `cli config` 告诉用户「这一项怎么在命令行上调」；② CLI 参数落地成环境变量。
# [!] 只登记「用户会调」的项 —— 框架运行期自设的（RUN_ID / PARTITION / W）**刻意不在此表**：
#     暴露给用户=误导（设了只会把链路搞乱）。判据 test_internal_only_vars_have_no_cli_flag 守着这条。
# [!] 一个环境变量只许映射一个参数（项目铁律：同一能力收敛成唯一入口）。
ENV_TO_FLAG: dict[str, str] = {
    "HYBRID_AI_RETRY": "--ai-retry",
    "HYBRID_SHOTS": "--shots",
    "HYBRID_VIDEO": "--video",
    "HYBRID_CASE_TIMEOUT": "--timeout",
    "HYBRID_BASE_URL": "--base-url",
    "HYBRID_STRICT_LOCATE": "--strict-locate",
    "HYBRID_HEADED": "--headed",
    "HYBRID_SLOWMO": "--slowmo",
}
#: 纯开关类参数：出现即设 `1`（不许写 "1"/"true" 折腾用户）
_SWITCH_FLAGS = {"--shots", "--video", "--strict-locate", "--headed"}


def _apply_flag_as_env(flag: str, value: str | None, rest: list[str]) -> None:
    """把 CLI 给的可调项**落到环境变量**（V8.4）。

    为什么用环境变量当落地层而不改各调用点：这些值最终由**生成物/子进程**读取
    （harness 在 pytest 进程里读 `HYBRID_*`），环境变量是天然能跨进程传递的唯一载体；
    而且优先级天然正确 —— 我们在起子进程**之前**设，覆盖掉 shell/`.env` 里的同项。
    优先级链条：**CLI 参数 > 环境变量 > 默认值**。
    """
    import os
    env = next((k for k, v in ENV_TO_FLAG.items() if v == flag), None)
    if env is None:
        return
    if flag in _SWITCH_FLAGS:
        os.environ[env] = "1"
    else:
        v = _arg_value(rest, flag)
        if v:
            os.environ[env] = v


def _usage(cmd: str) -> str:
    fs = sorted(CMD_FLAGS.get(cmd, set()))
    return " ".join(fs) if fs else "(无参数)"


def _fail(msg: str, hint: str = "") -> None:
    """参数错误：明确报错 + 非 0 退出（脚本调用方必须能察觉）。"""
    print(f"\n[cli] [NG] {msg}", file=sys.stderr)
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
    """`--help` / `-h`：总览或单子命令帮助。

    [!] 业务规则（2026-09-28 定）：**help 的每一行都由代码生成** ——
      · 子命令清单 / 每个子命令的**全部参数**取自 `CMD_FLAGS`（唯一注册表）；
      · 一句话说明取自各子命令函数的 docstring 首行。
    -> 新增子命令 / 参数时**不用改本函数**，总览自动带上它（人只写那句 docstring）。
    判据：`tests/_helpers/test_cli_help_coverage.py`（含「注册即显示」机制自证
    + 「漏一个 flag 必须被判红」的负向自证）。
    """
    import inspect
    if cmd is None:
        print((__doc__ or "").strip())
        print("\n子命令：")
        for c in CMD_FLAGS:
            first = (inspect.getdoc(_CMD_FUNCS[c]) or "").strip().splitlines()[0]
            print(f"  {c:<9} {first}")
            print(f"            {'参数：' + _usage(c)}")
        print("\n查看单个子命令：python -m framework.cli <子命令> --help（含参数取值说明）")
        print("run / all 的两个危险开关（其余参数见上面的『参数：』行）：")
        print("        --force-workers   = 无视内存预检强行并发（有 OOM 风险）")
        print("        --isolated-target = 显式声明『目标已按 worker 隔离数据』，放行并发；")
        print("                            没声明时框架会探测目标 /api/health，未声明就保守降到 1 并发")
        return
    print(f"用法：python -m framework.cli {cmd} {_usage(cmd)}\n")
    print((inspect.getdoc(_CMD_FUNCS[cmd]) or "").strip())


def _version() -> str:
    """版本号读 `build_tools/build_html.py`（**版本单一来源**）；读不到就如实说 unknown，不编。"""
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
    #   (1) 自身 stdout/stderr 转 UTF-8（Windows cp936 下 v/[NG]/[!] 不再 UnicodeEncodeError）；
    #   (2) PYTHONUTF8/PYTHONIOENCODING 写进 os.environ -> 之后所有 Python 子进程按 UTF-8 输出；
    #   (3) Windows 控制台代码页 → 65001，中文显示不乱码。
    force_stdio()
    _fs_warn = fs_encoding_warning()
    if _fs_warn:
        # 文件系统编码不是 UTF-8 -> 中文文件名会落成 GBK/其他字节名（仓库里就是乱码）。
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

    # ★ V8.4：把命令行给的可调项落到环境变量（**优先级：CLI > env > 默认**）。
    #   必须在这里做：早于任何子进程（pytest 生成物读的是环境变量），
    #   且在 _validate_args 之后（参数合法性已经查过，不会把脏值写进 env）。
    for _f in ENV_TO_FLAG.values():
        if _f in rest or any(a.startswith(_f + "=") for a in rest):
            _apply_flag_as_env(_f, None, rest)

    workers = _worker_from(rest)
    headed = _debug_from(rest)
    force_workers = _force_from(rest)
    isolated = _isolated_from(rest)
    cases = _arg_values(rest, "--case")
    slowmo = _slowmo_from(rest)
    allow_unmapped = "--allow-unmapped" in rest
    # ★ 浏览器预检（2026-09-23，V8.2.2）：需要浏览器的命令先探一次，
    #   缺浏览器 -> 当场给「一行修复命令」+ exit 2（绝不让它到 Playwright 那层才炸原始栈）。
    if cmd in ("probe", "generate", "explore", "run", "all"):
        try:
            from framework.tools.common.browser import BrowserNotInstalledError, ensure_browser_installed
            ensure_browser_installed()
        except BrowserNotInstalledError as e:
            print(f"\n[cli] {e}", file=sys.stderr)
            print("        （跳过这道检查：HYBRID_SKIP_BROWSER_CHECK=1；"
                  "详见 docs/training.html 第 9 章「装环境三件事」）", file=sys.stderr)
            raise SystemExit(2) from None

    # ★ 分发必须**采纳**子命令的返回值（2026-09-23，V8.2.3 修）：
    #   原来这里是 8 个裸调用，返回值被丢弃 -> cmd_generate 里 DanglingDatasetError 的
    #   `return 2` 变成**空转**（"报了错却告诉调用方成功" exit 0）。同族另外三个错误
    #   （_report_unmapped / _report_data_sets / _report_case_quality）都是 -> NoReturn 直接 raise，
    #   只有这一条走 return -> 典型的不一致。修在分发层 = 根因修复：以后任何子命令
    #   只要 return 非 0，调用方都看得见。
    if cmd == "probe":
        rc = cmd_probe()
    elif cmd == "generate":
        rc = cmd_generate(rest, allow_unmapped=allow_unmapped)
    elif cmd == "explore":
        rc = cmd_explore(rest)
    elif cmd == "run":
        rc = cmd_run(workers, headed, force_workers, cases=cases, slowmo=slowmo,
                     isolated_target=isolated)
    elif cmd == "all":
        rc = cmd_all(workers, headed, force_workers, cases=cases, slowmo=slowmo,
                     isolated_target=isolated, allow_unmapped=allow_unmapped)
    elif cmd == "setup":
        rc = cmd_setup(rest)
    elif cmd == "prune":
        rc = cmd_prune(rest)
    elif cmd == "config":
        rc = cmd_config(rest)
    if isinstance(rc, int) and rc != 0:
        raise SystemExit(rc)


def cmd_setup(argv: list[str]) -> int:
    """一条命令搞定环境：装依赖 + 装浏览器（第一次跑之前执行它）。

    为什么有这条命令（2026-09-23，V8.2.3）：新机器上最容易漏的是「装浏览器」这一步
    —— `pip install -r requirements.txt` **不会**顺带装 Playwright 的浏览器，
    漏了就报 `BrowserType.launch: Executable doesn't exist at …ms-playwright\…`。
    有了它，新人只要记一条命令，第三步不可能再被漏。

    参数：
        --check    只体检，不安装（看清到底缺什么，只读）
        --force-browser  浏览器强制重下（playwright 包换过版本就用它，避免 revision 对不上）
        --with-ai  连 AI 依赖（requirements-ai.txt）一起装

    顺序：(1) 依赖 → (2) 浏览器 → (3) 自检（真启一次 chromium 验证能干活）。
    任一步失败即退出码 2，并把原始输出尾部打出来（不静默）。
    """
    import subprocess
    from pathlib import Path as _Path
    repo_root = _Path(__file__).resolve().parents[1]
    check_only = "--check" in argv
    force = "--force-browser" in argv
    with_ai = "--with-ai" in argv
    py = sys.executable
    print(f"\n[setup] 目标解释器：{py}")
    print(f"[setup] 模式：{'只体检（--check）' if check_only else '安装'}"
          f"{' · 浏览器强制重下（--force-browser）' if force else ''}")
    for _ln in _version_report(_pinned_playwright(repo_root), _installed_playwright()):
        print(_ln)

    ok = True

    # ---- (1) 依赖 ----
    reqs = ["requirements.txt"] + (["requirements-ai.txt"] if with_ai else [])
    have_reqs = [r for r in reqs if (repo_root / r).exists()]
    if check_only:
        missing = [m for m in ("playwright", "pytest", "yaml") if not _can_import(m)]
        if missing:
            ok = False
            print(f"\n[setup] (1) 依赖：[NG] 缺 {missing}")
        else:
            print("\n[setup] (1) 依赖：[OK] 关键包都在（playwright / pytest / yaml）")
    elif not have_reqs:
        print("\n[setup] (1) 依赖：[!] 没找到 requirements.txt，跳过（解压不完整？）")
    else:
        print(f"\n[setup] (1) 装依赖：{', '.join(have_reqs)}")
        cmd, kind = _pip_install_cmd(py, have_reqs)
        if cmd is None:
            ok = False
            print("[setup]    [NG] 本环境既没有 pip 也没有 uv -> 请先装一个：")
            print("            python -m ensurepip --upgrade      # 自带 pip")
        else:
            print(f"[setup]    用 {kind} 安装 …")
            r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=900)
            if r.returncode != 0:
                ok = False
                print(f"[setup]    [NG] 装依赖失败（exit {r.returncode}），尾部输出：")
                print(_tail(r.stdout, r.stderr))
            else:
                print("[setup]    [OK] 依赖就绪")

    # ---- (2) 浏览器 ----
    if check_only:
        ok_b, why = _browser_state()
        print(f"\n[setup] (2) 浏览器：{'[OK] 可用（真启一次成功）' if ok_b else '[NG] 不可用 —— ' + why}")
        ok = ok and ok_b
    else:
        print("\n[setup] (2) 装浏览器（chromium + 无头用的 chromium-headless-shell）")
        cmd = [py, "-m", "playwright", "install", "chromium"] + (["--force"] if force else [])
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=1800)
        except Exception as e:  # noqa: BLE001
            r = None
            print(f"[setup]    [NG] 起不来：{e}")
            ok = False
        if r is not None:
            if r.returncode != 0:
                ok = False
                print(f"[setup]    [NG] 装浏览器失败（exit {r.returncode}），尾部输出：")
                print(_tail(r.stdout, r.stderr))
                print("[setup]    提示：若机器不能联网，请在能联网的机器上装好后拷 "
                      "ms-playwright 缓存目录（见培训页 9.0）")
            else:
                print("[setup]    [OK] 浏览器就绪")

    # ---- (3) 自检（真启一次）----
    if not check_only and ok:
        ok_b, why = _browser_state()
        print(f"\n[setup] (3) 自检：{'[OK] 真启 chromium 成功' if ok_b else '[NG] ' + why}")
        ok = ok and ok_b

    if ok:
        print("\n[setup] [OK] 环境就绪，可以跑了：")
        print("            python -m framework.cli probe     # 探测页面元素")
        print("            python -m framework.cli all       # 探测→生成→执行 全链路")
        return 0
    print("\n[setup] [NG] 环境还没就绪（上面有原因）；修好后重跑 python -m framework.cli setup")
    return 2


def _version_report(pin: str | None, inst: str | None) -> list[str]:
    """给 `setup` 打印「锁定版本 vs 实际版本」这几行（抽成纯函数 -> 好做负向判据）。

    不一致时**只告警不拦**：新版 playwright 未必不能用（框架本身不挑版本），
    但「包升了、浏览器没重下」是踩坑的头号原因（期望的 revision 号会变）——所以要让漂移**看得见**。
    """
    if pin and inst:
        if pin == inst:
            return [f"[setup] playwright 版本：锁定 {pin} · 环境 {inst}   [OK] 一致"]
        return [
            f"[setup] playwright 版本：锁定 {pin} · 环境 {inst}   [!] 不一致",
            "[setup]   不是错，但浏览器可能对不上（期望的 revision 号会变）；要对齐就：",
            "[setup]       python -m framework.cli setup --force-browser",
        ]
    if inst:
        return [f"[setup] playwright 版本：环境 {inst}（requirements.txt 里没锁）"]
    if pin:
        return [f"[setup] playwright 版本：锁定 {pin} · 环境未装（先跑 python -m framework.cli setup）"]
    return []


def _pinned_playwright(repo_root) -> str | None:
    """从 `requirements.txt` 读 playwright 的锁定版本（`playwright==X`；没锁/读不到 -> None）。"""
    try:
        text = (repo_root / "requirements.txt").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if line.startswith("playwright=="):
            return line.split("==", 1)[1].strip() or None
    return None


def _installed_playwright() -> str | None:
    """当前环境里 playwright 的实际版本（没装 -> None）。"""
    try:
        import importlib.metadata as md
        return md.version("playwright")
    except Exception:  # noqa: BLE001
        return None


def _can_import(name: str) -> bool:
    """能不能导入某个包（不打印任何东西）。"""
    try:
        __import__(name)
        return True
    except Exception:  # noqa: BLE001
        return False


def _pip_install_cmd(py: str, reqs: list[str]) -> tuple[list[str] | None, str]:
    """选装依赖的方式：优先 pip，没有再退 uv（本机实测 .venv 可能没带 pip）。"""
    import importlib.util as iu
    import shutil
    if iu.find_spec("pip") is not None:
        return [py, "-m", "pip", "install", "-r", reqs[0]] + _extra_r(reqs), "pip"
    if shutil.which("uv"):
        return ["uv", "pip", "install", "--python", py] + _req_flags(reqs), "uv"
    return None, ""


def _req_flags(reqs: list[str]) -> list[str]:
    out: list[str] = []
    for r in reqs:
        out += ["-r", r]
    return out


def _extra_r(reqs: list[str]) -> list[str]:
    return _req_flags(reqs[1:])


def _tail(stdout: str, stderr: str, n: int = 12) -> str:
    """失败时给出尾部输出（人要看的是最后那几行，不是全部）。"""
    text = ((stdout or "") + "\n" + (stderr or "")).strip().splitlines()
    return "\n".join("            " + ln for ln in text[-n:])


def _browser_state() -> tuple[bool, str]:
    """真启一次 chromium 判断环境是否可用（不写死路径、不看版本）。"""
    try:
        from framework.tools.common.browser import ensure_browser_installed, BrowserNotInstalledError
    except Exception as e:  # noqa: BLE001
        return False, f"框架自身导入失败：{e}"
    try:
        ensure_browser_installed()
        return True, ""
    except BrowserNotInstalledError as e:
        return False, str(e)
    except Exception as e:  # noqa: BLE001
        return False, f"启动失败：{e}"


_CMD_FUNCS = {"probe": cmd_probe, "generate": cmd_generate, "explore": cmd_explore,
              "run": cmd_run, "all": cmd_all, "prune": cmd_prune, "setup": cmd_setup,
              "config": cmd_config}


if __name__ == "__main__":
    main()
