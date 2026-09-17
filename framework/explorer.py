"""【Browser Use】AI 探索与规划

职责：理解自然语言测试意图 → 规划步骤 → 从 probe 探测出的交互元素里
挑出每个动作的目标元素 → 产出 ElementMap（步骤 + 元素语义引用）。

两种模式：
  - ai_explore()  : LLM 语义识别与步骤编排（**用 browser_use.llm 的 ChatDeepSeek 直连**
                    的 ainvoke(output_format) 拿结构化步骤；经 .env 配 LLM key 启用）
                    注：**不是** browser-use 的 Agent —— Agent 对 DeepSeek 有 input_text
                    schema bug（见 skill 实测记录），故走"方案C"直连编排，能力等价。
  - mock_explore(): 不用 LLM，用一条简单的确定性规则挑元素拼出演示场景，
                    让整条链路在无 key 环境下仍能跑通验证。

✚ 本文件是【智能层】。它负责"理解与决策"，把每个步骤的【目标元素】
   用人类可读的语义引用出来。但它【不产生】最终 locator —— 定位永远
   由 locator_bridge（Playwright）完成，绝不让 LLM 输出 CSS/XPath。
"""
from __future__ import annotations
import asyncio          # 2026-09-13 修：_ai_explore_async 里 `await asyncio.sleep(...)`（LLM 抖动退避重试）
                       # 一直用的是**函数内**的局部 import（只有 ai_explore / _get_llm_text 里有），
                       # 于是重试路径一触发就 NameError 崩溃 —— 退避重试等于从来没生效过。
import json
import time             # 2026-09-14：弹层/弹窗探测改成「有界轮询等新控件出现」，需要单调时钟
from pydantic import BaseModel, Field
from .element_map import ElementMap, TestStep, ElementRef
from .browser import launch_opts


# 交给 ChatDeepSeek(ainvoke output_format) 的结构化步骤 schema
# 只让 AI 产出语义引用 + 描述，绝不产 selector / locator。
class _StepModel(BaseModel):
    order: int = Field(default=1, description="步骤序号")
    action: str = Field(default="click", description="click/fill/select/check/goto/expect_text/expect_url/press_enter")
    semantic_name: str = Field(default="", description="probe 清单里的 semantic_name，禁止自造")
    value: str | None = Field(default=None, description="fill 填入的值")
    assertion: str | None = Field(default=None, description="expect_text 断言")
    description: str = Field(default="", description="一句话说明")


class _PlanModel(BaseModel):
    steps: list[_StepModel] = Field(default_factory=list)


def _norm_name(s: str) -> str:
    """语义名规范化（去下划线/空格/标点 + 小写）—— 用于 AI 名字与探测名的模糊对齐。"""
    import re
    return re.sub(r"[\s_\-，。、：:（）()\[\]【】/]+", "", (s or "").lower())


def _match_item(sn: str, items: list[dict]) -> tuple[dict | None, str]:
    """把 AI 给的 semantic_name 对到清单里的控件。返回 (item | None, 说明)。

    三级：① 精确匹配 → ② 规范化后唯一包含（AI 写了人话名，如"合同名称" vs 清单"请输入合同名称"）
    → ③ 对不上就返回 None（由调用方**明确告警**，不再静默丢弃）。
    """
    if not sn:
        return None, "空"
    for x in items:
        if x.get("semantic_name") == sn:
            return x, "精确"
    key = _norm_name(sn)
    if key:
        hits = [x for x in items
                if key in _norm_name(x.get("semantic_name"))
                or _norm_name(x.get("semantic_name")) in key]
        if len(hits) == 1:
            return hits[0], f"模糊对齐({sn} → {hits[0].get('semantic_name')})"
    return None, "未命中"


def _plan_to_steps(plan, items: list[dict]) -> list[TestStep]:
    """把 ChatDeepSeek 结构化输出(_PlanModel)转成 TestStep 列表。

    2026-09-11 修复：AI 的 semantic_name 对不上清单时**不再静默丢元素** ——
    那会把步骤变成"没有目标的操作"（element=None），生成脚本后必然定位失败，而且没人知道为什么
    （实测：新建场景里 6 个弹窗字段 + 提交按钮全被静默丢掉）。现在改为：尽力对齐 + 明确告警 + 给出清单名。
    """
    steps: list[TestStep] = []
    unmatched: list[str] = []
    for i, s in enumerate(plan.steps):
        sn = (s.semantic_name or "").strip()
        it, how = _match_item(sn, items)
        if it is not None and how.startswith("模糊"):
            print(f"      [explore] ⚠️ 第 {s.order or i + 1} 步元素名自动对齐：{how}")
        if sn and it is None:
            unmatched.append(f"第 {s.order or i + 1} 步 {s.action} 的 semantic_name={sn!r}")
        el = None
        if it:
            el = ElementRef(
                semantic_name=it.get("semantic_name"), role=it.get("role"), name=it.get("name"),
                placeholder=it.get("placeholder"), text=it.get("text"),
                test_id=it.get("test_id"),
                nearby_text=it.get("nearby_text"),
                container_heading=it.get("container_heading"),
                help_text=it.get("help_text"),
            )
        steps.append(TestStep(
            order=s.order or i + 1, action=s.action, element=el,
            value=s.value, assertion=s.assertion, description=s.description,
        ))

    if unmatched:
        print(f"      [explore] ⚠️ 有 {len(unmatched)} 步的元素名不在探测清单里（这些步骤无法定位）：")
        for u in unmatched:
            print(f"          - {u}")
        print(f"      [explore]    清单可用名字：{[x.get('semantic_name') for x in items]}")
    return steps


def _pick(items: list[dict], **conds) -> dict | None:
    """从 probe 结果里挑第一个满足条件的元素。"""
    for it in items:
        if all(it.get(k) == v for k, v in conds.items()):
            return it
    return None


