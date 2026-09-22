"""被测目标能力探针（F6b）—— 回答一个问题：这个目标**能不能并发跑**？

背景（2026-09-14 团队演示实测）：用例并发跑的前提是「每个 worker 读写自己的数据分区」。
目标支持分区（例如本项目 demo 的 /api/health 返回 partitioned=true，且 /api/* 认 ?w=<worker>）
→ 可以并发；不支持或探测不到 → **保守降级为 1 并发**，因为「多 worker 共享一份状态」会让
精确计数断言互相踩（本机已复现：期望 20 行实得 23、期望 4 条实得 6）。

设计口径（与用户「开关开了就要好用」一致）：
- 探测到支持 → 放行请求的并发数，并在日志里写明依据；
- 探测到不支持 → 降级为 1，并说明「为什么」与「要并发该怎么做」（--isolated-target）；
- 探测不到（没有 /api/health、非本项目目标）→ 同样保守降级，但提示是「未声明」而非「不支持」。
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

DEFAULT_BASE = "http://localhost:8000"


def _base_url(explicit: str | None = None) -> str:
    """目标基地址：显式参数 > HYBRID_BASE_URL > 复位接口推断 > demo 默认。"""
    for cand in (explicit, os.environ.get("HYBRID_BASE_URL"), None):
        if cand:
            return str(cand).rstrip("/")
    reset = (os.environ.get("HYBRID_RESET_URL") or "").strip()
    if reset and reset.lower() not in ("off", "0", "none", "no", "false"):
        from urllib.parse import urlsplit, urlunsplit
        u = urlsplit(reset)
        return urlunsplit((u.scheme, u.netloc, "", "", ""))
    return DEFAULT_BASE


def unreachable_hint(base: str, reason: object = None) -> str:
    """「连不上」的**统一文案** —— 先给动作（起 demo），再给真实原因。

    ⚠️ 为什么不再按「字符串里含 refused」分流（2026-09-22 修，AprilPark1012 本地 Windows 实测）：
    同一个「端口没人听」在 Linux 抛 `ConnectionRefusedError`，在 **Windows 抛 `TimeoutError`**
    ⇒ 老写法只覆盖了 Linux，在 Windows 上恰好把「另开一个窗口跑 `python -m demo.app`」这句
    **唯一的下一步指引**丢掉了 ⇒ 用户看到的仍是「看着像框架坏了」——正是 G2 要治的现象，
    却在 Windows 上没治住。
    ⇒ 口径改成：**任何**连不上（拒连 / 超时 / DNS / 泛 OSError）都给同一句；
    原因只作括注细节（`TimeoutError: timed out` 这类信息仍保留，便于排查）。
    """
    if reason is None:
        detail = "原因未明"
    else:
        detail = f"{type(reason).__name__}: {reason}" if str(reason) else type(reason).__name__
    return (f"连不上 {base}（{detail}）⇒ 被测目标没起："
            f"另开一个窗口跑 `python -m demo.app`（默认 8000）；"
            f"目标在别的地址就设 HYBRID_BASE_URL")


def probe_failed_hint(base: str, err: object) -> str:
    """兜底文案：原因不明时**也给动作**，但把「目标没起」写成条件（不硬下结论）。"""
    return (f"探测 {base} 失败（{type(err).__name__}: {err}）⇒ 若确认目标没起，"
            f"先跑 `python -m demo.app`（默认 8000）再试")


def reachability(url: str | None = None, timeout: float = 1.5) -> tuple[bool, str]:
    """目标是否**可达**。返回 (ok, 人话理由)。

    为什么单独一个函数（2026-09-15，F3 同源）：probe/generate 以前直接 `page.goto(TARGET_URL)`，
    目标没起时甩出一屏 Playwright traceback（`net::ERR_CONNECTION_REFUSED`）+ exit 1 ——
    既吵又误导（看着像框架坏了，其实是「demo 没启动」）。而且旧的 `probe_partitioned`
    把「连不上」和「有响应但没声明分区」混成同一句『未声明可并发隔离』⇒ 归因错位。
    这里统一口径：**先回答「活没活」，再谈能力**。

    ⚠️ 2026-09-22：连不上时的文案统一走 `unreachable_hint()`（跨平台，任何连不上都给动作）。
    """
    base = (url or _base_url()).rstrip("/")
    target = base + "/api/health"
    try:
        with urllib.request.urlopen(target, timeout=timeout) as r:
            return True, f"{base} 可达（/api/health → HTTP {r.status}）"
    except urllib.error.HTTPError as e:
        # 有响应 ⇒ 目标活着，只是没有 /api/health（老目标 / 非本项目目标）
        return True, f"{base} 可达（/api/health → HTTP {e.code}，无该接口）"
    except urllib.error.URLError as e:
        return False, unreachable_hint(base, getattr(e, "reason", e))
    except (TimeoutError, OSError) as e:
        # Windows 上「端口没人听」到这里（不走 URLError 包装）：详情见 unreachable_hint
        return False, unreachable_hint(base, e)
    except Exception as e:
        return False, probe_failed_hint(base, e)


def probe_partitioned(base: str | None = None, timeout: float = 1.5) -> tuple[bool | None, str]:
    """探测目标是否支持「按 worker 分区」。

    返回 (True/False/None, 人类可读理由)：
      True  = 支持（可放心并发）
      False = 明确声明不支持（必须串行）
      None  = 没有这个探针接口 ⇒ 未声明（保守按不支持处理）
    """
    url = _base_url(base) + "/api/health"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            body = json.loads(r.read().decode("utf-8", "replace") or "{}")
    except Exception as e:                       # 连不上 / 404 / 不是 JSON —— 一律视为"未声明"
        # 先分清「目标没起」和「目标起了但没这个接口」——两者对使用者的下一步完全不同
        ok, why = reachability(_base_url(base))
        if not ok:
            return None, f"目标不可达（{why}）⇒ 视为『未声明可并发隔离』"
        return None, f"探测 {url} 失败（{type(e).__name__}）⇒ 视为『未声明可并发隔离』"
    if not isinstance(body, dict) or "partitioned" not in body:
        return None, f"{url} 响应里没有 partitioned 字段 ⇒ 视为『未声明可并发隔离』"
    if body.get("partitioned"):
        return True, f"{url} 声明 partitioned=true（presets={body.get('presets')}）"
    return False, f"{url} 明确声明 partitioned=false"
