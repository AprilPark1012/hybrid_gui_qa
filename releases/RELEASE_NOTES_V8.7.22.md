# V8.7.22 发布说明（2026-10-29）

> 上一版：V8.7.21 · 版本号单一来源 = `build_tools/build_html.py:VERSION`

## 一句话

**拦下了，却没告诉它怎么改** —— 把行内列清单落盘并喂回 AI。

---

## 一、V8.7.21 那次真链路：两轮重试，失败原因**完全相同**

```
[explore] [!] 失败原因与上一轮**相同** -> 停止重试（再问也是同一个答案，不白烧 token）
[explore] [NG] 重试用尽仍不合格（已尝试 2 次 · 上限 HYBRID_AI_RETRY=2）

假绿红线拦下：1 条用例、共 1 处
断言 '全链路-{datetime}' 就是本用例自己 fill 进去的值（输入回显 = 假绿）
```

最后三步：

```
59. fill        订单名称@发票列表页 ← 全链路-{datetime}
60. click       搜索@发票列表页
61. expect_text assert=全链路-{datetime}   "搜索结果列表行中出现该订单名称"
```

**AI 的思路完全正确**（搜到了 = 创建成功），**闸门也判得对**（断言值 == 自己 fill 的值 = 假绿的典型形态）。

### 但 AI 无路可走

错误信息让它「改用 `expect_first_row`」，而 `expect_first_row` 需要 `cell_field` —— 那是页面 `td[data-field=...]` 的值（`orderName`），**不是表头文案**（`订单名称`）。

**探针本来就有这个映射**（V8.7.16 的 `_fix_first_row_column_by_header` 全靠它反查），但它**只活在 explore 的内存里，从来没落进 elementMap**。

于是：case_builder 拿不到 → 只能干说「用 expect_first_row」→ **AI 拼不出值** → 两轮写同样 → 卡死。

---

## 二、修法：落盘 + 透传 + 错误信息里给候选

```
probe_row_fields()
    ↓ 打 page 标记（V8.7.22）
_ALL_ROW_FIELDS
    ↓ _finalize_map 按页分组
ElementMap.page_row_fields = {"发票列表页": [{"field":"orderName","header":"订单名称",...}]}
    ↓ to_dict() 按 pg.page 并进各页对象
element_map_*.json 每页多一个 row_fields
    ↓ ElementMap.from_data 读回
elementmap_to_cases_file → assertion_hard_errors(page_row_fields=...)
    ↓ 拦下时
"…改用 expect_first_row…；可用列 -> 发票列表页: orderName(订单名称)、invoiceNo(发票号)"
```

### 落地清单

| 位置 | 改动 |
|---|---|
| `probe_row_fields()` 调用处 | 每条列 `setdefault("page", 页名)` |
| `ElementMapPage` | 新增 `row_fields`，`to_dict`/`from_dict` 都带 |
| `ElementMap` | 新增 `page_row_fields`（页名→列清单），`to_dict` 按页并进 |
| `load_pages` | **不许丢掉**只有 `row_fields` 的页（否则读不回来） |
| `_finalize_map` | 从 `_ALL_ROW_FIELDS` 按页分组传给 `ElementMap` |
| `_row_field_hint()` | 新函数，把映射压成 `页名: field(表头)、…` |
| `assertion_hard_errors()` | 新增 `page_row_fields` 参数，拦下时附候选 |

### 两个坑（都在实现时踩到）

**① 单页兜底**：`normalized_pages()` 在 `steps` 为空或切页失败时给出 `page=""`，跟 `page_row_fields` 的中文页名对不上 → 列清单**数据活着但落盘为空**。单人页时清单只有一份、没有歧义，直接全塞。

**② `load_pages` 丢页**：原来 `return [x for x in pages if x.steps or x.probe_items]` —— 只有 `row_fields` 的页会被丢掉，读回来 `page_row_fields` 就是空。加上 `or x.row_fields`。