def mock_explore(scenario: str, items: list[dict], url: str) -> ElementMap:
    """【确定性 mock】无 LLM 也能跑：演示"填输入框→点添加→断言回显"。

    仅用于无 key 环境验证链路 / 教学。真实场景请用 ai_explore()。
    根据 scenario 关键词自动选一个演示场景（默认为添加待办）。
    """
    el = ElementMap(url=url, scenario=scenario)

    # 兜底：textbox / add 按钮（get 不到就 None，下面的 ElementRef 会 fallback）
    textbox = _pick(items, role="textbox", placeholder="添加新的待办事项...")
    add_btn = _pick(items, role="button", name="添加")
    span_item = _pick(items, tag="span", text="写周报")
    checkbox = _pick(items, role="checkbox", nearby_text="写周报")

    text_ref = ElementRef(
        semantic_name=(textbox or {}).get("semantic_name", "todo_input"),
        role="textbox", placeholder="添加新的待办事项...",
        test_id=(textbox or {}).get("test_id"),
    )
    add_ref = ElementRef(
        semantic_name=(add_btn or {}).get("semantic_name", "add_button"),
        role="button", name="添加",
        test_id=(add_btn or {}).get("test_id"),
    )

    # —— 演示2：勾选"写周报"（同名 checkbox 消歧场景）——
    if "勾选" in scenario or "check" in scenario.lower():
        cb_ref = ElementRef(
            semantic_name=(checkbox or {}).get("semantic_name", "todo_checkbox"),
            role="checkbox",
            nearby_text=(checkbox or {}).get("nearby_text", "写周报"),
        )
        el.steps = [
            TestStep(1, "goto", description=f"打开 {url}"),
            TestStep(2, "check", cb_ref, description="勾选'写周报'那一项的 checkbox"),
            TestStep(3, "expect_text", None, assertion="已更新",
                     description="断言勾选后状态提示"),
        ]
        return el

    # —— 默认演示1：添加待办 ——
    span_ref = ElementRef(
        semantic_name=(span_item or {}).get("semantic_name", "todo_item_text"),
        text="写周报",
    )
    el.steps = [
        TestStep(1, "goto", description=f"打开 {url}"),
        TestStep(2, "fill", text_ref, value="学习混合测试框架", description="在输入框输入内容"),
        TestStep(3, "click", add_ref, description="点击添加按钮"),
        TestStep(4, "expect_text", None, assertion="学习混合测试框架",
                 description="断言新增文案出现在页面"),
    ]
    return el


class AiExploreError(RuntimeError):
    """AI 语义识别失败（LLM 不可用 / 产出不可用）。

    存在意义：**绝不静默降级成 mock 冒充 AI 产物**（2026-09-11 修复的假 AI 缺陷）。
    """


def _collect_page_context(items: list[dict], url: str, pages: list[dict] | None = None):
    """【同步】探测页面上下文：基础控件 + 弹窗内控件 + 富 DOM 上下文。返回 (items, dom_ctx, err)。

    跨页流程（P3）：pages 给 ≥2 页时走 `_collect_pages_context`（一个浏览器顺序探每页 + 同名唯一化）；
    单页（pages 为空/只有 1 页）走原来的路径，**行为与改造前完全一致**。

    ⚠️ 必须在事件循环**之外**调用。2026-09-11 修复的真 bug：这段探测原来写在 async 函数里，
    `sync_playwright()` 在 asyncio loop 中必然抛
    "It looks like you are using Playwright Sync API inside the asyncio loop"，
    然后被一处静默 `except` 兜底成"只有外部清单、没有弹窗控件、没有 DOM 上下文" ——
    于是「DOM 上下文增强」和「弹窗字段补充」一直是**死代码**：AI 看不到弹窗里的表单字段，
    只能拿列表页的相似控件去顶（实测把弹窗客户下拉错选成搜索区的"全部客户_c1_c2_c3_c4"）。
    现在拆成两个阶段：同步探测 → 异步 LLM 规划。
    """
    if pages and len(pages) > 1:
        return _collect_pages_context(pages, items)

    from playwright.sync_api import sync_playwright
    from .probe import probe_page
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(**launch_opts(headless=True))
            pg = b.new_page()
            pg.goto(url)
            pg.wait_for_load_state("networkidle")
            base = probe_page(pg)
            modal_items = _try_collect_modal_items(pg, base)     # 点开弹窗补表单控件
            page_items = _merge_items(base, modal_items)
            dom_ctx = _collect_dom_context(pg)                   # 富 DOM 上下文（索引/可见性/状态）
            b.close()
        return page_items, dom_ctx, ""
    except Exception as e:
        print(f"      [explore] ⚠️ 页面探测失败（{type(e).__name__}: {str(e)[:160]}）"
              f"→ 退化为外部传入清单（{len(items)} 项）：弹窗内控件与 DOM 上下文将缺失")
        return items, [], f"{type(e).__name__}: {str(e)[:160]}"


def _collect_pages_context(pages: list[dict], items: list[dict]):
    """【同步】跨页探测（P3）：一个浏览器 + 一个 context，按声明顺序 goto 每页。

    - 环境约束：本机 1.87G 无 swap ⇒ 绝不为多页多开浏览器/并发探测（顺序 do 才是安全的）。
    - 每页都做：基础控件探测（打 page 标记）→ 弹窗补探测 → DOM 上下文（带页名前缀）。
    - 合并时做**同名唯一化**（`probe.uniquify_across_pages`）：两页同名的元素改成 `原名@页名`，
      并返回冲突清单供 CLI 明示 —— 因为 generate 的 semantic_name→locator 是全局一张表，
      同名会让两页元素争抢同一个键（过去是静默丢后者 = 悄悄用错页面的 locator）。
    返回 (merged_items, dom_ctx, err_for_ai, collisions)。
    """
    from playwright.sync_api import sync_playwright
    from .probe import probe_page, uniquify_across_pages
    try:
        per_page: list[tuple[str, list[dict]]] = []
        dom_ctx: list[dict] = []
        with sync_playwright() as p:
            b = p.chromium.launch(**launch_opts(headless=True))
            ctx = b.new_context()
            pg = ctx.new_page()
            for spec in pages:
                pg.goto(spec["url"])
                pg.wait_for_load_state("networkidle")
                base = probe_page(pg, page_name=spec["name"])
                modal_items = _try_collect_modal_items(pg, base)
                for it in modal_items:
                    it["page"] = spec["name"]
                merged_one = _merge_items(base, modal_items)
                per_page.append((spec["name"], merged_one))
                for d in _collect_dom_context(pg):
                    d["page"] = spec["name"]
                    dom_ctx.append(d)
                print(f"      [explore] 跨页探测: [{spec['name']}] {spec['url']} → "
                      f"{len(merged_one)} 个控件（弹窗补充 {len(modal_items)}）")
            b.close()
        merged, collisions = uniquify_across_pages(per_page)
        for c in collisions:
            print(f"      [explore] ⚠️ 跨页同名元素 {c['semantic_name']!r} 出现在 "
                  f"{'、'.join(c['pages'])} → 已唯一化为 "
                  f"{'、'.join(c['semantic_name'] + '@' + p for p in c['pages'])}")
        return merged, dom_ctx, "", collisions
    except Exception as e:
        print(f"      [explore] ⚠️ 跨页探测失败（{type(e).__name__}: {str(e)[:160]}）"
              f"→ 退化为外部传入清单（{len(items)} 项）")
        return items, [], f"{type(e).__name__}: {str(e)[:160]}", []


