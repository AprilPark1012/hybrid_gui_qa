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
        return None, f"探测 {url} 失败（{type(e).__name__}）⇒ 视为『未声明可并发隔离』"
    if not isinstance(body, dict) or "partitioned" not in body:
        return None, f"{url} 响应里没有 partitioned 字段 ⇒ 视为『未声明可并发隔离』"
    if body.get("partitioned"):
        return True, f"{url} 声明 partitioned=true（presets={body.get('presets')}）"
    return False, f"{url} 明确声明 partitioned=false"
