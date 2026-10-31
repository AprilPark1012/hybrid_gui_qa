# -*- coding: utf-8 -*-
"""一类判据：**失败取证（CDP 证据包）**（A+ 档能力 1，2026-10-31）。

## 守的是什么

失败时"只有一段 AI 的文本理由"等于没有证据。`framework/shared/evidence.py` 用
`context.new_cdp_session(page)` 抓 console / 异常 / network / 性能 / 无障碍树摘要，落成证据包。

三条口径必须被守住（否则这个能力会变成新的坑）：

1. **降级不报错**：Firefox / WebKit 上 `new_cdp_session` 会抛 -> `supported=False` + 原因，
   绝不把用例搞挂、也绝不假装拿到了数据。
2. **有界收集**：事件条数有上限，超了截断并留痕（`truncated=True`）；
   无界收集会把内存和磁盘一起吃光。
3. **证据包不许成为泄密源**：请求头/响应头里的 `Authorization` / `Cookie` / `Set-Cookie` /
   `X-Api-Key` 一律脱敏。这条**必须有判据**，光写注释迟早被改回去。

## 这些判据证明什么 / 不证明什么

* 证明：脱敏、降级、截断、事件聚合四条行为，且**负向自证过**
  （把脱敏摘掉 -> 判据当场红）；
* 不证明：真浏览器上 CDP 一定连得上 —— 那属于二类（需要 demo + Chromium），不在这里假绿。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from framework.shared import evidence as EV                                          # noqa: E402


# --------------------------------------------------------------- 替身

class _FakeSession:
    """最小 CDP session 替身：记录 enable 调用、按需回放事件。"""

    def __init__(self, metrics=None, ax_nodes=None):
        self.sent: list[tuple[str, dict]] = []
        self.handlers: dict[str, list] = {}
        self._metrics = metrics if metrics is not None else [{"name": "Nodes", "value": 10}]
        self._ax = {"nodes": ax_nodes if ax_nodes is not None else []}

    def send(self, method, params=None):
        self.sent.append((method, params or {}))
        if method == "Performance.getMetrics":
            return {"metrics": self._metrics}
        if method == "Accessibility.getFullAXTree":
            return self._ax
        return {}

    def on(self, event, cb):
        self.handlers.setdefault(event, []).append(cb)

    def fire(self, event, payload):
        for cb in self.handlers.get(event, []):
            cb(payload)


class _FakeContext:
    def __init__(self, session):
        self._session = session

    def new_cdp_session(self, page):
        if self._session is None:
            raise RuntimeError("不支持 CDP")
        return self._session


class _FakePage:
    def __init__(self, session):
        self.context = _FakeContext(session)


# --------------------------------------------------------------- 脱敏（含负向自证）

def test_sensitive_headers_are_redacted_case_insensitively():
    out = EV.redact_headers({"authorization": "Bearer SENTINEL-1",
                             "Cookie": "sid=SENTINEL-2",
                             "Set-Cookie": "sid=SENTINEL-3",
                             "X-Api-Key": "SENTINEL-4",
                             "X-Trace-Id": "keep-me"})
    assert out["authorization"] == "<redacted>"
    assert out["Cookie"] == "<redacted>"
    assert out["Set-Cookie"] == "<redacted>"
    assert out["X-Api-Key"] == "<redacted>"
    assert out["X-Trace-Id"] == "keep-me", "[NG] 非敏感头不许被动"
    joined = json.dumps(out, ensure_ascii=False)
    assert "SENTINEL" not in joined, "[NG] 证据里出现明文凭据: %s" % joined


def test_redact_keeps_key_names():
    """保留键名的理由：排障要判断"这个请求有没有带鉴权"，只看有没有用、不看值。"""
    out = EV.redact_headers({"Authorization": "x"})
    assert "Authorization" in out


def test_network_event_headers_are_redacted_in_bundle():
    """端到端（内存级）：事件里带凭据 -> 证据包里必须看不到明文。"""
    sess = _FakeSession()
    ev = EV.CdpEvidence(_FakePage(sess))
    assert ev.start() is True
    sess.fire("Network.requestWillBeSent", {
        "requestId": "r1", "type": "XHR",
        "request": {"method": "POST", "url": "http://x/api",
                    "headers": {"Authorization": "Bearer SENTINEL-9", "Accept": "*/*"}},
    })
    bundle = ev.collect()
    text = json.dumps(bundle, ensure_ascii=False)
    assert "SENTINEL-9" not in text, "[NG] 证据包里带了明文凭据"
    assert bundle["network"][0]["headers"]["Accept"] == "*/*"


def test_response_headers_are_redacted_in_bundle():
    sess = _FakeSession()
    ev = EV.CdpEvidence(_FakePage(sess))
    ev.start()
    sess.fire("Network.requestWillBeSent", {"requestId": "r2",
                                           "request": {"method": "GET", "url": "http://x"}})
    sess.fire("Network.responseReceived", {"requestId": "r2",
                                          "response": {"status": 200,
                                                       "headers": {"Set-Cookie": "sid=SENTINEL-8"}}})
    text = json.dumps(ev.collect(), ensure_ascii=False)
    assert "SENTINEL-8" not in text, "[NG] 响应头凭据没脱敏"
    assert ev.collect()["network"][0]["status"] == 200


# --------------------------------------------------------------- 降级不报错

def test_unsupported_browser_degrades_without_raising():
    """Firefox / WebKit 上会抛 —— 取证器必须降级，不许把用例搞挂。"""
    ev = EV.CdpEvidence(_FakePage(None))
    assert ev.start() is False
    bundle = ev.collect()
    assert bundle["supported"] is False
    assert "cdp-unavailable" in bundle["reason"]
    assert bundle["counts"]["network"] == 0


def test_capture_never_raises_on_unsupported(tmp_path):
    bundle = EV.capture(_FakePage(None), outdir=tmp_path, name="ev")
    assert bundle["supported"] is False
    written = (tmp_path / "ev.json")
    assert written.exists(), "[NG] 降级时也应留下证据文件（含原因）"
    assert json.loads(written.read_text(encoding="utf-8"))["supported"] is False


def test_capture_uses_given_recorder_instead_of_a_fresh_one():
    """契约：传了 `recorder` 就必须用它。

    为什么钉这条（实测踩过）：先 `start()` 收了事件、再调 `capture(page)`，
    后者内部又新建一个取证器 -> **事件全丢、counts 全 0**，而接口看起来"成功了"。
    """
    sess = _FakeSession()
    page = _FakePage(sess)
    rec = EV.CdpEvidence(page)
    rec.start()
    sess.fire("Runtime.consoleAPICalled", {"type": "error", "args": [{"value": "boom"}]})
    bundle = EV.capture(page, recorder=rec)
    assert bundle["counts"]["console"] == 1, "[NG] 传进来的 recorder 没被使用"


def test_capture_without_recorder_still_gives_snapshot():
    """一次性调用拿不到历史事件（只能当场查快照）—— 行为要有判据兜着，别被误用。"""
    sess = _FakeSession(metrics=[{"name": "Nodes", "value": 5}])
    bundle = EV.capture(_FakePage(sess))
    assert bundle["supported"] is True
    assert bundle["performance"]["Nodes"] == 5
    assert bundle["counts"]["console"] == 0


# --------------------------------------------------------------- 有界收集

def test_events_are_capped_and_truncation_is_recorded():
    sess = _FakeSession()
    ev = EV.CdpEvidence(_FakePage(sess), max_events=3)
    ev.start()
    for i in range(10):
        sess.fire("Runtime.consoleAPICalled", {"type": "log", "args": [{"value": "m%d" % i}]})
    bundle = ev.collect()
    assert bundle["counts"]["console"] == 3, "[NG] 上限没生效: %r" % (bundle["counts"],)
    assert bundle["limits"]["truncated"] is True, "[NG] 截断必须留痕"


# --------------------------------------------------------------- 快照与写盘

def test_snapshot_reports_metrics_and_ax_summary():
    sess = _FakeSession(metrics=[{"name": "Nodes", "value": 1216}],
                        ax_nodes=[{"role": {"value": "button"}, "name": {"value": "OK"}},
                                  {"role": {"value": "button"}, "name": {"value": ""}}])
    ev = EV.CdpEvidence(_FakePage(sess))
    ev.start()
    snap = ev.snapshot()
    assert snap["performance"]["Nodes"] == 1216
    assert snap["accessibility"]["node_count"] == 2
    assert snap["accessibility"]["unnamed_interactive"] == 1


def test_write_is_utf8_and_readable(tmp_path):
    sess = _FakeSession()
    ev = EV.CdpEvidence(_FakePage(sess))
    ev.start()
    sess.fire("Runtime.exceptionThrown",
              {"exceptionDetails": {"text": "空指针", "url": "http://x", "lineNumber": 3}})
    path = ev.write(tmp_path, name="fail_case")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["exceptions"][0]["text"] == "空指针"
    assert data["counts"]["exceptions"] == 1


def test_events_aggregate_into_one_request_entry():
    """同一个 requestId 的 request/response 必须合成一条，不许同一请求占两条。"""
    sess = _FakeSession()
    ev = EV.CdpEvidence(_FakePage(sess))
    ev.start()
    sess.fire("Network.requestWillBeSent", {"requestId": "r3",
                                           "request": {"method": "GET", "url": "http://y"}})
    sess.fire("Network.responseReceived", {"requestId": "r3", "response": {"status": 500,
                                                                          "headers": {}}})
    assert len(ev.network) == 1, "[NG] 同一请求被记成了多条: %r" % (ev.network,)