def ai_explore(
    scenario: str, items: list[dict], url: str, allow_mock_fallback: bool = False,
    page_bg: str = "", guard: str = "", pages: list[dict] | None = None,
) -> ElementMap:
    """【LLM 语义识别】理解意图、规划步骤、挑元素（ChatDeepSeek 直连编排，非 Agent）。

    需要 .env 里配好 LLM key（见 config.llm_from_env）。产出的 ElementMap
    与 mock 完全同一结构 —— 即后续 Playwright 执行链路对两者一视同仁。

    pages（P3 跨页，可选）：[{"name","url","page"}, ...]，≥2 页时按跨页模式探测与规划；
    不传/只 1 页 → 单页老路径（行为不变）。

    LLM 完全不可用时：默认 raise AiExploreError（拒绝产出假 AI 用例）；
    allow_mock_fallback=True（CLI 的 --mock-fallback）才显式降级为确定性 mock。
    """
    import asyncio

    # ① 同步阶段：Playwright 探测（基础控件 + 弹窗内控件 + 富 DOM 上下文）
    # 必须在事件循环【之外】做 —— Playwright Sync API 不能在 asyncio loop 里跑。
    ctx = _collect_page_context(items, url, pages=pages)
    page_items, dom_ctx, err = ctx[0], ctx[1], ctx[2]
    collisions = ctx[3] if len(ctx) > 3 else []
    if not page_items:
        raise AiExploreError("页面探测失败且没有备用控件清单 → 拒绝在信息不全时硬猜（会选错控件）。"
                             f"原因：{err}")

    # ② 异步阶段：LLM 语义识别（ChatDeepSeek）
    return asyncio.run(  # type: ignore
        _ai_explore_async(scenario, page_items, url, dom_ctx=dom_ctx,
                          allow_mock_fallback=allow_mock_fallback, page_bg=page_bg, guard=guard,
                          pages=pages, collisions=collisions)
    )


async def _aclose_llm(obj) -> None:
    """兜底：若 LLM 对象自己提供了 `aclose()`/`close()`，就在**本场景的 loop 还活着时**关掉它。

    ⚠️ 别把 `getattr(obj, "_client")` 当客户端用：browser-use 的 `ChatDeepSeek._client`
    是**方法**（每次调用 new 一个 `AsyncOpenAI`），拿到的只是绑定方法，关它毫无意义。
    真正避免「连接池泄漏 + 关 loop 后 GC 报 Event loop is closed」的做法是：
    由我们持有 httpx 连接池（见 `_ai_explore_async` 里注入 `client_params={'http_client': …}`，
    再在 finally 里关闭）。本函数只是给别的 provider 留个兜底口子。
    """
    for name in ("aclose", "close"):
        fn = getattr(obj, name, None)
        if not callable(fn):
            continue
        try:
            r = fn()
            if asyncio.iscoroutine(r):
                await r
            return
        except Exception:
            pass


async def _ai_explore_async(
    scenario: str, page_items: list[dict], url: str, dom_ctx: list[dict] | None = None,
    allow_mock_fallback: bool = False, page_bg: str = "", guard: str = "",
    pages: list[dict] | None = None, collisions: list[dict] | None = None,
) -> ElementMap:
    """【异步阶段】只做 LLM 语义识别：读场景 + 控件清单 + DOM 上下文 → 步骤。

    （页面探测已在 _collect_page_context 里同步完成；这里绝不能碰 Playwright Sync API。）
    """
    import os
    from .config import llm_from_env

    prompt = _build_planner_prompt(scenario, page_items, url, dom_ctx, page_bg=page_bg, guard=guard,
                                   pages=pages, collisions=collisions)
    first_url = (pages[0]["url"] if pages else url)
    obj = llm_from_env()   # ChatDeepSeek(deepseek) / ChatOpenAI 等

    # ★ 连接池由**我们自己**持有并关闭（2026-09-13 批量 --scenario-dir 实测的坑）：
    #   browser-use 的 `ChatDeepSeek._client()` 每次 ainvoke 都 new 一个 AsyncOpenAI，
    #   既不复用也不关闭 ⇒ ① 每次调用白扔一个 httpx 连接池；
    #   ② 那个连接池绑在**本场景的 loop** 上，等它被 GC 时（往往已经是下一个场景的 loop 在跑），
    #      openai 的 `AsyncHttpxClientWrapper.__del__` 会 `create_task(self.aclose())`
    #      ⇒ 在**已关闭的旧 loop** 上关 transport ⇒ stderr 一坨
    #        `Task exception was never retrieved … RuntimeError('Event loop is closed')`。
    #   正解：注入一个我们自己的 httpx 连接池，并在本场景 loop 还活着时显式关闭
    #   （`__del__` 里有 `if self.is_closed: return` ⇒ 关过就彻底安静）。
    http_client = None
    try:
        import httpx
        http_client = httpx.AsyncClient()
        if hasattr(obj, "client_params"):
            obj.client_params = {**(obj.client_params or {}), "http_client": http_client}
        else:
            http_client = None
    except Exception as e:
        http_client = None
        print(f"      [explore] ℹ️ 共享 httpx 连接池未启用（{type(e).__name__}: {e}）"
              f"——识别不受影响，批量模式下可能多几条客户端清理告警")

    # 2026-09-11 实测：DeepSeek 的 function calling 有【间歇性】JSON 解析抖动
    # （同一 prompt 第 1 次成功、第 2 次报 ModelProviderError: Extra data: line 1 column 550），
    # 属上游不稳 ⇒ 带退避重试（HYBRID_LLM_ATTEMPTS 可调），不能一次发抖就判死刑。
    n_attempts = max(1, int(os.environ.get("HYBRID_LLM_ATTEMPTS", "3")))
    last_err = "未拿到可用步骤"

    try:
        for attempt in range(1, n_attempts + 1):
            steps: list[TestStep] = []

            # 路径1：ainvoke(output_format) —— ChatDeepSeek 原生 function calling，最稳
            if hasattr(obj, "ainvoke"):
                try:
                    from browser_use.llm.messages import SystemMessage, UserMessage
                    msgs = [
                        SystemMessage(content="你是 GUI 自动化测试规划师。只输出 JSON。"),
                        UserMessage(content=prompt),
                    ]
                    r = await obj.ainvoke(msgs, output_format=_PlanModel)
                    steps = _plan_to_steps(r.completion, page_items)
                    if not steps:
                        last_err = "结构化输出解析不出步骤"
                except Exception as e:
                    last_err = f"output_format 路径 {type(e).__name__}: {str(e)[:120]}"
                    print(f"      [explore] 第 {attempt}/{n_attempts} 次结构化输出失败 → {last_err}")

            # 路径2：纯文本 + 宽松解析（兼容无 output_format 的 provider；必须用 async 版，
            # 不能再走 asyncio.run 的 _get_llm_text —— 在事件循环里调它会直接 RuntimeError）
            if not steps:
                try:
                    text = await _get_llm_text_async(obj, prompt)
                    steps = _parse_steps_text(text, page_items) if text else []
                    if not steps:
                        last_err = f"文本解析没抽出步骤（返回 {len(text)} 字符）"
                except Exception as e:
                    last_err = f"文本路径 {type(e).__name__}: {str(e)[:120]}"
                    print(f"      [explore] 第 {attempt}/{n_attempts} 次文本解析失败 → {last_err}")

            if steps:
                if attempt > 1:
                    print(f"      [explore] 第 {attempt}/{n_attempts} 次重试成功（上游抖动，重试即恢复）")
                steps = _apply_semantic_calibration(steps, page_items)
                return _finalize_map(first_url, scenario, steps, pages=pages)

            if attempt < n_attempts:
                await asyncio.sleep(1.5 * attempt)      # 退避：抖动/限流通常等一下就好
    finally:
        # 在**本场景自己的 loop 还活着**的时候把连接池关掉：
        # 否则 loop 一关、客户端被 GC，openai 的 __del__ 就会在死 loop 上关 transport，
        # 打出 `Task exception was never retrieved … Event loop is closed` 噪声
        # （--scenario-dir 批量模式实测；不影响结果，但会污染日志）。
        if http_client is not None:
            try:
                await http_client.aclose()
            except Exception:
                pass
        await _aclose_llm(obj)

    # 重试用尽 —— 绝不静默用 mock 冒充 AI 产物（2026-09-11 修复的假 AI 缺陷）
    if not allow_mock_fallback:
        raise AiExploreError(
            f"AI 语义识别失败（已重试 {n_attempts} 次）：{last_err}。"
            "已拒绝用 mock 冒充 AI 产物（不写假 AI 用例）；请检查 key/网络/限流后重试；"
            "若确实要降级成确定性 mock，显式加 --mock-fallback。"
        )
    print("      [explore] ⚠️ LLM 不可用 → 按 --mock-fallback 显式降级为【确定性 mock】"
          "（这不是 AI 产物，不会写入 cases/）")
    steps = mock_explore(scenario, page_items, url).steps
    steps = _apply_semantic_calibration(steps, page_items)
    return _finalize_map(first_url, scenario, steps, pages=pages)


