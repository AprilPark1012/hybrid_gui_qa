# V8.7.16 发布说明（2026-10-29）

> 上一版：V8.7.15 · 版本号单一来源 = `build_tools/build_html.py:VERSION`

## 一句话

**AI 时对时错，框架自己兜** —— 中文表头当 `data-field` 用，按 header 唯一反查补正。

---

## 一、为什么 V8.7.15 不够

V8.7.15 只**警告**不拦。但你的二次实测证明了更严重的事：

| | 第 1 轮 | 第 2 轮 |
|---|---|---|
| **第一次跑**（10:52） | 62 步 715.0s FAILED | 61 步 391.0s **PASSED** ✅ |
| **第二次跑**（13:02） | 716.8s FAILED | 又一次 FAILED |

**同一场景、同一清空数据起点，结果不同。**

第一次 AI 第 2 轮自己把断言改对了；第二次**两轮都写错**。这是 AI 的**非确定性编排缺陷** —— 不能押在「下次它自己会改对」上。

## 二、根因

AI 写的是：

```python
expect_first_row  cell_field='订单名称'  value='全链路-{datetime}'
```

生成出来的选择器是：

```python
tbody tr:first-child td[data-field='订单名称']
```

而页面上真正的列是 **`data-field='orderName'`**（`订单名称` 只是**表头文案**）。

→ 选择器永远命中 0 个 → 断言等满 160s 有界等待 → 报「表格没有第一行、或没有 '订单名称' 列」。

## 三、修法：header → field 唯一反查

`probe_row_fields()` 本来就返回：

```python
{"table": "orders", "field": "orderName", "header": "订单名称", "index": 2, "kind": ""}
```

**`header` 是页面真实表头文案，`field` 是真实 `data-field`。** AI 写的是 header，反查 field 是**唯一确定的映射关系** —— 不是相似度猜测，不是编造。

```python
_fix_first_row_column_by_header(steps, row_fields)
```

补正后会**出声**：

```
[explore] [OK] 有 1 步 `expect_first_row` 的列写成了**表头文案** -> 已按表头反查补正（唯一映射，不是猜）:
    - 第 22 步 `cell_field='订单名称'` 是**表头文案**、不是 data-field -> 已按表头反查补正为 'orderName'（唯一映射，非猜测）
```

## 四、只在唯一解时才改

| 情况 | 行为 |
|---|---|
| AI 写的正好是合法 `data-field` | **不动** |
| header 命中**唯一**一列 | **补正** + 出声 |
| header 命中**多列**（多表都有「订单名称」但 field 不同）| **不动**（改哪个都是猜）|
| header 找不到 | **不动**（诚实降级）|
| 列本身没有 `data-field`（如勾选列）| **不动**（无从反查）|
| 非 `expect_first_row` 的步骤 | **不动**（语义不同）|

与 `_fill_missing_row_column`（勾选列唯一解才补）**同一口径**。

## 五、接线顺序：先补正、再警告

```python
_rowcol_fixed = _fix_first_row_column_by_header(steps, _LAST_ROW_FIELDS or None)   # ① 能补的先补
if _rowcol_fixed:
    print(...)                                                                     # 出声
_warn_nonexistent_row_columns(steps, _LAST_ROW_FIELDS or None)                     # ② 补不上的才警告
```

**顺序反了就会「能补的也被报成警告」** —— 判据 `test_ordering_fix_runs_before_warn` 专门钉住这一行。

## 六、判据 7 条

| 测试 | 守什么 |
|---|---|
| `test_header_text_is_translated_to_data_field` | 核心：`订单名称` → `orderName`，且**出声**说明改了什么 |
| `test_valid_field_untouched` | 合法 field 一个字节不动 |
| `test_ambiguous_header_not_touched` | 多义命中原样保留（不猜）|
| `test_unknown_text_not_touched` | 找不到不改（不编）|
| `test_columns_without_data_field_cannot_be_fixed` | 无 `data-field` 的列无从反查 |
| `test_other_ops_ignored` | 只碰 `expect_first_row` |
| `test_ordering_fix_runs_before_warn` | **补正必须排在警告之前** |

**反向验证**：把函数第一行改成 `return notes`（短路）→ `test_header_text_is_translated_to_data_field` **立刻变红**；恢复 → 7 passed。

## 七、本轮完整数据（供你复盘）

```
第一次（10:52）：got none 0 次 ✅ · 第 1 轮 715.0s FAILED · 第 2 轮 391.0s PASSED
第二次（13:02）：got none 0 次 ✅ · 第 1 轮 716.8s FAILED · 第 2 轮也 FAILED
```

**`got none` 两次都是 0 次** —— V8.7.14 的修复稳定有效。这次的失败是另一个问题（列名），现在也堵上了。

## 八、验证

```
全量：pytest tests/ -q
判据：7 passed（含反向验证）
```

## 九、兼容性

**纯增量补正，零行为变更**：只在「AI 写了表头文案 + 反查唯一」这一种情况下改字段，其余一律不动。

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
.venv\Scripts\python -m pytest tests\特性2-语义识别与步骤编排\test_first_row_column_header_fallback.py -v
```

**真实链路验证**：按你固定流程（删 `cases/ scripts/ output/ log/ .data` → 重启 demo → `cli explore --ai`），
如果 AI 又写中文表头，日志里会出现：

```
[explore] [OK] 有 N 步 `expect_first_row` 的列写成了**表头文案** -> 已按表头反查补正（唯一映射，不是猜）
```

**这时那条断言就有机会跑通了。**

## 十一、提交状态

V8.7.14 / V8.7.15 / V8.7.16 都还没提交，等你验完点头。

—— AprilPark1012
