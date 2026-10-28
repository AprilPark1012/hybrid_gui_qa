# V8.7.5 发布说明（2026-10-27）

> 上一版：V8.7.4（2026-10-26）· 版本号单一来源 = `build_tools/build_html.py:VERSION`

## 一句话

**体检说「可以用」，真跑却跑不动。** 小 schema 通过 ≠ 真实规模能跑；
外加把「实现出处」当成了「端点归属」，让用户以为配错了模型。

---

## 用户报的两个现象

### 现象 1：`provider` 显示 `deepseek`，可是端点明明是 GLM

```
[llm-doctor] provider  deepseek                                    ← 用户：感觉不太对
[llm-doctor] 端点      https://open.bigmodel.cn/api/paas/v4
[llm-doctor] 模型      glm-5.3
```

**根因**：框架为了接任意 OpenAI 兼容端点，复用了 `ChatDeepSeek` 作为基类。
它带着**实现类里写死**的 `provider='deepseek'`。`llm-doctor` 直接
`getattr(obj, "provider")` 打印，于是配 GLM 也显示 deepseek。

> 「**实现出处**」不等于「**端点归属**」。体检要报的是后者。

**修复**：厂商按**实际端点**认（复用 V8.7.3 的 `llm_vendor_of()`），
实现类单独标注，并报出配置来源 —— 「哪个厂商」「哪个客户端类」「配置来自哪组变量」
是三件事，排查时都需要。

```
[llm-doctor] provider  智谱 GLM（客户端实现类: ChatOpenAICompatible）
[llm-doctor] 配置来源  LLM_*
[llm-doctor] 端点      https://open.bigmodel.cn/api/paas/v4
[llm-doctor] 模型      glm-5.3
[llm-doctor] 思考档位  high
```

### 现象 2：发完第 2 次以后「卡住不走」

**根因**：`reasoning_effort` 与 `HYBRID_LLM_TIMEOUT` 的组合问题。

一次 explore 的真实节奏（实测）：

```
第 1 次 结构化输出   → 83.0s → Expected tool_calls in response but got none   ← low 档
第 2 次 纯文本兜底   → 33.4s → 拿到 4731 字符 / 51 步
一轮 ≈ 116s
```

而 `low` 档**在 11.6 万字符的 prompt 上根本不返回 tool_calls**，
结构化路径整个失效 —— 框架只能靠纯文本兜底，产出质量下降、更容易 L0 不合格，
于是进入重试。3 轮 × 116s ≈ 6 分钟，中间几乎没有输出，观感就是「卡住」。

---

## 三档实测对照（同一端点 / 同一模型 / 同一 11.4 万字符 prompt）

| `reasoning_effort` | `HYBRID_LLM_TIMEOUT` | 结果 |
|---|---|---|
| `low` | 180s | **83.0s → 零 tool_calls**（结构化路径失效） |
| `high` | 180s（默认） | **180.2s 超时**（差 4 秒就成功） |
| `high` | **400s** | **175.9s → 39 步成功** |

> 175.9 秒 vs 180 秒默认值只差 **4.1 秒** —— 默认值没有任何余量。

## 用户必做的配置（两项必须一起改）

```ini
# .env
LLM_REASONING_EFFORT=high      # 从 low 改成 high（low 在大 prompt 上不返回 tool_calls）
HYBRID_LLM_TIMEOUT=400         # 新增（默认 180 秒不够 high 档用）
```

- 只改档位 → **必然超时**（high 要 175.9s）
- 只改超时 → **结构化路径失效**（low 不出 tool_calls）

改完跑一次自检：

```bash
python -m framework.cli llm-doctor
```

第 3 项应该变成绿色的「大 prompt 实探 ... 真实规模下可用」。

---

## 本版改动

### 1. `llm-doctor` 新增第 3 项：大 prompt 实探

原先只发 2 次请求、用**极小 schema**（`ok: bool`），只证明「tools 通」——
这只够说「端点活着」，不够说「能跑」。现在加第 3 项：

- 走框架**自己的** `_build_planner_prompt()`（真链路同源，不是我手拼一份）
- 优先用真实 `element_map` 生成清单；本机没有则用合成清单兜底（并注明来源）
- 超时取 `llm_timeout_s()` —— 测的就是用户真实配置，不是另设一个数
- **实探失败会阻断「可以用」结论**，改成「小请求能用，但真实规模跑不动」

```
[llm-doctor] [OK] 连通      3.78s
[llm-doctor] [OK] function calling 正常（tool_calls 能解析）  5.67s
[llm-doctor] [OK] 大 prompt 实探  175.9s · 114225字符 → 39步（来源 真实 element_map）-> **真实规模下可用**
[llm-doctor] 结论：**可以用**（连通 + function calling + 真实规模实探都正常）。
```

失败时的样子（这是本版的核心价值 —— **不再给假保证**）：

