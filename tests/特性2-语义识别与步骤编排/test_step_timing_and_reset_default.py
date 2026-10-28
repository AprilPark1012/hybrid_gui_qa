"""V8.7.7 判据：每步耗时埋点 + reset 默认值不再假设「被测应用能清库」。

事故背景（2026-10-27 用户实测）：
  61 步全链路用例，`--verify` 试跑 **397.3s**，紧接着 `run` 只用 **201.4s** ——
  同一份脚本、同一套断言。而 run 是 `-n 16`（16 个 worker 各起一套浏览器），
  按常理该更慢，结果反而快一倍。

  **这说明 verify 那 397 秒里有一段是在「等」而不是在干活**（多半是某几步等满
  定位/断言超时）。但当时**日志里没有任何每步耗时**，所以只能猜 ——
  之前我还据此编出一个「试跑跑在脏数据上」的解释，用户当场否掉：
  他每次跑前都删了 `demo/.data`，且 explore 的探测只点击不提交、不写数据。

  结论：**没有每步耗时，任何优化都是拍脑袋**。所以做两件事：
    1. 在 `_log`（唯一的步骤日志入口）里量出每步耗时；
    2. reset 默认值不再写死 demo 的 `localhost:8000` —— 生产环境没有清库开关，
       框架也不该假设有（用户原话：有些测试数据还是要保留的）。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

BASE = Path(__file__).resolve().parents[2]
GEN_SRC = BASE / "framework/features/f02_semantic/generator_generate.py"


def _gen() -> str:
    return GEN_SRC.read_text(encoding="utf-8")


# ---------- 一、每步耗时埋点 ----------

def test_step_log_records_per_step_duration() -> None:
    """`_log` 必须量出「距上一步的间隔」—— 这正是「397 秒花在哪」的答案来源。"""
    src = _gen()
    i = src.find("def _log(page, step, detail=")
    assert i > 0, "找不到 _log 定义"
    seg = src[i:i + 2200]
    assert "monotonic()" in seg, "必须用 time.monotonic()（不受系统时间调整影响）"
    assert "gap" in seg and "{gap:.1f}" in seg, "必须把单步耗时打进日志"
    assert "_LOG_N[0] += 1" in seg, "必须有步骤计数（[step k]）"
    assert "累计" in seg, "必须有累计耗时（判断还剩多久）"


def test_step_log_marks_slow_steps() -> None:
    """单步超过阈值要打标记 —— 慢步骤要一眼能挑出来，不能让人肉眼扫 61 行数字。

    阈值 5s 的依据：本项目定位/断言的默认超时是 15s，单步 5s 已属异常。
    """
    src = _gen()
    i = src.find("def _log(page, step, detail=")
    seg = src[i:i + 2200]
    assert "[SLOW]" in seg, "必须有慢步骤标记"
    assert ">= 5" in seg or ">=5" in seg, "阈值应在 5 秒量级"


def test_step_log_flushes() -> None:
    """`_log` 必须 flush —— 否则进度在管道里被缓冲，等于没打（V8.7.6 同款问题）。"""
    src = _gen()
    i = src.find("def _log(page, step, detail=")
    seg = src[i:i + 2200]
    assert "flush=True" in seg


def test_step_timing_lives_in_single_entrypoint() -> None:
    """埋点必须在 `_log` 这个**唯一入口**，不许在 _act/_assert_* 各处重复实现。

    理由：分散埋点必然漏（改一处忘三处），且量出来的口径不一致。
    """
    src = _gen()
    # 单步耗时的计数变量只应出现在 _log 附近，不许散落多处
    assert src.count("_LOG_LAST[0] = now") == 2, "_LOG_LAST 只在 _log 与 _log_check 各更新一处"
    assert src.count("_LOG_T0[0] = now") == 2, "_LOG_T0 只在 _log 与 _log_check 各初始化一处"


def test_check_log_counts_toward_step_timing() -> None:
    """**断言**也必须计入步骤耗时 —— 否则长等待会被算到下一步头上。

    实测事故（2026-10-27）：场景里「等订单状态按时间流转到已关闭」等了 150.5s，
    因为它走的是 `[CHECK]`（只 print 不更新计时器），这 150 秒记到了**下一条** `_log`
    头上 —— 日志显示「点开角色菜单 (+150.5s) [SLOW]」，看着像点击慢，
    实际点击只花 0.4s。连我自己都据此误判了一次，所以必须钉死。
    """
    src = _gen()
    assert "def _log_check(" in src, "必须有 _log_check（断言专用计时入口）"
    i = src.find("def _log_check(")
    assert i > 0
    seg = src[i:i + 1800]
    assert "_LOG_LAST[0] = now" in seg, "断言必须更新计时器（否则耗时串到下一步）"
    assert "_LOG_N[0] += 1" in seg, "断言必须占一个 step 序号"
    assert "{gap:.1f}" in seg, "断言必须打出自己的耗时"
    # 「只 print 不计时」的老写法不许残留
    assert src.count('line = f"[CHECK]') == 0, "不许再有只打印不计时的 [CHECK]"


# ---------- 二、reset 默认值：不假设被测应用能清库 ----------

def _harness_module():
    """导入渲染后的 _harness（真入口，不是照抄一份逻辑）。"""
    gen_dir = BASE / "scripts" / "generated"
    if str(gen_dir) not in sys.path:
        sys.path.insert(0, str(gen_dir))
    import importlib
    if "_harness" in sys.modules:
        importlib.reload(sys.modules["_harness"])
    import _harness  # noqa: F401
    return sys.modules["_harness"]


def test_reset_defaults_to_off() -> None:
    """不设 `HYBRID_RESET_URL` 时必须**什么都不做** —— 这是接真实系统的正确默认。"""
    h = _harness_module()
    old = os.environ.pop("HYBRID_RESET_URL", None)
    try:
        assert h._resolve_reset_url() == "", "默认必须是 off（不碰被测数据）"
    finally:
        if old is not None:
            os.environ["HYBRID_RESET_URL"] = old


@pytest.mark.parametrize("raw", ["off", "OFF", "", "0", "none", "no", "false"])
def test_reset_off_variants(raw: str) -> None:
    """各种「关」的写法都要认（大小写不敏感）。"""
    h = _harness_module()
    old = os.environ.get("HYBRID_RESET_URL")
    try:
        os.environ["HYBRID_RESET_URL"] = raw
        assert h._resolve_reset_url() == "", f"{raw!r} 应当解析为空串"
    finally:
        if old is None:
            os.environ.pop("HYBRID_RESET_URL", None)
        else:
            os.environ["HYBRID_RESET_URL"] = old


def test_reset_auto_derives_from_target() -> None:
    """`auto` 从被测地址推导，而不是写死 localhost:8000。"""
    h = _harness_module()
    old_r = os.environ.get("HYBRID_RESET_URL")
    old_t = os.environ.get("TARGET_URL")
    old_b = os.environ.get("HYBRID_BASE_URL")
    try:
        os.environ["HYBRID_RESET_URL"] = "auto"
        os.environ["TARGET_URL"] = "https://prod.example.com"
        os.environ.pop("HYBRID_BASE_URL", None)
        assert h._resolve_reset_url() == "https://prod.example.com/api/reset?purge=1"
        # 末尾斜杠要处理干净（不能拼出 //api）
        os.environ["TARGET_URL"] = "https://prod.example.com/"
        assert h._resolve_reset_url() == "https://prod.example.com/api/reset?purge=1"
    finally:
        for k, v in (("HYBRID_RESET_URL", old_r), ("TARGET_URL", old_t),
                     ("HYBRID_BASE_URL", old_b)):
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_reset_explicit_url_passthrough() -> None:
    """给具体 URL 时原样使用（要自定义 purge 参数或换路径的场合）。"""
    h = _harness_module()
    old = os.environ.get("HYBRID_RESET_URL")
    try:
        os.environ["HYBRID_RESET_URL"] = "https://x.internal/cleanup?full=1"
        assert h._resolve_reset_url() == "https://x.internal/cleanup?full=1"
    finally:
        if old is None:
            os.environ.pop("HYBRID_RESET_URL", None)
        else:
            os.environ["HYBRID_RESET_URL"] = old


def test_reset_reads_env_each_call_not_cached() -> None:
    """必须**每次现读**环境变量 —— 缓存过一次之后改就无效了。

    实测踩过：设 `HYBRID_RESET_URL=off` 却仍返回 demo 地址，因为模块加载时
    就把值缓存进了 `_RESET_RAW`。可调项必须真的随时可调。
    """
    src = _gen()
    assert "_RESET_RAW" not in src, "不许把 HYBRID_RESET_URL 缓存进模块级变量"
    i = src.find("def _resolve_reset_url")
    assert i > 0
    seg = src[i:i + 900]
    assert 'os.environ.get("HYBRID_RESET_URL"' in seg, "函数体内必须现读环境变量"


def test_template_no_longer_hardcodes_demo_endpoint_as_default() -> None:
    """模板里不许再出现「默认值 = localhost:8000/api/reset」（那会让真实系统白等）。"""
    src = _gen()
    assert 'os.environ.get("HYBRID_RESET_URL", "http://localhost:8000/api/reset?purge=1")' not in src, \
        "默认值不许再写死 demo 的 reset 端点"
    assert 'os.environ.get("HYBRID_RESET_URL", "off")' in src, "默认值应为 off"


def test_reset_failure_still_warns_but_never_blocks() -> None:
    """复位失败只告警、绝不中断用例 —— 真实系统没有该端点时也必须能继续跑。"""
    src = _gen()
    i = src.find("def _reset_target_data")
    assert i > 0
    seg = src[i:i + 1600]
    assert "except Exception" in seg, "必须捕获异常"
    assert "yield None" in seg, "失败后仍要 yield（不中断用例）"
    assert "互相污染" in seg, "要提示后果"
