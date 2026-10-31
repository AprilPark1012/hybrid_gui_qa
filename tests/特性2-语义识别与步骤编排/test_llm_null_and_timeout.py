# -*- coding: utf-8 -*-
"""LLM 端点兼容性契约：显式 null 当缺失（GLM）+ 请求必须带超时（否则卡死）。

V8.7.3（2026-10-26）真机事故驱动 —— 两条都是**换 GLM 才暴露**的问题：

  · GLM 的 function calling 给「没填的字段」发 `null`，DeepSeek 是**省略该键**；
    Pydantic 的 `default=` 只认后者 -> GLM 走结构化输出时 16 个步骤全挂
    （`Input should be a valid string [input_value=None]`），且**每轮必挂**。
  · 客户端没设 timeout -> `AsyncOpenAI(timeout=None)` -> httpx 里 **None = 禁用超时**
    -> 第 2 次重试遇到端点不回包就**永久挂住**，日志停在「第 1/3 次失败」不动。

两条都必须由判据锁住：前者不修 GLM 这条腿永远跑不通，后者任何端点抖动都会变卡死。
"""
from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


# ---------------- (1) 显式 null 必须等价于「键缺失」（GLM 兼容）----------------

def test_step_model_accepts_explicit_null_like_glm():
    """GLM 给没填的字段发 `null`，必须能用 default 兜住（不报 16 validation errors）。"""
    from framework.features.f02_semantic.explorer_explore import _StepModel

    s = _StepModel(order=None, op=None, semantic_name=None, desc=None)
    assert s.order == 1, "order=null 应回落到 default 1"
    assert s.op == "click", "op=null 应回落到 default 'click'"
    assert s.semantic_name == "", "semantic_name=null 应回落到 default ''"
    assert s.desc == ""


def test_step_model_keeps_optional_fields_none():
    """`X | None` 字段本来就接受 null —— 不许被兜成别的值（那会改语义）。"""
    from framework.features.f02_semantic.explorer_explore import _StepModel

    s = _StepModel(value=None, row_index=None, cell_field=None, assertion=None,
                   cell_by=None, cell_index=None, row_text=None)
    assert s.value is None
    assert s.row_index is None
    assert s.cell_field is None
    assert s.assertion is None
    assert s.cell_by is None
    assert s.cell_index is None
    assert s.row_text is None


@pytest.mark.parametrize("bad_kwargs,why", [
    ({"semantic_name": 123}, "数字塞进 str"),
    ({"order": "abc"}, "字符串塞进 int"),
    ({"op": ["click"]}, "列表塞进 str"),
])
def test_step_model_still_rejects_wrong_types(bad_kwargs, why):
    """放宽 null ≠ 放松校验：错类型必须照样报错（否则等于把 schema 废了）。"""
    from framework.features.f02_semantic.explorer_explore import _StepModel

    with pytest.raises(Exception):
        _StepModel(**bad_kwargs)


def test_step_model_keeps_real_values():
    """正常值必须原样保留 —— 不能被 null 兜底逻辑顺手改掉。"""
    from framework.features.f02_semantic.explorer_explore import _StepModel

    s = _StepModel(semantic_name="账号", op="fill", order=7, value="super")
    assert (s.semantic_name, s.op, s.order, s.value) == ("账号", "fill", 7, "super")


# ---------------- (2) LLM 请求必须带超时（None = 永不超时 = 卡死）----------------

def test_llm_timeout_default_and_override(monkeypatch):
    from framework.shared import config as cfg

    monkeypatch.delenv("HYBRID_LLM_TIMEOUT", raising=False)
    assert cfg.llm_timeout_s() == 180.0, "默认超时应为 180 秒"
    monkeypatch.setenv("HYBRID_LLM_TIMEOUT", "45")
    assert cfg.llm_timeout_s() == 45.0, "HYBRID_LLM_TIMEOUT 必须可调"


@pytest.mark.parametrize("bad", ["", "   ", "abc", "0", "-5"])
def test_llm_timeout_illegal_falls_back(monkeypatch, bad):
    """非法/非正值一律回落默认。

    [!] 尤其不能用 0 / 负数：在 httpx 语义里那等于**取消超时**，
        正好是这次事故的形态（永久挂住）。宁可回落，也不许静默失效。
    """
    from framework.shared import config as cfg

    monkeypatch.setenv("HYBRID_LLM_TIMEOUT", bad)
    assert cfg.llm_timeout_s() == 180.0


