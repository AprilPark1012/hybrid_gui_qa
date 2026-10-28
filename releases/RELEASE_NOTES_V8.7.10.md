# V8.7.10 发布说明（2026-10-28）

> 上一版：V8.7.9（2026-10-28）· 版本号单一来源 = `build_tools/build_html.py:VERSION`

## 一句话

**三处文档与代码对齐**：`cli --help` / `README` / `training.html` 全部按代码真值刷新，并删掉失效示例。

---

## 你的要求

> 「你同步刷新好 readme，培训文档 training.html，还有把 cli --help 也打开检查核对下，
>   把失效的命令删掉，这 3 个东西都要保证和代码实现同步一致。」

---

## 一、`cli --help`：删掉了指向不存在对象的示例

**最实的一处**：

```diff
- python -m framework.cli run --debug --case contracts_search_by_no   # 只跑一条用例
+ python -m framework.cli run --debug --case <case_id>                # 只跑一条用例（case_id = cases/ 里的文件名）
```

`contracts_search_by_no` 这个 case **在仓库里根本不存在**（`cases/` 下只有
`orders_invoice_full_lifecycle`）。而且真实的 case id **带时间戳**（`ai_..._161243`），
每次生成都变 —— **写死任何一个具体 id 都注定过时**。

这正是那个老原则：**不拿「观测到的具体值」当地基**。改成占位符 + 说明取值来源。

**另外三处调整**：

| 改动 | 为什么 |
|---|---|
| 新增 `all --ai --no-run` 示例（标注【开发期】） | V8.7.9 加了能力，help 里没告诉人怎么用 |
| 把 `explore --ai` 三种用法移到独立段落，标题写「**不是主线**，跑全流程请用 all --ai」 | 遵守你 2026-10-11 的「统一入口」口径，别让人以为还有第二条主线 |
| `all` / `explore` 的子命令描述首行重写 | 描述取 docstring 第一行，原来说的是旧语义 |

**核对结果**（机器核对，不是我眼看）：

```
命令         help   代码    结论
all        28      28     OK
config      0       0     OK
explore    13      13     OK
generate    6       6     OK
prune       7       7     OK
run        12      12     OK
setup       3       3     OK
verify     12      12     OK
```

9 个子命令（含 `llm-doctor`）**参数零差异** —— help 列的每个参数代码都认，代码认的每个参数 help 都列了。

---

## 二、README：更新过时数字

| 位置 | 原文 | 改为 |
|---|---|---|
| 判据条数说明 | `实测 1218 passed / 3 skipped` | `实测 1336 passed / 3 skipped` |
| 自检清单表 | `1218 passed / 3 skipped`，~50s | `1336 passed / 3 skipped`，~54s |

**README 里 13 条 cli 命令逐条机器验证**：子命令都存在、参数都被接受。
开发期那行已指向 `all --ai --no-run`。

---

## 三、training.html：两处说旧话 + 两个新能力缺失

### 1. `HYBRID_RESET_URL` 默认值还在说旧话（重要）

培训页原本写：

```
HYBRID_RESET_URL | http://localhost:8000/api/reset?purge=1
```

**但 V8.7.7 起默认已经是 `off`**（你自己定的：生产环境没有 reset 开关，框架不能依赖这个业务假设）。
文档没跟上，等于把那个修复又讲回去了。已改为：

```
HYBRID_RESET_URL | off（V8.7.7 起默认不碰数据）
  off  = 默认，什么都不做
  auto = 从 HYBRID_BASE_URL 推导 {base}/api/reset?purge=1（只在本机跑 demo 时用）
  具体 URL = 原样 POST
  [!] 默认改成 off 的原因：真实生产环境不会有 reset 开关，测试数据有时还要保留
```

### 2. 可调项数量过时

`全清单（45 项）` → **`51 项`**（`cli config` 实际输出 51 项，机器数的）。

