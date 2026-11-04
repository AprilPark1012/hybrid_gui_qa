# V8.9.4 发行说明

**日期**：2026-11-04
**主题**：堵两个「看不见的假绿」—— 自愈零判据（L11）+ 行区产物带病分发（A′）

---

## 一、B · 自愈 5 条行为判据（原 L11「零判据」）

### 为什么这块最危险

`framework/features/f06_healer/healer_run.py`（178 行）**真接在生成链上**：

```python
generator_generate.py:3639
    h = _HEALER.try_heal(page, TestStep(0, "locate", element=el, desc=hint))
```

而在此之前它**一条行为判据都没有**（`tests/` 全文搜 `healer` / `try_heal` 只有
`test_docs_sync` / `test_no_stale_paths` 的非行为引用）。

**自愈一退化 = 静默点错控件、用例还绿** —— 这类假绿用户看不见，是最贵的缺陷。

### 补的 5 条（按**当前代码**写，不是照抄老清单）

| # | 判据 | 防的是什么 |
|---|---|---|
| 1 | 无用元素（`goto`/`expect_text`/无 element）早退且**不污染事件流** | 否则 `output/heals/` 堆满噪声，真 diff 被淹没 |
| 2 | A 级必须以 `TIER2_THRESHOLD×0.75` / `TIER2_MINGAP×0.6` 调 `resolve_locator`（**抓真实传参**） | 原样重跑严格 Tier2 = 什么都没做，却在「看起来在干活」 |
| 3 | A 级失败才进 B 级；`_llm_renegotiate` 是**未实现的骨架**，必须如实说「未实现」 | 不许越过 A 级直接问 LLM；更不许回退成「需配 key」的误导（V8.4.6 修过，实测有人真去查 key/额度） |
| 4 | 三态裁决 `recovered`/`real_bug`/`failed`；**`real_bug` 时 locator 必须置空** | 若 real_bug 仍返回 locator，运行期会**继续用错的 locator 点下去** —— 自愈掩盖真 bug 的假绿路径 |
| 5 | heals json+md 留下「原语义 → 新 locator → 置信度 → 结果」 | 自愈必须可审；`dump()` 两份文件都要在 |

### 老清单里有一条**已经过时**，我按当前代码重写了

`tests/特性6-自愈闭环Healer/UNVERIFIED.md`（2026-10-07 写的）原计划 4 条，其中
「② B 级只在 A 级失败后触发」—— 但当前代码里 B 级是**刻意未实现的骨架**（源码原话：
「不管有没有 key 都返回同一句…别按「配 key」排查」）。所以判据改成钉它的**真实约束**：
进不去 + 进去了也必须 `ok=False` 且说「未实现」。

`UNVERIFIED.md` 已删除（有了判据，留着反而会让 `feature_verification_report` 把它标成 `[skip]`）。

## 二、A′ · 行区控件严格体检（打包硬闸）

### 为什么不放在 explore

`ai_output` 闸门里 `_ROW_SCOPE_NOTES` 是**警告级**，这是 **2026-10-13 的裁决**，理由写在源码里：

> ③ **录像回放模式**下「报缺陷 → 喂回重试」这条路根本走不通（AI 产出是固定的，重试必然得到同一份）
> ⇒ 硬拦 = **死路**，把整个 `all --ai` 挡在 explore 里（EXIT=3：script 未生成、run 未执行）

所以硬闸**只加在分发链路**：产物可以先跑，但不许当交付物发出去。

### 机制

```
HYBRID_ROW_ZONE_STRICT=1   （默认 0，不影响现有打包）
  -> pack_release.py 打包前体检：
     包里 `_probe_snapshot.json` 里有 row_zone 标记的控件
     × 用例里引用了它、却没给 `row_index` / `row_text`
     -> 拒绝出包（并删掉半成品 zip）
```

**口径两条**（都写了判据）：
- `row_index` **或** `row_text` 任一存在即算给了行定位 —— 只认一种会把另一半合法用例打成坏包
- 快照里没有 `row_zone` 条目（老包/老探针）→ **一律不报**，避免把老产物判成坏包

开关已登记进 `cli config`（可发现）：

```
HYBRID_ROW_ZONE_STRICT   0   默认   —   行区控件严格体检（1=开）：打包时若用例里「行区控件没给
                                        row_index/row_text」-> 拒绝出包。只拦分发链路，不拦 explore
```

## 三、验证真值

| 项 | 结果 |
|---|---|
| 一类全量 | **1601 passed / 3 skipped / 0 failed** |
| 自愈判据 | `test_healer_behavior.py` **5 条** + **3 组负向自证** |
| 严格体检判据 | `test_row_zone_pack_strict.py` **5 条** + **2 组负向自证** |
| 子特性 | **62**（新增 6.1 / 6.2 自愈；9.4 补严格体检） |

**负向自证明细**（全部当场变红，还原后全绿）：

| 破坏点 | 变红的判据 |
|---|---|
| 摘掉 `real_bug` 清空 locator | 三态裁决判据 |
| A 级不放宽阈值 | A 级阈值判据 |
| 早退路径也记事件 | 早退判据 |
| 只认 `row_index`（误伤 `row_text`） | 不误伤判据 |
| 拔掉 `main()` 里的开关接线 | 开关接线判据 |

## 四、踩坑（第三次同一类）

新写的注释里又用了 `⇒`（U+21D2），GBK 编不了 → `test_source_has_no_gbk_unencodable_chars` 红。

> **规矩**：往 `.py` 写中文（尤其注释/docstring）后，先 `ch.encode('gbk')` 扫一遍，再跑测试。

## 五、版本关系

| 版本 | 状态 |
|---|---|
| **V8.9.4** | ✅ 本版（自愈判据 + 打包严格体检） |
| V8.9.3 | 行区提示词改无条件（真机确认 AI 已写 `row_index`） |
| V8.9.2 | ⚠️ 已被取代（其「第 1 轮 PASSED」是单行路径的侥幸） |
| V8.9.1 | 回放选错录像 / 超时留现场 / 慢目标误判卡死 |

---

发布署名：AprilPark1012
