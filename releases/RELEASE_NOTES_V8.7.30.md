# V8.7.30 发布说明（2026-10-31）

> 上一版：V8.7.27 · 版本号单一来源 = `build_tools/build_html.py:VERSION`

## 一句话

**列清单的三个源头全断了** —— 登录静默失败 / div 网格探不到 / 弹窗探测把页面带跑。

---

## 一、为什么 V8.7.24/26 怎么改都治不好

V8.7.27 你跑出来的三轮全是：

```
AssertionError: 表格没有第一行、或没有 '订单名称' 列 —— 无法验证「第一条记录」
```

第 1 轮 `订单名称`、第 2 轮换 `合同编号`、第 3 轮还是失败。我前几版一直在改**下游**（提示词、按页校验、按页补正），但顺着「AI 为什么要猜列名」查下去才发现：

**它猜，是因为它真的没数据可看。**

而数据缺的原因有三层，**每一层都不报错、只是静默地产出错数据**。

---

## 二、第一层：登录静默失败

### 现象

清空 `output/` 后第一次跑：

```
[登录前置] [!] 失败 -> Error: It looks like you are using Playwright Sync API inside the asyncio loop.
```

然后**探测照常进行**，7 页全部被 demo 重定向：

```
>>> login.html?next=%2Forder_detail.html%3Fno%3DSO-1001 | table=1 | 列=3
>>> login.html?next=%2Finvoice_create.html                | table=1 | 列=3
>>> login.html?next=%2Finvoice_list.html                  | table=1 | 列=3
最终行内列: {'登录页':3, '合同列表页':3, '新建订单页':3, '订单列表页':3,
             '订单详情页':3, '开票页':3, '发票列表页':3}
```

**每页那 3 条「列」都是登录页 `login-accounts` 的角色/账号/密码**，却被标上「发票列表页」的页名，一路喂给 AI。

### 根因（两处，都得修）

**① `_probe_login_page` 嵌套 `sync_playwright()`**

原 docstring 写着「必须自己开浏览器、自己关：调用方（`_explore_one`）此刻还没开浏览器」。

**但这个假设早就不成立了**。真实调用链是：

```python
with sync_playwright() as p:
    b = p.chromium.launch(...)
    ctx = b.new_context()            # ← 浏览器已经开好了
    ensure_logged_in(ctx, ...)       # → login_on_page → plan_login → _probe_login_page → 又开一个
```

**嵌套 `sync_playwright()` → 必炸。**

**② `plan_login` 里裸 `asyncio.run`**

`asyncio.run(_ai_explore_async(...))` 同样与 Playwright Sync API 互斥。

（这两处我一开始以为是同一个问题，实际是**独立的两个**，修了第一个第二个还在炸。）

### 修法

| 位置 | 改法 |
|---|---|
| `_probe_login_page(url)` → `(url, ctx=None)` | 有 ctx 就**复用调用方的 context**；只有真没人给 ctx 时才自己开 |
| `plan_login(..., ctx=None)` | 透传 |
| `login_on_page` | `ctx=getattr(page, "context", None)` |
| `asyncio.run(...)` → `run_async_isolated(...)` | **独立线程**跑 asyncio，线程结束即回收 |

### 实测

```
[login] [i] 登录页控件 7 个 -> 交给同一个规划器
[login] [OK] 登录步骤 4 步 -> login_ad73149c1dedd531.json（决策档案，可审计）
    goto | http://localhost:8000/login.html
    fill | super
    fill | super@123
    click | None
```

**和你 V8.7.27 日志里那 4 步完全一致。**

> **为什么你那边没炸**：你主力机是 Windows，那套 Playwright/Python 组合不检测这个嵌套。Linux + Python 3.11 一删 `output/` 就必炸（登录缓存 `output/login_maps/` 被删 → 只能走 AI 规划 → 踩链）。

---

## 三、第二层：div 网格探不到

### 现象

`order_detail.html` 探到 **0 条列**，但页面明明有：

```html
<div class="lines-grid" id="lines-grid">
  <div class="head">操作</div><div class="head">行号</div>...     ← 表头 10 个
  <div class="cell">...</div>
  <div class="cell" data-field="lineNo">{{ idx + 1 }}</div>        ← 不是 <td>！
  ...
  <div class="cell" data-field="lineStatus">{{ ln.status }}</div>
</div>
```

### 根因

`probe_row_fields` 第一行：

```python
tables = page.locator("table")      # ← 只扫 <table>
```

**div 网格完全在扫描范围外。** AI 永远不知道 `lineNo` / `lineStatus` 可用，要做行内断言只能瞎猜。

### 修法

新增 `probe_div_grid_fields()`：

- **只认带 `data-field` 的元素**（与 `<table>` 路径同一个"列字段"概念，不引入新原语）
- **产出同构**（`{table, index, field, header, kind}`）→ 提示词拼装 / 按页校验 / 首行断言补正**全都不用改**
- **`closest('table')` 跳过表格内元素**，避免和 table 路径重复产出
- **同名列去重**（div 每行都重复渲染 `data-field`，不去重会随行数线性膨胀）
- **表头按「同 class 连续段」推断每行单元格数**（`head×10` + `cell×N` → 每行 10 个），**推断不出就留空串**

> **为什么表头宁空不错**：空表头只是少一条线索；**错表头会让 AI 把列名对到错误的语义上**，比没有更糟。

