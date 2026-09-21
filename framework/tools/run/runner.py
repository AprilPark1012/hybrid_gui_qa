"""【Playwright】确定性回归执行引擎（Phase 3 自愈闭环版）

职责：在真实浏览器里，对 ElementMap 的每一步：
  1. resolve_locator() 分层唯一性校验（Tier1 语义 / Tier2 指纹）
  2. 定位失败时不中断，交给 Healer 自愈（再协商 / 业务兜底 / 可审 diff）
  3. 执行动作 + web-first 断言（expect 自动重试）
  4. 默认开 trace，失败/成功都留证据

自愈边界（防 false heal / 不掩盖真 bug）：
  - 自愈只修 locator 漂移；若业务断言不过 → 判定疑似真 bug，如实报错。
  - 每条 heal 都落盘成可审 diff（output/heals/），绝不静默改写。

✔ 本文件不含 LLM 调用（Healer 的 LLM 重猜是可选路径）。
"""
from __future__ import annotations
from playwright.sync_api import sync_playwright, expect
from framework.tools.probe.element_map import ElementMap, TestStep
from framework.tools.probe.locator_bridge import resolve_locator
from framework.tools.run.healer import Healer
from framework.tools.common.config import TRACE_DIR
from framework.tools.common.browser import launch_opts


def _run_step(page, t: TestStep, log, healer: Healer):
    a = t.action
    if a == "goto":
        page.goto(t.value or "http://localhost:8000")
        log(f"goto        -> {t.value}")
        return

    if a == "expect_text":
        assert t.assertion, "expect_text 步骤缺少断言文本"
        # AI 规划的断言常是【自然语言片段】（非完整文本），需支持子串匹配：
        # 先试精确，找不到再退到"包含该片段"的非精确匹配（web-first 自动重试）。
        loc = page.get_by_text(t.assertion, exact=True)
        try:
            loc.first.wait_for(timeout=3000)
        except Exception:
            loc = page.get_by_text(t.assertion, exact=False)
            loc.first.wait_for(timeout=5000)
        expect(loc).to_be_visible()          # web-first：自动重试
        log(f"assert_text -> {t.assertion!r}  ✓")
        return

    if t.element is None:
        log(f"skip        -> {a} (无目标元素)")
        return

    # 分层定位；失败进入自愈闭环
    resolved = resolve_locator(page, t.element)
    if not resolved["ok"]:
        healed = healer.try_heal(page, t)
        if not healed["recovered"]:
            raise RuntimeError(
                f"[{t.order}] {t.element.semantic_name} 定位失败且自愈未成功: "
                f"{healed.get('reason') or '未知'}。请补 data-testid 或人工确认。"
            )
        loc = healed["locator_obj"]
        log(f"[HEAL ✓] {t.element.semantic_name} 自愈 -> {healed['strategy']} "
            f"conf={healed['confidence']} ({healed['result']})")
    else:
        loc = resolved["locator_obj"]
        tag = "fingerprint-heal" if resolved.get("healed") else "exact"
        if resolved.get("healed"):
            healer.record_heal(t, resolved)      # 指纹自愈也进可审 diff
            log(f"[HEAL ✓] {t.element.semantic_name} 指纹自愈 -> {resolved['strategy']} "
                f"conf={resolved['confidence']}")
        log(f"{a:<10} -> {t.element.semantic_name} "
            f"[{resolved['strategy']} {tag} conf={resolved['confidence']}]")

    if a == "click":
        loc.click()
    elif a == "fill":
        loc.fill(t.value or "")
    elif a == "select":
        loc.select_option(t.value or "")
    elif a == "check":
        loc.check()
    elif a == "press_enter":
        loc.press("Enter")
    else:
        raise NotImplementedError(f"未知动作: {a}")


def run_scenario(m: ElementMap, headless: bool = True, save_trace: bool = True) -> list[str]:
    """执行 ElementMap 的完整场景，返回执行日志。默认开 trace + 自愈闭环。"""
    lines: list[str] = []
    log = lambda s: (lines.append(s), print(f"  [PLAYWRIGHT] {s}"))  # noqa: E731
    healer = Healer()

    print(f"\n===== [PLAYWRIGHT 确定性执行] 场景: {m.scenario} =====")
    with sync_playwright() as p:
        browser = p.chromium.launch(**launch_opts(headless=headless))
        context = browser.new_context()
        if save_trace:
            context.tracing.start(screenshots=True, snapshots=True, sources=False)
        page = context.new_page()
        try:
            for t in m.steps:
                _run_step(page, t, log, healer)
            print("      ✓ 全部步骤通过")
        except Exception as e:
            # 若发生过自愈但场景仍失败 → 提示疑似真 bug（不掩盖回归）
            if healer.events:
                print(f"      ✗ 场景失败，但期间发生 {len(healer.events)} 次自愈 "
                      f"→ 疑似真 bug 或自愈点错，请人工确认 heal diff")
            print(f"      ✗ 执行失败: {e}")
            raise
        finally:
            if healer.events:
                paths = healer.dump()
                print(f"      [heal] 自愈记录(diff) -> {paths}")
            if save_trace:
                TRACE_DIR.mkdir(parents=True, exist_ok=True)
                # trace 文件名带场景 + 时间戳：多次 run_scenario 不再互相覆盖（原为固定 latest_trace.zip）
                import datetime as _dt
                import re as _re
                # 用 [^\w]+ 而非 [^0-9A-Za-z]+ —— \w 在 py3 是 Unicode 感知，能保留中文场景名
                _slug = _re.sub(r"[^\w]+", "_", (m.scenario or "scenario")).strip("_")[:24] or "scenario"
                trace_path = TRACE_DIR / f"trace_{_dt.datetime.now():%Y%m%d_%H%M%S}_{_slug}.zip"
                context.tracing.stop(path=str(trace_path))
                print(f"      [trace] 已保存 -> {trace_path}")
            browser.close()
    return lines


if __name__ == "__main__":
    from framework.tools.probe.probe import probe_page
    with sync_playwright() as p_:
        b = p_.chromium.launch(**launch_opts(headless=True))
        pg = b.new_page()
        pg.goto("http://localhost:8000")
        items = probe_page(pg)
        b.close()
    print(f"探测到 {len(items)} 个交互元素")
