"""目标可达性预检的回归测试（V7.5.1，G2）。

背景（2026-09-15 实测）：demo 没起时 `cli probe` 直接 `page.goto()` ⇒ 一屏 Playwright traceback
（`net::ERR_CONNECTION_REFUSED`）+ exit 1，现象像「框架坏了」，其实只是一句「demo 没启动」。
同时旧 `probe_partitioned` 把「连不上」和「有响应但没声明分区」混成同一句『未声明』⇒ 归因错位。

判据：
  ① 端口没人听 ⇒ 判不可达，且话里给出下一步（起 demo）
  ② 目标活着（哪怕 /api/health 404） ⇒ 判可达（不能把「老目标」误判成死）
  ③ 并发闸的归因要把两种情况分开
  ④ `cli probe` 在不可达时 **exit 2 + 人话**，且**不启 Playwright**（测试里用假模块兜住）

跑法（秒级，只起 stdlib 小服务，不启浏览器）：
    cd ~/hybrid_gui_qa && source .venv/bin/activate
    python -m pytest frameworkTest/test_target_reachability.py -v
"""
from __future__ import annotations

import contextlib
import socket
import sys
import threading
import types
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from framework import cli
from framework.tools.common.target_probe import probe_partitioned, reachability   # noqa: E402


def _free_port() -> int:
    """拿一个当前没人听的端口（bind 后立刻关闭）。"""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class _HealthHandler(BaseHTTPRequestHandler):
    partitioned = True
    status = 200

    def do_GET(self):                                        # noqa: N802
        if self.path != "/api/health":
            self.send_error(404)
            return
        body = b'{"partitioned": true, "presets": 20}' if self.partitioned else b'{"ok": 1}'
        self.send_response(self.status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):                    # 静音
        pass


@contextlib.contextmanager
def _server(handler=_HealthHandler):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}"
    finally:
        srv.shutdown()
        srv.server_close()


# ---------- 一、可达性判定 ----------

def test_reachable_when_target_is_up():
    with _server() as base:
        ok, why = reachability(base, timeout=2)
    assert ok is True
    assert "可达" in why


def test_unreachable_when_nothing_listens():
    """★ 核心：端口没人听 ⇒ 判不可达，并且**话里带下一步动作**（不是一句「失败」）。"""
    ok, why = reachability(f"http://127.0.0.1:{_free_port()}", timeout=2)
    assert ok is False
    assert "demo.app" in why, f"不可达时必须告诉用户先起 demo：{why}"


def test_target_alive_even_without_health_endpoint():
    """老目标/非本项目目标：/api/health 404 也说明**它活着**，不许误判成死。"""
    class _NoHealth(_HealthHandler):
        def do_GET(self):                                    # noqa: N802
            self.send_error(404)

    with _server(_NoHealth) as base:
        ok, why = reachability(base, timeout=2)
    assert ok is True, why
    assert "404" in why


# ---------- 二、并发闸归因要分开 ----------

def test_partition_probe_says_unreachable_when_down(monkeypatch):
    monkeypatch.setenv("HYBRID_BASE_URL", f"http://127.0.0.1:{_free_port()}")
    capable, why = probe_partitioned(timeout=2)
    assert capable is None
    assert "不可达" in why, f"「连不上」不该被说成「未声明」：{why}"


def test_partition_probe_reports_true_when_declared():
    with _server() as base:
        capable, why = probe_partitioned(base, timeout=2)
    assert capable is True
    assert "partitioned=true" in why


# ---------- 三、CLI 层：exit 2 + 人话，且不启浏览器 ----------

@pytest.fixture
def playwright_trap(monkeypatch):
    """装一个「被调用就断言失败」的假 playwright —— 证明预检在开浏览器**之前**就退了。"""
    fake = types.ModuleType("playwright.sync_api")

    def _should_not_run(*a, **k):
        raise AssertionError("不可达时不该启动 Playwright（预检没生效）")

    setattr(fake, "sync_playwright", _should_not_run)
    setattr(fake, "Page", type("Page", (), {}))
    setattr(fake, "expect", lambda *a, **k: None)
    setattr(fake, "__getattr__", lambda name: type(name, (), {}))
    pkg = types.ModuleType("playwright")
    setattr(pkg, "sync_api", fake)
    monkeypatch.setitem(sys.modules, "playwright", pkg)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", fake)
    return fake


def test_cli_probe_exits_2_with_human_message_when_target_down(playwright_trap, monkeypatch, capsys):
    import framework.cli as cli_mod
    monkeypatch.setattr(cli_mod, "TARGET_URL", f"http://127.0.0.1:{_free_port()}")

    with pytest.raises(SystemExit) as si:
        cli_mod.cmd_probe()
    assert si.value.code == 2, "不可达必须非 0 退出（旧行为：traceback + exit 1）"

    out = capsys.readouterr().out
    assert "探测没跑" in out
    assert "demo.app" in out, "环境问题要给动作，不能只给栈"
    assert "Traceback" not in out


def test_cmd_all_forwards_allow_unmapped(monkeypatch):
    """`all` 必须把 --allow-unmapped 透传给 generate（参数契约与行为一致）。"""
    seen = {}

    def _fake_generate(rest=None, allow_unmapped=False):
        seen["allow_unmapped"] = allow_unmapped

    monkeypatch.setattr(cli, "cmd_probe", lambda: None)
    monkeypatch.setattr(cli, "cmd_generate", _fake_generate)
    monkeypatch.setattr(cli, "cmd_run", lambda *a, **k: None)

    cli.cmd_all(workers=1, allow_unmapped=True)
    assert seen["allow_unmapped"] is True