---

## 三、附带修掉一个假红（环境耦合）

跑判据时撞到：

```
test_llm_client_really_has_timeout_via_real_entry
assert 900.0 == 180.0
```

**我在本机也复现了**（不是你的环境问题）。追下去发现真凶是**第三方库**：

```
browser_use/logging_config.py:8   →   load_dotenv()      ← 无参，import 期无条件执行
    ↓
.dotenv/main.py:429  →  dotenv.set_as_environment_variables()
    ↓
.dotenv/main.py:108  →  os.environ[k] = v                ← 把 .env 的值写回环境
```

**`llm_timeout_s()` 本身完全正确**（删掉环境变量就返回 180），是 `browser_use` 在 import 时把项目 `.env` 的 `HYBRID_LLM_TIMEOUT=900` 又塞回去了。

**影响**：任何**带 `.env` 的环境**（包括你解压目录里手建的 `.env`）跑这条判据都会红。和 V8.7.19 那个 `.env` 事件是同一类。

**修法**：判据里拦截 `load_dotenv`（patch 三处覆盖全部引用形态：`dotenv.load_dotenv` / `dotenv.main.load_dotenv` / `browser_use.logging_config.load_dotenv`）。

---

## 四、一个刻意的取舍：**没有改提示词**

改 `_PLANNER_SYSTEM`（让 AI 第一次就知道有可用列）当然更好，但**会让录像键 `sha256(系统提示 + 提示词)` 全变、必须重录所有录像**。

而**错误信息带候选已经够闭环** —— 重试时 AI 会看到 `可用列 -> 发票列表页: orderName(订单名称)`。

**所以这一版先不动提示词**，把录像重录的成本留到你决定。如果你想让 AI 一次就对，我再改提示词 + 重录。

---

## 五、验证

| 手段 | 结果 |
|---|---|
| `test_row_fields_reach_ai.py`（新，11 条） | **11 passed** |
| 反向验证：断掉 `page_row_fields` 传递 + 闸门传 None | **`test_wiring_static` 变红** ✅ |
| 恢复后 | **11 passed** |
| `test_llm_null_and_timeout.py`（含修好的那条） | **25 passed** |

新判据守 8 件事：

1. `ElementMapPage.to_dict/from_dict` 带 `row_fields`
2. `to_dict()` 按页名并进去，多页不串味
3. **单页兜底**（页名对不上也要落盘）
4. `load_pages` 不许丢掉只有 `row_fields` 的页
5. `from_data(to_dict())` 能读回
6. `_row_field_hint` 格式正确、**空映射返回空串**（不许编造）、超长截断
7. 闸门传了映射就带候选、不传则不带
8. 静态接线三处（打 page 标记 / `_finalize_map` 传参 / 闸门拿到映射）

---

## 六、怎么验

```powershell
# 只看这次的
.venv\Scripts\python -m pytest tests\特性2-语义识别与步骤编排\test_row_fields_reach_ai.py -v
# 预期 11 passed

# 那条之前会红的
.venv\Scripts\python -m pytest tests\特性2-语义识别与步骤编排\test_llm_null_and_timeout.py -q
# 预期 25 passed（带 .env 也不红了）

# 全量
.venv\Scripts\python -m pytest tests\ -q
```

**真链路**（删四目录 + `.data` → 重启 demo → `explore --ai --verify`）：

**预期**：假绿红线还会拦（这是对的），但**重试时 AI 能看到候选列**，从而改成：

```yaml
- op: expect_first_row
  cell_field: orderName        # ← 候选里给的 data-field 值
  value: 全链路-{datetime}
```

**如果 AI 还是写 `expect_text`**，把日志发我 —— 说明候选提示的措辞/位置还不够显眼，我再调。

---

## 七、提交状态

V8.7.14 ~ 22 全部等你验完点头再提交，push 一律等你点头。

—— AprilPark1012
