"""动作后的「等页面就绪」—— **框架侧唯一实现**（P22 批 3 · 缺口 1b）。

为什么需要：demo 的「切换为订单管理员」实现是 `location.reload()`（`demo/auth.js:130`）；
而生成物的 `_act` 以前只有 `loc.click()`、之后**不等任何状态** ⇒ 紧接着的步骤落在旧文档上 /
新页面还没渲染完 ⇒ 竞态（假红，或更糟的假绿）。

⚠️ **为什么必须先确认"导航发生过"、再等 ready 标记**（2026-09-29 实测踩到，代价 = V2 两条判据红）：
   朴素写法 `click()` 之后直接 `wait_for_function(ready === '1')`，会被**旧文档**的现成标记
   立刻满足 —— 那时 reload 还没发生 ⇒ 读到的是切换**前**的角色。
   实证：同一轮里「切完读角色」= 超级管理员（错），而「再 goto 一次业务页」= 订单管理员（对）。
   ⇒ 判据必须建立在"确实发生过主框架导航"之上。

口径：**只在真的发生导航时才付等待成本** —— 有界 400ms 短探，没导航立即返回（不进固定 sleep）。

单一来源：生成物模板（`generator._CONFTEST_TEMPLATE` 的 `_wait_after_action` 只做转发）与
二类脚本（`verify_role_switch_click.py`）都走这里 —— 不许两处各写一份。
"""
from __future__ import annotations

import time

READY_SELECTOR = "body[data-hybrid-ready='1']"
DEFAULT_READY_TIMEOUT_MS = 15000


def wait_after_action(page, probe_ms: int = 400, ready_timeout_ms: int | None = None) -> bool:
    """动作之后若页面发生导航/重载，等它就绪。

    :param probe_ms: 短探窗口（毫秒）—— 这段时间内没观察到主框架导航就直接返回。
    :param ready_timeout_ms: 等就绪标记的上限（默认 15s，与生成物的 `HYBRID_READY_TIMEOUT` 同源）。
    :return: True = 确实观察到导航并等过一次就绪；False = 没导航（零/极少额外开销）。
    """
    navs: list = []

    def _on_nav(frame):
        try:
            if frame == page.main_frame:
                navs.append(1)
        except Exception:                                          # noqa: BLE001
            pass

    try:
        page.on("framenavigated", _on_nav)
        deadline = time.time() + (probe_ms / 1000.0)
        while time.time() < deadline and not navs:
            page.wait_for_timeout(50)
        if navs:
            page.wait_for_selector(READY_SELECTOR,
                                   timeout=int(ready_timeout_ms or DEFAULT_READY_TIMEOUT_MS),
                                   state="attached")
        return bool(navs)
    except Exception:                                              # noqa: BLE001
        return bool(navs)
    finally:
        try:
            page.remove_listener("framenavigated", _on_nav)
        except Exception:                                          # noqa: BLE001
            pass
