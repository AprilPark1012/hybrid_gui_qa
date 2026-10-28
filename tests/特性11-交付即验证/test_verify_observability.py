"""V8.7.6 判据：`--verify` 试跑阶段的可观测性与超时。

事故背景（2026-10-27 用户实测）：
  跑 `all --ai` 时日志停在「[explore] --verify：先 generate 一次，再逐条试跑 1 条新用例…」
  之后**一行输出都没有**，用户以为卡死。

  根因有两层：
    1. **父进程全程静默**：`generate` 和试跑都走 `run_capture(...)`（同步阻塞 + 捕获全部输出），
       子进程跑完才返回，期间父进程不打印任何东西。而一条真实全链路用例有 62 步、
       含「等订单状态按时间流转」的有界等待（最长约 160s），整体 3~10 分钟 ——
       用户只看到「打完这行彻底没声了」。
    2. **子进程超时默认 None = 永久等**：`run_capture` 的 `timeout` 默认 `None`，
       一旦 demo 没响应 / 等待条件永不满足，父进程就是**真卡死**，只能 Ctrl+C，
       而且看不出停在哪一步。

  修法是两条一起：
    · 每次阻塞前交代「在做什么 / 要等多久 / 想看进度去哪看」（可观测性）；
    · 试跑必须带超时（`verify_timeout_s()`），超时后**明确报错并给出排查命令**（不卡死）。
"""
from __future__ import annotations

import os
import re
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
CLI_SRC = BASE / "framework/features/f10_cli/cli.py"


def _cli() -> str:
    return CLI_SRC.read_text(encoding="utf-8")


# ---------- ① 超时取值：默认 900，非法值回落，绝不变成「禁用超时」 ----------

def test_verify_timeout_default_is_900() -> None:
    """不设环境变量时默认 900 秒（实测 360s 的 2.5 倍余量）。"""
    from framework.shared.config import verify_timeout_s
    old = os.environ.pop("HYBRID_VERIFY_TIMEOUT", None)
    try:
        assert verify_timeout_s() == 900.0
    finally:
        if old is not None:
            os.environ["HYBRID_VERIFY_TIMEOUT"] = old


def test_verify_timeout_rejects_bad_values() -> None:
    """空 / 非数 / 0 / 负数 / inf 一律回落 900 —— 绝不能静默变成「无限等」（回到事故状态）。

    `1e400` 会被 `float()` 解析成 `inf`，而 `inf > 0` 成立 —— 若只用 `val > 0` 判断，
    它会被当成合法超时传下去，效果等于**又禁用了一次超时**（2026-10-27 修 verify 时发现，
    `llm_timeout_s()` 当时也有同一个洞）。
    """
    from framework.shared.config import verify_timeout_s
    old = os.environ.get("HYBRID_VERIFY_TIMEOUT")
    try:
        for bad in ("", "  ", "abc", "0", "-5", "1e400", "inf", "-inf", "nan"):
            os.environ["HYBRID_VERIFY_TIMEOUT"] = bad
            assert verify_timeout_s() == 900.0, f"{bad!r} 应回落 900"
        os.environ["HYBRID_VERIFY_TIMEOUT"] = "1800"
        assert verify_timeout_s() == 1800.0
    finally:
        if old is None:
            os.environ.pop("HYBRID_VERIFY_TIMEOUT", None)
        else:
            os.environ["HYBRID_VERIFY_TIMEOUT"] = old


def test_llm_timeout_also_rejects_inf() -> None:
    """`llm_timeout_s()` 同样不许接受 inf/nan —— 这是 V8.7.3 起就存在的洞，回归判据。"""
    from framework.shared.config import llm_timeout_s
    old = os.environ.get("HYBRID_LLM_TIMEOUT")
    try:
        for bad in ("1e400", "inf", "nan", "-inf"):
            os.environ["HYBRID_LLM_TIMEOUT"] = bad
            got = llm_timeout_s()
            assert got == 180.0, f"{bad!r} 应回落 180，实际 {got}"
            assert got != float("inf"), f"{bad!r} 让超时变成无限大 = 等于禁用超时"
        os.environ["HYBRID_LLM_TIMEOUT"] = "400"
        assert llm_timeout_s() == 400.0
    finally:
        if old is None:
            os.environ.pop("HYBRID_LLM_TIMEOUT", None)
        else:
            os.environ["HYBRID_LLM_TIMEOUT"] = old


# ---------- ② 试跑必须带超时（否则 run_capture 默认 timeout=None = 永久等） ----------

