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
from urllib.parse import urlsplit

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


def _dynamic_assert_kind(text) -> str | None:
    """断言文本里是否含「运行时才知道」的内容（计数/时间戳/随机值）。

    ⚠️ **只对字符串期望值做文本检查**：结构化断言的期望值可以是数字/布尔（典型 `count` 的 `20`）。
    2026-09-17 实测：旧写法把 `expect: 20` 直接喂给正则 ⇒ `TypeError: expected string or bytes-like
    object, got 'int'`，质量闸一碰到手写 11 类断言用例就崩（守门人自己倒下 = 没法守门）。
    """
    if not isinstance(text, str):
        return None
    for pat, kind in _DYNAMIC_ASSERT_PATTERNS:
        if pat.search(text):
            return kind
    return None


# ============================================================================
# P4 换页证据质量闸（2026-09-17）：弱 url 断言 = 假绿
# ----------------------------------------------------------------------------
# 背景（2026-09-14 实测挖出）：AI 给「点返回列表回到列表页」产过 `expect: localhost` ——
# 而**上一个页面的 URL 也含 localhost** ⇒ 点击后立刻就能通过，根本没证明发生了换页
# （跨页用例的关键证据悬空）。当时的 AI 提示词甚至**在教 AI 这么写**（见 explorer 规划规则）。
#
# 判据：**换页证据必须只指向一页**。匹配口径与生成脚本的 `_assert_url` 同源：
#   非 http 片段 → 按「包含」匹配；以 http 开头 → 精确匹配。
#
# 分级（同「未映射元素」的红线口径：任何「少验一步还报绿」都必须显式失败）：
#   · 跨页用例里 url 断言**唯一作用**就是换页证据 ⇒ **红线**（拒绝落盘 / 拒绝生成、带人话与非 0 退出）
#   · 单页用例里的同类片段只**告警**（手写用例可能是有意的，如专门验 host:port；也可能根本没声明 pages）
# ============================================================================
REDLINE = "redline"
WARN = "warn"

# ⚠️ 别用「像域名的正则」判 host（实测踩到：`index.html` 会被 `^[\w.\-]+$` 判成 host）——
# 改成「跟已知页面 URL 的 host[:端口] 对得上」为主、形态为兜底。
_HOST_PORT_RE = re.compile(r"^[A-Za-z0-9\-]+(?::\d+)?$")          # localhost / localhost:8000
_IPV4_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?$")       # 127.0.0.1 / 127.0.0.1:9999


def _host_candidates(case: dict) -> set[str]:
    """本用例「所有页共用的 host[:端口]」候选（含裸主机名）—— 来自 pages[].url 与 base_url。"""
    urls = [str((p or {}).get("url") or "") for p in (case.get("pages") or [])]
    if case.get("base_url"):
        urls.append(str(case["base_url"]))
    out: set[str] = set()
    for u in urls:
        if not u:
            continue
        net = urlsplit(u if "://" in u else "http://" + u).netloc.lower()
        if net:
            out.add(net)
            out.add(net.split(":")[0])
    return out


def _is_host_only(frag: str, hosts: set[str]) -> bool:
    """片段是不是「只有 host[:端口]、不含任何路径信息」—— 这种片段证明不了「到了哪一页」。"""
    s = frag.strip().rstrip("/")
    if "://" in s:
        s = s.split("://", 1)[1].rstrip("/")
    if hosts and s.lower() in hosts:                 # 跟已知页面 host 精确对得上 → 铁定是
        return True
    return bool(_IPV4_RE.match(s) or _HOST_PORT_RE.match(s))


