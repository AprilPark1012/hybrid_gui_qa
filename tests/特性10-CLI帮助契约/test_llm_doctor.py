# -*- coding: utf-8 -*-
"""特性10 · LLM 体检 `llm-doctor` + 思考强度旋钮 `LLM_REASONING_EFFORT`（V8.6.1）。

起因（用户 2026-10-14）：问「框架能不能用 GLM / Kimi / Qwen / MiniMax」。
查文档会查错（我一度断言 GLM-5.2 不在册，实际 2026-06-16 就发布了），而烧一次完整
端到端要 4 分钟 + 十几次调用 —— 所以做一个「真发 2 次请求、两秒出结论」的体检。

体检第一次跑就抓到真问题：当前生产配置的 deepseek-flash 报
    400 Thinking mode does not support this tool_choice
=> 框架的结构化输出路径其实一直失败、一直走文本兜底。
进一步实测定位：这类端点拒的是「指名函数」与 `required`，**接受 `auto` / 不传**；
而 browser_use 内置客户端发的正是**指名函数**（deepseek/chat.py 里 tool_choice =
{'type':'function','function':{'name':...}}）—— 正好撞上。
（该发现只作诊断，改不改工具层的 tool_choice 留给用户拍板。）

本文件钉住两类东西：
  A. 旋钮真的进请求体（断言 `_request_kwargs()` 的**产出**，不是断言"我们调了它"——
     上游改签名时要能立刻红，而不是静默失效）；
  B. 体检本身：注册齐全 / 不打印密钥 / 真发请求 / 能区分「不通」与「能用但打折」。
"""

from __future__ import annotations

import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CLI = ROOT / "framework" / "features" / "f10_cli" / "cli.py"
COMPAT = ROOT / "framework" / "shared" / "llm_compat.py"
CFG = ROOT / "framework" / "shared" / "config.py"


# --------------------------------------------------------------------------
# 假 OpenAI 端点：让体检有东西可打，且**不依赖外网**（本机 pypi 都不通）
# --------------------------------------------------------------------------
class _FakeLLM:
    """最小 OpenAI 兼容端点：回一个 tool_call（名字按请求里给的来）。

    `mode="ok"`       -> 正常返回 tool_calls
    `mode="nogood"`   -> 返回 400，文案照抄 DeepSeek thinking 模式那句
    """

    def __init__(self, mode: str = "ok"):
        self.mode = mode
        self.hits: list[dict] = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n) or b"{}")
                outer.hits.append(body)
                has_tools = bool(body.get("tools"))
                # 降级场景要**真实**：纯文本通、带 tools 才 400（否则第一步就连不通，
                # 判成「不可用」而不是「能用但打折」，测的就不是我们想测的那条路径了）
                if outer.mode == "nogood" and has_tools:
                    payload = {"error": {"message": "Thinking mode does not support "
                                                    "this tool_choice",
                                         "type": "invalid_request_error", "code": "invalid"}}
                    raw = json.dumps(payload).encode()
                    self.send_response(400)
                elif outer.mode == "named" and isinstance(body.get("tool_choice"), dict):
                    # 真实思考模式端点的行为：只拒「指名函数」，接受 auto / 不传
                    payload = {"error": {"message": "Thinking mode does not support "
                                                    "this tool_choice",
                                         "type": "invalid_request_error", "code": "invalid"}}
                    raw = json.dumps(payload).encode()
                    self.send_response(400)
                elif not has_tools:
                    payload = {
                        "id": "x", "object": "chat.completion", "created": 0,
                        "model": body.get("model") or "m",
                        "choices": [{"index": 0, "finish_reason": "stop",
                                     "message": {"role": "assistant", "content": "正常"}}],
                        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                    }
                    raw = json.dumps(payload).encode()
                    self.send_response(200)
                else:
                    tools = body.get("tools") or []
                    name = "tool"
                    if tools:
                        fn = tools[0].get("function") or {}
                        name = fn.get("name") or name
                    payload = {
                        "id": "x", "object": "chat.completion", "created": 0,
                        "model": body.get("model") or "m",
                        "choices": [{"index": 0, "finish_reason": "tool_calls",
                                     "message": {"role": "assistant", "content": None,
                                                 "tool_calls": [
                                                     {"id": "call_1", "type": "function",
                                                      "function": {"name": name,
                                                                   "arguments": '{"ok": true}'}}]}}],
                        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                    }
                    raw = json.dumps(payload).encode()
                    self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def log_message(self, format, *args):   # 静音（签名对齐父类）
                pass

        self.srv = HTTPServer(("127.0.0.1", 0), H)
        self.port = self.srv.server_address[1]
        self.t = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.t.start()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/v1"

    def stop(self):
        self.srv.shutdown()
        self.srv.server_close()


