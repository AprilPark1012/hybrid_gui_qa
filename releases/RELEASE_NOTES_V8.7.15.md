# V8.7.15 发布说明（2026-10-29）

> 上一版：V8.7.14 · 版本号单一来源 = `build_tools/build_html.py:VERSION`

## 一句话

**列名写错别等 715 秒** —— `expect_first_row` 的列在生成阶段就提醒。

---

## 一、问题（你 V8.7.14 实测日志）

```
第 1 轮  62 步  → 实跑 715.0s → FAILED
        E  AssertionError: 表格没有第一行、或没有 '订单名称' 列 —— 无法验证「第一条记录」
第 2 轮  61 步  → 实跑 391.0s → PASSED
```

**只差 1 步，耗时差 324 秒。**

## 二、性质：不是框架 bug

AI 写了一步：

```
第 21 步  expect_first_row  全链路-{datetime}
        desc: 列表第一条就是刚创建的订单
```

而**订单列表页没有「订单名称」这一列**。断言条件永远等不到，把有界等待（最长 160s）的时间全耗光。

**L1 重试按设计兜住了**（第 2 轮 AI 自己把断言改对）—— 框架没做错什么。但**那 715 秒是纯浪费**。

## 三、机会：框架其实早就知道列清单

探测阶段 `probe_row_fields()` 返回的是：

```python
[{"table": "orders", "field": "orderNo", "header": "订单编号", "index": 1, "kind": ""},
 {"table": "orders", "field": "customer", "header": "客户",   "index": 2, "kind": ""}]
```

**AI 写的 `cell_field` 该不该存在于这个清单里，一眼就能查** —— 但框架从未拿它校验过。

## 四、修法

新增 `_warn_nonexistent_row_columns()`，在 `_finalize_map` 里调用。效果：

```
[explore] [!] 有 1 步 `expect_first_row` 要查的列**不在本次探测到的列里**
            （实跑会报「没有这一列」；跨页场景下列清单可能对不上，**仅供参考、不拦**）:
    探测到的列: customer、orderNo
    - 第 21 步 要查列 '订单名称'
```

**这样在生成阶段就能看到，不用等 715 秒。**

## 五、为什么刻意「只警告不拦」

`_LAST_ROW_FIELDS` **只保留最后一次探测的页**。本用例跨 4 个页面：

- 第 21 步属于**订单列表页**
- 第 61 步属于**发票列表页**

列清单只对得上其中一页 —— **拿它拦人必然误伤**。

你 2026-10-29 明确选「只警告不拦」，与本项目「**宁漏不误伤**」口径一致：**误拦会让人绕过这道闸门、甚至不再信它，比漏报更糟。**

所以：
- 调用点是**裸调用**，返回值直接丢弃（不赋值、不判断）
- 提醒文案**自陈局限**：「跨页场景下列清单可能对不上，仅供参考、不拦」

## 六、三个边界处理

| 情况 | 行为 |
|---|---|
| 没探到列清单（`row_fields` 为空） | **静默**（没依据不下判断）|
| 清单里全是空 `field`（列没有 `data-field`）| **静默** |
| 列存在 | **零输出**（不刷屏）|
| 非 `expect_first_row` 的步骤 | **不管**（`fill`/`click` 的 `cell_field` 语义不同）|

## 七、判据 `test_row_column_precheck_warns_only.py`（5 条）

| 测试 | 守什么 |
|---|---|
| `test_warns_when_column_missing` | 列不存在时必须提醒，且**列出实际可用的列**（否则用户没法对照）|
| `test_silent_when_column_exists` | 列存在时零输出 |
| `test_silent_without_row_fields` | 没探到列 / 列无 `data-field` 时静默 |
| `test_other_ops_ignored` | 只管 `expect_first_row` |
| `test_warning_never_blocks` | **调用点必须丢弃返回值**，文案必须自陈「仅供参考、不拦」|

**反向验证**：把调用改成

```python
_rowcol_notes = _warn_nonexistent_row_columns(...)
if _rowcol_notes:
    raise ValueError('列名预检不合格')
```

→ 第 5 条**立刻变红**；恢复 → 5 passed。

**这条判据的意义**：防止以后有人（包括我）图省事把它从「提醒」改成「拦截」。

## 八、验证

```
全量：1356 passed / 3 skipped / 0 failed
判据：5 passed（含反向验证）
真链路：V8.7.14 那轮 got none = 0 次（修复有效）
```

## 九、兼容性

**纯增量提醒，零行为变更**。不拦任何用例，不改变任何产出。

你的配置继续有效：
```ini
LLM_MODEL=glm-5.3
LLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4
LLM_REASONING_EFFORT=high
HYBRID_LLM_TIMEOUT=900
```

## 十、怎么验

```powershell
.venv\Scripts\python -m pytest tests\ -q
# 预期 1356 passed / 3 skipped

.venv\Scripts\python -m pytest tests\特性2-语义识别与步骤编排\test_row_column_precheck_warns_only.py -v
# 预期 5 passed
```

**真实场景验证**：跑一次 `explore --ai`，如果 AI 又写了不存在的列，日志里会出现
`[!] 有 N 步 expect_first_row 要查的列不在本次探测到的列里`。

## 十一、改动未提交

V8.7.14 + V8.7.15 都等你验完点头再提交，push 一律等你点头。

—— AprilPark1012
