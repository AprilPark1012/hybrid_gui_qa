# -*- coding: utf-8 -*-
"""特性10 · 通用 LLM 入口（V8.6.1）：一个开关接所有 **OpenAI 兼容**服务。

起因（用户 2026-10-14 提问）：「框架除了 deepseek，还能用 GLM、Kimi 吗？」
实测结论：能 —— DeepSeek / GLM / Kimi 都是 OpenAI 兼容协议，框架的 LLM 层
（`browser_use.llm`）只差三个环境变量。于是在原有「5 家写死的 provider 分支」之外，
加了**通用入口** `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL`：接第 6 家不必再改代码。

判据守住四件事（都是实测出来的，不是拍脑袋）：
  1. **通用入口必须走 function calling**（`tools`），不能走 `response_format=json_schema`
     —— 实测 `ChatOpenAI` 走 json_schema(strict)，第三方端点支持度参差，
     "结构化输出路径"会连续失败；`ChatDeepSeek` 走 tools，GLM/Kimi 官方都支持。
  2. **优先级**：LLM_* > 各家专用变量（用户显式配了通用入口就该用它）。
  3. **`cli config` 必须让人发现它**（框架铁律：可调项必须可发现），
     且 **密钥值不许被打印**（这个命令的用途是"发现旋钮"，不是"泄露 key"）。
  4. **`LLM_API_KEY` 不许有 CLI 参数**（密钥写进命令行会留 shell 历史）。
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CONFIG = REPO / "framework" / "shared" / "config.py"
CLI = REPO / "framework" / "features" / "f10_cli" / "cli.py"
EXPLORER = REPO / "framework" / "features" / "f02_semantic" / "explorer_explore.py"
CASSETTE = REPO / "framework" / "features" / "f08_replay" / "llm_cassette_explore.py"


def _env_branch(src: str, var: str) -> str:
    """截出某个 `if os.environ.get("<var>"):` 分支的**办法体**（到下一个同类 if 为止）。

    为什么不能简单切固定长度：实测踩过 —— 切 700 字符会把**后面正式分支**里的
    `ChatOpenAI(model="gpt-4.1-mini")`（那是 OpenAI 官方分支，本来就该用 ChatOpenAI）
    也算进来，判据因此误红。
    """
    i = src.index(f'if os.environ.get("{var}")')
    j = src.find('if os.environ.get("', i + 1)
    return src[i: j if j != -1 else len(src)]


def test_general_entry_uses_function_calling_not_json_schema():
    """通用入口必须用 ChatDeepSeek（function calling），不能用 ChatOpenAI（json_schema）。

    实测依据（对着本地假 OpenAI 端点抓请求体）：
      · ChatDeepSeek -> 请求含 tools + tool_choice（function calling）
      · ChatOpenAI   -> 请求含 response_format={"json_schema":{...,"strict":true}}，无 tools
    第三方端点对 strict json_schema 的支持度参差，走它时结构化输出连续失败。
    """
    seg = _env_branch(CONFIG.read_text(encoding="utf-8"), "LLM_API_KEY")
    # V8.6.1：通用入口改用 ChatOpenAICompatible（= ChatDeepSeek 的子类 + reasoning_effort）。
    # 所以①用**行为级**断言钉住「它确实继承那条走 function calling 的实现」，
    #     ②字符串断言必须写 `ChatOpenAI(`，**不能**写 `ChatOpenAI` ——
    #     "ChatOpenAICompatible" 本身就含这个子串，判据会自绊（这坑踩过一次）。
    from browser_use.llm.deepseek.chat import ChatDeepSeek
    from framework.shared.llm_compat import ChatOpenAICompatible

    assert issubclass(ChatOpenAICompatible, ChatDeepSeek), (
        "ChatOpenAICompatible 不再是 ChatDeepSeek 的子类 —— 必须继承「发 tools + "
        "tool_choice」那条实现，否则就不是 function calling 了"
    )
    assert "ChatOpenAICompatible" in seg, (
        "通用入口没使用走 function calling 的客户端"
    )
    assert "ChatOpenAI(" not in seg, (
        "通用入口用了 ChatOpenAI 本体 —— 它不发 tools（function calling），"
        "第三方端点的结构化输出会失败"
    )
    assert "response_format" not in seg, "通用入口不该自己拼 response_format"


def test_fix_applies_to_default_deepseek_entry_too(monkeypatch):
    """**出厂默认配置**（只配 `DEEPSEEK_API_KEY`）必须也吃到 tool_choice 兜底。

    为什么单列一条（2026-10-14 踩过，值得记）：最初只在「通用入口 `LLM_*`」那支把客户端
    换成 `ChatOpenAICompatible`，**忘了 `DEEPSEEK_*` 那一支** —— 而**出厂 `.env` 用的正是
    `DEEPSEEK_*`**（通用入口是新加的、默认没配）。后果：
      · 手工构造 `ChatOpenAICompatible(...)` 做实验 -> 通过，看起来修好了；
      · 真链路走 `llm_from_env()` -> 拿到裸 `ChatDeepSeek` -> 兜底**从未触发**。
    即 **「修了但没生效」**。这条判据专门钉「修复是否覆盖真实默认路径」，
    而不是只钉「那个类本身对不对」。
    """
    for k in ("LLM_API_KEY", "BROWSER_USE_API_KEY", "OPENAI_API_KEY",
              "ANTHROPIC_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.delenv("LLM_REASONING_EFFORT", raising=False)

    from framework.shared import config as cfg
    from framework.shared.llm_compat import ChatOpenAICompatible

    obj = cfg.llm_from_env()
    assert isinstance(obj, ChatOpenAICompatible), (
        f"出厂默认配置（DEEPSEEK_*）拿到的是 {type(obj).__name__} —— tool_choice 兜底没覆盖到它，"
        f"等于默认配置下这个修复不存在（真实链路会走文本兜底而没人知道）"
    )
    assert type(obj).__name__ != "ChatDeepSeek", "拿到的是上游裸客户端，没有兜底能力"

    # 思考档位旋钮在这支也必须生效（否则用户在默认配置下设了 low 却无效 = 静默失效）
    monkeypatch.setenv("LLM_REASONING_EFFORT", "low")
    obj2 = cfg.llm_from_env()
    assert getattr(obj2, "reasoning_effort", None) == "low", (
        "DeepSeek 入口没吃 LLM_REASONING_EFFORT —— 可调项在默认配置下静默失效"
    )


def test_secret_has_no_cli_flag():
    """`LLM_API_KEY` 不许映射 CLI 参数（密钥写进命令行会留 shell 历史）。"""
    src = CLI.read_text(encoding="utf-8")
    i = src.index("ENV_TO_FLAG: dict[str, str] = {")
    body = src[i: src.index("\n}", i)]
    # 只看**真映射行**（`"VAR": "--flag",`），注释里提到变量名不算 ——
    # 实测踩过：表里有条注释「LLM_API_KEY 刻意不映射」，按子串查会误红。
    mapped = set(re.findall(r'^\s*"([A-Z_]+)"\s*:', body, re.M))
    assert "LLM_API_KEY" not in mapped, (
        "LLM_API_KEY 被映射了 CLI 参数 —— 密钥不该出现在命令行里"
    )
    assert "LLM_BASE_URL" in mapped and "LLM_MODEL" in mapped, (
        "LLM_BASE_URL / LLM_MODEL 应在 ENV_TO_FLAG 里（这两个不是密钥，可以命令行给）"
    )


def test_general_entry_has_highest_priority():
    """`LLM_*` 必须排在所有专用变量**之前**（用户显式配的通用入口最具体）。"""
    src = CONFIG.read_text(encoding="utf-8")
    i_general = src.index('os.environ.get("LLM_API_KEY")')
    for later in ('os.environ.get("BROWSER_USE_API_KEY")', 'os.environ.get("OPENAI_API_KEY")',
                  'os.environ.get("ANTHROPIC_API_KEY")', 'os.environ.get("GOOGLE_API_KEY")',
                  'os.environ.get("DEEPSEEK_API_KEY")'):
        assert src.index(later) > i_general, (
            f"`{later}` 排在通用入口 LLM_API_KEY 之前 —— 通用入口应优先"
        )


def test_auto_detect_recognizes_general_entry():
    """`auto_detect_llm()` 必须认 `LLM_API_KEY`（否则 Healer 的语义重猜不会启用）。"""
    src = CONFIG.read_text(encoding="utf-8")
    i = src.index("def auto_detect_llm")
    seg = src[i: i + 400]
    assert "LLM_API_KEY" in seg, "auto_detect_llm 不认 LLM_API_KEY"


def test_general_entry_is_discoverable_via_cli_config():
    """`cli config` 必须列出三个通用入口项（框架铁律：可调项必须可发现）。"""
    src = CLI.read_text(encoding="utf-8")
    for var in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL"):
        assert var in src, f"`{var}` 没登记进 cli config 的可调项清单（用户发现不了它）"


def test_secret_values_are_not_printed_by_cli_config():
    """`cli config` 不许打印密钥值 —— 只报「有没有设」。"""
    src = CLI.read_text(encoding="utf-8")
    assert "_SECRET_ENV_KEYS" in src, "缺少密钥脱敏白名单"
    i = src.index("_SECRET_ENV_KEYS = {")
    seg = src[i: i + 400]
    assert "LLM_API_KEY" in seg, "LLM_API_KEY 没进密钥脱敏名单 —— cli config 会把 key 打到终端"
    # 脱敏分支必须真的生效（在循环里被判断）
    loop = src[src.index("for env, default, desc in TUNABLE_CATALOG:"):][:600]
    assert "env in _SECRET_ENV_KEYS" in loop, (
        "脱敏名单没被 cmd_config 使用 —— 登记了却不用，等于没做"
    )


def test_model_mismatch_on_replay_is_warned():
    """换模型后命中旧录像，**必须**有告警 —— 这是最容易骗过人的坑。

    背景：录像键 `sha256(system + prompt)` **刻意不含模型名**（为保住「A 机录、B 机放」），
    于是换模型后仍会命中旧模型的录像；离线机没配环境变量时更是静默通过。
    """
    cas = CASSETTE.read_text(encoding="utf-8")
    assert "_model" in cas, "录像 lookup 没把模型名带出来（_model）"
    exp = EXPLORER.read_text(encoding="utf-8")
    i = exp.index("def _replay_from_cassette")
    seg = exp[i: i + 3000]
    assert "模型不一致" in seg, (
        "回放命中旧模型录像时没有告警 —— 用户会以为「我在用 GLM 跑」，"
        "实际吃的是另一个模型录的结论"
    )
    assert "--llm-record" in seg, "告警里没有给出「怎么在新模型上重出结论」的下一步"