def _url_evidence_issues(case: dict) -> list[tuple[str, str]]:
    """换页证据（`kind=url` 断言）的区分力检查 —— 返回 `[(级别, 说明)]`（级别见 REDLINE / WARN）。"""
    asserts = case.get("asserts") or []
    urls: list[str] = []
    for p in (case.get("pages") or []):
        u = str((p or {}).get("url") or "")
        if u and u not in urls:                      # 去重保序
            urls.append(u)
    goto_urls = {str(s.get("url") or "") for s in (case.get("steps") or []) if s.get("op") == "goto"}
    goto_urls.discard("")
    multi = len(urls) > 1 or len(goto_urls) > 1
    hosts = _host_candidates(case)

    out: list[tuple[str, str]] = []
    for a in asserts:
        if str(a.get("kind") or "").strip() != "url":
            continue
        exp = a.get("expect")
        if not isinstance(exp, str) or not exp.strip():
            out.append((REDLINE, "url 断言没给 expect（无法判断它指向哪一页）→ 补上目标页独有的 URL 片段"))
            continue
        frag = exp.strip()
        exact = frag.startswith("http")                       # 与 conftest._assert_url 同口径：精确 vs 包含
        if exact:
            hits = [u for u in urls if u.rstrip("/") == frag.rstrip("/")]
        else:
            hits = [u for u in urls if frag in u]
        host_only = _is_host_only(frag, hosts)
        if multi and host_only and not exact:
            # 跨页用例 + 只有 host[:端口] 的片段 ⇒ 换页前后都能通过，证明不了换页（红线）
            out.append((REDLINE,
                        f"换页证据 {frag!r} 只是 host[:端口]：跨页用例里**每个页面都含它** ⇒ "
                        f"换页前后都能通过，证明不了「确实换页了」（假绿）。改用只出现在目标页的片段"
                        f"（如 contract_detail）；若目标页没有独有片段（多是列表页根路径 /）→ "
                        f"改对该页独有文案做 text 断言"))
        elif len(hits) >= 2:
            out.append((REDLINE,
                        f"换页证据 {frag!r} 在本用例声明的 {len(hits)} 个页面 URL 里都出现"
                        f"（{'、'.join(hits[:3])}）⇒ 换页前后都能通过，证明不了「确实换页了」（假绿）。"
                        f"改用只出现在目标页的片段（如 contract_detail）；"
                        f"若目标页没有独有片段（多是列表页根路径 /）→ 改对该页独有文案做 text 断言"))
        elif multi and not hits:
            out.append((WARN,
                        f"换页证据 {frag!r} 跟本用例声明的页面 URL 都对不上 ⇒ 该断言可能永远不会通过"
                        f"（自造片段？）；要么改成清单里真实存在的片段，要么删掉它"))
        elif host_only:
            out.append((WARN,
                        f"url 断言的期望值 {frag!r} 只是 host[:端口]：任何页面都含它，"
                        f"若意图是证明换页则证明不了（单页用例里若只是想验『URL 含该 host』可忽略本告警）"))
    return out


def case_errors(case: dict, guard: dict | None = None) -> list[str]:
    """**红线级**问题（假绿）——命中即不许落盘 / 不许生成产物（与映射质量闸同一口径）。"""
    return [msg for level, msg in _url_evidence_issues(case) if level == REDLINE]


class CaseQualityError(Exception):
    """用例质量红线：产物永不允许带假绿 ⇒ 拒绝产出，并给出「改哪一条、怎么改」。"""

    def __init__(self, entries: list[tuple[str, list[str]]]):
        self.entries = entries
        super().__init__("; ".join(f"{cid}: {len(errs)} 条红线" for cid, errs in entries))

    @property
    def total(self) -> int:
        return sum(len(errs) for _cid, errs in self.entries)


def case_warnings(case: dict, guard: dict | None = None) -> list[str]:
    """落盘前校验：抓「假绿」风险（断言只是输入回显 / 断言是猜出来的运行时值）。

    guard：来自 scenario 文件的 `assert_guard`（must_contain / forbidden），
    把"断言必须操作前可确定"从全局规则升级为**本场景硬约束**的事后校验。
    """
    warns: list[str] = []
    steps = case.get("steps", [])
    asserts = case.get("asserts", [])

    # 期望值可能是数字/布尔（结构化断言，如 count 的 20）⇒ 全程按字符串口径比对，
    # 避免把 int 喂给正则/哈希集合（2026-09-17 修：旧写法对 `expect: 20` 直接 TypeError）
    fill_values = {str(s.get("value")) for s in steps if s.get("op") == "fill" and s.get("value")}
    for a in asserts:
        exp = a.get("expect")
        if isinstance(exp, str) and exp and exp in fill_values:
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

    # ---- P4 换页证据质量闸（2026-09-17）：弱 url 断言（红线项见 case_errors）----
    warns.extend(msg for _level, msg in _url_evidence_issues(case))

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
    red = case_errors(case, guard=guard)
    if red:
        # 红线（假绿）⇒ **拒绝落盘**：产物永不允许带假绿（与生成侧映射质量闸同一口径）
        raise CaseQualityError([(case["case_id"], red)])
    warns = elementmap_warnings(m) + case_warnings(case, guard=guard)
    return write_case(case, cases_dir=cases_dir), warns
