# -*- coding: utf-8 -*-
"""登录链路 **AI 化**（L35）：登录步骤 = 普通步骤，走同一套语义识别与定位。

改造前的三套 schema（这就是要删的东西）
------------------------------------
    scenarios/*.yml   login.steps[]  = {op, by, value}        ← 人写**选择器**（by: {id/css/...}）
    ElementMap.steps[]                 = {op, element, value}  ← AI 写**语义名**
    生成脚本里                          `_login_do(page, op, by)` ← 又一套执行器
同一件事（在登录页上填两个框、点一个按钮）有三份表达、三份执行器。后果：
  · 登录页改版要改**场景**里的选择器（而业务页不用）—— 登录这条链根本没用上框架的语义定位；
  · `by` 只能表达 id/css/text/label/role，**表达不了**「弹窗里的那个按钮」「第 2 行」这类；
  · 登录步骤不在 ElementMap 里 -> 不进决策档案、不进录像、不可回放。

现在的口径（**一套**）
--------------------
    scenarios/*.yml   login: {url, scenario: "<自然语言>", wait: {...}}
    → 用**同一个规划器**（`ai_explore`）在登录页上产出 ElementMap（普通 TestStep）
    → 用**同一套定位栈**（`resolve_locator`）执行
    → 落 `output/login_maps/login_<hash>.json`（决策档案，可审计、可回放）

两处执行方共用本模块：
  · 探测期 / 生成期：`shared.login.ensure_logged_in`（要登录才能探业务页）
  · 执行期：生成物 harness 的 `_login_flow`（读用例里已落盘的登录步骤，**零 AI**）

设计约束（踩过的坑，别改回去）
------------------------------
1. **AI 只在"没有缓存"时跑一次**，结果落盘。否则每跑一次用例都烧一次 token，
   而且离线机器（没有 key）根本跑不了。
2. **执行期绝不调 AI**：生成物里带的是已解析的步骤（`op/desc/element/value`），
   与 `_probe_snapshot` 无关 —— 登录页控件不在业务快照里，所以定位必须按
   `ElementRef` 走 `resolve_locator`，**不能**指望语义名查表。
3. 未知动作**出声**（统一用 `shared.step_ops` 的词表 + 措辞），不许静默跳过。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from framework.features.f03_locate.element_map import ElementMap, ElementRef, TestStep
from framework.shared import config
from framework.shared.step_ops import ASSERT_OPS, STEP_OPS, unknown_hint

LOGIN_MAP_DIR = config.OUTPUT_DIR / "login_maps"


# ---------------------------------------------------------------- 声明 -> 绝对地址
def _executable(m: ElementMap, *, quiet: bool = False) -> list[TestStep]:
    """取**可执行**的登录步骤（只保留 `STEP_OPS` 里的操作类动作）。

    断言类（`expect_*`）不是"登录动作"，执行器没有也**不该有**对应分支 ——
    它们在规划产物里出现属于 AI 的正常发挥（它会顺手写"断言已进入首页"），
    这里滤掉并留日志，不算错误。规划与读缓存**共用**这一处（否则缓存里会存进
    不可执行步骤，运行时必炸：实测 `expect_url` 就是这么把登录整条打断的）。
    """
    out: list[TestStep] = []
    skipped: list[tuple[int, str]] = []
    for s in (m.steps if m is not None else []):
        if (s.op or "").strip() in STEP_OPS:
            out.append(s)
        else:
            skipped.append((s.order, s.op))
    if skipped and not quiet:
        print(f"      [login] [!] 登录步骤里有非操作动作，已跳过：{skipped}")
    return out


def login_url_of(spec: dict, base_url: str) -> str:
    """场景里的 `login.url` 常写相对路径（`/login.html`）—— 必须拼成绝对地址。

    否则 Playwright 会把它当成"相对当前页"的路径（实测会跑错页）。
    未声明时按 `login.html` 兜底（与改造前一致，行为不变）。
    """
    url = str((spec or {}).get("login_url") or (spec or {}).get("url") or "").strip()
    from urllib.parse import urlsplit
    parts = urlsplit(str(base_url or ""))
    origin = f"{parts.scheme}://{parts.netloc}" if parts.scheme and parts.netloc else str(base_url or "").rstrip("/")
    if not url:
        return origin + "/login.html"
    if url.startswith(("http://", "https://")):
        return url
    # [!] 只拼到**站点根**，不拼到"当前页"：`base_url` 传进来的可能是任意一页
    #   （本场景的 pages[0] 就是登录页）—— 按当前页拼会得到 `.../login.html/login.html`
    #   （实测踩到：探不到任何控件，整条链在登录规划这一步就停）。
    return origin + "/" + url.lstrip("/")


def login_scenario_of(spec: dict) -> str:
    """取自然语言登录意图（唯一字段 `scenario`；老口径 `steps` 由 scenario 层直接拒掉）。"""
    return str((spec or {}).get("scenario") or "").strip()


def cache_key(login_url: str, scenario: str) -> str:
    """缓存键：**声明**决定身份（地址 + 自然语言），与探测期数据无关。

    不含模型名：在 A 机生成、B 机执行要能命中（与录像键同一口径）。
    """
    h = hashlib.sha256()
    h.update((login_url or "").encode("utf-8"))
    h.update(b"\x00")
    h.update((scenario or "").encode("utf-8"))
    return h.hexdigest()[:16]


def cache_path(login_url: str, scenario: str) -> Path:
    return LOGIN_MAP_DIR / f"login_{cache_key(login_url, scenario)}.json"


# ---------------------------------------------------------------- 规划（AI，只跑一次）
def plan_login(spec: dict, base_url: str, *, llm_cassette=None, cassette_strict: bool = False,
               force: bool = False) -> dict:
    """把 `login: {url, scenario, wait}` 解析成**带步骤**的登录声明（缺缓存时才调 AI）。

    返回 `{"login_url", "scenario", "wait", "steps": [TestStep.to_dict(), ...], "cached": bool}`。
    `steps` 的形状与用例步骤**完全相同**（op/desc/element/value/...）—— 这是"一套"的关键：
    下游（ensure_logged_in / 生成物）拿到的就是普通步骤，不需要知道"这是登录"。

    AI 不可用时**如实抛**（不返回空步骤 —— 空步骤会让"登录"变成静默 no-op，
    表现为"探到的全是登录页控件"，最难查）。
    """
    url = login_url_of(spec, base_url)
    scenario = login_scenario_of(spec)
    if not scenario:
        raise RuntimeError(
            "登录声明缺 `scenario`（自然语言）—— L35 起登录步骤由 AI 用同一套语义识别生成，"
            "不再接受 `steps/by` 选择器写法。示例：\n"
            "  login:\n    url: /login.html\n"
            "    scenario: 在登录页填写账号与密码，然后点「登录」按钮\n"
            "    wait: {url_not: login.html}")

    p = cache_path(url, scenario)
    out = {"login_url": url, "scenario": scenario, "wait": dict((spec or {}).get("wait") or {})}
    if p.is_file() and not force:
        try:
            m = ElementMap.from_json(p)
            exec_steps = _executable(m, quiet=True)
            if exec_steps:
                print(f"      [login] [i] 复用登录步骤缓存 {p.name}（{len(exec_steps)} 步，零 AI）")
                return dict(out, steps=[s.to_dict() for s in exec_steps], cached=True)
            print(f"      [login] [!] 缓存 {p.name} 里没有可执行步骤 -> 重新规划")
        except Exception as e:                                        # noqa: BLE001
            # 缓存坏了不许静默重建（会掩盖"产物被改坏"），如实说然后重规划
            print(f"      [login] [!] 缓存读取失败（{type(e).__name__}: {e}）-> 重新规划")

    print(f"      [login] [key] 用同一套语义识别规划登录步骤：{scenario[:40]!r}")
    items, dom_ctx = _probe_login_page(url)
    if not items:
        raise RuntimeError(
            f"登录页 {url} 探不到任何控件 —— 登录步骤无从规划。"
            f"先确认页面能打开（curl {url}），或场景的 login.url 写错了。")
    print(f"      [login] [i] 登录页控件 {len(items)} 个 -> 交给同一个规划器")
    import asyncio
    from framework.features.f02_semantic.explorer_explore import _ai_explore_async
    m = asyncio.run(_ai_explore_async(
        scenario, items, url, dom_ctx=dom_ctx,
        llm_cassette=llm_cassette, cassette_strict=cassette_strict,
        allow_login_steps=True))     # 登录页规划：登录步骤就是正确答案（业务规划仍禁）
    steps = _executable(m)
    if not steps:
        raise RuntimeError(f"AI 没有产出可执行的登录步骤（ElementMap {len(m.steps)} 步，"
                           f"全部不是操作类动作）—— 登录意图写清楚一点再试")
    LOGIN_MAP_DIR.mkdir(parents=True, exist_ok=True)
    # 缓存只存**可执行**步骤：读缓存的那条路不再需要二次过滤（一处口径）
    m.steps = steps
    m.to_json(p)
    print(f"      [login] [OK] 登录步骤 {len(steps)} 步 -> {p.name}（决策档案，可审计）")
    return dict(out, steps=[s.to_dict() for s in steps], cached=False)


def _probe_login_page(url: str):
    """探登录页（只要**控件清单 + DOM 事实**）。

    为什么不用 `scan_page`（探测链唯一入口）：登录页没有弹窗/可展开容器需要展开，
    而 `scan_page` 在"进页面就跳转"的登录页上实测会返回空清单（详见模块尾部注释）。
    这里用同一支探针（`probe_page`）+ 同一份 DOM 事实采集，喂给**同一个规划器**。

    必须**自己开浏览器、自己关**：调用方（`_explore_one`）此刻还没开浏览器，
    而在 `ensure_logged_in` 里再开一个浏览器是明确禁止的（内存/并发事故来源）。
    """
    from playwright.sync_api import sync_playwright
    from framework.features.f02_semantic.explorer_explore import _collect_dom_context
    from framework.features.f03_locate.probe import probe_page
    from framework.shared.browser import launch_opts

    with sync_playwright() as p:
        b = p.chromium.launch(**launch_opts(headless=True))
        try:
            ctx = b.new_context()
            pg = ctx.new_page()
            pg.goto(url, wait_until="domcontentloaded")
            try:
                pg.wait_for_selector("body[data-hybrid-ready='1']", timeout=8000, state="attached")
            except Exception:                                         # noqa: BLE001
                pg.wait_for_timeout(500)
            return probe_page(pg, page_name="登录页"), _collect_dom_context(pg)
        finally:
            b.close()


# ---------------------------------------------------------------- 执行（同一套定位栈）
def _steps_of(spec: dict) -> list[TestStep]:
    raw = (spec or {}).get("steps") or []
    return [TestStep.from_dict(x) if isinstance(x, dict) else x for x in raw]


def run_login_steps(page, spec: dict, *, timeout: int = 15000) -> dict:
    """在登录页上执行步骤序列（goto -> 各动作），再等**可观测**成功条件。

    定位走 `resolve_locator`（与业务步骤**同一个**分层定位栈）：
    登录页控件不在业务快照里，所以这里按 `ElementRef` 现场解析，而不是查语义名表。
    """
    from framework.features.f03_locate.locator_bridge_locate import resolve_locator

    steps = _steps_of(spec)
    if not steps:
        raise RuntimeError("登录步骤为空 —— 计划没生成？这会让登录变成静默 no-op")

    done = 0
    for st in steps:
        op = (st.op or "").strip()
        if op not in STEP_OPS:
            raise RuntimeError(unknown_hint(op))
        if op == "goto":
            target = str(st.value or st.element or "").strip()
            if not target:
                raise RuntimeError(f"登录第 {st.order} 步 goto 没有地址")
            page.goto(target, wait_until="domcontentloaded")
            done += 1
            continue
        el = st.element
        if el is None:
            raise RuntimeError(f"登录第 {st.order} 步（{op}）没有目标元素 —— 规划产物不完整")
        r = resolve_locator(page, el if isinstance(el, ElementRef) else ElementRef.from_dict(el))
        if not r.get("ok"):
            raise RuntimeError(f"登录第 {st.order} 步（{op} {el.semantic_name!r}）定位失败："
                               f"{r.get('reason')}")
        loc = r["locator_obj"]
        if op == "fill":
            loc.fill(str(st.value or ""), timeout=timeout)
        elif op == "click":
            loc.click(timeout=timeout)
        elif op == "check":
            loc.check(timeout=timeout)
        elif op == "press_enter":
            loc.press("Enter", timeout=timeout)
        elif op == "select":
            loc.select_option(str(st.value or ""), timeout=timeout)
        else:                                   # click_new_tab / close_tab：登录页上用不到
            print(f"      [login] [!] 登录步骤里的 {op} 不适用于登录页 -> 跳过")
            continue
        done += 1

    wait = dict((spec or {}).get("wait") or {})
    if wait:
        if wait.get("url_not"):
            pat = str(wait["url_not"])
            page.wait_for_url(lambda u: pat not in u, timeout=timeout)
        elif wait.get("url"):
            page.wait_for_url(str(wait["url"]), timeout=timeout)
        elif wait.get("selector"):
            page.wait_for_selector(str(wait["selector"]), timeout=timeout)
        elif wait.get("text"):
            page.wait_for_selector(f"text={wait['text']}", timeout=timeout)
    return {"ok": True, "steps": done, "url": page.url}


def login_on_page(page, spec: dict, base_url: str, *, llm_cassette=None,
                  cassette_strict: bool = False) -> dict:
    """一站式：规划（有缓存则零 AI）→ 打开登录页 → 执行 → 等成功条件。

    供 `shared.login.ensure_logged_in` 与生成物 harness 共用（唯一执行入口）。
    """
    planned = plan_login(spec, base_url, llm_cassette=llm_cassette,
                         cassette_strict=cassette_strict)
    url = planned["login_url"]
    if (_steps_of(planned)[0].op or "").strip() != "goto":
        page.goto(url, wait_until="domcontentloaded")
    return run_login_steps(page, planned)


def as_case_field(spec: dict, base_url: str, *, llm_cassette=None,
                  cassette_strict: bool = False) -> dict:
    """转成**用例产物**里的 `login` 字段（explore 落盘、generate 读、执行期零 AI）。"""
    planned = plan_login(spec, base_url, llm_cassette=llm_cassette,
                         cassette_strict=cassette_strict)
    return {"login_url": planned["login_url"], "wait": planned.get("wait") or {},
            "steps": planned["steps"]}


def json_literal(obj) -> str:
    """把 dict 渲染成**可嵌进生成脚本**的 Python 字面量（中文不转义）。"""
    return json.dumps(obj, ensure_ascii=False)
