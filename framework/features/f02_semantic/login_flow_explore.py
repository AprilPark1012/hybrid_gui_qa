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
import threading
from pathlib import Path

from framework.features.f03_locate.element_map import ElementMap, ElementRef, TestStep
from framework.shared import config
from framework.shared.step_ops import ASSERT_OPS, STEP_OPS, unknown_hint

LOGIN_MAP_DIR = config.OUTPUT_DIR / "login_maps"


# ---------------------------------------------------------------- 声明 -> 绝对地址
# 登录段能**执行**的断言：只是校验、无副作用，`_login_flow` 会走 `_run_assert_step`。
# `expect_first_row` 不在内 —— 它要 `cell_field`（第一行哪一列），登录页通常没有表格行，
# 硬带上只会在运行期炸；这里丢掉并**说清原因**（不是静默）。
LOGIN_ASSERT_OPS = frozenset({"expect_url", "expect_text"})


def _executable(m: ElementMap, *, quiet: bool = False) -> list[TestStep]:
    """取**可执行**的登录步骤：操作类 + 登录段有意义的断言（`expect_url` / `expect_text`）。

    [!] 口径变更（2026-11-05 · V8.9.6 · L38「断言步骤可用性对齐」）：
    旧实现把**所有** `expect_*` 都丢掉，理由写的是「执行器没有对应分支」。
    但断言只是**校验**、没有副作用 —— 全丢掉的后果是 AI 顺手写的
    「断言已进入首页」变成一句空话，**登录成功的判定少了一道**
    （真机日志：`登录步骤里有非操作动作，已跳过：[(4, 'expect_url')]`）。

    正确的对齐方式不是删断言，而是让登录链路也能执行断言 ——
    `_login_flow` 里 op ∈ `ASSERT_OPS` 走 `_run_assert_step`（与主链路**同一入口**）。
    这里只保留登录段说得通的 `LOGIN_ASSERT_OPS`；`expect_first_row` 仍丢，但日志写明原因。

    规划与读缓存**共用**这一处（否则缓存里会存进不可执行步骤，运行时必炸）。
    """
    out: list[TestStep] = []
    skipped: list[tuple[int, str]] = []
    unsupported_assert: list[tuple[int, str]] = []
    for s in (m.steps if m is not None else []):
        op = (s.op or "").strip()
        if op in STEP_OPS or op in LOGIN_ASSERT_OPS:
            out.append(s)
        elif op in ASSERT_OPS:
            unsupported_assert.append((s.order, op))
        else:
            skipped.append((s.order, op))
    if skipped and not quiet:
        print(f"      [login] [!] 登录步骤里有未知动作，已跳过：{skipped}")
    if unsupported_assert and not quiet:
        print(f"      [login] [i] 登录段不执行行断言（要 cell_field、登录页一般没有表格行），"
              f"已跳过：{unsupported_assert} —— 需要的话请在业务步骤里断" )
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


def run_async_isolated(factory):
    """在**独立线程**里跑 `asyncio.run(factory())`，返回其结果（异常原样抛出）。

    为什么必须开线程（V8.7.28 实测取证）
    --------------------------------
    Playwright 的 **Sync API 与当前线程的 asyncio event loop 互斥**。本模块的调用者
    （`shared/login.py:ensure_logged_in` -> `scan_pages_probe.scan_pages`）全部活在
    `with sync_playwright()` 上下文里，直接 `asyncio.run(...)` 会抛：

        Error: It looks like you are using Playwright Sync API inside the asyncio loop.

    后果不是"报个错就算了"：`scan_pages` 的登录前置失败后**探测照常进行**，7 个页
    全部被 demo 重定向到 `login.html?next=...`，于是 `probe_row_fields` 在每一页都探到
    **登录页 login-accounts 的 3 条空 field 列**（角色/账号/密码）并打上"发票列表页"的
    页名 —— 脏数据一路喂给 AI，AI 只能猜列名（V8.7.24/26 的按页校验全部落空）。

    `_ai_explore_async` 只做 LLM 语义识别、**不碰任何 Playwright 对象**，所以在旁路线程
    里跑它没有并发风险；线程结束即回收，不留 event loop 给主线程。
    """
    box: dict = {}

    def _target():
        import asyncio
        try:
            box["value"] = asyncio.run(factory())
        except BaseException as e:            # noqa: BLE001 —— 原样抛给调用方，不吞
            box["error"] = e

    th = threading.Thread(target=_target, name="login-plan-async", daemon=True)
    th.start()
    th.join()
    if "error" in box:
        raise box["error"]
    if "value" not in box:
        raise RuntimeError(
            "异步规划线程没有返回结果（既没异常也没值）—— 线程可能被提前终止。"
            "这是框架内部错误，不要当成场景问题排查。")
    return box["value"]


