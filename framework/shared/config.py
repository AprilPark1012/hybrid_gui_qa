"""配置：目标 URL、LLM provider、输出目录。"""
from __future__ import annotations
import os
from pathlib import Path

from dotenv import load_dotenv  # type: ignore

def _repo_root(start: Path) -> Path:
    """向上找含 pyproject.toml 的目录 = 仓库根。

    为什么不写死 parents[N]：V8.0 结构重构把本文件从 framework/ 挪到 framework/shared/，
    层级一变 parents[N] 就**悄悄**指错（症状是「scripts/test_cases.py 不存在」这类莫名其妙报错）。
    按标记文件找，以后再挪位置也不会破。
    """
    for p in (start, *start.parents):
        if (p / "pyproject.toml").exists():
            return p
    return start


BASE = _repo_root(Path(__file__).resolve().parent)
# 先加载项目 .env（若有，可覆盖），再加载 Hermes 主 .env（复用 DEEPSEEK_API_KEY）
load_dotenv(BASE / ".env")
_hermes_env = Path.home() / ".hermes" / ".env"
if _hermes_env.exists():
    load_dotenv(_hermes_env, override=False)   # 项目 .env 优先，Hermes 兜底

# ---- 被测应用 ----
# 目标地址：TARGET_URL（本项目老名字）> HYBRID_BASE_URL（生成脚本/target_probe 用的名字）> 默认。
# 2026-09-15 统一：以前只有 probe/generate 认 TARGET_URL、而生成脚本与 /api/health 探测认
# HYBRID_BASE_URL -> 只设 HYBRID_BASE_URL 的人会发现「probe 还在打 localhost:8000」，
# 属于「参数名不新手秒懂」。现在两个名字等效（TARGET_URL 优先，保持向后兼容）。
DEFAULT_TARGET_URL = "http://localhost:8000"


def target_url() -> str:
    """被测应用地址（**运行期**读取的唯一入口）。

    [!] P25 片 4（2026-10-11 实测修复）：这里原来是个**模块级常量**
        （`TARGET_URL = os.environ.get(...)`），而 `os.environ` 是在 **import 那一刻**求值的 ——
        CLI 的 `--base-url` 却是在 import **之后**才被解析并写进 `HYBRID_BASE_URL`
        （见 `cli._apply_flag_as_env`）=> **设了完全不生效**：`probe --base-url http://X`
        照样打 `localhost:8000`。这类"参数看着能改、实际改不动"最误人（与"参数名不新手秒懂"同档）。
        改成函数后，「CLI 参数 > 环境变量 > 默认」这条优先级链才真正成立。

    优先级：`TARGET_URL`（本项目老名字）> `HYBRID_BASE_URL`（生成脚本/target_probe 用的名字）
    > 默认。两个名字等效是 2026-09-15 定的（只设一个的人不该发现"框架还在打别的地址"）。
    """
    return (os.environ.get("TARGET_URL")
            or os.environ.get("HYBRID_BASE_URL")
            or DEFAULT_TARGET_URL)

# ---- 版本号单一来源（2026-09-19 把 build_html.py 挪进 tools/ 时收敛）----
# 培训页生成器 `build_tools/build_html.py` 顶部的 VERSION / VERSION_DATE 是**唯一**版本来源。
# 路径只在这里定义一次；读版本一律走 read_version()（cli / llm_cassette / pack_release 共用）
# -> 以后再挪位置只改这一行；漏改会被 tests/_helpers/test_cli_flags.py 的判据当场抓住（--version 不许变 unknown）。
VERSION_SOURCE = BASE / "build_tools" / "build_html.py"


def read_version() -> tuple[str, str]:
    """→ (VERSION, VERSION_DATE)；读不到就 ("unknown", "")，**绝不编**。"""
    try:
        import re
        src = VERSION_SOURCE.read_text(encoding="utf-8")
        v = re.search(r'^VERSION\s*=\s*"([^"]+)"', src, re.M)
        d = re.search(r'^VERSION_DATE\s*=\s*"([^"]+)"', src, re.M)
        if not v:
            return "unknown", ""
        return v.group(1), (d.group(1) if d else "")
    except Exception:
        return "unknown", ""