### 实测

```
probe_row_fields 总数 = 2
  table=lines-grid idx=13 field='lineNo'      header='行号'
  table=lines-grid idx=20 field='lineStatus'  header='状态'
```

---

## 四、第三层：弹窗探测把页面带跑

### 现象

这个最隐蔽。`scan_page` 阶段：

```
[scan_page] 发票列表页   前=invoice_list.html   后=invoice_create.html?token=HX5PguNbOgJUvXwTR9GEbw   <<<< URL 变了
```

页面**在探测过程中被点跑了**，于是紧跟着的 `probe_row_fields` 打在**开票页**上 —— 发票列表那条真表（单独访问实测 **11 列**）**一条都探不到**。

### 根因

`_try_collect_modal_items` 的候选按钮名单：

```python
_MODAL_BUTTON_HINTS = ("新建", "添加", "新增", "创建", "登记", "打开")
```

它**假设「新建/创建」类按钮都会开弹窗**。但「创建」有两种：

| 类型 | 行为 |
|---|---|
| 弹窗型 | 弹个层，填完提交（本函数要处理的）|
| **导航型** | **整页跳到另一个页面** ← 发票列表页的「创建」就是这种 |

点了导航型按钮，**探测所在的页面本身就被带跑了**。

### 修法

判据很干脆：**点完 URL 变了 = 导航，不是弹窗**。

```python
_url_before = pg.url
_probe_click(btn.first, timeout=8000)
_url_after = pg.url
if _url_before and _url_after and _url_after != _url_before:
    print("[!] 「创建」是**导航**不是弹窗 → 退回原页，跳过弹窗补充")
    pg.go_back(...) or pg.goto(_url_before, ...)     # 两条腿都要
    return []
```

**关键是退回原页** —— 不只跳过收集，还要把页面还原，否则后续所有探测错位。

### 实测

```
[scan_page] 发票列表页   前=invoice_list.html   后=invoice_list.html     ← URL 不再变了
```

---

## 五、修完的结果：7 页列全齐

```
登录页 3 · 合同列表页 8 · 新建订单页 2 · 订单列表页 12 · 订单详情页 2 · 发票列表页 11
                                                                          ↑ A 修的    ↑ B 修的

发票列表页的列: ['', 'invoiceNo', 'invoiceType', 'invoiceDate', 'businessUnit',
                'contractNo', 'fromOrder', 'customer', 'salesman', 'currency', 'lineCount']
                                                                  ↑ 「订单编号」就是它
```

**`fromOrder`（订单编号）终于被探到了** —— 这正是 AI 三轮都在猜「订单名称」时，本该用的那个字段。

---

## 六、判据（26 条，全部反向验证过）

| 文件 | 条数 | 反向验证 |
|---|---|---|
| `test_login_no_nested_playwright.py` | **10** | 去掉 ctx 复用 → **4 条变红** |
| | | 换回裸 `asyncio.run` → **2 条变红** |
| `test_div_grid_row_fields.py` | **10** | 断掉接线 → **2 条变红** |
| `test_modal_probe_never_navigates.py` | **6** | 去掉 URL 比较 → **2 条变红** |

**接线判据是标配**（V8.7.24/26 同一个错误犯过两次）：
- 不只测「函数本身对不对」，还测「**调用点真的把 ctx 传进去了**」
- 不只测「div 网格函数能出数据」，还测「**`probe_row_fields` 默认真的调用了它**」

---

## 七、三个 bug 的共同特征

**「失败不报错、脏数据继续往下走」**：

| bug | 失败时的表现 |
|---|---|
| 登录失败 | **探测照常跑**，7 页探成登录页垃圾列 |
| div 网格探不到 | **返回 0 条**，看起来像"这页本来没表格" |
| 弹窗点跑页面 | **不检查**，后面所有探测错位 |

**而 AI 拿不到真列名就只能猜，猜出来的运行时必然找不到** —— 就是你看到的那三轮 `AssertionError`。

**V8.7.24/26 的按页校验、按页补正逻辑本身没错，但它们一直在拿残缺数据做判断。**

---

## 八、怎么验

```powershell
# 三组新判据
.venv\Scripts\python -m pytest tests\特性2-语义识别与步骤编排\test_login_no_nested_playwright.py -v
.venv\Scripts\python -m pytest tests\特性3-分层定位与控件识别\test_div_grid_row_fields.py -v
.venv\Scripts\python -m pytest tests\特性2-语义识别与步骤编排\test_modal_probe_never_navigates.py -v

# 全量
.venv\Scripts\python -m pytest tests\ -q
```

**真链路**（按你的规矩：删 `cases/ scripts/ log/ output/ .data/` → 重启 demo → 跑）：

```powershell
.venv\Scripts\python -m framework.cli explore --ai --scenario-file scenarios\orders\orders_invoice_full_lifecycle.yml
```

**重点看这几行**：

```bash
# 1) 登录必须 ok
grep '登录前置' 日志

# 2) 发票列表页必须探到 11 列（探不到就是没修好）
grep '发票列表页' 日志

# 3) 不该再出现「不在任何一页列清单里」
grep -c '不在.*列清单' 日志     # 预期 0
```

---

## 九、提交状态

V8.7.14 ~ V8.7.30 全部等你验完点头再提交，push 一律等你点头。

—— AprilPark1012
