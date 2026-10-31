# V8.7.26 发布说明（2026-10-30）

> 上一版：V8.7.25 · 版本号单一来源 = `build_tools/build_html.py:VERSION`

## 一句话

**同一个 bug 换了道门进来** —— 切页必须只有一份实现。

---

## 一、先说 V8.7.25 修对了（登录取证）

你这次日志里 **登录前置：ok**，三次都是：

```
第 17 行   [explore] [key] 登录前置：ok
第 277 行  [explore] [key] 登录前置：ok
第 556 行  [explore] [key] 登录前置：ok
```

**V8.7.25 那个 `goto` 拿 ElementRef 当 URL 的 bug，修好了。**

---

## 二、但这次 FAILED 在别处，而且是我 V8.7.24 的疏漏

### 现场

```
三轮都是 715s 左右 FAILED：
AssertionError: 表格没有第一行、或没有 'orderName' 列 —— 无法验证「第一条记录」
```

### 真凶：`_fix_first_row_column_by_header` 仍是跨页全集

V8.7.24 我把 **`_warn_nonexistent_row_columns`（警告器）** 改成了按页判，
跨页串用问题解决了、你那次真机 PASSED。

**但紧挨着它的 `_fix_first_row_column_by_header`（表头文案反查补正器），我没改。**

这次的具体链路：

```
第 57 步  fill 订单名称@发票列表页 ← 页面上真有「订单名称」这个搜索框
第 59 步  expect_first_row  cell_field='订单名称'（表头文案）
   ↓
补正器拿【跨页全集】的 header->field 映射反查
   ↓
查到【订单列表页】的 orderName（同表头「订单名称」、唯一解）
   ↓
cell_field 被改成 orderName
   ↓
发票列表页没有这一列 → 实跑 715s FAILED
```

**关键混淆点**：发票列表页**确实有「订单名称」这个搜索框**（`order_name`，label='订单名称'），
**但表格列里叫 `fromOrder`（来源订单）**。AI 看到搜索框就以为表格里也有这一列，
而补正器"帮它"把这个错补成了另一个页的列 —— **比不补更糟**。

---

## 三、修法：切页收敛成唯一入口

### 新增 `_steps_page_index()`

```python
def _steps_page_index(steps, pages, by_page) -> dict[int, str]:
    """算出「每个步骤属于哪一页」-> {id(step): 页名}（**唯一入口**）"""
```

**补正器和警告器都走它。** 不许任何一处自己写 `split_steps_by_page` 再拼 dict ——
那正是"改了一个、漏了紧挨着的另一个"的根源。

### 补正器改成按页

```python
_pn = _page_of.get(id(st), "")
if _pn and _pn in by_header_page:
    hits = by_header_page[_pn].get(cf) or []
    if not hits:
        continue          # 该页没有这个表头 -> 不补（补出来必然是该页不存在的列）
elif _pn:
    continue              # 知道页名但该页没探到列 -> 诚实降级，不拿别页的映射猜
else:
    hits = by_header.get(cf) or []   # 切不出页 -> 退回全局（老行为，宁漏不误伤）
```

### 效果对照

| 场景 | 老行为 | 新行为 |
|---|---|---|
| 订单列表页写「订单名称」 | 补成 `orderName` ✅ | 补成 `orderName` ✅ |
| **发票列表页写「订单名称」** | **错补成 `orderName`** ❌ | **不补**，交给警告器报「该页可用列：contractNo、fromOrder、invoiceNo」✅ |

---

## 四、验证

| 手段 | 结果 |
|---|---|
| `test_row_column_page_scoped.py`（13 条，本轮 ⑧~⑬ 新增 6 条） | **13 passed** |
| 反向验证：断掉补正调用点的 `pages=pages` | **`test_wiring_passes_pages_to_header_fix` 变红** ✅ |
| GBK 闸门 | **21 passed** |
| 全量 | 见交付日志 |

### 新增的 6 条判据

- ⑧ 补正器按页（订单页补、发票页不补）
- ⑨ 不传 `pages` 退回全局（固化降级路径，不是推荐用法）
- ⑩ 切页必须唯一入口 `_steps_page_index`（**AST 扫真实调用**）
- ⑪ 表头文案写错页时，警告要列出该页可用列
- ⑫ **接线判据**：补正调用点必须传 `pages`
- ⑬ 补正器与警告器**都**走 `_steps_page_index`

---

## 五、我今天犯的错，说清楚

### ① 同一个错误犯了第二次

V8.7.24 那次：6 条判据全都**自己传参数**，把调用点断掉时一条都不红 → 补了第 7 条接线判据。

**这次又犯了一遍**：⑧⑨ 也是自己传 `pages`，断掉接线时一条不红。
所以才有 ⑫ 这条。

**已固化进 skill**：新增/改带 `pages` 这类"按作用域"参数时，**必须同时加一条接线判据** ——
否则判据测的是"函数本身对不对"，测不到"真链路有没有用它"。

### ② 文本扫描又误伤

⑩ 第一版扫文本找 `split_steps_by_page(`，结果命中 docstring 里的说明文字
（「修复：按 `split_steps_by_page()` 切页…」）。改用 **AST** 找真实 `Call` 节点才对。

### ③ 又混进 GBK 编不了的字符

⑪⑫⑬ 这三个**带圈数字**（U+246A~U+246C）GBK 编不了 → GBK 闸门当场红。换成 `11)` `12)` `13)`。

**这条我已经踩了第 3 次**（前两次是 `⇒` 和 `⚠️`）。以后判断标准的写法是：
**只写中英文数字与括号，不写任何 `①⑪→⇒⚠️✅` 这类符号**。

---

## 六、怎么验

```powershell
.venv\Scripts\python -m pytest tests\特性2-语义识别与步骤编排\test_row_column_page_scoped.py -v
# 预期 13 passed

.venv\Scripts\python -m pytest tests\ -q
```

**真链路**（删四目录 + `.data` → 重启 demo → `explore --ai`）：

**预期**：第 59 步所在页是发票列表页时，若 AI 又写「订单名称」，日志应该出现：

```
[explore] [!] 有 1 步 `expect_first_row` 要查的列**不在该步骤所在页**:
  - 第 59 步 expect_first_row 的 cell_field='订单名称' 不在「发票列表页」这一页的列里
    （该页可用列：contractNo、currency、customer、fromOrder、invoiceNo…）
    —— 实跑会报「表格没有第一行、或没有 '订单名称' 列」
```

**而 `cell_field` 不会被偷偷改成 `orderName`。**

AI 下一轮看到"可用列"就能改成 `fromOrder` 或 `contractNo`（你上次 V8.7.24 成功那次就是改成了「合同编号」）。

---

## 七、关于那 100+ 条「跨页同名元素」警告

日志第 86~198 行有一大堆：

```
[explore] [!] 跨页同名元素 'HT_1001' 出现在 合同列表页、订单列表页、订单详情页、发票列表页
  → 已唯一化为 HT_1001@合同列表页、HT_1001@订单列表页、...
```

**这是正常行为**（合同号在多个页面的列表里都有，框架做跨页唯一化），
但它**刷了 100 多行**，把真正的信息埋了。

**这属于噪音预算问题**（和 V8.7.18 的行容器 53 条同类）。我没在这次改 ——
**先确认主链路通了再降噪**，免得又改出别的问题。

要降的话我建议：同前缀（`HT_`）合并成一行汇总 `'HT_1001'~'HT_1013' 共 13 个跨页同名 → 已唯一化`。

---

## 八、提交状态

V8.7.14 ~ 26 全部等你验完点头再提交，push 一律等你点头。

—— AprilPark1012
