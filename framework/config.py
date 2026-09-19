"""配置：目标 URL、LLM provider、输出目录。"""
from __future__ import annotations
import os
from pathlib import Path

from dotenv import load_dotenv  # type: ignore

BASE = Path(__file__).resolve().parent.parent
# 先加载项目 .env（若有，可覆盖），再加载 Hermes 主 .env（复用 DEEPSEEK_API_KEY）
load_dotenv(BASE / ".env")
_hermes_env = Path.home() / ".hermes" / ".env"
if _hermes_env.exists():
    load_dotenv(_hermes_env, override=False)   # 项目 .env 优先，Hermes 兜底

# ---- 被测应用 ----
# 目标地址：TARGET_URL（本项目老名字）> HYBRID_BASE_URL（生成脚本/target_probe 用的名字）> 默认。
# 2026-09-15 统一：以前只有 probe/generate 认 TARGET_URL、而生成脚本与 /api/health 探测认
# HYBRID_BASE_URL ⇒ 只设 HYBRID_BASE_URL 的人会发现「probe 还在打 localhost:8000」，
# 属于「参数名不新手秒懂」。现在两个名字等效（TARGET_URL 优先，保持向后兼容）。
TARGET_URL = (os.environ.get("TARGET_URL")
              or os.environ.get("HYBRID_BASE_URL")
              or "http://localhost:8000")

# ---- 版本号单一来源（2026-09-19 把 build_html.py 挪进 tools/ 时收敛）----
# 培训页生成器 `tools/build_html.py` 顶部的 VERSION / VERSION_DATE 是**唯一**版本来源。
# 路径只在这里定义一次；读版本一律走 read_version()（cli / llm_cassette / pack_release 共用）
# ⇒ 以后再挪位置只改这一行；漏改会被 tests/test_cli_flags.py 的判据当场抓住（--version 不许变 unknown）。
VERSION_SOURCE = BASE / "tools" / "build_html.py"


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
# ⇒ 凭空多出空目录。已整体删除；防复发见 tests/test_cli_exit_codes.py::test_ensure_dirs_only_declares_used_dirs。

# ---- P5 数据驱动新增目录 ----
LOG_DIR = BASE / "log"                       # 用例执行日志
SCENARIOS_DIR = BASE / "scenarios"           # 用例编排表(index.json)

# ---- 重构后的目录 ----
CASES_DIR = BASE / "cases"                   # ★ 手写的自然语言用例文件（写死数据）
SCRIPTS_DIR = BASE / "scripts"               # ★ generate 产物（playwright 脚本 + datasets 抽离）

# ---- Browser Use 探索阶段需要 LLM ----
# 负责"智能理解"：读懂自然语言测试意图、规划步骤、挑元素、写 plan。
# 这是 AI 之力的成本来源（每步一次模型推理）。
def llm_from_env():
    """按 .env 里配了哪个 key，构造对应的 Browser Use LLM 实例。
    优先级: ChatBrowserUse > OpenAI > Anthropic > Google > DeepSeek(ChatDeepSeek 原生)。"""
    try:
        from browser_use.llm import ChatBrowserUse, ChatOpenAI, ChatAnthropic, ChatGoogle
    except ImportError as e:
        raise ImportError(
            "browser-use 未安装。pip install browser-use 后重试。"
        ) from e

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
    # 3) DeepSeek —— 用 browser-use 0.13.10 原生 ChatDeepSeek（OpenAI 兼容，走 function calling）
    if os.environ.get("DEEPSEEK_API_KEY"):
        from browser_use.llm.deepseek.chat import ChatDeepSeek
        return ChatDeepSeek(
            api_key=os.environ["DEEPSEEK_API_KEY"],
            base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
            model=os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
            temperature=0.0,
        )
    raise RuntimeError(
        "未检测到 LLM 环境变量。请在 .env 配置 BROWSER_USE_API_KEY / "
        "OPENAI_API_KEY / ANTHROPIC_API_KEY / GOOGLE_API_KEY / DEEPSEEK_API_KEY 之一。"
    )


def auto_detect_llm() -> bool:
    """是否检测到可用的 LLM key（Healer 的 Level-B 语义重猜才启用）。"""
    return bool(os.environ.get("BROWSER_USE_API_KEY") or os.environ.get("OPENAI_API_KEY")
                or os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("GOOGLE_API_KEY")
                or os.environ.get("DEEPSEEK_API_KEY"))


def ensure_dirs():
    # 2026-09-13 冷启动排查补：原来不含 LOG_DIR / SCRIPTS_DIR / CASES_DIR ——
    # 冷启动（目录被清掉）时它们只是"碰巧"被后续 parents=True 的 mkdir 建出来，
    # 属于隐式依赖；这里显式建，任何入口都不会因为缺目录而诡异失败。
    # 2026-09-14 收窄（用户反馈「空目录残留」）：
    #   急切创建只保留「入口扫描/写入之前不会自建」的目录。
    #   TRACE_DIR / HEALS_DIR 的写入方（runner.record_trace / healer.dump）**使用前显式 mkdir**
    #   ⇒ 不是隐式依赖；在此急切创建只会让空目录常驻仓库。谁要写谁自建。
    #   防复发：tests/test_cli_exit_codes.py::test_ensure_dirs_only_declares_used_dirs
    #   （此处声明的每个常量都必须在 config.py 之外有真实使用者，否则就是"为了建空目录而建"）。
    for d in (OUTPUT_DIR, ELEMENT_MAP_DIR, LOG_DIR, SCRIPTS_DIR, CASES_DIR):
        d.mkdir(parents=True, exist_ok=True)