# ---------------------------------------------------------------- 规划（AI，只跑一次）
def plan_login(spec: dict, base_url: str, *, llm_cassette=None, cassette_strict: bool = False,
               force: bool = False, ctx=None) -> dict:
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
    # 跨 origin（V8.10.0）：`login.session` 必须原样透传进规划结果 —— 曾经在这里丢掉，
    # 导致用例落盘后**没有 session**，执行期不铺会话，跨 origin 的页面被踢回各自登录页
    # （实测：goto 8001/orders.html 后断言「订单系统」5s 超时）。
    if (spec or {}).get("session"):
        out["session"] = dict((spec or {}).get("session") or {})
    if p.is_file() and not force:
        try:
            m = ElementMap.from_json(p)
            exec_steps = _executable(m, quiet=True)   # 口径在执行侧：换规则就对老缓存也生效
            if exec_steps:
                print(f"      [login] [i] 复用登录步骤缓存 {p.name}（可执行 {len(exec_steps)} 步"
                      f" / 档案 {len(m.steps)} 步，零 AI）")
                return dict(out, steps=[s.to_dict() for s in exec_steps], cached=True)
            print(f"      [login] [!] 缓存 {p.name} 里没有可执行步骤 -> 重新规划")
        except Exception as e:                                        # noqa: BLE001
            # 缓存坏了不许静默重建（会掩盖"产物被改坏"），如实说然后重规划
            print(f"      [login] [!] 缓存读取失败（{type(e).__name__}: {e}）-> 重新规划")

    print(f"      [login] [key] 用同一套语义识别规划登录步骤：{scenario[:40]!r}")
    items, dom_ctx = _probe_login_page(url, ctx=ctx)
    if not items:
        raise RuntimeError(
            f"登录页 {url} 探不到任何控件 —— 登录步骤无从规划。"
            f"先确认页面能打开（curl {url}），或场景的 login.url 写错了。")
    print(f"      [login] [i] 登录页控件 {len(items)} 个 -> 交给同一个规划器")
    from framework.features.f02_semantic.explorer_explore import _ai_explore_async
    # V8.7.28：**不许**在本线程直接 asyncio.run —— Playwright Sync API 与 event loop 互斥，
    #   实测会让登录前置静默失败、7 页全被重定向后探成登录页的垃圾列。见 run_async_isolated 的 docstring。
    m = run_async_isolated(lambda: _ai_explore_async(
        scenario, items, url, dom_ctx=dom_ctx,
        llm_cassette=llm_cassette, cassette_strict=cassette_strict,
        allow_login_steps=True))     # 登录页规划：登录步骤就是正确答案（业务规划仍禁）
    steps = _executable(m)
    if not steps:
        raise RuntimeError(f"AI 没有产出可执行的登录步骤（ElementMap {len(m.steps)} 步，"
                           f"全部不是操作类动作）—— 登录意图写清楚一点再试")
    LOGIN_MAP_DIR.mkdir(parents=True, exist_ok=True)
    # [!] 缓存存**AI 的原始决策**，可执行性由**读**时的 `_executable` 过滤（2026-11-05 · V8.9.6）。
    #   旧口径是「只把可执行步落盘」，后果是**过滤规则一改，老缓存永远不生效** ——
    #   L38 就把 AI 写的 `expect_url` 固化丢在了缓存里，得重规划才补回来。
    #   过滤属于**执行侧**（框架怎么执行），不是 AI 的决策；决策档案就该原样留着可审计。
    m.to_json(p)
    print(f"      [login] [OK] 登录步骤 {len(steps)} 步"
          f"（AI 原始 {len(m.steps)} 步）-> {p.name}（决策档案，可审计）")
    return dict(out, steps=[s.to_dict() for s in steps], cached=False)


