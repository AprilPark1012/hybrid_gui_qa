"""ElementMap → cases/*.json 转换器 + 用例质量校验。

背景（2026-09-11 链路审计）
--------------------------
explore 产出的 ElementMap 只落 `output/element_maps/*.json`，而 generate 只认
`cases/*.json` ⇒ **AI 用例到不了 generate**，链路断在这里。本模块补上这座桥。

映射规则
--------
    ElementMap.steps[].action   ──同名直映射──▶  cases.steps[].op
    expect_text 步骤            ──▶  asserts[]（断言不是"操作步骤"，不该进 steps）
    step.element.semantic_name  ──▶  cases.steps[].element
    step.value                  ──▶  value
    step.description            ──▶  desc

约定（Q2 决策）
--------------
AI 生成的用例统一 `ai_` 前缀 → 与手写用例一眼可分、可批量清理，不会误删手写资产。
"""
from __future__ import annotations

import datetime as _dt
import json
import re
from pathlib import Path

from .config import CASES_DIR
from .element_map import ElementMap

# action → cases 的 op（同名直映射；不在表内的动作不产出步骤，不静默造假）
_OP_MAP = {
    "goto": "goto",
    "click": "click",
    "fill": "fill",
    "select": "select",
    "check": "check",
    "press_enter": "press_enter",
}

# 断言动作（转为 asserts[]，不是步骤）
#   expect_text → 文本断言（原有）
#   expect_url  → URL 断言（P3 跨页：证明"确实换页了"，用刚加的 url 断言类型）
_ASSERT_ACTIONS = {"expect_text", "expect_url"}


def slugify(text: str, maxlen: int = 24) -> str:
    """场景文本 → 文件名安全 slug（`\\w` 是 Unicode 感知，保留中文）。"""
    s = re.sub(r"[^\w]+", "_", text or "").strip("_")
    return s[:maxlen] or "case"


def make_case_id(scenario: str, ts: _dt.datetime | None = None) -> str:
    """AI 用例 id：ai_<场景slug>_<HHMMSS>。"""
    stamp = (ts or _dt.datetime.now()).strftime("%H%M%S")
    return f"ai_{slugify(scenario)}_{stamp}"


def make_case_id_from_scenario_id(scenario_id: str, ts: _dt.datetime | None = None) -> str:
    """场景文件版 case_id：`ai_<scenario_id>_<HHMMSS>`。

    scenario_id 稳定 ⇒ `ls cases/ai_contracts_search_by_no*` 能拿到同一场景的全部历史产物；
    保留 HHMMSS ⇒ 每次生成可追溯、不覆盖。
    """
    stamp = (ts or _dt.datetime.now()).strftime("%H%M%S")
    return f"ai_{slugify(scenario_id, maxlen=40)}_{stamp}"


def elementmap_to_case(m: ElementMap, case_id: str | None = None,
                       extra: dict | None = None) -> dict:
    """ElementMap → cases 用例字典。

    - expect_text / expect_url 步骤转成 asserts[]（并**丢弃**它身上的 element —— 断言步本不该带元素）；
      位置保留：`after_step` = 该断言之前的操作步数 ⇒ 断言在流程中间原地执行（跨页的「换页证据」靠它）
    - 未知 action 跳过（宁可少一步，也不造假步骤）
    """
    cid = case_id or make_case_id(m.scenario)
    steps: list[dict] = []
    asserts: list[dict] = []

    for st in m.steps:
        action = (st.action or "").strip()

        if action in _ASSERT_ACTIONS:
            pos = len(steps) or None      # 紧跟前面已渲染的操作步之后（0 → 落用例末尾，保持老行为）
            if action == "expect_url":
                # 跨页换页证据：URL 片段断言（value 或 assertion 都接受，取有值的那个）
                exp = st.value or st.assertion
                if exp:
                    asserts.append({
                        "kind": "url",
                        "desc": st.description or f"断言 URL 含 {exp}（证明已换页）",
                        "expect": exp,
                        "after_step": pos,
                    })
            elif st.assertion:
                asserts.append({
                    "desc": st.description or f"断言出现 {st.assertion}",
                    "expect": st.assertion,
                    "after_step": pos,
                })
            continue

        if action == "goto":
            steps.append({
                "op": "goto",
                "desc": st.description or "打开页面",
                "url": st.value or m.url,
            })
            continue

        op = _OP_MAP.get(action)
        if op is None:
            continue

        item: dict = {"op": op}
        semantic = st.element.semantic_name if st.element is not None else ""
        item["desc"] = st.description or (f"{op} {semantic}".strip() if semantic else op)
        if semantic:
            item["element"] = semantic
        if st.value is not None:
            item["value"] = st.value
        steps.append(item)

    case = {
        "case_id": cid,
        "name": m.scenario or cid,
        "base_url": m.url,
        "steps": steps,
        "asserts": asserts,
    }
    # 溯源字段（scenario_id / source_scenario）：generator 只读 case_id/steps/asserts，
    # 多出来的字段被忽略 ⇒ 对执行零影响（已核对 generator.py:87/195-197/264-280）
    if extra:
        case.update(extra)
    return case