# ---- 输出产物目录 ----
OUTPUT_DIR = BASE / "output"
ELEMENT_MAP_DIR = OUTPUT_DIR / "element_maps"
TRACE_DIR = OUTPUT_DIR / "traces"            # 运行时证据：runner 用到时自建（不在 ensure_dirs 急切创建）
HEALS_DIR = OUTPUT_DIR / "heals"             # 自愈可审 diff：healer 用到时自建（同上）
# 2026-09-14 清理（用户反馈「仓库里有空目录残留」）：
#   PLAN_DIR(output/plans) / GENERATED_TESTS_DIR(generated_tests) /
#   TEST_SCENARIO_DIR(testScenario) / DATASETS_DIR(datasets)
# 四个旧概念常量**已无任何使用者**，唯一"效果"就是被 ensure_dirs() 每次启动建出来
# -> 凭空多出空目录。已整体删除；防复发见 tests/_helpers/test_cli_exit_codes.py::test_ensure_dirs_only_declares_used_dirs。

# ---- P5 数据驱动新增目录 ----
LOG_DIR = BASE / "log"                       # 用例执行日志
SCENARIOS_DIR = BASE / "scenarios"           # 用例编排表(index.json)

# ---- 重构后的目录 ----
CASES_DIR = BASE / "cases"                   # ★ 手写的自然语言用例文件（写死数据）
SCRIPTS_DIR = BASE / "scripts"               # ★ generate 产物（playwright 脚本 + datasets 抽离）
GENERATED_DIR = SCRIPTS_DIR / "generated"     # ★P20 生成脚本目录（<scenario_id>/<case_id>.py + index.json）

# ---- LLM 编排阶段需要 LLM（借 browser-use 的 LLM 客户端，非其 Agent）----
# 负责"智能理解"：读懂自然语言测试意图、规划步骤、挑元素、写 plan。
# 这是 AI 之力的成本来源（每步一次模型推理）。
def llm_from_env():
    """按 .env 里配了哪个 key，构造对应的 LLM 客户端实例
    （来自 browser_use.llm 包；**不使用** browser-use 的 Agent）。
    优先级: 通用 LLM_* > ChatBrowserUse > OpenAI > Anthropic > Google > DeepSeek(ChatDeepSeek 原生)。"""
    try:
        from browser_use.llm import ChatBrowserUse, ChatOpenAI, ChatAnthropic, ChatGoogle
    except ImportError as e:
        raise ImportError(
            "browser-use 未安装。pip install browser-use 后重试。"
        ) from e

    # 0) 通用 OpenAI 兼容入口（V8.6.1）—— 一个开关接所有 OpenAI 兼容服务：
    #    智谱 GLM / 月之暗面 Kimi / 通义 / 豆包 / 本地 vLLM·Ollama…全都走这一支。
    #
    # 为什么单开一组变量，而不是让用户复用 DEEPSEEK_*：
    #   那组名字把厂商写死了 —— 配 Kimi 却要写 DEEPSEEK_API_KEY，语义错乱，
    #   每接一家都得重新解释一遍（用户 2026-10-14 实测提问引出）。
    #
    # [!] 这里**借用 ChatDeepSeek 当通用 OpenAI 兼容客户端**，不用 ChatOpenAI —— 实测对比：
    #     · ChatDeepSeek 用 **function calling**（请求带 tools + tool_choice），
    #       而 GLM / Kimi 官方都明确支持 tool calling；
    #     · ChatOpenAI 用 **response_format=json_schema(strict=True)**（或把 schema 塞 system
    #       prompt），第三方端点对 strict json_schema 的支持度参差 —— 实测走它时
    #       "结构化输出路径"连续 3 次失败（框架的解析层拿不到步骤）。
    #     两者请求体都干净（只发 model / messages / temperature / tools），
    #     所以选**与框架既有链路一致**的那个，风险最低。
    #     名字里的 deepseek 只是实现出处：provider 字段会记 'deepseek'，仅影响日志。
    #
    # [!] 客户端用 `ChatOpenAICompatible`（= ChatDeepSeek + reasoning_effort），原因：
    #     这一代国产旗舰正在集体**取消「关闭思考」的选项**（GLM-5.3 起完全不能关、
    #     默认 max 档；MiniMax-M3.1 不允许 disabled）。探索阶段每步都要调一次 LLM，
    #     走服务端默认档 = 每次都跑最贵推理级别。给个旋钮把强度压下来。
    if os.environ.get("LLM_API_KEY"):
        from framework.shared.llm_compat import ChatOpenAICompatible
        return ChatOpenAICompatible(
            api_key=os.environ["LLM_API_KEY"],
            base_url=os.environ.get("LLM_BASE_URL") or None,   # 空 = 让服务方决定（默认 DeepSeek）
            model=os.environ.get("LLM_MODEL", "gpt-4o-mini"),
            temperature=0.0,
            # 空字符串按「没设」处理（.env 里 `LLM_REASONING_EFFORT=` 是常见写法，
            # 不能让它变成发一个空字段出去）。
            reasoning_effort=os.environ.get("LLM_REASONING_EFFORT") or None,
        )
    # 1) Browser Use 自家优化模型
    if os.environ.get("BROWSER_USE_API_KEY"):
        return ChatBrowserUse()
    # 2) 通用 provider
    if os.environ.get("OPENAI_API_KEY"):
        return ChatOpenAI(model="gpt-4.1-mini")
    if os.environ.get("ANTHROPIC_API_KEY"):
        return ChatAnthropic(model="claude-sonnet-4-0", temperature=0.0)
    if os.environ.get("GOOGLE_API_KEY"):
        return ChatGoogle(model="gemini-flash-latest")
    # 3) DeepSeek —— OpenAI 兼容，走 function calling
    # [!] 这里**必须和上面「通用入口」用同一个客户端类** `ChatOpenAICompatible`，
    #     不能用 browser_use 原生的裸 `ChatDeepSeek`。原因（2026-10-14 踩过）：
    #     裸 `ChatDeepSeek` 不给「指名函数被拒」留兜底，而**出厂 .env 走的正是这一支**
    #     （默认配 DEEPSEEK_API_KEY）—— 只在通用入口上做修复 = 默认配置根本吃不到，
    #     属于「修了但没生效」。判据 test_llm_provider_switch 里有一条专门钉这件事。
    if os.environ.get("DEEPSEEK_API_KEY"):
        from framework.shared.llm_compat import ChatOpenAICompatible
        return ChatOpenAICompatible(
            api_key=os.environ["DEEPSEEK_API_KEY"],
            base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
            model=os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
            temperature=0.0,
            reasoning_effort=os.environ.get("LLM_REASONING_EFFORT") or None,
        )
    raise RuntimeError(
        "未检测到 LLM 环境变量。请在 .env 配置 LLM_API_KEY（通用 OpenAI 兼容：GLM / Kimi / "
        "通义 / 豆包 / 本地 vLLM·Ollama 等，配 LLM_BASE_URL + LLM_MODEL）/ "
        "BROWSER_USE_API_KEY / OPENAI_API_KEY / ANTHROPIC_API_KEY / GOOGLE_API_KEY / "
        "DEEPSEEK_API_KEY 之一。"
    )