### 3. 补上 `--no-run`（两处）

- **4.1 节的「推荐节奏」行**：开发期循环（改场景重跑）正是 `--no-run` 的场景，写清了省什么、代价是什么
- **第 8 章命令清单**：新增 `(1)'` 一行

### 4. 「用例前自动复位」这个已废掉的假设，正文里还在讲（**另两处**）

第一遍只改了参数表，扫全文才发现正文里还有两处在**教人依赖 reset**：

| 位置 | 原文 | 改为 |
|---|---|---|
| 4.x「写场景前必知的 demo 三件事」 | 「每条用例开始前框架**会复位数据** -> 列表页固定 20 条预置」 | 「复位是**可选能力，默认不开**（V8.7.7 起 off）；无论开不开，都别写跨用例依赖 —— 生产环境通常没有 reset 接口、数据还会累积，依赖它必翻车」 |
| 「断言与依赖纪律」表 (3) | 「每条用例开始前框架**复位数据** ->『上一条建的记录』不存在」 | 「『上一条建的记录』**不能假定它还在**：框架**默认不复位**」 |

**为什么必须改**：这两处不是在说「有个开关」，而是在**陈述框架行为**。
按旧文字，新人会写出「上一条建的单据，下一条去查」这种用例 —— 在 demo 上碰巧通过（因为以前真会复位），
接上真实系统就必然翻车。**文档讲错了行为，比没有文档更危险。**

**同时核对过**：`scenarios/README.md` 第 2 条也是同一处旧话，已一并改。
`2161-2166` 行的「用例间自动复位数据」在 **CHANGELOG 冻结区内**，按 R9 原样保留不动。

### 5. 另两份 `GUIDE_DOCS` 也核过了

- `scenarios/README.md`：入口口径（主线 `all --ai`）本来就对，只改了 reset 那段
- `docs/feature_map.md`：生成的，重渲即同步

**培训页正文 21 条 cli 命令逐条机器验证全部有效**（CHANGELOG 段是冻结历史，按 R9 不查不改）。

---

## 四、我自己的两个错，都被工具当场抓住了

**1. LSP 抓到 f-string 里的 `{base}`**

我在培训页模板里写了 `{base}/api/reset?purge=1` —— 那段在 f-string 里，
`{base}` 会被当**Python 变量求值**，运行时 `NameError`。

Pyright 当场报 `"base" is not defined`，改成 `{{base}}` 转义。

**这个坑不抓到的话，是渲染培训页时直接崩**，不是样式问题。

**2. `--case` + `--no-run` 静默不生效**（V8.7.9 埋的，本版一并修）

`cmd_all` 里 `cases` 只传给 `cmd_run`，所以 `--no-run` 时 `--case` 完全不生效但**不报错**。
违反「无效参数绝不静默忽略」。已改为 `exit 2` + 指出正确做法（`run --case <case_id>`），
并补判据钉住。

---

## 五、判据

- 新增 `test_no_run_rejects_case_combination`（`--case` + `--no-run` 必须报错）
- 既有的文档真值判据全部通过：`test_docs_truth_contract`（含 `test_j2_no_explore_ai_as_runnable_command`）、
  `test_feature_map_doc_is_in_sync`、`test_cli_help_coverage`、`verify_html_sync`

---

## 六、怎么自己复核（你不用信我）

```bash
# 1) help 与代码一致
python -m framework.cli --help                    # 看是否还有 contracts_search_by_no

# 2) 培训页与代码一致
python -m framework.cli config | wc -l            # 对上培训页写的「51 项」
grep -c 'no-run' docs/training.html               # 应 > 0

# 3) README 的条数
python -m pytest tests/ -q                        # 对上 README 写的 1336
```

---

## 七、兼容性

**代码行为零变更**（只有文档 + help 字符串 + `--case`/`--no-run` 的组合校验）。
V8.7.9 的 `all --ai --no-run` 用法完全不变。
