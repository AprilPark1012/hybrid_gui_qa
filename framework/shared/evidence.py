"""失败取证（CDP 证据包）—— A+ 档能力 ①（2026-10-31）。

## 为什么需要

失败时「只有一句 LLM 的文本理由」等于没有证据：报给开发、报给客户都答不上
「为什么失败」。而 Playwright 本身**不需要换驱动**就能拿到 Chrome DevTools Protocol：
`context.new_cdp_session(page)` 是官方口子，实测一次 `Accessibility.getFullAXTree` 拿
941 个节点只用 130ms、`Performance.getMetrics` 一并可取 —— 开销可忽略。

## 边界（写进文档，别让下一个人误解）

* **只 Chromium 系可用**。Firefox / WebKit 上 `new_cdp_session` 会抛，本模块**降级为
  `supported=False` + 给出原因**，绝不报错退出、也不假装拿到了数据。
* **事件数量有上限**（`MAX_EVENTS`），超了截断并留痕（`truncated=True`）——
  证据包是给人看的，不是 HAR 全集；无界收集会把内存和磁盘一起吃掉。
* **不取响应体**（`getResponseBody`）：代价高、体积大、且最容易夹带凭据。需要时按
  `requestId` 单独取（留给后续能力）。

## 硬规矩：证据包本身不许成为泄密源

网络事件的请求头 / 响应头里常有 `Authorization` / `Cookie` / `Set-Cookie` / `X-Api-Key`。
证据包会被落盘、被打进交付件、被转发给第三方 —— 所以**所有头一律过 `redact_headers`**，
敏感值替换成 `<redacted>`（保留键名，便于判断"有没有用它"）。

这一点必须有判据守着（并且要负向自证）：只写注释不写判据 = 迟早被人改回去。
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = [
    "SENSITIVE_HEADERS",
    "MAX_EVENTS",
    "redact_headers",
    "CdpEvidence",
    "capture",
]

# 敏感头（小写比较；命中即整值替换）
SENSITIVE_HEADERS = (
    "authorization",
    "cookie",
    "set-cookie",
    "proxy-authorization",
    "x-api-key",
    "x-auth-token",
    "x-csrf-token",
    "x-xsrf-token",
)

# 每类事件的条数上限（截断留痕，不做无界收集）
MAX_EVENTS = 300

# 无障碍树最多留多少个节点的摘要（整棵树太大，摘要够定位问题）
AX_TOP_ROLES = 15


def redact_headers(headers: dict | None) -> dict:
    """把敏感头的**值**替换成 `<redacted>`，键名保留（大小写不敏感匹配）。

    为什么保留键名：排障时要判断「这个请求到底有没有带鉴权」，只看"有没有用"而不看值。
    """
    out: dict = {}
    for k, v in (headers or {}).items():
        if str(k).strip().lower() in SENSITIVE_HEADERS:
            out[k] = "<redacted>"
        else:
            out[k] = v
    return out


def _clip(text: object, limit: int = 400) -> str:
    s = str(text if text is not None else "")
    return s if len(s) <= limit else s[:limit] + "...(truncated)"


@dataclass
class CdpEvidence:
    """挂在某个 page 上的取证器（Chromium 系）。用法：`start()` -> 跑用例 -> `collect()`。"""

    page: Any
    max_events: int = MAX_EVENTS
    supported: bool = False
    reason: str = ""
    console: list = field(default_factory=list)
    exceptions: list = field(default_factory=list)
    network: list = field(default_factory=list)
    failed_requests: list = field(default_factory=list)
    truncated: bool = False
    _session: Any = None

    # ---------------------------------------------------------------- 生命周期

    def start(self) -> bool:
        """连上 CDP 并开始收集。返回是否可用（不可用不抛错，只置 `supported=False`）。"""
        try:
            self._session = self.page.context.new_cdp_session(self.page)
        except Exception as exc:                                   # noqa: BLE001
            self.supported = False
            self.reason = "cdp-unavailable: %s" % (type(exc).__name__,)
            return False
        for method, params in (
            ("Network.enable", {}),
            ("Runtime.enable", {}),
            ("Log.enable", {}),
        ):
            try:
                self._session.send(method, params)
            except Exception:                                      # noqa: BLE001
                continue                                           # 单个域不可用不影响其它
        self._bind()
        self.supported = True
        self.reason = "ok"
        return True

    def _bind(self) -> None:
        sess = self._session
        if sess is None:
            return

        def _console(ev):                                          # Runtime.consoleAPICalled
            if len(self.console) >= self.max_events:
                self.truncated = True
                return
            args = []
            for a in (ev.get("args") or [])[:6]:
                args.append(_clip(a.get("value", a.get("description", a.get("type")))))
            self.console.append({"type": ev.get("type"), "text": _clip(" ".join(args), 600)})

        def _exception(ev):                                        # Runtime.exceptionThrown
            if len(self.exceptions) >= self.max_events:
                self.truncated = True
                return
            det = (ev.get("exceptionDetails") or {})
            exc = (det.get("exception") or {})
            self.exceptions.append({
                "text": _clip(exc.get("description") or det.get("text")),
                "url": det.get("url", ""),
                "line": det.get("lineNumber"),
            })

        def _request(ev):                                          # Network.requestWillBeSent
            if len(self.network) >= self.max_events:
                self.truncated = True
                return
            req = ev.get("request") or {}
            self.network.append({
                "requestId": ev.get("requestId", ""),
                "method": req.get("method", ""),
                "url": _clip(req.get("url"), 300),
                "type": ev.get("type", ""),
                "headers": redact_headers(req.get("headers")),
            })

        def _response(ev):                                         # Network.responseReceived
            # 只回填到已有请求上（不另立条目），避免同一请求占两条
            rid = ev.get("requestId", "")
            for it in reversed(self.network[-50:]):
                if it.get("requestId") == rid:
                    it["status"] = (ev.get("response") or {}).get("status")
                    it["respHeaders"] = redact_headers((ev.get("response") or {}).get("headers"))
                    return

        def _failed(ev):                                           # Network.loadingFailed
            if len(self.failed_requests) >= self.max_events:
                self.truncated = True
                return
            self.failed_requests.append({
                "requestId": ev.get("requestId", ""),
                "errorText": _clip(ev.get("errorText"), 200),
                "type": ev.get("type", ""),
            })

        def _log(ev):                                              # Log.entryAdded
            if len(self.console) >= self.max_events:
                self.truncated = True
                return
            entry = ev.get("entry") or {}
            self.console.append({"type": "log:%s" % entry.get("level", ""),
                                 "text": _clip(entry.get("text"), 600)})

        for event, cb in (
            ("Runtime.consoleAPICalled", _console),
            ("Runtime.exceptionThrown", _exception),
            ("Network.requestWillBeSent", _request),
            ("Network.responseReceived", _response),
            ("Network.loadingFailed", _failed),
            ("Log.entryAdded", _log),
        ):
            try:
                sess.on(event, cb)
            except Exception:                                      # noqa: BLE001
                continue

    # ---------------------------------------------------------------- 采集

    def snapshot(self) -> dict:
        """一次性快照：性能指标 + 无障碍树摘要（不依赖之前收集的事件）。"""
        out: dict = {"performance": {}, "accessibility": {}, "errors": []}
        sess = self._session
        if sess is None:
            return out
        try:
            sess.send("Performance.enable", {})
            metrics = sess.send("Performance.getMetrics", {}).get("metrics") or []
            out["performance"] = {m.get("name"): m.get("value") for m in metrics}
        except Exception as exc:                                   # noqa: BLE001
            out["errors"].append("performance: %s" % type(exc).__name__)
        try:
            tree = sess.send("Accessibility.getFullAXTree", {})
            nodes = tree.get("nodes") or []
            roles: dict = {}
            unnamed = 0
            for n in nodes:
                role = ((n.get("role") or {}).get("value") or "")
                roles[role] = roles.get(role, 0) + 1
                if role in ("button", "link", "textbox", "checkbox") and not (n.get("name") or {}).get("value"):
                    unnamed += 1
            top = sorted(roles.items(), key=lambda kv: (-kv[1], kv[0]))[:AX_TOP_ROLES]
            out["accessibility"] = {
                "node_count": len(nodes),
                "top_roles": [{"role": r, "count": c} for r, c in top],
                "unnamed_interactive": unnamed,
            }
        except Exception as exc:                                   # noqa: BLE001
            out["errors"].append("accessibility: %s" % type(exc).__name__)
        return out

    def collect(self) -> dict:
        """产出证据包（dict）。不写盘 —— 写盘交给 `write()`，便于调用方决定落点。"""
        bundle = {
            "supported": self.supported,
            "reason": self.reason,
            "limits": {"max_events": self.max_events, "truncated": self.truncated},
            "console": self.console[: self.max_events],
            "exceptions": self.exceptions[: self.max_events],
            "network": self.network[: self.max_events],
            "failed_requests": self.failed_requests[: self.max_events],
            "counts": {
                "console": len(self.console),
                "exceptions": len(self.exceptions),
                "network": len(self.network),
                "failed_requests": len(self.failed_requests),
            },
        }
        bundle.update(self.snapshot())
        return bundle

    def write(self, outdir: str | os.PathLike, name: str = "evidence") -> Path:
        """把证据包写成 JSON（UTF-8，`ensure_ascii=False` 便于人读）。"""
        d = Path(outdir)
        d.mkdir(parents=True, exist_ok=True)
        path = d / ("%s.json" % name)
        path.write_text(json.dumps(self.collect(), ensure_ascii=False, indent=2),
                        encoding="utf-8")
        return path


def capture(page, outdir: str | os.PathLike | None = None,
            name: str = "evidence", recorder: "CdpEvidence | None" = None) -> dict:
    """抓一份证据包（可用时写盘），返回 dict。

    **重要契约（实测踩过）**：`capture(page)` **拿不到历史事件** ——
    console / network 只能从 `start()` 那一刻开始收，写完页面再新建取证器必然是空列表。
    所以两种用法：

    * 要事件：先 `ev = CdpEvidence(page); ev.start()`，跑用例，失败时
      `capture(page, outdir=..., recorder=ev)`；
    * 只要快照（性能指标 + 无障碍树摘要）：`capture(page)` 就够（这两个是当场查的，与历史无关）。

    非 Chromium 环境下返回 `supported=False` + 原因，**不抛错**（取证不该把用例搞挂）。
    """
    ev = recorder if recorder is not None else CdpEvidence(page)
    if recorder is None:
        ev.start()
    bundle = ev.collect()
    if outdir:
        try:
            Path(outdir).mkdir(parents=True, exist_ok=True)
            (Path(outdir) / ("%s.json" % name)).write_text(
                json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:                                          # noqa: BLE001
            pass                                                   # 写不了盘不影响返回值
    return bundle
