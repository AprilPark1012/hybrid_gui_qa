"""视觉 grounding 兜底（A+ 档能力 ③）—— 只在确定性定位**都失败**时才调一次。

## 为什么需要

a11y / 默认选择器看不见的控件（裸 div、canvas、图标按钮）会让 AI 得出"这里不能点"。
能力②（`clickable_probe`）把这些元素**补进清单**；但补进来的元素仍然可能定位不到
（没有稳定属性、没有锚点）。这时唯一还剩的客观信息就是**像素**：
把截图交给多模态模型要一个坐标，点它，然后**校验点完有没有变化**。

实测（2026-10-31，本机 1280x800 演示页，真值由 DOM 给出）：

| 模型 | 任务 | 输出（0-1000 归一化） | 换算像素 | 偏差 | 是否命中 |
|---|---|---|---|---|---|
| GLM-5.3-Flash | 定位「某个按钮」 | (500, 351) | (640.0, 280.8) | 0.8 px | 命中 |
| GLM-4.6V（关思考） | 4 个同名按钮里定位指定那一行 | (412, 656) | (527.4, 524.8) | 8.7 px | 命中 |

## 四条纪律

1. **不是主路径**：调用方只在确定性定位失败后调它，且开关默认受 `HYBRID_VISION_GROUNDING` 控制。
2. **坐标是 0-1000 归一化**：必须按**截图实际尺寸**换算，不能当像素用（Qwen 系还报过整体偏移）。
3. **点了必须校验**（铁律 18「做了 != 生效了」）：点完签名没变 => 报 `no-effect`，绝不报成功。
4. **失败不抛、只报原因**：拿不到坐标就返回 `ok=False` + `reason`，把决定权交回调用方。

## 实测踩到的坑（写进代码，别再踩）

* **思考模式会吃满 token 预算**：`max_tokens` 给小了，额度全烧在 `reasoning_content` 上、
  `content` 返回**空字符串且 HTTP 200** —— 静默失败。这里对空返回做一次**收紧提示词的重试**，
  仍空则如实报 `empty-content`。
* **套餐不等于模型清单**：GLM Coding Plan 不覆盖全部模型（`glm-4.6v-flash` 实测 429/1309）。
  模型名走配置，别在代码里写死某个型号。
"""
from __future__ import annotations

import base64
import json
import os
import re
import time
from typing import Any, Callable

__all__ = [
    "NORM_MAX",
    "norm_to_px",
    "parse_point",
    "grounding_enabled",
    "VisionGrounding",
]

# 模型坐标系口径（0-1000，左上原点）
NORM_MAX = 1000

# 提示词：只问坐标、只许 JSON。静态策略进这里，别掺业务词。
_PROMPT = (
    "这是一张网页截图，尺寸 {w}x{h} 像素。请定位「{desc}」。"
    "把目标控件的**中心点**坐标按 0-1000 归一化返回，"
    "输出格式严格为 JSON：{{\"x\": <0-1000 的整数>, \"y\": <0-1000 的整数>}}。"
    "只输出这个 JSON，不要解释、不要代码块围栏。"
)

_PROMPT_STRICT = (
    "只输出一个 JSON 对象，形如 {{\"x\": 500, \"y\": 300}}，数值是 0-1000 归一化坐标。"
    "目标：{desc}。不要任何其它文字。"
)

_JSON_RE = re.compile(r"\{[^{}]*\"x\"\s*:\s*-?\d+(?:\.\d+)?[^{}]*\"y\"\s*:\s*-?\d+(?:\.\d+)?[^{}]*\}"
                      r"|\{[^{}]*\"y\"\s*:\s*-?\d+(?:\.\d+)?[^{}]*\"x\"\s*:\s*-?\d+(?:\.\d+)?[^{}]*\}")
_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def grounding_enabled(default_env: str = "HYBRID_VISION_GROUNDING") -> bool:
    """开关：`HYBRID_VISION_GROUNDING=0` 即关（**默认开**，但它只在兜底路径上被调用）。"""
    return (os.environ.get(default_env, "1") or "1").strip() != "0"


