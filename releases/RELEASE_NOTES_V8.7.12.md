# V8.7.12 发布说明（2026-10-28）

> 上一版：V8.7.11（2026-10-28）· 版本号单一来源 = `build_tools/build_html.py:VERSION`

## 一句话

**诊断不许瞎猜** —— `got none` 先读 effort 再说话，别再把人往错方向带。

---

## 一、问题：框架的诊断把方向带反了

你在 Windows 上跑 V8.7.11 的 `explore --ai`，日志出现：

```
[explore] 第 1/3 次结构化输出失败 -> ModelProviderError: Expected tool_calls in response but got none
[explore] [i] 端点**给了内容但没有 tool_calls** —— 这多半不是模型不稳定，而是 reasoning_effort 太低：
[explore]     实测 GLM-5.3 在 low 档 + 大 prompt 下**完全不返回 tool_calls**（V8.7.5 复现：83s / 11.6 万字符）
[explore]     修法：LLM_REASONING_EFFORT=high，并把 HYBRID_LLM_TIMEOUT 提到 400+
```

**这段话三层全错：**

| 框架断言 | 实际情况 |
|---|---|
| 「这多半**不是**模型不稳定」 | **就是模型偶发不稳定** —— 同一 prompt 第 2 次重试就过了 |
| 「**大 prompt** 下才失效」 | 出错的是**登录页**：`DOM 事实：7 条记录，并入清单 3 条` —— **极小 prompt** |
| 「修法：改成 high」 | 你的 `LLM_REASONING_EFFORT` **本来就是 high** |

## 二、实际代价（这才是要修的真正理由）

这条错误诊断把排查**带偏了整整一轮**。按它的指引，我们先后排查了：

1. **大 prompt 规模** → 构造了 12 万字符的 prompt 去测（成功，排除）
2. **端点差异** → `/coding/paas/v4` vs `/paas/v4` 交叉测（都成功，排除）
3. **`max_tokens`** → 测 1500/3000/6000/8000 全成功（排除）
4. **换模型** → 还基于「轻量模型更快」的错误常识推荐了 flash（后来实测 flash 反而比 5.3 慢 3 倍）

**全部白跑。** 真正该做的一直是：**让重试兜住它**（框架本来就有 3 次重试，这次也是第 2 次就过了）。

## 三、修法：先读现场证据，再下结论

诊断改为**先读 `LLM_REASONING_EFFORT` 再分流**：

```python
_eff = (os.environ.get("LLM_REASONING_EFFORT") or "").strip().lower()
if _eff in ("", "low", "minimal"):
    # 档位确实偏低 —— 这才是原结论适用的场景
    print("... 档位偏低是**主要嫌疑**：")
    print("... 修法：LLM_REASONING_EFFORT=high ...")
else:
    # effort 已经够高 —— 别再说是档位问题，那是误导
    print(f"... 当前 reasoning_effort={_eff}，**所以不是档位太低**，而是模型**偶发不调工具**：")
    print("... 处置：让**重试**兜住它（HYBRID_LLM_ATTEMPTS 默认 3，可加到 5）；")
    print("... 连续多次仍失败再查提示词/端点，**别去改 reasoning_effort**。")
```

**删掉了那句误导措辞**：「这多半不是模型不稳定」。

## 四、一条通用教训

> **诊断信息本身也是一种交付物。** 它错了比没有更糟 —— 因为它会把人引向错误的方向，且看起来「很有把握」。

**硬编码的因果断言必须以「能读到的现场证据」为前提，读不到就说不确定。** 这次的反面是：框架在拿不到 `finish_reason`（browser-use 的异常里没带这个字段）的情况下，直接断言了根因。

**补充**：如果将来能拿到 `finish_reason`，正确分流应该是：

| `finish_reason` | 真实原因 | 处置 |
|---|---|---|
| `length` | 输出被 `max_tokens` 截断（思考吃满配额） | 加大 `max_tokens` |
| `stop` + 无 tool_calls | 模型偶发不调工具 | 靠重试兜住 |
| 超时 | 端点没回包 | 调大 `HYBRID_LLM_TIMEOUT` |

## 五、新增判据 `test_got_none_diagnosis_honesty.py`（4 条）

| 判据 | 守什么 |
|---|---|
| `test_diagnosis_reads_effort_before_advising` | 必须先读 `LLM_REASONING_EFFORT`，且按偏低/已高分流 |
| `test_high_effort_does_not_blame_the_knob` | effor 已高时，不许再出现「档位太低 / 改 high」 |
| `test_old_misleading_phrase_is_gone` | 「这多半不是模型不稳定」不许出现在**实际话术**里（只查非注释代码，注释里的反面教材合法） |
| `test_both_branches_are_reachable_in_source` | 正向自证：两支话术都真实存在 |

**反向验证做过**：把分流条件改成 `if True:` → 判据立刻变红；还原 → 4 passed。

## 六、本次排查留下的实测数据（供以后参考）

| 结论 | 数据 |
|---|---|
| `glm-5.3-flash` **不比** `glm-5.3` 快 | 12 万字符 prompt：flash 42.2s / 思考 1361 tokens；5.3 **12.7s** / 思考 501 tokens |
| `glm-5.3-flash` 的 `low` 档**不会**失效 | 12 万字符下 low 也正常返回 tool_calls（与 5.3 的历史结论不同） |
| `reasoning_effort=medium` **不是有效档位** | 实测 reasoning_tokens=0（等同 low）；`minimal` 反而有 6 |
| 端点 `/paas/v4` 与 `/coding/paas/v4` **都能工作** | 4 组 key×端点交叉全部 200；吃套餐的判断只能看费用明细「抵扣资源包」列 |
| `got none` **与 prompt 大小无关** | 登录页 3 条清单（极小）也复现 |

## 七、兼容性

**框架运行行为零变更** —— 只改诊断话术 + 加判据。

你验证过的配置继续有效：
```ini
LLM_MODEL=glm-5.3-flash
LLM_BASE_URL=https://open.bigmodel.cn/api/coding/paas/v4
LLM_REASONING_EFFORT=high
HYBRID_LLM_TIMEOUT=900
```

**可选**：把 `HYBRID_LLM_ATTEMPTS` 从 3 加到 5，让重试更好地兜住偶发失败（这次的 `got none` 就是重试救回来的）。