@pytest.fixture()
def fake_ok():
    f = _FakeLLM("ok")
    yield f
    f.stop()


@pytest.fixture()
def fake_nogood():
    f = _FakeLLM("nogood")
    yield f
    f.stop()


@pytest.fixture(autouse=True)
def _clear_rejected_cache():
    """清掉「已知拒指名函数端点」缓存 —— 否则用例之间会互相污染（它是模块级状态）。"""
    from framework.shared.llm_compat import _REJECTED_ENDPOINTS
    _REJECTED_ENDPOINTS.clear()
    yield
    _REJECTED_ENDPOINTS.clear()


@pytest.fixture()
def point_at(monkeypatch):
    """把通用入口指到假端点（真链路用的就是这几个变量）。"""
    def _apply(fake, model="glm-5.3", effort=None):
        monkeypatch.setenv("LLM_API_KEY", "sk-fake-for-test")
        monkeypatch.setenv("LLM_BASE_URL", fake.base_url)
        monkeypatch.setenv("LLM_MODEL", model)
        if effort is None:
            monkeypatch.delenv("LLM_REASONING_EFFORT", raising=False)
        else:
            monkeypatch.setenv("LLM_REASONING_EFFORT", effort)
    return _apply


# ==========================================================================
# A. 旋钮：真的进请求体
# ==========================================================================
def test_reasoning_effort_lands_in_request_body():
    """设了就得真出现在请求参数里（断言产出，不是断言调用）。"""
    from framework.shared.llm_compat import ChatOpenAICompatible as C
    kw = C(api_key="k", base_url="http://x/v1", model="glm-5.3",
           temperature=0.0, reasoning_effort="low")._request_kwargs()
    assert kw.get("extra_body", {}).get("reasoning_effort") == "low", (
        "reasoning_effort 没进 extra_body —— 用户设了低档其实没生效，属于静默失效"
    )


def test_reasoning_effort_absent_by_default():
    """没设就不发这个字段（不能污染各端服务端默认行为）。"""
    from framework.shared.llm_compat import ChatOpenAICompatible as C
    kw = C(api_key="k", base_url="http://x/v1", model="glm-5.3",
           temperature=0.0)._request_kwargs()
    assert "extra_body" not in kw, "没设 effort 却发了个空 extra_body"


def test_reasoning_effort_merges_not_overwrites():
    """与 deepseek-v4 的 thinking 开关**共存**（顺序覆盖会把那个开关吃掉）。"""
    from framework.shared.llm_compat import ChatOpenAICompatible as C
    kw = C(api_key="k", base_url="http://x/v1", model="deepseek-v4-pro",
           temperature=0.0, reasoning_effort="low")._request_kwargs()
    eb = kw.get("extra_body") or {}
    assert eb.get("reasoning_effort") == "low"
    assert eb.get("thinking") == {"type": "disabled"}, (
        "thinking 开关被 reasoning_effort 覆盖掉了 —— 静默改变了 deepseek-v4 的行为"
    )


def test_empty_env_means_not_set(monkeypatch):
    """`.env` 里写成 `LLM_REASONING_EFFORT=`（空值）要按「没设」处理，不能发空字段。"""
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("LLM_REASONING_EFFORT", "")
    from framework.shared import config as cfg
    obj = cfg.llm_from_env()
    assert getattr(obj, "reasoning_effort", None) in (None, ""), (
        "空字符串被当成有效值传下去了 -> 会发一个空字段给端点"
    )


def test_knob_is_discoverable():
    """框架铁律：可调项必须可发现（cli config 要列得出来 + 有 CLI 参数）。"""
    src = CLI.read_text(encoding="utf-8")
    assert '("LLM_REASONING_EFFORT"' in src, "没登记进 TUNABLE_CATALOG -> cli config 看不到"
    assert '"LLM_REASONING_EFFORT": "--reasoning-effort"' in src, (
        "没登记进 ENV_TO_FLAG -> 命令行给不了"
    )
    assert "--llm-base-url" in src and "--llm-model" in src


# ==========================================================================
# B. 体检命令本身
# ==========================================================================
def test_doctor_is_fully_registered():
    """加一个子命令要动 4 个地方 —— 漏一个就是「函数写了但调不到」/「参数不认」。"""
    src = CLI.read_text(encoding="utf-8")
    assert '"llm-doctor": {"--llm-base-url", "--llm-model", "--reasoning-effort"}' in src, \
        "CMD_FLAGS 没登记 -> _validate_args 会把参数判为未知"
    assert '"llm-doctor": cmd_llm_doctor' in src, "_CMD_FUNCS 没登记 -> --help 看不到"
    assert 'elif cmd == "llm-doctor":' in src, "main() 没分发 -> 命令根本不会被执行"


