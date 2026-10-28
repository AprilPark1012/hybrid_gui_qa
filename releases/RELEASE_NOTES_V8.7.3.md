# V8.7.3 发行说明（2026-10-26）

> 承接 **V8.7.2**（2026-10-25）。本版修的是**换 OpenAI 兼容端点（GLM）才暴露**的两个问题：
> 一个是「必然失败」，一个是「永久卡死」。两者叠加，表现为你看到的那样——跑着跑着不动了。

---

## 一、事故现场（V8.7.2 + GLM-5.3 实测）

```
[explore] DOM 事实：364 条记录（38 条带非默认状态），已并入清单 293 条…
[explore] 第 1/3 次结构化输出失败 -> ModelProviderError: 16 validation errors for _PlanModel
steps.1.semantic_name
  Input should be a valid string [type=string_type, input_value=None, input_type=NoneType]
```

日志到此为止，之后**再无一行输出**——看起来「卡住」，只能 Ctrl+C，且拿不到任何错误信息。

同一个场景、同一份代码，**10-25 用 DeepSeek 跑是通的**。差别只在模型端点。

---

## 二、根因 1：GLM 发 `null`，框架只兼容了「省略键」（必然失败）

`_StepModel.semantic_name` 定义是 `str = Field(default="")`。两种模型对「没填的字段」表达方式不同：

| 模型 | 行为 | Pydantic 结果 |
|---|---|---|
| DeepSeek | **省略该键** | 走 `default=""` → 通过 |
| **GLM-5.3** | 显式发 `null` | `default=` **不生效**，按类型校验 → **报错** |

实测报文里 `input_value=None` 就是铁证：GLM 的 function calling 给未填字段生成了 `null`。

⇒ **不是 GLM 答得差，是框架没兼容它的 null 习惯**。16 个步骤全缺 `semantic_name`，
所以 `_PlanModel` 整轮校验失败，**每轮必挂**——与场景复杂度、提示词都无关。

### 修复

`_StepModel` 加 `field_validator("*", mode="before")`：把**显式 null** 等价成**键缺失**，让 `default=` 生效。

口径（**放宽 null ≠ 放松校验**）：
- 只有「字段有非 None 的 default」才用 default 顶上；
- `X | None` 这类 `default=None` 的字段保持 `None`（本来就接受）；
- **任何真实值 / 错类型照样严格报错**（数字塞进 str、字符串塞进 int、列表塞进 str 都被判据锁住）。

---

## 三、根因 2：客户端 `timeout=None` = 永不超时（永久卡死）

`browser_use` 的 `ChatDeepSeek` 字段默认 `timeout: float | httpx.Timeout | None = None`，
而 `config.py` 构造时**没传** → 它被**显式赋成 None**：

```
显式 timeout=None  -> None                                          ← httpx: 禁用超时
不传 timeout        -> Timeout(connect=5.0, read=600, write=600)   ← SDK 默认
```

httpx 里 `timeout=None` 不是「用默认值」，是**禁用超时**。所以第 2 次重试遇到端点不回包，
客户端闭着眼等——这就是「卡住」。

**叠加放大**：SDK 自己还有 `max_retries=2`，框架 `HYBRID_LLM_ATTEMPTS=3`
⇒ 最坏 **3×3=9 次请求，每次都可以无限等**。

### 修复

两条腿（`LLM_*` 与出厂默认的 `DEEPSEEK_*`）都补上：

```python
timeout=llm_timeout_s(),            # 默认 180 秒，HYBRID_LLM_TIMEOUT 可调
client_params={"max_retries": 0},   # SDK 不再自己重试，重试唯一权威是框架的 attempts
```

新开关 **`HYBRID_LLM_TIMEOUT`**（默认 `180`），已登记进 `cli config` 可查可调。
**非法值/非正值一律回落 180**——尤其不许静默用 0/负数，那等于取消超时，正好是本次事故形态。

---

## 四、可观测性：重试轮要能看出「在等」而不是「死了」

事故里最难受的一点是**日志停在最后一行不动**，分不清端点还在算、还是已经死了。

现在每次**重试轮**（`attempt > 1`）在发请求前打印：

```
[explore] [i] 第 2/3 次请求已发出，等待端点响应（超时 180s）—— 长时间无新输出 = 端点没回包，
            到点会自动报超时而不是一直挂着
```

考虑到「静默等待最坏」，宁可多一行进度。

---

## 五、新增判据（`tests/特性2-语义识别与步骤编排/test_llm_null_and_timeout.py`，登记在 2.2）

| 判据 | 守什么 |
|---|---|
| `test_step_model_accepts_explicit_null_like_glm` | GLM 式 `null` 必须被 default 兜住 |
| `test_step_model_keeps_optional_fields_none` | `X \| None` 字段不许被兜成别的值 |
| `test_step_model_still_rejects_wrong_types`（3 个参数化） | **放宽 null ≠ 放松校验** |
| `test_step_model_keeps_real_values` | 正常值原样保留 |
| `test_llm_timeout_default_and_override` | 默认 180 / 可调 |
| `test_llm_timeout_illegal_falls_back`（5 个参数化） | 空/空白/abc/0/-5 全部回落 |
| `test_llm_client_really_has_timeout_via_real_entry` | 走**真入口** `llm_from_env()`，断言到 `_client()` 底层 httpx 客户端 |
| `test_deepseek_branch_also_has_timeout` | 出厂默认那条腿同样不许漏 |
| `test_retry_prints_progress_before_waiting` | 重试轮必须有进度输出，且限定在 `attempt > 1` |

> 「断言到 `_client()` 底层」是刻意的：只看 `client.timeout` 不够，真正决定 httpx 行为的是底层
> `AsyncOpenAI` 实例。历史上踩过「手工 new 一个对象做实验 ≠ 真链路拿到的对象」的假修。

---

## 六、验证

| 验证 | 结果 |
|---|---|
| 走真入口看底层客户端 | `timeout=180.0` · `max_retries=0`（两支都验） |
| 可调性 | `30→30` · `300→300` · `""/abc/0/-5 → 180` |
| null 兼容 | 显式 null → 用 default；错类型仍报错；真实值不被吞 |
| 新增判据 | 15 passed |
| 特性 9（spec 契约） | 427 passed |
| 全量 `pytest tests/` | 见正文（本版实测） |

---

## 七、对你的影响

- **用 DeepSeek**：行为不变（它本来就省略键、且现在有了 180 秒超时兜底，只会更快失败而不是挂死）。
- **用 GLM / Kimi / 通义等 OpenAI 兼容端点**：之前「一跑就 16 validation errors」的，现在能过。
- **端点抖动 / 网络异常**：从「永久卡死」变成「180 秒后明确报超时」，错误信息能看到。
- **不必改任何配置**：`HYBRID_LLM_TIMEOUT` 不设就是 180。

---

## 八、遗留（未在本版处理，避免混进来）

控件清单在这次实测里从 3 条涨到 **293 条**（DOM 事实 364 条），prompt 预算
`HYBRID_PROMPT_LIST_CHARS` 默认 9 万字符。清单这么大，任何模型漏字段的概率都会上升。
本版只修「必然失败」和「永久卡死」两条硬伤；**提示词瘦身属独立议题**，等这版在 Windows 上
验证通过后再单独评估——不把两件事混在一个版本里。