def norm_to_px(nx: float, ny: float, width: int, height: int) -> tuple[int, int]:
    """0-1000 归一化坐标 -> 像素坐标（夹在有效范围内，绝不产生越界点击）。

    换算口径：`x_px = round(nx / 1000 * (width - 1))` —— 用 `width - 1` 是因为
    像素坐标最大合法值是 `width - 1`（`0 .. width-1` 共 width 个点）。
    """
    if width <= 0 or height <= 0:
        raise ValueError("width/height 必须为正: %r x %r" % (width, height))
    px = int(round(float(nx) / NORM_MAX * (width - 1)))
    py = int(round(float(ny) / NORM_MAX * (height - 1)))
    px = max(0, min(width - 1, px))
    py = max(0, min(height - 1, py))
    return px, py


def parse_point(text: str | None) -> tuple[float, float] | None:
    """从模型回复里抠出 (x, y) 归一化坐标；抠不出来返回 None（**绝不猜**）。

    容忍的形态（都实测见过）：纯 JSON、```json 围栏、`<tool_call>` 包裹、
    先给一句解释再给 JSON、键顺序颠倒。只剩两个裸数字时按「先 x 后 y」理解。
    """
    if not text:
        return None
    s = str(text)
    m = _JSON_RE.search(s)
    if m:
        try:
            obj = json.loads(m.group(0))
            return float(obj["x"]), float(obj["y"])
        except Exception:                                          # noqa: BLE001
            pass
    # 退化：整段里恰好两个数字（"坐标是 (640, 280)" 这类）
    nums = _NUM_RE.findall(s)
    if len(nums) >= 2:
        try:
            return float(nums[0]), float(nums[1])
        except Exception:                                          # noqa: BLE001
            return None
    return None


def _png_b64(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def _default_llm_call(png: bytes, prompt: str) -> str:             # pragma: no cover - 真网络
    """走框架**唯一 LLM 入口**（`llm_from_env`）发一次多模态请求，返回文本回复。

    同步封装：Explorer 侧是 async，而 Playwright 这里是 sync。

    **必须另起一个线程跑事件循环**（实测踩过）：在 sync Playwright 的主线程里直接
    `asyncio.run()` 会撞上 `asyncio.run() cannot be called from a running event loop`
    （sync API 自己就占着主线程的事件循环），报出来还只是个光秃秃的 RuntimeError。
    开线程 => 新循环 => 与 Playwright 互不干扰；也不用 nest_asyncio 那种黑魔法。
    """
    import asyncio
    import concurrent.futures

    from framework.shared.config import llm_from_env
    from browser_use.llm.messages import (UserMessage, ContentPartTextParam,
                                          ContentPartImageParam, ImageURL)

    msg = UserMessage(content=[
        ContentPartImageParam(image_url=ImageURL(url=_png_b64(png))),
        ContentPartTextParam(text=prompt),
    ])
    model = llm_from_env()

    async def _run():
        res = await model.ainvoke([msg])
        return getattr(res, "completion", None) or ""

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(_run())).result()