```
[llm-doctor] [NG] 大 prompt 实探失败  180.2s · 114225字符 · ModelProviderError: Request timed out.
[llm-doctor]      -> 处置：把 HYBRID_LLM_TIMEOUT 提到 400+（GLM high 档实测 312s）。
[llm-doctor] 结论：**小请求能用，但真实规模跑不动** —— 别拿上面的「function calling 正常」
              当可以上生产（那两项用的是极小 schema）。
```

### 2. 结构化失败时点破真因

`Expected tool_calls in response but got none` 这条报文有**几乎唯一**的解释。
现在当场打印：

```
[explore] [i] 端点**给了内容但没有 tool_calls** —— 这多半不是模型不稳定，而是 reasoning_effort 太低：
[explore]     实测 GLM-5.3 在 low 档 + 大 prompt 下**完全不返回 tool_calls**，结构化路径失效。
[explore]     修法：LLM_REASONING_EFFORT=high，并把 HYBRID_LLM_TIMEOUT 提到 400+。
```

> 不加这句，用户会以为是「模型不稳定」去换模型 —— 其实是一个配置项。

### 3. `.env.example` 补登记 4 项

这几项此前**只活在源码里**，用户在 `.env` 里看不到、也就无从调：

| 项 | 默认 | 补记的关键提示 |
|---|---|---|
| `HYBRID_LLM_TIMEOUT` | 180 | high 档实测 175.9s；别设 0/负数（=取消超时，会永久挂住） |
| `HYBRID_AI_RETRY` | 2 | 上界 5 |
| `HYBRID_LLM_ATTEMPTS` | 3 | 结构化输出尝试次数 |
| `HYBRID_PROMPT_LIST_CHARS` | 90000 | **只约束「其余」控件**，必给层不占预算 → 116490 字符是正常的 |

---

## 判据（新增 13 条）

`tests/特性2-语义识别与步骤编排/test_llm_doctor_vendor_and_bigprobe.py`

| 组 | 钉住什么 |
|---|---|
| 厂商显示 | 必须用 `llm_vendor_of()` 按端点认；**不许**再直接打印实现类的 `provider` 字段；实现类单独标注；配置来源单列 |
| 厂商映射 | 走真入口验 endpoint → vendor；认不出时必须说「未识别」，不许瞎猜 |
| 大 prompt 实探 | 必须存在 `out["big"]`；必须复用 `_build_planner_prompt()`；超时必须取 `llm_timeout_s()`；**失败必须阻断「可以用」结论**；无 map 时须有合成兜底 |
| 报错点破 | 缺 tool_calls 时必须出现 effort 提示 + 超时值建议 |
| 可发现性 | `.env.example` 必须登记那 4 项，且写明 312 秒这个实测依据 |

**反向验证**：把三处改动退回旧写法 → **6 条变红**；恢复后 13 条全绿。
（过程中一度因 `assert` 写在 `try` 之前导致源文件没恢复，已用备份还原并重验 —— 见下方「过程记录」。）

---

## 过程记录（诚实留档）

1. 我一开始建议把 `LLM_REASONING_EFFORT` 从 `high` 改成 `low`，理由是「high 在 536 控件上 180s 超时」。
   **这个建议是错的**：当时没验证 low 会不会让模型不返回 tool_calls。实测 low 在 11.6 万字符 prompt 上
   **完全不返回 tool_calls**，把结构化路径打死了。本版已在代码里把这条教训固化成诊断提示。
2. 做反向验证时，第一版脚本把 `assert` 写在 `try` 之前，断言失败时 `finally` 没执行，
   导致 `cli.py` 停在「回退版」。发现后从备份还原、diff 校验一致、重跑 13 条判据全绿。
   **教训**：文件回滚逻辑必须放最外层 `try/finally`，断言不能挡在它前面。

---

## 升级检查清单

```bash
# 1) 改 .env（两项一起）
LLM_REASONING_EFFORT=high
HYBRID_LLM_TIMEOUT=400

# 2) 自检：第 3 项应为绿色「真实规模下可用」
python -m framework.cli llm-doctor

# 3) 换模型/换档位后要重录录像（录像键不含模型名，否则会命中旧模型录像）
python -m framework.cli explore --ai --scenario-file <yml> --llm-record

# 4) 真跑
python -m framework.cli all --ai --scenario-file scenarios/orders/orders_invoice_full_lifecycle.yml
```

---

## 兼容性

- 无破坏性变更。不设 `HYBRID_LLM_TIMEOUT` 仍是 180（旧行为不变），
  只是 `llm-doctor` 现在会告诉你「这个值在你的场景下够不够」。
- `llm-doctor` 输出**多了两行**（配置来源 + 大 prompt 实探）。若有脚本解析它的输出，
  注意按前缀匹配而不是按行号。