def _get_llm_text(obj, prompt: str) -> str:
    """通用：从 LLM 对象拿文本（兼容 get_client 直调）。"""
    client = getattr(obj, "get_client", None)
    if client is None:
        return ""
    import asyncio
    ac = client() if callable(client) else client
    try:
        resp = asyncio.run(ac.chat.completions.create(
            model=getattr(obj, "model_name", "deepseek-chat"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
        ))
    except Exception:
        return ""
    return (resp.choices[0].message.content or "") if resp.choices else ""


async def _get_llm_text_async(obj, prompt: str) -> str:
    """从 LLM 拿纯文本（**async 版**）——供事件循环内使用。

    为什么单独写一个：原来的 `_get_llm_text` 内部用 `asyncio.run(...)`，而 ai_explore 的
    调用链本身就跑在 `asyncio.run` 里 ⇒ 在协程里再调它会 RuntimeError（被 except 吞掉），
    导致"文本兜底路径"实际是**死代码**（2026-09-11 实测发现）。这里改成 await，兜底才真的兜得住。
    """
    if hasattr(obj, "ainvoke"):
        try:
            from browser_use.llm.messages import SystemMessage, UserMessage
            r = await obj.ainvoke([
                SystemMessage(content="你是 GUI 自动化测试规划师。只输出 JSON。"),
                UserMessage(content=prompt),
            ])
            c = getattr(r, "completion", None)
            if isinstance(c, str):
                return c
            if c is not None:
                return str(c)
        except Exception:
            pass
    client = getattr(obj, "get_client", None)
    if client is None:
        return ""
    ac = client() if callable(client) else client
    resp = await ac.chat.completions.create(
        model=getattr(obj, "model_name", "deepseek-chat"),
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
    )
    return (resp.choices[0].message.content or "") if resp.choices else ""


def _finalize_map(url: str, scenario: str, steps: list[TestStep],
                  pages: list[dict] | None = None) -> ElementMap:
    """补 goto + 构造 ElementMap。

    跨页（P3）：首步 goto 指向**第一页**的 URL（描述带页名）；ElementMap.url 记第一页，
    下游 generate 用它当 base_url。单页时与改造前完全一致。
    """
    first = pages[0] if pages else None
    first_url = first["url"] if first else url
    if steps and steps[0].action != "goto":
        label = f"【{first['name']}】{first_url}" if first else first_url
        steps.insert(0, TestStep(0, "goto", value=first_url, description=f"打开 {label}"))
    return ElementMap(url=first_url, scenario=scenario, steps=steps)


# 触发弹窗的关键词（识别"新建/添加/新增/创建"类按钮 → 点开以探测表单控件）
_MODAL_BUTTON_HINTS = ("新建", "添加", "新增", "创建", "登记", "打开")
# 已探测控件中加入弹窗字段时，跳过与基础控件重复的（按 test_id 去重）
_MODAL_TEST_ID_HINTS = ("inp-", "sel-", "btn-", "modal")
# 「点开会出下一层」的控件关键词（选客户 / 选物料 / 高级查询 这类 picker 层）
_LAYER_OPEN_HINTS = ("选择", "打开", "浏览", "更多", "查询", "查看")
# 绝不去点的（点下去会提交/删除/关掉当前层，探测上下文就毁了）
_LAYER_AVOID_HINTS = ("提交", "确定", "保存", "删除", "取消", "关闭", "返回", "重置", "导出")
# 关卡用的按钮关键词
_LAYER_CLOSE_HINTS = ("取消", "关闭", "返回", "Cancel", "Close")
# 有界：每层最多再展开几个、最多往下钻几层、最多尝试几个候选（防在陌生页面里乱点）
_MAX_LAYER_CLICKS = 2
_MAX_LAYER_DEPTH = 2
_MAX_LAYER_TRIES = 4
# 2026-09-14：点开一层/一个弹窗后，**最长等多久**让新控件出现（轮询间隔）。
# 为什么是「有界轮询」而不是固定 sleep(300)：实测（2026-09-14 00:33，机器内存吃紧、
# 并发在跑 pytest 时）客户列表层的渲染慢于 300ms，探测拿到「没有新控件」⇒ AI 把
# 「从列表里选一行」判成无法绑定的步骤、--verify 因此 FAILED。固定 sleep 两头不讨好：
# 健康机器上白等，拥挤机器上又不够。轮询到就立刻走，最坏只等 _LAYER_RENDER_WAIT_S。
_LAYER_RENDER_WAIT_S = 2.5
_LAYER_POLL_MS = 200


def _try_collect_modal_items(pg, base_items: list[dict]) -> list[dict]:
    """点开「新建类」弹窗 —— **并继续钻进弹窗里嵌的层（picker）** —— 探测其中的控件。

    2026-09-14 扩展（AprilPark1012需求①：客户从下拉框改成「弹出客户列表页里选一行」）：
    原来只探**一层**弹窗 —— 嵌在弹窗之上的 picker 层（客户列表）里的控件对 AI
    **完全不可见**：AI 既不知道列表长什么样，也不知道该点哪一行的「选择」，
    于是「从列表里选一个」这种最常见的企业 UI 直接没法测。现在：
      ① 点开弹窗后，从弹窗控件里挑「选择/打开/查询」类按钮继续点开下一层；
      ② 每点开一层就重新探测，把**新出现**的可见控件并入结果（不再按 test_id 白名单卡死，
         否则 pick-c1 这种命名会被过滤掉）；
      ③ 钻完把这一层关掉、最后把弹窗也关掉，页面恢复干净状态。
    有界（≤2 层、每层 ≤2 次点击）+ 排除提交/删除/取消类关键词 —— 绝不在陌生页面上乱点。
    失败只影响"少一份控件清单"，不打断探测，但**不静默**：打印原因。
    """
    from .probe import probe_page
    collected: list[dict] = []
    seen_names = {it.get("semantic_name") for it in base_items}
    seen_ids = {_item_identity(it) for it in base_items}

    def _absorb(items: list[dict]) -> list[dict]:
        """把探测到的新控件并入结果，返回本次新增的。

        去重口径（2026-09-14 修）：**先按元素身份（test_id / role+name+placeholder）去重，再看语义名**。
        只按语义名去重会漏掉这种真问题：同一个按钮在不同探测轮次里**名字会变**
        （只开弹窗时叫「取消」，再开一层后同一个按钮变成「取消@新建合同」）⇒ 同一个元素被收两遍，
        AI 看到一个不存在的"重复按钮"，生成的 locator 也会指向同一个元素。
        """
        fresh = []
        for it in items:
            sn, ident = it.get("semantic_name"), _item_identity(it)
            if not sn or sn in seen_names or ident in seen_ids:
                continue
            seen_names.add(sn)
            seen_ids.add(ident)
            collected.append(it)
            fresh.append(it)
        return fresh

    try:
        opener = next((it for it in base_items
                       if it.get("role") == "button"
                       and any(h in (it.get("name") or "") for h in _MODAL_BUTTON_HINTS)), None)
        if opener is None:
            return []
        btn = pg.get_by_role("button", name=opener.get("name"))
        if btn.count() != 1:
            return []
        btn.first.click()

        # ---- 第 1 层：弹窗本体（沿用原有 test_id 特征过滤 ⇒ 老页面行为不变）----
        # 2026-09-14：固定 sleep(300) → 有界轮询（弹窗渲染可能慢于 300ms，见 _LAYER_RENDER_WAIT_S 注释）
        modal_items: list[dict] = []
        deadline = time.monotonic() + _LAYER_RENDER_WAIT_S
        while True:
            modal_items = _absorb([x for x in probe_page(pg)
                                   if x.get("test_id") and x["test_id"].startswith(_MODAL_TEST_ID_HINTS)])
            if modal_items or time.monotonic() >= deadline:
                break
            pg.wait_for_timeout(_LAYER_POLL_MS)
        if not modal_items:
            print(f"      [explore] ℹ️ 点开「{_one_line(opener.get('name') or '')}」后"
                  f"没有任何弹窗控件出现（不是弹窗？或页面响应太慢）→ 跳过弹窗补充")
            return []

        # ---- 第 2..N 层：弹窗里嵌的 picker 层 ----
        for _ in range(_MAX_LAYER_DEPTH - 1):
            # 只把**按钮/链接**当"打开下一层"的候选：原生 select 的名字常带「请选择」会误入候选，
            # 但点它并不会新增可见 DOM（实测把点击预算吃光，真正的「选择客户」没轮到）。
            # 下拉的可选项本身已由 probe 的 name（拼接 option 文本）覆盖，不靠点开。
            cands = [it for it in collected
                     if it.get("role") in ("button", "link")
                     and not any(a in (it.get("name") or "") for a in _LAYER_AVOID_HINTS)
                     and any(h in (it.get("name") or "") for h in _LAYER_OPEN_HINTS)]
            if not cands:
                break
            opened = 0
            for cand in cands[:_MAX_LAYER_TRIES]:       # 尝试次数与"成功层数"分开计数
                if opened >= _MAX_LAYER_CLICKS:
                    break
                if _open_layer_and_collect(pg, cand, _absorb):
                    opened += 1
            if not opened:
                break
        _close_layer_by_item(pg, collected)          # 收尾：把弹窗/层关掉，页面恢复干净
    except Exception as e:
        hint = "" if _page_alive(pg) else "（页面/渲染进程已失效：崩溃或被 OOM 杀 → 环境事故）"
        print(f"      [explore] ⚠️ 弹窗/弹层探测中断（{type(e).__name__}: {str(e)[:120]}）"
              f"—— 已收集 {len(collected)} 项，层内控件可能缺失{hint}")
    return collected


def _item_identity(it: dict) -> str:
    """元素身份（跨探测轮次稳定）：test_id 优先，否则 role+name+placeholder+text。"""
    tid = (it.get("test_id") or "").strip()
    if tid:
        return f"tid:{tid}"
    return "sig:" + "|".join(str(it.get(k) or "") for k in ("role", "name", "placeholder", "text"))


def _one_line(s: str, n: int = 40) -> str:
    """把控件名压成一行：原生 select 的 name 里带换行，直接打印会把日志搞成一团。"""
    return " ".join((s or "").split())[:n]


def _page_alive(pg) -> bool:
    """页面/渲染进程还活着吗（2026-09-14 加）。

    为什么要单独判：内存吃紧时内核 OOM killer 会把 chrome-headless 渲染进程干掉
    （本机 1.87G / 无 swap，实测 2026-09-14 00:33 连杀两个 chrome + 一个 hermes），
    此时 Playwright 报的是 "Target crashed"。如果笼统写成「点开后没有新控件（不是弹层？）」，
    就会把**环境事故**伪装成**业务结论** —— 正是最坑人的那种日志。
    """
    try:
        if pg.is_closed():
            return False
        pg.evaluate("1")
        return True
    except Exception:
        return False


def _wait_fresh_items(pg, absorb, timeout_s: float = _LAYER_RENDER_WAIT_S) -> list[dict]:
    """点开一层后，**有界轮询**直到探测到新控件；返回新增清单（超时则为空）。

    取代原来的固定 pg.wait_for_timeout(300)（理由见 _LAYER_RENDER_WAIT_S 注释）。
    一轮都探不到时不会立刻放弃：最多轮询到 timeout_s，探到就立刻返回。
    """
    from .probe import probe_page
    deadline = time.monotonic() + timeout_s
    while True:
        fresh = absorb(probe_page(pg))
        if fresh or time.monotonic() >= deadline:
            return fresh
        pg.wait_for_timeout(_LAYER_POLL_MS)


def _open_layer_and_collect(pg, cand: dict, absorb) -> bool:
    """点开一个「下一层」候选控件，把新出现的控件吸收进来；返回是否真打开了新层。

    打开后立刻用该层内的「取消/关闭」按钮（按 test_id 精确定位 —— 页面上同名「取消」往往有多个）
    把这一层关掉，避免层叠影响后续点击。
    ⚠️ 失败必须**打印原因**：以前这里静默 return False，导致「层没探到」和「层里啥也没有」
    在日志上长得一模一样（2026-09-14 实测踩到：客户列表层没被收集，日志里一点线索都没有）。
    """
    from .probe import probe_page
    role, name, test_id = cand.get("role"), cand.get("name") or "", cand.get("test_id") or ""
    shown = _one_line(name)
    try:
        loc = pg.get_by_test_id(test_id) if test_id else pg.get_by_role(role, name=name)
        n = loc.count()
        if n != 1:
            print(f"      [explore] ℹ️ 弹层候选「{shown}」命中 {n} 个（要求唯一）→ 跳过")
            return False
        loc.first.click()
        fresh = _wait_fresh_items(pg, absorb)
        if not fresh:
            if not _page_alive(pg):
                print(f"      [explore] ⚠️ 点开「{shown}」后页面/渲染进程已失效（标签崩溃或被 OOM 杀掉）"
                      f"—— 这不是「没有弹层」，是环境事故，本层控件会缺失")
            else:
                print(f"      [explore] ℹ️ 点开「{shown}」后没有出现新的可见控件（不是弹层？）→ 跳过")
            return False
        print(f"      [explore] 弹层探测：点开「{shown}」→ 新收集 {len(fresh)} 个控件"
              f"（{', '.join(_one_line(x.get('semantic_name', ''), 18) for x in fresh[:4])}…）")
        _close_layer_by_item(pg, fresh)
        return True
    except Exception as e:
        hint = "" if _page_alive(pg) else "（页面/渲染进程已失效：崩溃或被 OOM 杀 → 环境事故，不是页面没有弹层）"
        print(f"      [explore] ⚠️ 弹层探测失败（{shown}）：{type(e).__name__}: {str(e)[:140]}{hint}")
        return False


def _close_layer_by_item(pg, items: list[dict]) -> None:
    """用给定控件清单里的「取消/关闭」按钮把当前层关掉（有 test_id 才对，避免同名点错）。"""
    closer = next((x for x in items
                   if x.get("role") == "button" and x.get("test_id")
                   and any(h in (x.get("name") or "") for h in _LAYER_CLOSE_HINTS)), None)
    if not closer:
        return
    try:
        loc = pg.get_by_test_id(closer["test_id"])
        if loc.count() == 1 and loc.first.is_visible():
            loc.first.click()
            pg.wait_for_timeout(200)
    except Exception:
        pass


def _merge_items(base: list[dict], extra: list[dict]) -> list[dict]:
    """合并基础控件清单 + 弹窗控件清单，按 semantic_name 去重。"""
    seen = {it.get("semantic_name") for it in base}
    out = list(base)
    for it in extra:
        if it.get("semantic_name") not in seen:
            out.append(it)
            seen.add(it["semantic_name"])
    return out


# 采集"完整版 DOM 上下文"用的交互元素选择器（加上 dropdown/select/combobox 等）
_DOM_INTERACTIVE_SELECTOR = (
    "button, input, select, textarea, a, "
    "[role=button], [role=textbox], [role=checkbox], [role=link], "
    "[role=combobox], [role=radio], [role=menuitem], [role=tab], [role=option]"
)


def _collect_dom_context(pg) -> list[dict]:
    """用 Playwright 抓"完整版 DOM 上下文"，供 AI 判别控件。

    比 probe 的语义清单更"全"：额外拿到全局索引(idx)、可见性(visible)、
    启用/可编辑状态(disabled/readonly)、可访问名(aria_label) —— 这些
    正是 AI 在复杂/弹窗页面判别"该选哪个控件"时的关键依据。
    """
    try:
        return pg.evaluate(
            f"""() => {{
              const list = [];
              const sels = "{_DOM_INTERACTIVE_SELECTOR}";
              document.querySelectorAll(sels).forEach((el,i) => {{
                const r = el.getBoundingClientRect();
                const style = getComputedStyle(el);
                list.push({{
                  idx: i,
                  tag: el.tagName.toLowerCase(),
                  role: el.getAttribute('role') ||
                        (el.tagName==='INPUT' && (el.type==='checkbox'?'checkbox':el.type==='button'?'button':'textbox')) ||
                        (el.tagName==='BUTTON'?'button': el.tagName==='SELECT'?'combobox': el.tagName==='A'?'link':'') ,
                  test_id: el.getAttribute('data-testid') || '',
                  placeholder: el.getAttribute('placeholder') || '',
                  aria_label: el.getAttribute('aria-label') || el.getAttribute('title') || '',
                  text: (el.textContent||'').trim().slice(0,60),
                  name: (el.getAttribute('aria-label') || (el.textContent||'').trim().slice(0,40)),
                  visible: r.width>0 && r.height>0 && style.visibility!=='hidden' && style.display!=='none',
                  disabled: !!el.disabled,
                  readonly: !!el.readOnly,
                }});
              }});
              return list;
            }}"""
        )
    except Exception:
        return []


def _build_planner_prompt(scenario: str, items: list[dict], url: str,
                         dom_ctx: list[dict] | None = None,
                         page_bg: str = "", guard: str = "",
                         pages: list[dict] | None = None,
                         collisions: list[dict] | None = None) -> str:
    """构造给 LLM 的规划提示：自然语言场景 + probe 语义清单 + 富 DOM 上下文，要求产出轻量步骤 JSON。

    page_bg / guard：来自 scenario 文件（见 framework/scenario.py）——
      page_bg 是【页面背景】（页面说明+前置条件+领域上下文），guard 是【本场景断言护栏】。
    两者都拼进提示，把"断言必须操作前可确定"从通用规则升级为每场景专属硬约束。

    pages（P3 跨页）：≥2 页时提示里加【页面清单】+ 按页分组的控件清单 + 跨页规则；
      单页/不给 → 提示与改造前**逐字一致**（老链路行为不变）。
    """
    multi = bool(pages and len(pages) > 1)
    if multi:
        lines = [f"你是 GUI 自动化测试规划师。**本场景跨 {len(pages)} 个页面**，按下面顺序执行："]
        for i, pg in enumerate(pages, 1):
            one = f"  {i}. 【{pg['name']}】{pg['url']}"
            if pg.get("page"):
                one += f" —— {pg['page']}"
            lines.append(one)
        prompt = ("\n".join(lines) + "\n"
                  + f"自然语言测试场景: 「{scenario}」\n\n"
                  + "跨页规则（**必须遵守**）：\n"
                  + "  · 每个控件都有 `page` 字段，标出它属于哪一页 —— **只能操作当前所在页面的控件**；\n"
                  + "  · 换页用 action=goto + value=<页面清单里的该页 URL>，"
                    "或点击当前页上能跳过去的目标（如结果行里可点的编号/详情链接）；\n"
                  + "  · **换页必须有断言**（证明\"确实到了那一页\"）："
                    "action=expect_url + value=**逐字从上面页面清单里复制**该页 URL 里真实存在的片段"
                    "（如详情页写 contract_detail —— 只出现在目标页 URL 里的片段；"
                    "⚠️ **禁止**用 localhost / localhost:8000 / 127.0.0.1 这类**每个页面都含**的片段"
                    "当换页证据：点击前后都能通过 = 没验到换页，框架会直接拦下这种用例），"
                    "**禁止自造片段**（写 index.html / list 这类清单里没有的字符串就会直接失败）；"
                    "或 action=expect_text + assertion=目标页的特征文本（更稳，推荐与 expect_url 一起用；**目标页没有独有 URL 片段时改用它**，如列表页就是根路径 /）；\n")
        if collisions:
            prompt += ("跨页同名控件（同名的已自动加 @页名 后缀，清单里的名字即最终名，原样引用即可）：\n"
                       + "\n".join(f"  - {c['semantic_name']} → "
                                   + "、".join(f"{c['semantic_name']}@{p}" for p in c["pages"])
                                   for c in collisions) + "\n")
        prompt += "\n"
    else:
        prompt = (
            f"你是 GUI 自动化测试规划师。目标页面: {url}\n"
            f"自然语言测试场景: 「{scenario}」\n\n"
        )

    # 控件清单：跨页时按页分组（每页限额，防 prompt 膨胀）；单页保持原样
    if multi:
        by_page: dict[str, list[dict]] = {}
        for it in items:
            by_page.setdefault(it.get("page") or "", []).append(it)
        budget_per_page = max(8, 60 // max(1, len(pages)))
        prompt += "页面已探测出以下可交互控件（**已按页分组**，只有这些可用，绝不自己编造 selector）:\n"
        for pg in pages:
            grp = by_page.get(pg["name"]) or []
            prompt += (f"【{pg['name']}】{json.dumps(grp[:budget_per_page], ensure_ascii=False, indent=1)}\n")
        prompt += "\n"
    else:
        prompt += (
            f"页面已探测出以下可交互控件（只有这些可用，绝不自己编造 selector）:\n"
            f"{json.dumps(items[:60], ensure_ascii=False, indent=1)}\n\n"
        )
    # 场景文件带来的两块增量（内联模式下为空，行为与从前完全一致）
    if page_bg:
        prompt += f"页面背景（来自场景文件，供你判断控件语义与数据规则）:\n{page_bg}\n\n"
    if guard:
        prompt += (f"本场景断言护栏（**优先级高于下面的通用规则**，必须遵守）:\n{guard}\n\n")
    # 富 DOM 上下文：给 AI 额外的可见性/状态/索引，判断"该选哪个"更准
    if dom_ctx:
        prompt += (
            f"额外 DOM 上下文（含全局索引 idx / 可见性 visible / 状态 disabled,readonly；"
            f"同名控件务必用 visible + 邻近文本综合判断是否为目标）:\n"
            f"{json.dumps(dom_ctx[:80], ensure_ascii=False, indent=1)}\n\n"
        )
    prompt += (
        f"请把场景规划成【JSON 步骤】，格式（严格按此，不要多余字段）:\n"
        f'{{"steps": [{{"order":1,"action":"fill","semantic_name":"<清单里的semantic_name>",'
        f'"value":"填的值","assertion":"断言文本","description":"一句话说明"}}]}}\n\n'
        f"规则:\n"
        f"1. action 只允许: goto / click / fill / check / select / expect_text / expect_url / press_enter\n"
        f"2. semantic_name 必须**原样复制**上面清单里的 semantic_name（含下划线，如 请输入合同名称 / "
        f"请选择_0021_0451_1031），禁止自造、禁止写你自己的描述性名字（“合同名称”≠`请输入合同名称`）；\n"
        f"   fill / select / check / press_enter 这些表单步骤**必须**给 semantic_name，绝不允许留空；\n"
        f"   多个同名控件时用 nearby_text / visible / container_heading / label 区分；"
        f"business_context 里的字段人话名只是帮你理解，最终仍要填清单里的 semantic_name\n"
        f"2b. **区域消歧**：多个控件语义相似时（例如两个都含 c1/c2/c3/c4 的下拉），\n"
        f"   用 container_heading（所属区块标题）与 label（字段标签）判断哪个在你要操作的那个区域里；\n"
        f"   场景里说『打开弹窗填写表单』时，就选 container_heading=该弹窗标题、label=该字段名的那个控件，\n"
        f"   不要选列表页上方的筛选控件（它们的 container_heading 是页面标题或空）\n"
        f"3. fill 需给 value；断言类步骤用 expect_text + assertion\n"
        f"4. 只输出 JSON，不要解释、不要 markdown 代码块\n"
        f"5. expect_text / expect_url 步骤**不要**给 semantic_name —— 断言的是页面结果，不是某个控件；expect_url 用 value 给 URL 片段（如 contract_detail），expect_text 用 assertion 给文本\n"
        f"6. assertion 必须是【操作之后页面上出现的结果文本】(如搜索结果/新出现的列表项)，"
        f"**不得与任何 fill 的 value 相同** —— 否则只是验证了「输入回显」，属于假绿\n"
        f"7. assertion 必须是【操作前就能确定的文本】：页面固定文案（列表标题/状态前缀/表头），\n"
        f"   或按页面数据规则可推出的记录标识（如清单里 合同编号=HT-1007、名称=合同7 这类）。\n"
        f"   严禁出现只能在运行时才知道的内容 —— 「共 N 条」「命中 N 条」等计数、时间戳、随机值，\n"
        f"   你无法算出正确数字，写进 assertion 就是猜，会直接导致用例失败或假绿\n"
        f"8. assertion 里的关键文本（如记录编号/名称）必须能在上面的控件清单或 DOM 上下文中找到依据，\n"
        f"   找不到依据就不要写断言，宁可不写 expect_text 步骤\n"
    )
    return prompt


def _parse_steps_text(text: str, items: list[dict]) -> list[TestStep]:
    """宽松解析 LLM 返回的步骤文本：容忍前后有杂字、markdown、单双引号混用。

    不依赖 browser-use 的 ActionModel schema —— 只认我们约定的轻量 steps JSON。
    """
    import re
    if not text:
        return []
    # 找最外层 JSON（允许被 ```json ... ``` 包裹）
    candidates = re.findall(r"\{[\s\S]*\}", text)
    data = None
    for blob in candidates:
        candidate = blob
        # 剥掉可能的 markdown 代码块围栏
        m = re.search(r"```(?:json)?[\s\S]*?```", candidate)
        if m:
            candidate = m.group(0).replace("```json", "").replace("```", "")
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict) and "steps" in parsed:
                data = parsed
                break
        except Exception:
            continue
    steps: list[TestStep] = []
    if not data:
        return steps
    unmatched: list[str] = []
    for s in data.get("steps", []):
        sn = (s.get("semantic_name") or "").strip()
        it, how = _match_item(sn, items)      # 文本兜底路径同样不静默丢元素
        if it is not None and how.startswith("模糊"):
            print(f"      [explore] ⚠️ 元素名自动对齐：{how}")
        if sn and it is None:
            unmatched.append(f"{s.get('action', 'click')} 的 semantic_name={sn!r}")
        el = None
        if it:
            el = ElementRef(
                semantic_name=it.get("semantic_name"), role=it.get("role"), name=it.get("name"),
                placeholder=it.get("placeholder"), text=it.get("text"),
                test_id=it.get("test_id"),
                nearby_text=it.get("nearby_text"),
                container_heading=it.get("container_heading"),
                help_text=it.get("help_text"),
            )
        steps.append(TestStep(
            order=int(s.get("order", len(steps) + 1)),
            action=s.get("action", "click"),
            element=el,
            value=s.get("value"),
            assertion=s.get("assertion"),
            description=s.get("description", ""),
        ))
    if unmatched:
        print(f"      [explore] ⚠️ 有 {len(unmatched)} 步的元素名不在探测清单里（无法定位）：{unmatched}")
        print(f"      [explore]    清单可用名字：{[x.get('semantic_name') for x in items]}")
    return steps


# 方向①语义校准：AI 的 description 是否和它选中的元素语义一致
SEMANTIC_MIN_SIM = 0.3   # 低于此重叠度 → 判"AI 可能选错控件"，降 conf + 打警告
# desc 侧要剔的"纯动作动词"（这些是'做了什么'，不是控件名；元素语义侧不剔，
# 因为元素语义里的"提交/搜索/选择"正是控件名，剔了会误伤）。
_ACTION_WORDS_STRIP = ("输入", "点击", "选择", "查看", "打开", "填写", "按下", "回车",
                      "在", "然后", "并", "再", "请", "和", "与", "或", "的", "了", "还", "后", "前")


def _semantic_sim(text_a: str, text_b: str) -> float:
    """核心词元重叠度：把两段文字处理成字符级词元集合，看交集占比。

    text_a 通常为 AI 的 desc（动作句，剔动词），text_b 为元素语义串（保留控件名）。
    """
    import re
    a = _to_char_set(text_a, strip_actions=True)
    b = _to_char_set(text_b, strip_actions=False)
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / max(1, min(len(a), len(b)))


def _to_char_set(text: str, strip_actions: bool = False) -> set[str]:
    """去标点/空格；strip_actions=True 时再剔纯动作动词（仅 desc 侧用）。"""
    import re
    s = text or ""
    s = re.sub(r"[\s，。！？、,.!?；;：:()（）\"'“”‘’「」『』]+", "", s)
    if strip_actions:
        for w in _ACTION_WORDS_STRIP:
            s = s.replace(w, "")
    return set(s)


def _element_semantics_blob(it: dict) -> str:
    """把元素字典的关键语义拼成一个串，供与 AI 比对。"""
    return " ".join(x for x in [
        it.get("placeholder") or "",
        it.get("text") or "",
        it.get("name") or "",
        it.get("aria_label") or "",
        it.get("label") or "",
        it.get("nearby_text") or "",
        it.get("container_heading") or "",
    ] if x)


def _apply_semantic_calibration(steps: list[TestStep], items: list[dict]) -> list[TestStep]:
    """方向①：AI 挑完元素后，用其 description(自然语言) 与元素自身语义比对。

    注意：AI 的 description 是"动作句"（如 输入/点击），元素语义是"控件名词"
    （如 placeholder/搜索），两者语法层不同。所以先提取 desc 的【核心控件词】，
    再与元素语义比对相似度 —— 这样"在搜索框输入'合同1'"才匹配得上"搜索框"。
    不匹配(<SEMANTIC_MIN_SIM) → 打警告，但不硬拦（靠 Tier1/Tier2 兜底）。
    """
    for st in steps:
        if st.element is None or not st.description:
            continue
        it = next((x for x in items if x.get("semantic_name") == st.element.semantic_name), None)
        if it is None:
            continue
        sim = _semantic_sim(st.description, _element_semantics_blob(it))
        if sim < SEMANTIC_MIN_SIM:
            st.element.notes = (
                f"[语义校准警告] AI 描述《{st.description}》与所选控件语义重叠度仅 {sim:.2f}"
                f"(<{SEMANTIC_MIN_SIM})，疑似选错控件，请人工核对"
            )
            print(f"      [语义校准⚠] step{st.order} 「{st.description}」 "
                  f"vs 控件语义 重叠度 {sim:.2f} → 疑似选错")
    return steps