def _isolate_dotenv(monkeypatch) -> None:
    """拦掉**所有** `load_dotenv()` 调用，让判据能验「没有该环境变量时的默认值」。

    [!] 为什么必须拦（2026-10-29 实测，追到第三方库）：
        `browser_use/logging_config.py:8` 在**模块 import 期**无条件调用 `load_dotenv()`（无参），
        它会顺着调用者文件向上找 `.env` -> 命中项目根的 `.env` -> 把 `HYBRID_LLM_TIMEOUT=900`
        等值**写回 `os.environ`**。
        于是判据里 `monkeypatch.delenv("HYBRID_LLM_TIMEOUT")` 刚删掉，
        `llm_from_env()` 首次 import browser_use 时又被塞回 900 -> `c.timeout == 900.0` 而不是 180。
        **这不是被测代码的问题**（`llm_timeout_s()` 本身完全正确：删掉环境变量就返回 180），
        是第三方库的副作用；判据要验的是「没配时的默认值」，所以必须让它找不到 `.env`。

    patch 三处是为了覆盖全部引用形态：
      · `dotenv.load_dotenv` / `dotenv.main.load_dotenv` —— 后来的 import 拿到的替身；
      · `browser_use.logging_config.load_dotenv` —— 模块若**已被 import**，它命名空间里存的是原函数。
    """
    import dotenv
    import dotenv.main as _dm
    _noop = lambda *a, **k: False  # noqa: E731
    monkeypatch.setattr(dotenv, "load_dotenv", _noop, raising=False)
    monkeypatch.setattr(dotenv, "find_dotenv", lambda *a, **k: "", raising=False)
    monkeypatch.setattr(_dm, "load_dotenv", _noop, raising=False)
    monkeypatch.setitem(__import__("sys").modules, "dotenv", dotenv)
    try:
        import browser_use.logging_config as _blc
        monkeypatch.setattr(_blc, "load_dotenv", _noop, raising=False)
    except Exception:            # 还没装/还没 import -> 上面的 patch 已足够
        pass


def test_llm_client_really_has_timeout_via_real_entry(monkeypatch):
    """走**真入口** `llm_from_env()`：超时必须真的挂到 SDK 上，且 SDK 不许自己重试。

    [!] 断言到 `_client()` 这一层，不只断言 `client.timeout`：
        真正决定 httpx 行为的是底层 AsyncOpenAI 实例。手工 new 一个对象验不出
        真链路拿到的东西（历史教训：验错层 = 假修）。
    """
    from framework.shared import config as cfg

    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("HYBRID_LLM_TIMEOUT", raising=False)
    _isolate_dotenv(monkeypatch)      # 第三方库 import 期会 load_dotenv()，不拦就测不到默认值

    c = cfg.llm_from_env()
    assert c.timeout == 180.0, (
        "LLM 客户端必须带超时 —— timeout=None 在 httpx 里是**禁用超时**，"
        "端点不回包就永久挂住（2026-10-26 实测事故形态）")
    assert (c.client_params or {}).get("max_retries") == 0, (
        "SDK 层不许自己重试：它会与框架的 HYBRID_LLM_ATTEMPTS 相乘"
        "（3×3=9 次 × 每次 180s = 27 分钟才报错，看着就是卡死）")

    real = c._client()          # 真链路的底层 httpx 客户端
    assert real.timeout is not None, "底层 AsyncOpenAI 的 timeout 不许是 None"
    assert real.max_retries == 0


def test_deepseek_branch_also_has_timeout(monkeypatch):
    """出厂默认那条腿（DEEPSEEK_*）同样必须带超时 —— 别只修新入口。"""
    from framework.shared import config as cfg

    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.delenv("HYBRID_LLM_TIMEOUT", raising=False)
    _isolate_dotenv(monkeypatch)      # 同上：第三方库 import 期 load_dotenv() 会盖回默认值

    c = cfg.llm_from_env()
    assert c.timeout == 180.0
    assert c._client().timeout is not None


# ---------------- (3) 重试轮必须能看出「在等」而不是「死了」----------------

def test_retry_prints_progress_before_waiting():
    """重试轮要打印「第 k/n 次请求已发出 / 超时 Xs」。

    没有它，用户看到的最后一行永远是「第 1/3 次结构化输出失败」——
    分不清是端点在算还是已经死了（这次事故就是这么被报成"卡住"的）。
    """
    src = (REPO / "framework" / "features" / "f02_semantic" / "explorer_explore.py") \
        .read_text(encoding="utf-8", errors="replace")
    assert "次请求已发出" in src, "重试轮缺「请求已发出」进度输出"
    assert "等待端点响应" in src, "重试轮缺「等待端点响应」提示"
    # 必须是**重试轮**才打印（attempt > 1），不能每轮都刷
    assert "if attempt > 1:" in src, "进度输出应限定在重试轮（attempt > 1）"


