# V8.6.1 发行说明（2026-10-14）

> 上游路径：`releases/RELEASE_NOTES_V8.6.1.md`（交付时随代码包一并发出）

## 一句话

**通用 LLM 入口**：一个开关接所有 OpenAI 兼容服务 —— 框架除了 DeepSeek，现在可以直接用
**GLM（智谱）/ Kimi（月之暗面）/ 通义 / 豆包 / Qwen / MiniMax / 本地 vLLM·Ollama**，
而且**接第 N 家都不用改代码**。配套一条 **`cli llm-doctor` 体检命令**（换模型前先跑它）
和 **`LLM_REASONING_EFFORT` 思考档位旋钮**。

> 顺带**修掉一个出厂就存在的老问题**：思考模式端点拒「指名函数」`tool_choice`，
> 导致框架的结构化输出路径**一直在失败、一直走文本兜底** —— 现在自动降级为 `auto` 重试，已恢复。

## 缘起

用户提问：「框架除了能用 DeepSeek，还能用其他模型吗？比如 GLM、Kimi 能用吗？」

实测答案：**能**。DeepSeek / GLM / Kimi 都是 OpenAI 兼容协议，框架的 LLM 层
（`browser_use.llm`）与它们之间只差三个环境变量。但原状有两个毛病：

1. 变量名**写死成 `DEEPSEEK_*`** —— 配 Kimi 却要写 `DEEPSEEK_API_KEY`，语义错乱；
2. 接第 6 家**必须改代码**（provider 是 5 个写死的 `if` 分支）——
   违背「补能力必须与场景解耦」。

## 怎么用（换模型只动三个变量）

```bash
# ---- 智谱 GLM ----
LLM_API_KEY=你的 GLM key
LLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4
LLM_MODEL=glm-4.7

# ---- 月之暗面 Kimi ----
LLM_API_KEY=你的 Kimi key
LLM_BASE_URL=https://api.moonshot.cn/v1
LLM_MODEL=kimi-k3

# ---- 本地 vLLM / Ollama（OpenAI 兼容端口）----
LLM_API_KEY=任意非空值
LLM_BASE_URL=http://localhost:8000/v1
LLM_MODEL=你的本地模型名
```

**优先级**：`LLM_*` > `BROWSER_USE_API_KEY` > `OPENAI_API_KEY` > `ANTHROPIC_API_KEY` >
`GOOGLE_API_KEY` > `DEEPSEEK_*`（**旧写法仍然支持**）。

**升级须知**：**未配置 `LLM_API_KEY` 时行为完全不变** —— 老用户零影响。

## 两条重要提醒

### ① 换模型后请重录录像

录像键是 `sha256(system + prompt)`，**刻意不含模型名**（为保住「有外网的机器录、离线机器放」的可用性）。
代价是：**换了模型仍会命中旧模型的录像** —— 离线机器没配环境变量时更是静默通过，
你会以为「我在用 GLM 跑」，实际吃的却是另一个模型录下的结论。

V8.6.1 起框架会在回放时**对比录像里的模型名与当前模型，不一致就打印告警**并给出下一步：

```
[explore] [LLM] [!] **模型不一致**：录像由 `deepseek-chat` 录制，当前配置的是 `glm-4.7`。
                 -> 录像键刻意不含模型名，所以换模型后仍会命中旧录像…
                 -> 想在 `glm-4.7` 上重新出结论：清掉录像目录，或加 `--llm-record` 重录一份。
```

### ② 模型需支持 function calling（工具调用）

框架的结构化输出走 **`tools`**（function calling），**不是** `response_format` json_schema。
原因（实测抓包对比，非推断）：

| 客户端 | 结构化输出靠什么 | 第三方端点支持度 |
|---|---|---|
| `ChatDeepSeek`（本项目采用）| `tools` + `tool_choice` | ✅ **function calling 是主流能力**，GLM / Kimi 官方都支持 |
| `ChatOpenAI` | `response_format=json_schema(strict=True)`，**不发 tools** | ⚠️ 参差；实测走它时结构化输出**连续 3 次失败** |

**GLM-4.7 及以上、Kimi K2 / K3 系列**都支持 tool calling。

> [!] **但「支持 tool calling」不等于「你的档位能用」**：**思考模式**的端点（如默认配置的
> `deepseek-flash`）会拒绝**指名函数**形式的 `tool_choice`。V8.6.1 起框架会**自动降级为
> `tool_choice=auto` 重试**（详见 ⑤），但**换模型后仍请跑一次 `llm-doctor` 实测** ——
> 各家的坑不一样，别只看文档。

### ③ 换模型前先跑体检：`cli llm-doctor`

```bash
python -m framework.cli llm-doctor
```

真发 **2 次请求**（① 纯文本验连通 ② 带极小 schema 验 function calling），两秒出结论：