class VisionGrounding:
    """在某个 page 上做「看截图 -> 要坐标 -> 点击 -> 校验生效」。

    `llm_call` 可注入（判据用假实现，零网络）；默认走 `_default_llm_call`。
    """

    def __init__(self, page: Any, *,
                 llm_call: Callable[[bytes, str], str] | None = None,
                 enabled: bool | None = None,
                 click: bool = True):
        self.page = page
        self._llm_call = llm_call or _default_llm_call
        self.enabled = grounding_enabled() if enabled is None else enabled
        self._allow_click = click

    # ---------------------------------------------------------------- 内部

    def _signature(self) -> tuple:
        """页面签名（用于「点了到底有没有生效」的后置校验）。取不到就返回空签名。"""
        try:
            url = str(self.page.url)
        except Exception:                                          # noqa: BLE001
            url = ""
        try:
            # 签名必须覆盖「表单状态」：只填输入框不改 innerText、也不增删节点，
            # 用 [文本长度, 节点数] 会判成"没变化" -> 把成功误报成 no-effect（实测踩过）。
            info = self.page.evaluate(
                "() => {"
                " const els = document.querySelectorAll('input,textarea,select');"
                " let vlen = 0, vsum = 0;"
                " els.forEach(e => { const v = String(e.value || ''); vlen += v.length;"
                "                     for (let i = 0; i < v.length; i++) vsum = (vsum * 31 + v.charCodeAt(i)) % 1000000007; });"
                " return [document.body ? document.body.innerText.length : 0,"
                "         document.querySelectorAll('*').length, vlen, vsum,"
                "         document.querySelectorAll('[aria-expanded=true],[aria-selected=true]').length];"
                " }")
            return (url,) + tuple(int(x) for x in info)
        except Exception:                                          # noqa: BLE001
            return (url, -1, -1)

    def _ask(self, png: bytes, w: int, h: int, desc: str) -> tuple[str, str]:
        """先按标准提示词问；拿到空回复时**收紧提示词再问一次**（思考模式吃 token 的兜底）。"""
        first = self._llm_call(png, _PROMPT.format(w=w, h=h, desc=desc))
        if (first or "").strip():
            return first, "first"
        second = self._llm_call(png, _PROMPT_STRICT.format(desc=desc))
        return second or "", "retry-strict"

    # ---------------------------------------------------------------- 对外

    def locate(self, description: str) -> dict:
        """只看不点：返回定位结果（含归一化坐标、像素坐标、耗时与原因）。"""
        desc = (description or "").strip()
        if not self.enabled:
            return {"ok": False, "reason": "disabled"}
        if not desc:
            return {"ok": False, "reason": "empty-description"}
        started = time.time()
        try:
            png = self.page.screenshot(type="png")
        except Exception as exc:                                   # noqa: BLE001
            return {"ok": False, "reason": "screenshot-failed: %s" % type(exc).__name__}
        try:
            size = self.page.viewport_size or {}
            w, h = int(size.get("width") or 0), int(size.get("height") or 0)
        except Exception:                                          # noqa: BLE001
            w = h = 0
        if w <= 0 or h <= 0:
            # 视口未知时按截图**自身**的像素尺寸算（更准：截图就是模型看到的那张图）。
            # 直接读 PNG 的 IHDR（std 偏移 16/20 各 4 字节大端）—— 不引 PIL、也不开文件句柄：
            # 少一个依赖，也避开「文本模式 open() 缺 encoding」这条跨平台红线。
            try:
                if png[:8] != b"\x89PNG\r\n\x1a\n" or png[12:16] != b"IHDR":
                    raise ValueError("not a png")
                w = int.from_bytes(png[16:20], "big")
                h = int.from_bytes(png[20:24], "big")
            except Exception:                                      # noqa: BLE001
                return {"ok": False, "reason": "viewport-unknown"}
        try:
            raw, path_used = self._ask(png, w, h, desc)
        except Exception as exc:                                   # noqa: BLE001
            return {"ok": False, "reason": "llm-error: %s" % type(exc).__name__,
                    "elapsed_ms": int((time.time() - started) * 1000)}
        if not (raw or "").strip():
            return {"ok": False, "reason": "empty-content", "path": path_used,
                    "elapsed_ms": int((time.time() - started) * 1000)}
        pt = parse_point(raw)
        if pt is None:
            return {"ok": False, "reason": "parse-failed", "raw": raw[:200],
                    "elapsed_ms": int((time.time() - started) * 1000)}
        px, py = norm_to_px(pt[0], pt[1], w, h)
        return {"ok": True, "reason": "ok", "path": path_used,
                "x_norm": pt[0], "y_norm": pt[1], "px": [px, py],
                "size": [w, h], "raw": raw[:200],
                "elapsed_ms": int((time.time() - started) * 1000)}

    def click(self, description: str, *, settle_ms: int = 800) -> dict:
        """定位 + 点击 + **后置校验**（点完页面签名没变就报 `no-effect`，绝不报成功）。"""
        hit = self.locate(description)
        if not hit.get("ok"):
            return hit
        if not self._allow_click:
            hit["clicked"] = False
            return hit
        before = self._signature()
        px, py = hit["px"]
        try:
            self.page.mouse.click(px, py)
        except Exception as exc:                                   # noqa: BLE001
            hit.update({"ok": False, "reason": "click-failed: %s" % type(exc).__name__})
            return hit
        try:
            self.page.wait_for_timeout(settle_ms)
        except Exception:                                          # noqa: BLE001
            pass
        after = self._signature()
        hit["clicked"] = True
        hit["signature_changed"] = (before != after)
        if not hit["signature_changed"]:
            hit.update({"ok": False, "reason": "no-effect"})
        return hit