# ---------------- (4) 实际使用的模型必须能看见（V8.7.4，用户要求）----------------

class _FakeLLM:
    """最小替身：只用来验 describe_llm 的**格式化**（厂商识别/字段顺序）。

    真链路的取值由下面那条真入口判据守，两者分工不同。
    """

    def __init__(self, model, base_url, timeout=180.0):
        self.model = model
        self.base_url = base_url
        self.timeout = timeout


def test_describe_llm_reports_model_endpoint_vendor():
    """一行里必须同时有：模型名 / 端点 / 厂商人话 / 配置来源 / 超时。

    用户要的就是「跑 all --ai 到底用的是 GLM 还是 DEEPSEEK」——
    端点认成厂商是这句话的落点（光看模型名不可靠，`glm-5.3` 走 coding 端点也合法）。
    """
    from framework.shared.config import describe_llm

    s = describe_llm(_FakeLLM("glm-5.3", "https://open.bigmodel.cn/api/paas/v4"))
    assert "glm-5.3" in s, "缺模型名"
    assert "open.bigmodel.cn" in s, "缺端点"
    assert "智谱 GLM" in s, "端点没被认成厂商"
    assert "配置来源" in s and "超时" in s


@pytest.mark.parametrize("model,base,expect", [
    ("glm-5.3", "https://open.bigmodel.cn/api/coding/paas/v4", "智谱 GLM"),
    ("deepseek-chat", "https://api.deepseek.com/v1", "DeepSeek"),
    ("kimi-k2", "https://api.moonshot.cn/v1", "月之暗面 Kimi"),
    ("qwen-max", "https://dashscope.aliyuncs.com/compatible-mode/v1", "阿里通义"),
    ("llama3", "http://localhost:8000/v1", "本地端点"),
])
def test_describe_llm_vendor_mapping(model, base, expect):
    from framework.shared.config import describe_llm

    assert expect in describe_llm(_FakeLLM(model, base))


def test_describe_llm_unknown_vendor_says_so():
    """认不出的端点必须**明说认不出**，不许硬套一个厂商名（乱猜比不猜更坏）。"""
    from framework.shared.config import describe_llm

    s = describe_llm(_FakeLLM("my-model", "https://api.some-unknown-vendor.com/v1"))
    assert "未识别的端点" in s


def test_describe_llm_never_prints_the_key():
    """摘要里绝不许出现 key 值 —— 这行会进日志、被贴进聊天记录。"""
    import os

    from framework.shared.config import describe_llm

    secret = "sk-SUPER-SECRET-TEST-KEY-0123456789"
    old = os.environ.get("LLM_API_KEY")
    os.environ["LLM_API_KEY"] = secret
    try:
        s = describe_llm(_FakeLLM("glm-5.3", "https://open.bigmodel.cn/api/paas/v4"))
    finally:
        if old is None:
            os.environ.pop("LLM_API_KEY", None)
        else:
            os.environ["LLM_API_KEY"] = old
    assert secret not in s, "摘要里出现了 key 明文！"
    assert "SUPER-SECRET" not in s


def test_describe_llm_reads_from_obj_not_env(monkeypatch):
    """必须从**已构造的 obj** 读，而不是重读环境变量。

    命令行 `--llm-model` / `--llm-base-url` 的覆盖只体现在 obj 上；
    重读环境变量会把「配置里写的」当成「实际在用的」报出去（历史假修教训）。

    构造：环境变量只给一个值，obj 给另一个值 —— 输出必须跟 obj 走。
    """
    from framework.shared.config import describe_llm

    monkeypatch.setenv("LLM_MODEL", "ENV-SHOULD-NOT-WIN")
    monkeypatch.setenv("LLM_BASE_URL", "https://env-should-not-win.example.com/v1")
    s = describe_llm(_FakeLLM("obj-WINS", "https://api.deepseek.com/v1"))
    assert "obj-WINS" in s, "模型名没跟 obj 走（在读环境变量）"
    assert "ENV-SHOULD-NOT-WIN" not in s


def test_real_chain_prints_llm_identity():
    """真链路必须**真的打印**这一行（用户要的是跑 all --ai 时看见，不是有个函数没人调）。"""
    src = (REPO / "framework" / "features" / "f02_semantic" / "explorer_explore.py") \
        .read_text(encoding="utf-8", errors="replace")
    assert "describe_llm(obj)" in src, "真链路没有调用 describe_llm(obj)"
    assert "[LLM] 实际使用：" in src, "真链路没有打印「实际使用」这一行"