```
[llm-doctor] provider  deepseek
[llm-doctor] 端点      https://api.deepseek.com
[llm-doctor] 模型      deepseek-flash
[llm-doctor] 思考档位  (未设 -> 服务端默认)
[llm-doctor] [OK] 连通      1.89s
[llm-doctor] [!!] function calling 被端点拒了（0.18s）: 400 Thinking mode does not support this tool_choice
[llm-doctor]      -> 这是**思考模式端点**的行为。框架会自动退到纯文本路径：能跑，但少了结构约束。
[llm-doctor]      -> 机理（实测）：这类端点拒的是「指名函数」和 `required`，而**接受 `auto` / 不传**。
```

**为什么需要它**：换模型这类问题**只有真发一次请求才知道** —— 查文档会查错（我一度断言
GLM-5.2 不在册，实际它 2026-06-16 就发布了），而烧一次完整端到端要 4 分钟 + 十几次调用。

退出码：`0` = 可用（**含「能用但打折」**，会标 `[!!]`）；`2` = 不可用（没配 key / 连不通 / tools 不通）。
**不打印密钥**；只发 LLM 请求，所以**不需要浏览器**。

### ④ `LLM_REASONING_EFFORT` 思考档位旋钮

```bash
LLM_REASONING_EFFORT=low      # low / medium / high / max；空 = 不发该字段（用端点默认）
```

**起因**：GLM-5.3 起**不允许完全关闭思考**，且默认 `max` 档；而探索阶段**每一步都要调一次
LLM**（一次端到端十几二十次）⇒ 等于每步都跑最贵的推理级别，又慢又贵。

⚠️ **它治不了 ② 里那个 `tool_choice` 被拒**（实测：`deepseek-flash` 设 `low` 仍报同一个 400）——
它治的是「默认跑 max 档」。

### ⑤ 🔴 体检第一次跑就抓到的真问题 —— **已修**

**现象**：出厂配置的 `deepseek-flash` 报
`400 Thinking mode does not support this tool_choice`
⇒ 框架的**结构化输出路径其实一直在失败、一直走文本兜底**（V8.4.1 的降级逻辑兜住了，所以没炸，
但少了结构约束）。**这解释了为什么 AI 产出一直"还行但不够稳"。**

**根因（实验定位）**：该端点拒的是「**指名函数**」和 `required` 这两种 `tool_choice` 取值，
而**接受 `auto` / 不传**：

| `tool_choice` 传什么 | 结果 |
|---|---|
| 不传 | ✅ 通过，返回 tool_calls |
| `"auto"` | ✅ 通过，返回 tool_calls |
| `"required"` | ❌ 400 |
| 指名函数 | ❌ 400 |

而 browser_use 内置客户端发的恰好是**指名函数**
（`deepseek/chat.py:170`：`tool_choice={'type':'function','function':{'name': …}}`）—— 正好撞上。

**修法**：撞到这个错就**改用 `tool_choice=auto` 自己发一次请求**，结构化输出路径因此恢复。

> 为什么**不借道**上游「只给 tools、不给 output_format」那条分支：实测它自己有 bug ——
> 那条分支把原始 dict 塞进 `ChatInvokeCompletion(completion=<dict>)`，pydantic 按 TypeVar
> 上界 `BaseModel` 去校验，直接报 `BaseModel cannot be instantiated directly`（走不通的死路）。

**兜底的边界**（兜底必须有边界、可审计）：

| 边界 | 做法 |
|---|---|
| 只认特征明确的错 | 必须同时出现 `tool_choice` 与「不支持」语义；`500` / `401` / 超长等**照抛**（误吞 = 拿兜底盖真故障）|
| 只重试一次 | 不循环；且**记住端点特性**，本进程内后续直接走降级形态（一次端到端十几二十次调用，不白试）|
| 不丢可调项 | 降级请求仍带 `reasoning_effort` |
| 留痕 | 降级时打印一行，**不静默** |
| 不许假装成功 | 拿不到 `tool_calls` **如实抛错**，由上层退到纯文本路径 —— 不返回"看起来成功"的空壳 |

**实测对照（真实 `api.deepseek.com`）**：

```
① 上游原生            -> 失败（复现 400）
② 新客户端(自动降级)  -> 成功 · 1.32s   字段: {'ok': True, 'word': '好'}
③ 新客户端(第二次)    -> 成功 · 0.88s（不再白试 = 已记住端点特性）
④ 特征识别反向自证    -> 4/4 正确（不是 tool_choice 的错照抛）
```

> ⚠️ `LLM_REASONING_EFFORT=low` **与这件事无关**（实测设 low 仍会触发降级）——
> 它治的是「端点默认跑 max 档、又慢又贵」。两件事别混。

## 改了什么

