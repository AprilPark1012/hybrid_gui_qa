# V8.7.14 发布说明（2026-10-28）

> 上一版：V8.7.12 · 版本号单一来源 = `build_tools/build_html.py:VERSION`

## 一句话

**成功不该被判成失败** —— 模型把结果写进 `content` 通道时，别再丢掉重试。

---

## 一、问题

你两份 `explore --ai` 日志里都有：

```
[explore] 第 1/3 次结构化输出失败 -> ModelProviderError: Expected tool_calls in response but got none
```

而且**几乎都在登录页**（`DOM 事实：7 条记录 / 并入清单 3 条`，极小 prompt）。

## 二、排查过程（一路试探，全部排除）

被怀疑过、又用数据否掉的假设：

| # | 假设 | 怎么否掉的 |
|---|---|---|
| 1 | 大 prompt 导致超时 | 构造 12 万字符 prompt 测，成功 |
| 2 | 端点 `/paas` vs `/coding` 差异 | 4 组 key×端点交叉全 200，后实测两端点都能跑 |
| 3 | `max_tokens` 不够（思考吃满配额） | 测 1500/3000/6000/8000 全成功；不传也成功 |
| 4 | 模型选择问题（flash vs 5.3） | 两者单轮都 100% 成功；且实测 flash **不比 5.3 快**（12 万字符时 42.2s vs 12.7s） |
| 5 | `reasoning_effort` 档位太低 | high/low 都成功；且 `low` 在 flash 上**不会**失效（与 5.3 历史结论不同） |
| 6 | 多轮历史累积 | 0/2/4/8 轮对照，首档 6/6 全过 |
| 7 | `_PLANNER_SYSTEM` 的「只输出 JSON」 | 2×2 因子实验（history × prompt）**四组全部 5/5** |
| 8 | `reasoning_effort` 放 `extra_body` | T1 顶层 38%、T2 extra_body **88%**、T3 不传 75% —— 反而 extra_body 最高 |

**用 curl 前后测了 100+ 次，全部 100% 成功，一个都复现不出来。**

## 三、转折：改用框架真链路

```
llm_from_env() + ChatOpenAICompatible.ainvoke(...)   →   10 次里 8 次命中 got none
```

**问题一直在封装层**，不在模型/端点/prompt。

这也印证了一条早就写进记忆的教训：**「手工 new 一个对象做实验 ≠ 真链路拿到的对象」**。我用 curl 绕开封装层测了 100 次，等于测了个假对象。

## 四、根因

上游 `browser_use/llm/deepseek/chat.py:179-180`：

```python
msg = resp.choices[0].message
if not msg.tool_calls:
    raise ValueError('Expected tool_calls in response but got none')   # ← content 在这里被丢掉
```

**而实测那 8 次的 `msg.content`：**

```json
{"steps":[{"order":1,"op":"fill","semantic_name":"账号","value":"super","desc":"在账号输入框填入 super"}, ...
```

- **全部是完整合法的 JSON**
- **`finish_reason=stop`**（正常结束，不是 `length` 截断、不是超时、不是限流）

**所以：模型答对了，只是没走工具通道。框架把这当成失败，重试，每次白等 10~20 秒。**

这是「**成功被当成失败**」，不是模型失败。

## 五、修法（两条）

### ① content 通道兜底（`framework/shared/llm_compat.py`）

```
命中 got none  →  is_missing_tool_calls() 精确判定  →  重发一次，同时收 tool_calls / content
                                                          │
                              content 是合法 JSON  →  解析复用 + 打印一行说明走了哪条通道
                              content 解析不出    →  如实抛错（绝不造假）
                              两者都没有          →  单独报错（空响应）
```

**口径（与项目「静默降级=造假」原则的边界）**：
- **必须打印一行**说明本次走的是 content 通道，不静默
- 解析不出来 / 不符合 schema → **如实抛错**，绝不返回空壳假装成功
- **只在这一种异常下走这条路**，超时/限流/400 照抛

`is_missing_tool_calls()` 的判定必须**精确**，判据里专门钉了三条反例：

```python
assert is_missing_tool_calls(Exception("Request timed out.")) is False
assert is_missing_tool_calls(Exception("429 rate limit exceeded")) is False
assert is_missing_tool_calls(Exception("Thinking mode does not support this tool_choice")) is False
```

吞掉这些比原来的 bug 更糟 —— 会把超时/限流伪装成「模型走了 content 通道」。

### ② prompt 通道对齐（`explorer_explore.py`）