def _probe_login_page(url: str, ctx=None):
    """探登录页（只要**控件清单 + DOM 事实**）。

    为什么不用 `scan_page`（探测链唯一入口）：登录页没有弹窗/可展开容器需要展开，
    而 `scan_page` 在"进页面就跳转"的登录页上实测会返回空清单（详见模块尾部注释）。
    这里用同一支探针（`probe_page`）+ 同一份 DOM 事实采集，喂给**同一个规划器**。

    [!] `ctx`（V8.7.28 修复）：**能复用调用方的 context 就必须复用**。
    原实现无条件 `with sync_playwright()` 自己开浏览器，假设"调用方此刻还没开浏览器"。
    但真实调用链 `scan_pages` 是 **先开好 `ctx` 再调 `ensure_logged_in`**：

        with sync_playwright() as p:
            b = p.chromium.launch(...); ctx = b.new_context()
            ensure_logged_in(ctx, ...)          # -> plan_login -> _probe_login_page -> 再开一个 playwright

    于是 Playwright 抛 `It looks like you are using Playwright Sync API inside the asyncio loop.`
    （Linux + Python 3.11 实测必炸；Windows 上不炸，所以这个坑长期没暴露）。
    后果极隐蔽：登录前置失败后探测照常跑，7 页全被重定向成登录页，`probe_row_fields`
    在每页都探到 login-accounts 的 3 条空列并打上业务页名 —— 脏数据喂给 AI。
    """
    from framework.features.f02_semantic.explorer_explore import _collect_dom_context
    from framework.features.f03_locate.probe import probe_page

    def _probe_with(pg):
        pg.goto(url, wait_until="domcontentloaded")
        try:
            pg.wait_for_selector("body[data-hybrid-ready='1']", timeout=8000, state="attached")
        except Exception:                                         # noqa: BLE001
            pg.wait_for_timeout(500)
        return probe_page(pg, page_name="登录页"), _collect_dom_context(pg)

    if ctx is not None:
        # 复用调用方的 context：不开新浏览器（内存/并发事故来源），也不触发嵌套 sync_playwright
        pg = ctx.new_page()
        try:
            return _probe_with(pg)
        finally:
            try:
                pg.close()
            except Exception:                                     # noqa: BLE001
                pass

    from playwright.sync_api import sync_playwright
    from framework.shared.browser import launch_opts

    with sync_playwright() as p:
        b = p.chromium.launch(**launch_opts(headless=True))
        try:
            return _probe_with(b.new_context().new_page())
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
            # [!] 只认 `value`（URL）。**绝不许拿 `element` 顶替**（V8.7.24 修真 bug）：
            #     旧写法 `str(st.value or st.element or "")` 在 value 为空、element 有值时
            #     把 `ElementRef(...)` 的 repr 当 URL 传给 page.goto ->
            #       Error: Page.goto: Protocol error (Page.navigate): Cannot navigate to invalid URL
            #         navigating to "ElementRef(semantic_name='账号', role='textbox', ...)"
            #     后果：登录前置整条中断（explore 与 generate 两侧都会炸）。
            #     真正的病根是「AI 把 goto 和 click 混了」——那要**报错让它重生成**，
            #     而不是用 element 兜底把错误藏起来（静默降级 = 造假）。
            target = str(getattr(st, "value", "") or "").strip()
            if not target:
                _el = getattr(st, "element", None) or {}
                _elname = (_el.get("semantic_name") if isinstance(_el, dict)
                           else getattr(_el, "semantic_name", None))
                raise RuntimeError(
                    f"登录第 {st.order} 步 goto 没有地址（value 为空"
                    + (f"；该步还带了元素 {_elname!r}，可能是把 goto 和 click 写混了" if _elname else "")
                    + "）—— element 不能当 URL 用"
                )
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
                         cassette_strict=cassette_strict,
                         # V8.7.28：把**已有**的 browser context 透传下去，让 `_probe_login_page`
                         #   复用而不是自己 `with sync_playwright()` 再开一个 —— 嵌套必炸
                         #   （`scan_pages` 是本函数的真实调用方，它先开 ctx 再登录）。
                         ctx=getattr(page, "context", None))
    url = planned["login_url"]
    if (_steps_of(planned)[0].op or "").strip() != "goto":
        page.goto(url, wait_until="domcontentloaded")
    return run_login_steps(page, planned)


def as_case_field(spec: dict, base_url: str, *, llm_cassette=None,
                  cassette_strict: bool = False) -> dict:
    """转成**用例产物**里的 `login` 字段（explore 落盘、generate 读、执行期零 AI）。"""
    planned = plan_login(spec, base_url, llm_cassette=llm_cassette,
                         cassette_strict=cassette_strict)
    case_login = {"login_url": planned["login_url"], "wait": planned.get("wait") or {},
                  "steps": planned["steps"]}
    if planned.get("session"):
        case_login["session"] = dict(planned["session"])   # 跨 origin：执行期靠它铺会话
    return case_login


def json_literal(obj) -> str:
    """把 dict 渲染成**可嵌进生成脚本**的 Python 字面量（中文不转义）。"""
    return json.dumps(obj, ensure_ascii=False)