| 文件 | 改动 |
|---|---|
| `framework/shared/config.py` | `llm_from_env()` 新增通用入口分支（**优先级最高**）；`auto_detect_llm()` 认 `LLM_API_KEY`；通用分支改用 `ChatOpenAICompatible` 并接 `LLM_REASONING_EFFORT`（空值按「没设」）|
| **`framework/shared/llm_compat.py`**（新） | `ChatOpenAICompatible` = `ChatDeepSeek` 子类：① 覆盖 `_request_kwargs()` 注入 `extra_body.reasoning_effort`（**与 deepseek-v4 的 thinking 开关合并而非覆盖**）；② **`tool_choice` 拒绝时有界降级**（撞 400 就改用 `auto` 自己发一次请求，记住端点特性后不白试）|
| `framework/features/f02_semantic/explorer_explore.py` | `_llm_model_name()` 退路按 `LLM_MODEL > DEEPSEEK_MODEL`；**新增换模型告警**；失败提示补通用变量名 |
| `framework/features/f08_replay/llm_cassette_explore.py` | `lookup()` 三处 return（strict / struct / fuzzy）带出 `_model`（层间解耦：录像层只管带出来，比对由 explorer 做）|
| `framework/features/f10_cli/cli.py` | **新增 `cmd_llm_doctor`** + 4 处注册（`CMD_FLAGS` / `ENV_TO_FLAG` / `_CMD_FUNCS` / `main` 分发）；`FLAG_SPECS` 补 3 项；`cli config` 新增 4 项；**新增密钥脱敏**；`LLM_API_KEY` **刻意不给 CLI 参数**（密钥写进命令行会留 shell 历史）|
| `tests/特性10-CLI帮助契约/test_llm_provider_switch.py` | 7 条判据（并把「通用入口」断言升级为**行为级**：`issubclass(ChatOpenAICompatible, ChatDeepSeek)`）|
| **`tests/特性10-CLI帮助契约/test_llm_doctor.py`**（新） | 12 条判据（见下），含**真起假 OpenAI 端点**的端到端测试（不依赖外网）|
| **`tests/特性10-CLI帮助契约/test_llm_tool_choice_fallback.py`**（新） | 16 条判据，专钉**兜底的边界**而非「能用」（见下）|
| `.env.example` | 补通用入口（GLM/Kimi/Qwen/MiniMax 端点举例）+ `LLM_REASONING_EFFORT`；删掉停留在旧版本的注释 |
| `README.md` / `docs/training.html` | 文档同步：配置示例更新到 `glm-5.3`；新增体检入口与思考档位说明；培训页补上「思考模式拒 `tool_choice`」这个实测坑 |

## 新增判据（10.8 通用入口 7 条 + 10.9 LLM 体检 12 条 + 10.10 tool_choice 降级 16 条）

**10.8**：① 通用入口必须**走 function calling** ② 优先级最高 ③ `auto_detect_llm()` 认 `LLM_API_KEY`
④ 可被 `cli config` 发现 ⑤ 密钥值不许被打印 ⑥ `LLM_API_KEY` 不许映射 CLI 参数 ⑦ 换模型命中旧录像必须告警。

**10.9**：① 旋钮**真的进请求体**（断言 `_request_kwargs()` 的**产出**，不是断言「我们调了它」——
上游改签名要能立刻红，而不是静默失效）② 不设时不发 ③ 与 `thinking` 合并不覆盖 ④ 空值按没设
⑤ 可发现（`cli config` + CLI 参数）⑥ 命令注册齐全（**四处缺一不可**）⑦ 不进浏览器预检
⑧ 不打印密钥 ⑨ 无 key 时 exit 2 且给人话 ⑩⑪ 健康路径 / 「能用但打折」路径端到端
⑫ 旋钮真的到了线上请求体。

**10.10**：① 特征识别必须**窄**（7 组正反样本；误吞 = 拿兜底盖真故障）② **穿透异常链**（上游把 APIStatusError 包成 ModelProviderError，只看外层会漏判）③ 降级**真发 `tool_choice=auto`**、且第一次确实发的是指名函数（否则兜底是空转）④ 不丢 `reasoning_effort` ⑤ **只重试一次 + 记住端点**（第二次只发 1 个请求）⑥ 留痕不静默 ⑦ 非 tool_choice 的错照抛且**不写进端点缓存** ⑧ 拿不到 `tool_calls` **如实抛错** ⑨ 纯文本调用不被这层动到。

## 验证真值（2026-10-14 本机实测）

| 项 | 结果 |
|---|---|
| 全量判据 | `1165 passed / 3 skipped / 0 failed` |
| `cli config` | 新增 4 项可见，`LLM_API_KEY` 只报「未设置」不显示值 |
| 实测（本地假 OpenAI 端点抓请求体）| 走 `LLM_*` 时收到 `model='kimi-k3'` + `tools=1/tools=0` 交替 —— 与老路径行为完全一致 |
| 体检跑真端点 | 对 `api.deepseek.com` 真发请求：纯文本 `[OK] 连通 1.89s`；带 tools 得 400 `Thinking mode does not support this tool_choice` —— **即下条发现的来源** |
| `tool_choice` 取值实验 | 不传 / `auto` ✅ 返回 tool_calls；`required` / 指名函数 ❌ 400（详见 ⑤）|
| 思考档位实验 | `LLM_REASONING_EFFORT=low` 对该模型**无效**（仍 400）—— 如实说明，不含糊 |
| **tool_choice 降级（真实端点对照）** | 上游原生**失败**；新客户端**成功**拿到已校验对象（1.32s）；第二次 0.88s 且不再白试；特征识别反向自证 4/4 |
| 端到端 | 见提交时实测（回放模式，不烧 LLM 费用）|
