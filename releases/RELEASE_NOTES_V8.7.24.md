# V8.7.24 发布说明（2026-10-29）

> 上一版：V8.7.23 · 版本号单一来源 = `build_tools/build_html.py:VERSION`

## 一句话

**改对了写法，用错了页面** —— 列清单按页分组 + 按页校验。

---

## 一、V8.7.23 的改动确实生效了（这是好消息）

你那次日志里，AI 第 63 步是：

```
63. expect_first_row → 全链路-{datetime} | 能搜到刚创建的那张发票：
    搜索后第一行的「订单名称」列即该订单（结构性证据；发票号系统生成，不写死断言）
```

**它不再用 `expect_text` 断言自己 fill 的值了** —— 系统提示那条铁律起作用了，假绿闸门这次**一次都没拦**。

---

## 二、但实跑 735s 后 FAILED

```
AssertionError: 表格没有第一行、或没有 'orderName' 列 —— 无法验证「第一条记录」
```

### 真因：`orderName` 是**订单列表页**的列，不是发票列表页的

我把 demo 两个页面的 `data-field` 全 dump 出来对了：

| 页面 | data-field |
|---|---|
| `orders.html`（订单列表页） | **orderName**、orderNo、orderStatus、orderType、customer、contractNo、businessUnit、managementUnit、salesman、lineNo、invoiced、folder |
| `invoice_list.html`（发票列表页） | invoiceNo、invoiceType、invoiceDate、businessUnit、contractNo、**fromOrder**、customer、currency、salesman、lineCount |

**发票列表页没有 `orderName`**。AI 拿订单页的列去断发票页了。

---

## 三、三层都缺，所以没人拦住它

| 层 | 当时的行为 |
|---|---|
| **提示词** | `row_fields` 是**跨页累积的扁平列表**，直接 `json.dumps` 给模型 → 它看到一大堆 field，**分不清哪个属于哪一页** |
| **生成期校验** | `_warn_nonexistent_row_columns` 拿**跨页全集**判存在性 → `orderName` 在订单页里有 → **静默通过，一声不响** |
| **运行时** | `_assert_first_row` 定位 `tbody tr:first-child td[data-field='orderName']` → 找不到 → FAILED |

---

## 四、修法

### ① 提示词按页分组渲染

**改前**（扁平 json）：

```
表格行内列清单（行内定位与首行断言都用它...）：
[{"field":"orderName","header":"订单名称","page":"订单列表页",...},
 {"field":"invoiceNo","header":"发票号","page":"发票列表页",...}, ...]
```

**改后**（按页分组 + 显式规则）：

```
  · ★★必须用「这条断言发生在哪一页」那张表的列 —— 各页的列互不通用！
    拿别的页的 field 去断本页，实跑会报「表格没有第一行、或没有 'XXX' 列」。
    （2026-10-29 实测：AI 拿订单列表页的 orderName 去断发票列表页，
     而发票列表页没有这一列 -> 整条用例 FAILED。）

【订单列表页】的表格列：
    - field=orderName · 表头=订单名称 · index=4 · kind=text
    - field=orderNo · 表头=订单编号 · index=3 · kind=text
【发票列表页】的表格列：
    - field=invoiceNo · 表头=发票号 · index=1 · kind=text
    - field=fromOrder · 表头=来源订单 · index=7 · kind=text
```

### ② 生成期校验改为**按页**

```python
# 改前：跨页全集 -> 别的页有这列就静默放行
fields = {rf["field"] for rf in row_fields}

# 改后：split_steps_by_page 切页，逐页用该页的列清单判
by_page = {"订单列表页": {"orderName", "orderNo", ...},
           "发票列表页": {"invoiceNo", "fromOrder", ...}}
```

**警告里直接列出该页可用列**：

```
第 3 步 expect_first_row 的 cell_field='orderName' **不在「发票列表页」这一页的列里**
（该页可用列：customer、fromOrder、invoiceNo）—— 实跑会报「表格没有第一行、或没有
'orderName' 列」。各页列**互不通用**，别拿别的页的 field 断本页
```

**AI 下一轮就能照着改对。**

---

## 五、验证

| 手段 | 结果 |
|---|---|
| `test_row_column_page_scoped.py`（新，7 条） | **7 passed** |
| 反向验证：断掉调用点的 `pages=pages` | **`test_wiring_passes_pages_to_warning` 变红** ✅ |
| 恢复后 | **7 passed** |

### 我自己踩的两个坑（都记在判据里了）

**① 反向验证当场没变红**

第一版 6 条判据全都**直接调函数并自己传 `pages`** —— 把 `_finalize_map` 调用点的 `pages=pages` 断掉时**一条都不红**。但真链路走的才是调用点，断了等于整个功能失效。**补了第 7 条静态接线判据**才守住。

**② patch 留了死代码**

改 `_warn_nonexistent_row_columns` 时旧的打印段留在 `return notes` 后面（永远执行不到），已删。

---

## 六、怎么验

```powershell
# 只看这次的
.venv\Scripts\python -m pytest tests\特性2-语义识别与步骤编排\test_row_column_page_scoped.py -v
# 预期 7 passed

# 全量
.venv\Scripts\python -m pytest tests\ -q
```

**真链路**（删四目录 + `.data` → 重启 demo → `explore --ai`，录像目录空了会自动录）：

**预期**：第 63 步的 `cell_field` 应该变成**发票列表页真实存在的列**，比如：

```
63. expect_first_row → fromOrder | 全链路-{datetime}
```

或者 `customer` / `invoiceNo`（如果 AI 想验发票号非空）。

**不该再出现 `orderName`**。

如果 AI 还是写了 `orderName`，日志里应该能看到这条警告（这就是改进的证据，即使它还犯错）：

```
[explore] [!] 第 63 步 expect_first_row 的 cell_field='orderName' 不在「发票列表页」这一页的列里
（该页可用列：customer、currency、fromOrder、invoiceNo...）
```

---

## 七、提交状态

V8.7.14 ~ 24 全部等你验完点头再提交，push 一律等你点头。

—— AprilPark1012