def test_verify_pytest_call_passes_timeout() -> None:
    """`--verify` 里那次 pytest 调用必须传 timeout=，否则子进程卡住就是永久等。"""
    src = _cli()
    # 定位试跑那一处 run_capture（含 pytest 与 node 变量）
    i = src.find('"-m", "pytest", node')
    assert i > 0, "找不到 --verify 的试跑调用"
    # 超时值在 try 之前取（_vto = config.verify_timeout_s()），所以要**向前也看一段**
    seg = src[max(0, i - 400):i + 420]
    assert "timeout=" in seg, "--verify 的 pytest 调用必须显式传 timeout="
    assert "verify_timeout_s()" in seg, "超时必须走 verify_timeout_s()（唯一入口，可调）"


def test_verify_handles_timeout_expired() -> None:
    """超时必须被捕获并给出明确处置，不许让 exception 冒到顶层。"""
    src = _cli()
    assert "subprocess.TimeoutExpired" in src, "必须捕获 subprocess.TimeoutExpired"
    i = src.find("except subprocess.TimeoutExpired")
    assert i > 0
    seg = src[i:i + 900]
    assert "HYBRID_VERIFY_TIMEOUT" in seg, "报错里要告诉用户调哪个值"
    assert "pytest" in seg, "报错里要给出手工复跑命令（定位停在哪一步）"


# ---------- ③ 阻塞前必须交代进度（可观测性） ----------

def test_verify_announces_generate_step() -> None:
    """generate 那次阻塞前后都要有交代 —— 否则用户看到的是「打完一行就没声了」。"""
    src = _cli()
    assert "[1/2] 正在 generate" in src, "generate 前必须打印「在做什么」"
    assert re.search(r"\[1/2\] generate 结束（耗时", src), "generate 后必须报耗时"


def test_verify_announces_trial_run_step() -> None:
    """试跑前要说明「可能 3~10 分钟」并指出进度去哪看。"""
    src = _cli()
    assert "[2/2] 正在试跑" in src, "试跑前必须打印「在做什么」"
    i = src.find("[2/2] 正在试跑")
    seg = src[i:i + 700]
    assert "3~10 分钟" in seg or "3-10 分钟" in seg, "必须给出预期耗时，避免用户误判卡死"
    assert "log/" in seg, "必须告诉用户实时进度去哪看"


def test_verify_flush_true_on_progress_prints() -> None:
    """进度打印必须 flush —— 管道/PowerShell 里不带 flush 会被缓冲，
    等于没打（这正是「看不到输出」的另一个来源）。

    [!] V8.7.8 并发化后打印统一走 `_p()`（加锁 + flush），判据跟着改，但**不弱化**：
        ① `_p` 定义里必须有 `print(msg, flush=True)` -> 等价于每条进度都 flush；
        ② 进度打印必须**走 `_p`**，不许绕过锁直接 `print`（并发下会交错成乱码）。
        比原来更严：多了一条「不许绕过锁」。
    """
    src = _cli()
    i = src.find("[2/2] 正在试跑")
    assert i > 0
    seg = src[i:i + 1400]
    assert "_p(" in seg, "进度打印必须走 _p（加锁 + flush）"
    j = src.find("def _p(msg: str)")
    assert j > 0, "必须有 _p 这个并发安全打印入口"
    assert "print(msg, flush=True)" in src[j:j + 300], "_p 内部必须 flush=True"
    assert 'print(f"  [2/2] 正在试跑' not in seg, "不许绕过 _p 直接 print（并发会交错）"


# ---------- ④ 可调项可发现 ----------

def test_verify_timeout_registered_in_cli_config() -> None:
    """`HYBRID_VERIFY_TIMEOUT` 必须登记进 `cli config` 的清单。"""
    src = _cli()
    assert '"HYBRID_VERIFY_TIMEOUT"' in src, "必须登记进环境变量清单（否则用户不知道能调）"
    i = src.find('"HYBRID_VERIFY_TIMEOUT"')
    seg = src[i:i + 500]
    assert "900" in seg, "登记项要写出默认值"
    assert "卡" in seg or "超时" in seg, "登记项要说明它治的是什么问题"


def test_verify_timeout_documented_in_env_example() -> None:
    """`.env.example` 也要登记 —— 用户是在那里找可调项的。"""
    ex = (BASE / ".env.example").read_text(encoding="utf-8")
    assert "HYBRID_VERIFY_TIMEOUT" in ex, ".env.example 必须登记 HYBRID_VERIFY_TIMEOUT"
    i = ex.find("HYBRID_VERIFY_TIMEOUT")
    seg = ex[max(0, i - 300):i + 300]
    assert "900" in seg, ".env.example 要写出默认值 900"
    assert "永久等" in seg or "卡死" in seg, "要说明不设的后果（永久等）"