# 「运行时才知道」的断言特征 —— 操作前无法确定，AI 只能靠猜（2026-09-11 实测踩到：
# AI 给"共 1 条"，而页面真实是"共 20 条合同" → 用例必失败；若侥幸相等则是假断言）
_DYNAMIC_ASSERT_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"共\s*\d+\s*条"), "运行时计数（共 N 条）"),
    (re.compile(r"(命中|匹配|查询到|找到)\s*\d+"), "运行时计数（命中 N…）"),
    (re.compile(r"\d+\s*(条|个|项)\s*(记录|结果|数据)"), "运行时计数（N 条记录）"),
    (re.compile(r"\d{4}-\d{2}-\d{2}"), "时间戳/日期"),
    (re.compile(r"\d{1,2}:\d{2}(:\d{2})?"), "时间戳/时间"),
]


def _dynamic_assert_kind(text: str) -> str | None:
    """断言文本里是否含「运行时才知道」的内容（计数/时间戳/随机值）。"""
    for pat, kind in _DYNAMIC_ASSERT_PATTERNS:
        if pat.search(text or ""):
            return kind
    return None


def case_warnings(case: dict, guard: dict | None = None) -> list[str]:
    """落盘前校验：抓「假绿」风险（断言只是输入回显 / 断言是猜出来的运行时值）。

    guard：来自 scenario 文件的 `assert_guard`（must_contain / forbidden），
    把"断言必须操作前可确定"从全局规则升级为**本场景硬约束**的事后校验。
    """
    warns: list[str] = []
    steps = case.get("steps", [])
    asserts = case.get("asserts", [])

    fill_values = {s.get("value") for s in steps if s.get("op") == "fill" and s.get("value")}
    for a in asserts:
        exp = a.get("expect")
        if exp and exp in fill_values:
            warns.append(
                f"断言 {exp!r} 与某 fill 步骤的输入值完全相同 → 疑似「断言输入回显」，"
                f"用例会通过但实际没验证业务结果（假绿）"
            )
        if exp:
            kind = _dynamic_assert_kind(exp)
            if kind:
                warns.append(
                    f"断言 {exp!r} 含{kind} —— 操作前无法确定，属于「猜出来的期望值」→ "
                    f"大概率直接失败，侥幸相等则是假断言；改用页面固定文案或可推出的记录标识（编号/名称）"
                )
        # ---- 断言类型扩展（2026-09-13 D 项）后的两条 AI 护栏 ----
        # ① AI 永远不许产 selector：它只准引用 probe 探测出的 semantic_name（否则定位一步就退回
        #    「LLM 猜 CSS」，整套混合架构的立足点就没了）。
        if a.get("selector"):
            warns.append(
                f"AI 断言里出现了 selector={a['selector']!r} —— 本项目铁律：AI 永不产 selector，"
                f"只引用 probe 的 semantic_name；该断言不可信，请改用 element 或人工复核"
            )
        # ② AI 不许用结构化断言种类（尤其 count）绕开「运行时才知道的期望值」检查：
        #    文本形态的计数已被 _DYNAMIC_ASSERT_PATTERNS 拦下，结构化 kind=count 会绕过它，
        #    所以这里按「AI 链路只产 text 断言」把关。
        akind = str(a.get("kind") or "text").strip()
        # url 断言放行：它来自场景声明的页面清单（人给的确定性信息，跨页「换页证据」就用它）；
        # 其余结构化种类（count/attr/value/…）只给手写用例 —— 只有人能确定「操作前可确定」的期望值。
        if akind not in ("text", "url"):
            warns.append(
                f"AI 断言用了 kind={akind} —— AI 链路只允许 text / url 断言（结构化种类是给手写用例的，"
                f"因为只有人能确定『操作前可确定』的期望值，如行数/属性）"
            )
    if guard:
        must = [str(x) for x in (guard.get("must_contain") or [])]
        forbid = [str(x) for x in (guard.get("forbidden") or [])]
        exps = [str(a.get("expect") or "") for a in asserts]
        if must and not any(m and any(m in e for e in exps) for m in must):
            warns.append(
                f"断言未覆盖本场景护栏 must_contain={must} → 场景要求验的东西没被验（"
                f"当前断言：{exps or '（无）'}）"
            )
        for f in forbid:
            if any(f and f in e for e in exps):
                warns.append(f"断言命中了本场景禁止项 {f!r}（assert_guard.forbidden）→ 该断言不是可靠期望值")

    ops_need_el = {"click", "fill", "select", "check", "press_enter"}
    naked = [s for s in steps if s.get("op") in ops_need_el and not s.get("element")]
    if naked:
        detail = "；".join(f"{s.get('op')}（{s.get('desc') or '无描述'}）" for s in naked[:4])
        warns.append(
            f"有 {len(naked)} 个操作步骤没有绑定元素（element 为空）→ 生成脚本定位不到，执行必然失败：{detail}"
        )

    if not asserts:
        warns.append("该用例没有任何断言 → 只能证明「跑得通」，验证不了业务结果")
    if not any(s.get("op") != "goto" for s in steps):
        warns.append("该用例只有 goto 步骤（没有实际操作）")

    # ---- P3 跨页流程：换页必须有证据 ----
    pages = case.get("pages") or []
    goto_urls = [s.get("url") for s in steps if s.get("op") == "goto"]
    multi = len(pages) > 1 or len(set(goto_urls)) > 1
    if multi:
        if not any(str(a.get("kind") or "").strip() == "url" for a in asserts):
            warns.append(
                "跨页用例但没有任何 URL 断言（kind=url）→ 没有「确实换到了目标页」的证据："
                "只靠文本断言时，同一个词可能出现在两个页面上（假绿风险）。"
                "建议加 {\"kind\": \"url\", \"expect\": \"<目标页 URL 片段>\"}"
            )
        declared = [str(p.get("url") or "") for p in pages if p.get("url")]
        url_asserts = [str(a.get("expect") or "") for a in asserts
                       if str(a.get("kind") or "").strip() == "url"]

        def _visited(u: str) -> bool:
            """该页有没有\"到达证据\"：goto 过它，或 url 断言里出现过它的片段（点击跳转也算到过）。"""
            base = u.split("?")[0]
            if any(g and (g == u or g.split("?")[0] == base) for g in goto_urls):
                return True
            tail = base.rstrip("/").rsplit("/", 1)[-1]      # contract_detail.html → 片段
            for frag in url_asserts:
                if frag and (frag in u or (tail and frag in tail)):
                    return True
            return False

        missed = [u for u in declared if not _visited(u)]
        if missed:
            warns.append(
                f"跨页用例里这些声明过的页面既没有 goto 也没有 url 断言作为到达证据"
                f"（可能漏了一步，也可能只是没验\"到了没\"）：{missed}"
            )

    return warns


