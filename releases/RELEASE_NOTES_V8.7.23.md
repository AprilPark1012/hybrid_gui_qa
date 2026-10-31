# V8.7.23 发布说明（2026-10-29）

> 上一版：V8.7.22 · 版本号单一来源 = `build_tools/build_html.py:VERSION`

## 一句话

**把正确姿势送到离模型最近的地方** —— 系统提示点名 `expect_first_row`。

---

## 一、V8.7.22 是「事后补救」，这一版是「提前给对」

V8.7.22 做了：把 `cell_field` 的候选**落盘**，并在**假绿闸门的错误信息**里给出来。

**但那是事后**：AI 得**先写错一次、被拦一次**，才看得到候选。

你说「**不要吝啬那一点重录录像的 token**」—— 对，改提示词，**让它第一次就写对**。

---

## 二、为什么 AI 一直写错：三个缺口叠在一起

```
AI 最后一步：expect_text assert=全链路-{datetime}   "搜索结果里出现该订单名称"
```

拆开看：

| # | 缺口 | 现状 |
|---|---|---|
| ① | 「不得与 fill 值相同」这条规则 | 在 prompt **第 6 条、长篇中段** —— 模型没接上 |
| ② | prompt 说「用 expect_first_row（列 + 期望值）」 | **没说 `cell_field` 从哪来** —— 要的是 data-field 值（`orderName`），不是表头文案（`订单名称`）|
| ③ | 行内列清单**本来就在 prompt 里** | 但只标成「行内定位用」，**没告诉它可以用来做首行断言** |

**三个缺口缺一不可** —— 少任何一个，AI 都能写出正确的断言。

---

## 三、修法：升到系统提示

### 改 `_PLANNER_SYSTEM`（2269 字符，最高权重）

新增一条铁律：

```
★铁律：要验证「记录已经建出来了 / 能被搜到 / 出现在列表里」，
**唯一正确写法是 expect_first_row**（给了 cell_field + 期望值，框架去查第一行的那一列）；
**绝对不许**用 expect_text 去断言你刚刚 fill 进去的值 —— 那是「输入回显」，
框架的假绿闸门会直接拒绝落盘，你连试多少次都过不去。
cell_field 的合法值只能从提示里的「表格行内列清单」的 field 里抄
（是 data-field 值，如 orderName），**不是表头文案**（如 订单名称）。
列清单里 field 为空的行（勾选列）用 cell_by=index + cell_index。
```

### 改 `_build_planner_prompt` 的列清单段

原来标题是「表格行内列清单（**行内定位**用…）」，现在改成「（**行内定位**与**首行断言**都用它…）」，并补一条：

```
· **要验「记录建出来了 / 搜到了」** -> expect_first_row +
  cell_field=<这里某个 field> + value=<刚填的那个名称>。
  **这是唯一正确写法**：expect_first_row 查的是「第一行的这一列」，是结构性证据；
  而 expect_text 查整页文本，跟你刚 fill 的值一比就构成「输入回显」，闸门会拒绝落盘。
```

**关键**：同一份数据（列清单）**本来就在模型眼前**，只是没说清它能干什么。

---

## 四、代价：录像全部失效

录像键 = `sha256(系统提示 + 提示词)`。

**改了系统提示 → 键必然变 → 已有录像全部失效。**

```
改前结构键：（旧）
改后结构键：f88db3d04866f009
```

**需要 `--llm-record` 重录。** 这是你明确接受的成本。

⚠️ 如果不重录，回放模式会报「找不到对应录像」并**明确报缺**（不会静默改走 live —— 这是 V8.7.14 定下的铁律）。

---

## 五、验证

| 手段 | 结果 |
|---|---|
| `test_prompt_points_to_cell_field.py`（新，5 条） | **5 passed** |
| 反向验证：删掉系统提示里那条新铁律 | **`test_system_prompt_mandates_expect_first_row` 变红** ✅ |
| 恢复后 | **5 passed** |
| GBK 闸门 | **21 passed** |

新判据守 5 件事：

1. 系统提示有「**唯一正确写法**是 `expect_first_row`」
2. 系统提示指明 `cell_field` 来自列清单的 `field`、**不是表头文案**
3. 系统提示明确禁止 `expect_text` 断言自己 fill 的值（含「输入回显」「闸门」字样）
4. 列清单段说明「验记录建出来了」用 `expect_first_row` + 这里的 field
5. **原有两条铁律不许被改坏**（`_PlanModel` 工具调用 / 占位符逐字保留）

> 写判据时自己踩的坑：`_row_fields_section()` 第一版用 `"表格行内列清单（"` 当锚点，
> 结果**命中了源文件第 ~50 行的注释**（不是 prompt 段）→ 判据自己报假红。
> 改用完整开头 `"表格行内列清单（**行内定位**"` 才准确。

---

## 六、怎么验

```powershell
# 只看这次的
.venv\Scripts\python -m pytest tests\特性2-语义识别与步骤编排\test_prompt_points_to_cell_field.py -v
# 预期 5 passed

# 全量
.venv\Scripts\python -m pytest tests\ -q
```

**真链路**（关键是这一步）：

```powershell
# 首次跑要重录（录像键变了）
python -m framework.cli explore --ai --llm-record --scenario-file scenarios/orders/orders_invoice_full_lifecycle.yml
```

**预期看到**：最后一步变成

```
61. expect_first_row  订单名称@发票列表页 | cell_field=orderName | assert=全链路-{datetime}
```

而**不再是** `expect_text assert=全链路-{datetime}`。

**如果 AI 还是写 expect_text**，把日志发我 —— 那说明系统提示的权重还不够，我考虑把这条挪到 prompt 的最前面（但目前它在系统提示里，应该是最高权重了）。

---

## 七、提交状态

V8.7.14 ~ 23 全部等你验完点头再提交，push 一律等你点头。

—— AprilPark1012