def auto_detect_llm() -> bool:
    """是否检测到可用的 LLM key（Healer 的 Level-B 语义重猜才启用）。"""
    return bool(os.environ.get("LLM_API_KEY")
                or os.environ.get("BROWSER_USE_API_KEY") or os.environ.get("OPENAI_API_KEY")
                or os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("GOOGLE_API_KEY")
                or os.environ.get("DEEPSEEK_API_KEY"))


def ensure_dirs():
    # 2026-09-13 冷启动排查补：原来不含 LOG_DIR / SCRIPTS_DIR / CASES_DIR ——
    # 冷启动（目录被清掉）时它们只是"碰巧"被后续 parents=True 的 mkdir 建出来，
    # 属于隐式依赖；这里显式建，任何入口都不会因为缺目录而诡异失败。
    # 2026-09-14 收窄（用户反馈「空目录残留」）：
    #   急切创建只保留「入口扫描/写入之前不会自建」的目录。
    #   TRACE_DIR / HEALS_DIR 的写入方（runner.record_trace / healer.dump）**使用前显式 mkdir**
    #   -> 不是隐式依赖；在此急切创建只会让空目录常驻仓库。谁要写谁自建。
    #   防复发：tests/_helpers/test_cli_exit_codes.py::test_ensure_dirs_only_declares_used_dirs
    #   （此处声明的每个常量都必须在 config.py 之外有真实使用者，否则就是"为了建空目录而建"）。
    for d in (OUTPUT_DIR, ELEMENT_MAP_DIR, LOG_DIR, SCRIPTS_DIR, CASES_DIR):
        d.mkdir(parents=True, exist_ok=True)