def test_doctor_skips_browser_preflight():
    """体检只发 LLM 请求，**不该**被「浏览器没装」挡住。"""
    src = CLI.read_text(encoding="utf-8")
    i = src.index('if cmd in ("generate", "explore", "run", "all", "verify"):')
    assert '"llm-doctor"' not in src[i:i + 120], (
        "llm-doctor 被放进浏览器预检名单了 —— 没装浏览器的机器就做不了 LLM 体检"
    )


def test_doctor_never_prints_secret():
    """体检输出不许带出 key（同类教训：log/*/traces 因含明文凭据永不外发）。"""
    src = CLI.read_text(encoding="utf-8")
    start = src.index("def cmd_llm_doctor")
    end = src.index("#: 环境变量 -> CLI 参数 的映射", start)
    body = src[start:end]
    for bad in ("os.environ[\"LLM_API_KEY\"]", "print(obj.api_key", "print(api_key"):
        assert bad not in body, f"体检里出现了可疑的密钥打印：{bad}"
    assert "不打印 key" in body or "不展示" in body, "连「不打印密钥」的意图都没写"


def test_doctor_no_key_exits_2_with_human_hint(monkeypatch, capsys):
    """没配 key：exit 2 + 告诉人去哪配（不能只抛栈 / 静默返回 0）。"""
    for v in ("LLM_API_KEY", "BROWSER_USE_API_KEY", "OPENAI_API_KEY",
              "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "DEEPSEEK_API_KEY"):
        monkeypatch.delenv(v, raising=False)
    from framework.features.f10_cli import cli
    rc = cli.cmd_llm_doctor([])
    out = capsys.readouterr().out
    assert rc == 2, "没 key 却当成健康"
    assert ".env" in out and "LLM_API_KEY" in out, "没告诉用户下一步该怎么办"


def test_doctor_healthy_path_really_calls_endpoint(point_at, fake_ok, capsys):
    """健康路径：真发请求、报连通与 function calling 都 OK、exit 0。"""
    point_at(fake_ok, model="glm-5.3")
    from framework.features.f10_cli import cli
    rc = cli.cmd_llm_doctor([])
    out = capsys.readouterr().out
    assert fake_ok.hits, "体检没真发请求 —— 那它给的就是假保证"
    assert rc == 0
    assert "连通" in out and "[OK]" in out
    assert "function calling 正常" in out
    assert "结论" in out and "可以用" in out


def test_doctor_reports_degraded_not_fail(point_at, fake_nogood, capsys):
    """「能用但打折」要单独标出来：exit 0（它确实能用）+ 必须让人看见 [!!]。"""
    point_at(fake_nogood, model="deepseek-flash")
    from framework.features.f10_cli import cli
    rc = cli.cmd_llm_doctor([])
    out = capsys.readouterr().out
    assert rc == 0, "「能用但打折」不该判成不可用"
    assert "[!!]" in out, "降级情形没被标出来 —— 用户会以为一切正常"
    assert "tool_choice" in out and "auto" in out, (
        "没把「接受 auto」这个实测结论说出来，用户无法自救"
    )
    assert "文本兜底" in out or "文本路径" in out, "没说清框架会怎么处置"


def test_doctor_reports_auto_fallback_not_plain_ok(point_at, capsys):
    """端点拒「指名函数」但框架能自动降级救回来 —— 体检必须**如实报出来**。

    为什么单列一条：降级成功后若只打一句「function calling 正常」，等于把
    「这个端点其实不支持指名函数、真链路每次都要多一次请求」这件事藏起来 ——
    体检的全部价值就是让用户知道真链路上会发生什么，藏掉降级 = 给假保证。
    """
    f = _FakeLLM("named")
    try:
        point_at(f, model="deepseek-flash")
        from framework.features.f10_cli import cli
        rc = cli.cmd_llm_doctor([])
        out = capsys.readouterr().out
        assert rc == 0, "能降级救回来 = 可用，不该判不可用"
        assert "自动降级" in out and "auto" in out, (
            "没报出「是靠框架降级才通的」—— 用户会以为该端点原生支持 function calling"
        )
        assert "function calling 正常" not in out, "报成了「正常」，把降级路径藏起来了"
        assert "结论" in out, "没给结论"
    finally:
        f.stop()


def test_doctor_sends_effort_to_endpoint(point_at, fake_ok, capsys):
    """端到端确认旋钮真的到了线上请求体（不只停在 config 对象上）。"""
    point_at(fake_ok, model="glm-5.3", effort="low")
    from framework.features.f10_cli import cli
    cli.cmd_llm_doctor([])
    capsys.readouterr()
    sent = [h for h in fake_ok.hits if h.get("tools")]
    assert sent, "没有带 tools 的请求，无法判断结构化路径"
    assert sent[0].get("reasoning_effort") == "low", (
        f"请求体里没有 reasoning_effort（实收字段：{sorted(sent[0])}）"
    )
