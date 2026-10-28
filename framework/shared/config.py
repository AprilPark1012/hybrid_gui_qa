"""配置：目标 URL、LLM provider、输出目录。"""
from __future__ import annotations
import math
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


def llm_timeout_s() -> float:
    """LLM 单次请求超时（秒）。默认 180，`HYBRID_LLM_TIMEOUT` 可调。

    [!] 为什么必须**显式**给一个数（V8.7.3，2026-10-26 实测）：
        browser_use 的 `ChatDeepSeek` 字段默认是 `timeout: ... | None = None`，
        而我们构造时不传 -> 它被**显式赋成 None** -> `AsyncOpenAI(timeout=None)`
        -> httpx 里 **None = 禁用超时**（不是"用默认值"！）。
        实测（GLM-5.3 + 结构化输出重试）：第 1 次输出不合格后发第 2 次，端点不回包，
        客户端**永久挂住** —— 日志停在「第 1/3 次结构化输出失败」那行，用户只能 Ctrl+C，
        且拿不到任何错误信息。对照：不传 timeout 时 SDK 默认是
        `Timeout(connect=5.0, read=600, write=600, pool=600)`。

    取值口径：GLM/DeepSeek 出一次「十几步的结构化 JSON」实测 20~60 秒；给 180 秒
    留足余量，又不至于让人干等十分钟。非法/非正值一律回落默认（不静默变成 0=禁用）。
    """
    raw = str(os.environ.get("HYBRID_LLM_TIMEOUT") or "").strip()
    if not raw:
        return 180.0
    try:
        val = float(raw)
    except ValueError:
        return 180.0
    # [!] 必须挡 inf / nan：`float("1e400")` == inf，而 `inf > 0` 成立 ->
    #   会被当成合法超时传给 httpx，效果等于**又禁用了一次超时**（同一个坑换了个门进来）。
    if not math.isfinite(val) or val <= 0:
        return 180.0
    return val


def verify_timeout_s() -> float:
    """`--verify` 试跑**单条**用例的超时（秒）。默认 900，`HYBRID_VERIFY_TIMEOUT` 可调。

    为什么必须有：试跑走 `run_capture(... timeout=None)`，即**子进程卡住父进程就永久等**。
    真实全链路用例（实测 62 步）里有「等订单状态按时间流转」这类有界等待（最长约 160s），
    正常总耗时 3~6 分钟；但 demo 没响应 / 等待条件永不满足时，没有超时就是**真的卡死**，
    用户只能 Ctrl+C，还看不出卡在哪（2026-10-27 用户实测报「卡住了」）。

    900 秒 = 实测 360 秒的 2.5 倍余量。非法/非正值一律回落默认（不静默变成 0=禁用）。
    """
    raw = str(os.environ.get("HYBRID_VERIFY_TIMEOUT") or "").strip()
    if not raw:
        return 900.0
    try:
        val = float(raw)
    except ValueError:
        return 900.0
    # [!] 同 llm_timeout_s：挡 inf / nan（`float("1e400") == inf` 会让超时失效）
    if not math.isfinite(val) or val <= 0:
        return 900.0
    return val


#: 端点 -> 厂商的人话映射。**只用于打印给人看**，不参与任何逻辑判断
#: （判断该不该用某端点，只看它是否 OpenAI 兼容，不靠这张表）。
_LLM_VENDOR_HINTS = (
    ("bigmodel.cn", "智谱 GLM"),
    ("deepseek.com", "DeepSeek"),
    ("moonshot.cn", "月之暗面 Kimi"),
    ("dashscope.aliyuncs.com", "阿里通义"),
    ("volces.com", "字节豆包"),
    ("siliconflow", "硅基流动"),
    ("localhost", "本地端点（vLLM/Ollama 等）"),
    ("127.0.0.1", "本地端点（vLLM/Ollama 等）"),
)


def llm_vendor_of(base_url: object) -> str:
    """把端点认成厂商名（认不出就说认不出，**不瞎猜**）。"""
    low = str(base_url or "").lower()
    for frag, name in _LLM_VENDOR_HINTS:
        if frag in low:
            return name
    return "未识别的端点"


def llm_source_env() -> str:
    """当前是由**哪一组环境变量**提供的 LLM。顺序必须与 llm_from_env() 一致。"""
    for var, label in (
        ("LLM_API_KEY", "LLM_*"),
        ("BROWSER_USE_API_KEY", "BROWSER_USE_API_KEY"),
        ("OPENAI_API_KEY", "OPENAI_API_KEY"),
        ("ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY"),
        ("GOOGLE_API_KEY", "GOOGLE_API_KEY"),
        ("DEEPSEEK_API_KEY", "DEEPSEEK_*"),
    ):
        if os.environ.get(var):
            return label
    return "未配置"


def describe_llm(obj=None) -> str:
    """一行说清**实际生效**的 LLM：模型 / 端点 / 厂商 / 配置来源 / 超时。**绝不打印 key**。

    [!] 刻意从**已经构造好的 obj** 读属性，而不是重读环境变量（V8.7.4，2026-10-26）：
        重读环境变量得到的是「配置里写的」，而 obj 承载的是「真链路实际在用的」——
        命令行的 `--llm-model` / `--llm-base-url` 覆盖只体现在 obj 上。
        历史教训：拿"配置值"当"实际值"报，会得出错的结论。

    [!] 为什么要它：用户问「跑 all --ai 到底用的是 GLM 还是 DEEPSEEK」——
        这件事**必须从真链路打印**，不能靠人去看 .env 猜（两组变量名都能接 GLM，
        `DEEPSEEK_*` 里填 GLM 端点是合法用法，光看变量名会误判）。
    """
    model = "?"
    for attr in ("model_name", "model"):
        v = getattr(obj, attr, None)
        if isinstance(v, str) and v.strip():
            model = v.strip()
            break

    base = getattr(obj, "base_url", None)
    base_s = str(base) if base else "(端点默认)"
    host = base_s
    try:
        from urllib.parse import urlsplit
        sp = urlsplit(base_s if "//" in base_s else "//" + base_s.lstrip("/"))
        host = sp.netloc or base_s
        if sp.path and sp.path not in ("/", ""):
            host = f"{host}{sp.path}"
    except Exception:
        pass

    timeout = getattr(obj, "timeout", None)
    to_s = f"{timeout:g}s" if isinstance(timeout, (int, float)) else (
        str(timeout) if timeout else f"{llm_timeout_s():g}s")

    return (f"{model} @ {host} → {llm_vendor_of(base_s)}"
            f"｜配置来源 {llm_source_env()}｜超时 {to_s}")


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
            timeout=llm_timeout_s(),          # [!] 见 llm_timeout_s()：不给就是永不超时
            # [!] SDK 层不再自己重试：框架的重试（HYBRID_LLM_ATTEMPTS，默认 3）已经是
            #     唯一权威。SDK 默认 max_retries=2 会与它相乘 -> 最坏 3×3=9 次请求，
            #     每次都可以等满一个 timeout（180s）= 27 分钟才报错，看着就是"卡死"。
            client_params={"max_retries": 0},
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
            timeout=llm_timeout_s(),          # [!] 同上：不给就是永不超时（httpx 语义）
            client_params={"max_retries": 0},  # [!] 同上：重试唯一权威是框架的 attempts
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