```python
"你是 GUI 自动化测试规划师。只输出 JSON。"          ← 删掉
"你是 GUI 自动化测试规划师。**必须调用规划工具（_PlanModel）返回结构化结果**，
 不要用纯文本回复、也不要把 JSON 写进正文。"        ← 替换
```

路径 1 走的是 `output_format` = **强制 function calling**。提示词说「只输出 JSON」与它语义冲突 —— **模型选哪边都算听话**，表现为随机失败。

## 六、验证

| 手段 | 验证什么 | 结果 |
|---|---|---|
| **真链路 12 次**（新 prompt） | 修复后整体行为 | **12/12 OK** |
| 真链路 10 次（故意退回旧 prompt） | 尝试逼出 content 通道 | 10/10 OK（没触发） |
| **mock 单测 5 条** | 兜底 5 条分支 | **5 passed** |
| **反向验证**（摘掉接线） | 判据能否拦住 | **立刻变红**，恢复后 5 passed |
| 全量回归 | 没打破别的东西 | 见下方数字 |

**为什么用 mock 而不是只靠真链路**：`got none` 是偶发的 —— 修复前抓到 8/10，之后连续 22 次（含故意用旧 prompt）都不复现。**靠真链路碰运气去覆盖异常分支，等于交付没跑过的代码。**

兜底的 5 条单测：

| 测试 | 覆盖 |
|---|---|
| `test_content_channel_json_is_recovered` | content 是合法 JSON → 解析复用 + **出声** |
| `test_content_channel_tolerates_fence_and_chatter` | ```json 围栏 / 前后废话 |
| `test_content_not_json_raises_not_fakes_success` | 不是 JSON → **如实抛错** |
| `test_empty_response_raises_clearly` | 空响应 → 单独报错 |
| `test_tool_calls_path_does_not_print_content_notice` | 正常通道 → **不误报** |

## 七、新增排查工具

`build_tools/probe_real_llm_path.py` —— 用**真链路**（`llm_from_env()` + `ainvoke`）复刻 explore 的调用，跑 N 次统计成功率与失败类型。

```bash
PROBE_N=10 .venv/bin/python build_tools/probe_real_llm_path.py
```

**以后遇到「框架跑不通但 curl 通」的问题，直接用这个，别再绕开封装层猜。**

## 八、本次留下的实测数据

| 结论 | 数据 |
|---|---|
| `glm-5.3-flash` **不比** `glm-5.3` 快 | 12 万字符：flash 42.2s / 思考 1361 tokens；5.3 **12.7s** / 思考 501 |
| `glm-5.3-flash` 的 `low` 档**不会**失效 | 12 万字符下 low 也正常返回 tool_calls（与 5.3 的历史结论不同） |
| `reasoning_effort=medium` **不是有效档位** | 实测 reasoning_tokens=0（等同 low）；`minimal` 反而有 6 |
| 端点 `/paas/v4` 与 `/coding/paas/v4` **都能吃套餐** | 4 组交叉全 200；只能看费用明细「抵扣资源包」列 |
| `got none` **与 prompt 大小无关** | 登录页 3 条清单（极小）也会发生 |
| `got none` **是偶发的** | 修复前 8/10，连续 22 次其他地方不复现（受服务端状态影响） |

## 九、兼容性

**框架行为有一处变化**：以前 `got none` 一定抛错让上层重试；现在会先尝试 content 通道解析，成功则不重试、打印一行说明。

**你的配置继续有效**：
```ini
LLM_MODEL=glm-5.3-flash
LLM_BASE_URL=https://open.bigmodel.cn/api/coding/paas/v4
LLM_REASONING_EFFORT=high
HYBRID_LLM_TIMEOUT=900
```

⚠️ **`HYBRID_LLM_TIMEOUT` 记得设**：日志第 9 行显示 `超时 180s` 是**默认值**，你没设。`glm-5.3 + high + 大 prompt` 实测要 312s，180s 迟早撞上。

## 十、怎么验这一版

```powershell
# 1) 全量（约 1 分钟）
.venv\Scripts\python -m pytest tests\ -q

# 2) 只看这次的改动
.venv\Scripts\python -m pytest tests\特性2-语义识别与步骤编排\test_content_channel_fallback.py tests\特性2-语义识别与步骤编排\test_content_fallback_unit.py -v
# 预期 10 passed

# 3) 真链路探测（会发真实请求，约 3 分钟）
$env:PROBE_N=5; .venv\Scripts\python build_tools\probe_real_llm_path.py
# 预期全 OK；若出现「content 通道」提示，说明兜底在真实工作中
```

## 十一、改动仍未提交

按 R12：V8.7.12 已提交（`139c2f4`），**V8.7.14 等你验完点头再提交**，push 一律等你点头。

—— AprilPark1012