def elementmap_warnings(m: ElementMap) -> list[str]:
    """针对 ElementMap 原始形态的质量检查（转换后就看不到这些信息了）。

    expect_text 断言步不该带 element —— AI 常犯，会让断言指向一个控件而非页面结果。
    """
    warns: list[str] = []
    for st in m.steps:
        if (st.action or "").strip() in _ASSERT_ACTIONS and st.element is not None:
            warns.append(
                f"第 {st.order} 步 {st.action} 带了元素 {st.element.semantic_name!r} "
                f"→ 断言步不应绑定元素（转换时已丢弃），建议在 prompt 层面纠正"
            )
    return warns


def write_case(case: dict, cases_dir: Path | None = None) -> Path:
    """把用例写入 cases/<case_id>.json（同名自动加 -2/-3 后缀，不覆盖已有文件）。"""
    cases_dir = Path(cases_dir or CASES_DIR)
    cases_dir.mkdir(parents=True, exist_ok=True)
    cid = case["case_id"]
    path = cases_dir / f"{cid}.json"
    n = 2
    while path.exists():
        path = cases_dir / f"{cid}-{n}.json"
        n += 1
    path.write_text(json.dumps(case, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def elementmap_to_cases_file(
    m: ElementMap, cases_dir: Path | None = None, case_id: str | None = None,
    extra: dict | None = None, guard: dict | None = None,
) -> tuple[Path, list[str]]:
    """一站式：ElementMap → cases 文件，返回 (路径, 警告列表)。

    extra：回写进用例的溯源字段（scenario_id / source_scenario）
    guard：场景护栏（assert_guard），参与落盘质量校验
    """
    case = elementmap_to_case(m, case_id=case_id, extra=extra)
    warns = elementmap_warnings(m) + case_warnings(case, guard=guard)
    return write_case(case, cases_dir=cases_dir), warns
