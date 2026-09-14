# scenario 文件结构设计（AI 语义识别 GUI 自动化的场景库）

> 状态：**待你确认**（本轮只出设计，未改代码）
> 作者：AprilPark1012 · 2026-09-11
> 目标：`explore --ai` 除现有 `--scenario "内联提示词"` 外，新增「直接读 scenario 文件」的方式；
> 文件放项目根 `scenarios/`（config 里已有 `SCENARIOS_DIR = BASE / "scenarios"` 常量，目录尚未创建）。

---

## 0. 结论一句话

**一个场景 = 一个 YAML 文件**，字段按「谁读它」分五组：**人读 / 框架读 / AI 读 / 质量闸读 / 数据读**；
其中**只有 `scenario`（自然语言动作流）必填**，其余全可选 ⇒ 今天的 `--scenario "…"` 等价于"只给 scenario 字段"，
所以内联与文件两条路**共用同一套下游**（ElementMap → cases → generate → run），零分叉。

---

## 1. 现状核对（事实）

| 事实 | 核对结果 |
|---|---|
| `scenarios/` 目录 | **不存在**（config.py 里的 `SCENARIOS_DIR` 是 P5"用例编排表(index.json)"的遗留，从未落地）→ 正好复用这个名字，不用另起 |
| YAML 依赖 | `pyyaml 6.0.3` **已在 .venv 里**（无需新增依赖） |
| cases 结构 | `{case_id, name, base_url, steps[{op,desc,element,value,url}], asserts[{desc,expect}]}` |
| generate 读用例的方式 | `generator.py` 只取 `case["case_id"] / steps / asserts`（87、195-197、264-280 行）⇒ 用例里**多写字段安全，会被忽略** |
| explore 现有入参 | `--scenario "…"` 一个字符串；缺省写死一句话 |

---

## 2. 目录与命名约定

```
hybrid_gui_qa/
└── scenarios/
    ├── README.md              # 契约说明（字段表 + 示例 + 命名规则）——给人看，不参与执行
    ├── contracts/             # 按业务模块分子目录（模块少时可先平铺）
    │   ├── search_by_no.yml
    │   └── create_bu_a.yml
    └── ...
```

- **一个文件 = 一个场景**；**文件名 = 场景 id**（小写蛇形 `^[a-z][a-z0-9_]*$`）。
- 文件名与 `id` 不一致 → 打警告，**以 `id` 为准**（避免"改文件名忘改 id"造成溯源断裂）。
- 为什么不做一个大 `index.json`：一文件一场景才能 **diff / review / grep / 并行编辑不冲突**，
  出问题能一眼看出是哪个场景改坏了。

---

## 3. 文件结构（字段表）

| 字段 | 必填 | 谁读 | 说明 |
|---|---|---|---|
| `id` | 建议 | 框架/人 | 稳定标识；用于 case_id 命名与溯源。缺省用文件名 |
| `title` | ○ | 人 | 一句话标题（报告/日志可读性） |
| `description` | ○ | 人 | 更完整的意图说明（不进 AI prompt） |
| `tags` | ○ | 框架 | 分组筛选：`--tag smoke` / `--tag 合同` |
| `priority` | ○ | 框架 | P0/P1/P2，批量跑可排序 |
| `owner` / `updated` | ○ | 人 | 责任人与最近更新（场景腐坏时追溯） |
| `target.url` | ○ | 框架 | 缺省用 `config.TARGET_URL` |
| `target.page` | ○ | AI | 页面的人话描述，喂 prompt 帮 AI 判断"这是哪个页面" |
| `target.preconditions` | ○ | 人/AI | 前置条件（一期只作为 AI 上下文，不自动执行） |
| **`scenario`** | **●必填** | **AI** | **自然语言动作流**（就是现在 `--scenario` 传的那句话），YAML 块标量支持多行 |
| `business_context` | ○ | AI | 领域知识：字段含义、编号规则、容易踩的坑 → 喂 prompt |
| `assert_guard.must_contain` | ○ | AI+质量闸 | 期望出现的**稳定文本**（操作前可确定）；喂 prompt + 落盘硬校验 |
| `assert_guard.forbidden` | ○ | AI+质量闸 | 本场景专属禁止项（全局已禁"计数/时间戳/随机值"，这里补业务特例） |
| `data` | ○ | 框架(二期) | 参数化：每组数据产一条用例，`scenario` 里用 `{keyword}` 引用 |
| `notes` | ○ | 人 | 备注/历史/为什么这么写 |

**AI 侧 prompt 的变化**（这是本设计最关键的增量）：
```
现在：场景 + 控件清单 + DOM上下文 + 通用规则(1~8条)
文件版：上面这些 + 【页面背景】(target.page + business_context)
                   + 【本场景护栏】(must_contain：断言应围绕这些稳定文本 / forbidden：不得出现这些)
```
⇒ 把"断言必须操作前可确定"从**口头通用规则**升级为**每场景可声明的硬约束**，同时喂 prompt（事前）与质量闸（事后）。

---

## 4. 两个示例

### 4.1 搜索类（scenarios/contracts/search_by_no.yml）

```yaml
# 一个文件 = 一个场景；文件名即场景 id
id: contracts_search_by_no
title: 合同列表 · 按编号搜索
description: 输入合同编号片段 → 点搜索 → 确认列表出现对应编号的记录
tags: [合同, 搜索, smoke]
priority: P0
owner: AprilPark1012
updated: 2026-09-11

target:
  url: http://localhost:8000        # 缺省则用 config.TARGET_URL
  page: 合同列表页（列表 + 多条件搜索 + 新建弹窗）
  preconditions:
    - demo 已启动：python -m demo.app

# —— 下面这段就是 AI 语义识别的输入（等价于 --scenario 的字符串）——
scenario: |
  在合同列表页面的搜索框输入 '1005'，点击搜索按钮，
  确认结果列表里出现编号为 HT-1005 的合同记录。

# —— 领域上下文：帮 AI 挑对控件、判对断言 ——
business_context: |
  关键字搜索框的 placeholder 是“合同编号/名称/管理单元/合同类型/帐套”，名称列模糊匹配；
  合同编号规则 HT-1000+i（输入片段 1005 ⇒ 目标记录编号 HT-1005）；
  页面底部状态行文案形如“搜索完成，命中 N 条”——N 是运行时才知道的，不作断言。

# —— 断言护栏：喂 AI + 落盘硬校验 ——
assert_guard:
  must_contain: [HT-1005]     # 断言必须围绕这个稳定文本
  forbidden: ["共 ", "条合同"] # 额外禁止（计数类，全局已默认禁）

notes: |
  按编号搜最稳：编号是确定性生成的；不要用“共 N 条”当断言（实测翻车过一次）。
```

### 4.2 新建类（含弹窗 + 动态占位符）（scenarios/contracts/create_bu_a.yml）

```yaml
id: contracts_create_bu_a
title: 合同列表 · 新建合同（bu_a）
description: 打开新建弹窗 → 填字段 → 提交 → 列表出现刚建的数据
tags: [合同, 新建, regression]
priority: P1
updated: 2026-09-11

target:
  url: http://localhost:8000
  page: 合同列表页（新建走弹窗，字段：名称/管理单元/合同类型/客户/业务单元）

scenario: |
  点击“新建合同”按钮打开弹窗；填写合同名称、管理单元、合同类型、客户、业务单元；
  点击提交按钮；确认列表中出现刚填写的合同名称。

business_context: |
  弹窗内控件在弹窗打开前探测不到（框架会二次探测）；
  合同名称必须唯一，用 {datetime} 占位符生成，避免反复重跑撞名。

assert_guard:
  must_contain: []            # 名称是动态的，由 case.vars 承载，这里不写死
  forbidden: ["新增成功"]      # demo 没有这个提示，别让 AI 编

data:                          # 二期：参数化（一期先只解析不展开）
  - {name: "合同_{datetime}", mu: "0021", type: "合同", customer: "c1", bu: "bu_a"}

notes: |
  主检查点用“新建输入的合同名 + 各字段与输入一致”核验；不依赖后端返回编号。
```

---

## 5. CLI 契约（保留内联 + 新增文件）

```bash
# ① 原样保留（快、临时试玩、CI 一行命令）
python -m framework.cli explore --ai --scenario "在搜索框输入'1005'点搜索，确认出现 HT-1005"

# ② 新增：单个场景文件
python -m framework.cli explore --ai --scenario-file scenarios/contracts/search_by_no.yml

# ③ 新增：目录批量（可筛选/限流）
python -m framework.cli explore --ai --scenario-dir scenarios/ [--tag smoke] [--limit 5]
```

- **三者互斥**：`--scenario` / `--scenario-file` / `--scenario-dir` 同时给 → **报错 exit 2，不猜**。
- **校验**：文件缺 `scenario`、YAML 语法错、id 非法 → 明确报错；错误信息带文件路径与行号（能带就带）。
- **批量时的 `--verify` 策略**：`generate` 只跑一次（省时间），随后**每条新用例单独 pytest 单跑**（失败能精确归因到哪条场景）；
  汇总打印"✅ 通过 x 条 / ❌ 失败 y 条"，任一条失败 → exit 3。可用 `--no-verify` 整体跳过。
- 继续沿用现有保障：LLM 失败 exit 2（拒绝 mock 冒充）、落盘质量校验、`cli prune` 归档保留。

---

## 6. 数据流与溯源

```
scenarios/**.yml  ──(读文件：校验 + 拼 prompt)──▶  explore --ai  ──▶  cases/ai_<id>_<HHMMSS>.json
   （人的意图·资产）                                  （AI 语义识别）        （机器产物·可执行）
                                                                              │
                                                       generate（优先 element_map 快照）──▶ scripts/ + datasets/
                                                                              │
                                                                     run（pytest 并发 + 自愈）
```

- **case_id 命名**：`ai_<scenario_id>[_d<数据序号>]_<HHMMSS>`
  —— `scenario_id` 稳定 ⇒ 可用 `ls cases/ai_contracts_search_by_no*` 找到同一场景的历史产物；
  `HHMMSS` 保留 ⇒ 每次生成可追溯、不覆盖。
- **溯源回写**：生成的 case 顶层新增 `source_scenario`（文件相对路径）与 `scenario_id`；
  generator **只读** case_id/steps/asserts，多出的字段被忽略（已核对代码）⇒ 对执行零影响。
- **场景改了怎么办**：重跑该场景文件 → 得到新的 case（旧 case 仍在，可 diff 对比"AI 这次识别得是否一致"）。

---

## 7. 设计逻辑（为什么这么设计）

1. **为什么要文件化**：内联提示词跑完就丢——不能 diff、不能评审、不能复用；文件化后场景**变成可版本化的资产**，
   而且能挂"领域上下文/断言护栏"这类**只对某个页面成立**的约束（内联塞不下、也不好维护）。
2. **为什么一文件一场景 + 文件名即 id**：diff/review/grep 友好；并行编辑不冲突；`--tag` 分组筛选天然可做。
3. **为什么用 YAML**（而不是 JSON / 大 index.json）：
   - 块标量 `|` 写多行中文**无需转义**（JSON 得写一堆 `\n`），且**能写注释**（给人的设计说明就写在文件里）；
   - pyyaml 已在依赖里（实测可用），零新增成本；
   - 备选：Markdown + YAML front-matter（适合以后要写长 prose/表格），但一期没必要。
4. **为什么按"谁读它"分层**：字段一锅粥会导致"改给人看的说明，却意外影响 AI 行为"。
   人/框架/AI/质量闸/数据 五组各归其位；**只有 `scenario` 必填**，所以老用法（内联）天然兼容，是同一条路的退化形式。
5. **为什么把"断言护栏"写进文件**：断言质量是这套框架最容易翻车的地方（已实测两起：断言=输入回显、断言=编造计数）。
   全局 prompt 规则只能"泛泛地劝"，文件里逐场景声明 `must_contain/forbidden` 才能**事前约束 AI + 事后硬校验**，双保险。
6. **为什么 `scenarios/`（意图源）与 `cases/`（产物）分开**：职责不同、寿命不同——场景长期演进、用例随时可重建；
   分开后 `cases/ai_*` 可以放心批量清理，手写用例与场景文件都不会被误伤。
7. **为什么保留内联**：探索期需要"30 秒验证一个想法"；文件化是给"沉淀与批量回归"用的。两者共用下游，不存在两套实现。

---

## 8. 分期

**一期（本轮实现，等你点头）**
- `--scenario-file` / `--scenario-dir`（含 `--tag` / `--limit`）、三参数互斥校验、字段校验与清晰报错
- 字段：`id / title / tags / priority / target.url / target.page / target.preconditions / scenario / business_context / assert_guard.* / notes`
- 护栏接入 prompt + `case_warnings` 硬校验；case 回写 `source_scenario`；case_id 用 `<id>` 命名
- 批量 verify：generate 一次 + 逐条单跑 + 汇总 exit 3
- 落 `scenarios/README.md` + 2 个示例场景（跑通验证）

**二期（预留，不阻塞一期）**
- `data` 参数化展开（一场景 N 条用例）、`preconditions` 自动执行、`last_verified` 由 `--verify` 成功后回写（场景健康度）、`tags` 定时回归（接 cron）

---

## 9. 待你拍板

| # | 问题 | 我的建议 |
|---|---|---|
| Q1 | 文件格式：YAML / JSON / Markdown+front-matter | **YAML**（多行中文免转义 + 注释 + 依赖已在） |
| Q2 | `data` 参数化一期做不做 | **一期只解析不展开**（避免半成品），二期再落地 |
| Q3 | 目录结构：平铺 `scenarios/*.yml` vs 模块子目录 `scenarios/contracts/…` | **模块子目录**（现在只有合同模块，多用例后不混乱）；`--scenario-dir` 递归扫描 |
| Q4 | 目录名用 `scenarios/`（config 已有常量）还是新开 `scenario/` | **`scenarios/`**（复用已有常量，不动 config） |

---

## 10. 落地记录（2026-09-11 晚 · 已实现并实测）

**决策**：按建议执行 —— YAML / `data` 只解析不展开 / 模块子目录 / 目录名 `scenarios/`（复用 config 常量）。

### 10.1 改动清单

| 文件 | 改动 |
|---|---|
| `framework/scenario.py` | **新增**：`Scenario` 数据类 + `load_scenario_file()`（严格校验、报错带路径）+ `discover_scenarios()`（递归/`--tag` 过滤/priority 排序） |
| `framework/cli.py` | `cmd_explore` 支持 `--scenario-file` / `--scenario-dir`（`--tag` 可重复 / `--limit`）；**三入口互斥**（同时给 → exit 2）；批量 `--verify`：generate 只跑一次 + 逐条单跑 + 汇总 exit 3；新增 `_explore_one` / `_verify_cases` / `_arg_value(s)` |
| `framework/explorer.py` | prompt 接入【页面背景】+【本场景护栏】+ 规则 2b（区域消歧）；`_plan_to_steps` **不再静默丢元素**（精确 → 模糊对齐 → 明确告警）；新增同步探测 `_collect_page_context`，`_ai_explore_async` 退化为"只调 LLM" |
| `framework/probe.py` | `_label_text` 兜底：同容器内前置 `<label>`（无 `for`、未包裹也认）；`_nearest_heading` 增强：也认"内含 heading 的最近祖先区块"（弹窗标题是这样拿到的） |
| `framework/case_builder.py` | 新增 `make_case_id_from_scenario_id()`；`elementmap_to_cases_file(..., extra=, guard=)`；`case_warnings(case, guard=)` 增加**护栏校验**与**缺元素步骤拦截** |
| `scenarios/` | `README.md`（字段契约）+ `contracts/contracts_search_by_no.yml`（P0/smoke）+ `contracts/contracts_create_bu_a.yml`（弹窗 6 必填字段 + `{datetime}` 占位） |

### 10.2 实测证据（全部真跑）

| 验证项 | 结果 |
|---|---|
| 单场景文件 | ✅ `ai_contracts_search_by_no_221138`，`--verify` 实测 PASSED，exit 0 |
| 目录批量 + `--tag smoke` | ✅ 命中 1 条、P0 排前、用例落盘并校验通过 |
| **新建场景（弹窗 6 字段）** | ✅ AI 出 10 步，弹窗字段**全部挑对**（`请输入合同名称`/`请选择_0021_0451_1031`/…/`提交`），实测 **PASSED** |
| 错误路径 8 条 | ✅ 全部 exit 2 且信息明确：缺 `scenario`、id 非法、YAML 语法错、字段类型错、文件不存在、目录不存在、tag 无命中、参数互斥 |
| 溯源字段 | ✅ 用例内含 `scenario_id` / `source_scenario` |
| 全量回归 | ✅ 8 passed（`log/20260911_221808/report.html`） |

### 10.3 实现中额外挖出并修复的 3 个真缺陷（同一个家族：**静默兜底**）

1. **★ 最严重：Playwright Sync API 跑在 asyncio loop 里**
   `sync_playwright()` 被写在 `_ai_explore_async`（异步上下文）里 ⇒ 必然抛
   `It looks like you are using Playwright Sync API inside the asyncio loop` ⇒ 被一处静默
   `except: page_items = items` 兜底 ⇒ **「弹窗字段补充」与「DOM 上下文增强」一直是死代码**
   （AI 从来只看到外部传入的基础控件，DOM 上下文一直是空列表）。
   修法：拆成「同步探测 `_collect_page_context()` → 异步 LLM 规划」两段；探测失败**必须打印**，
   连备用清单都没有时直接 `AiExploreError`（拒绝在信息不全时硬猜）。
2. **重复探测**：新写的 CLI 先探一次、`ai_explore` 内部再探一次 ⇒ 连开两个 Chromium；
   内存吃紧时第二次失败，叠加 (1) 的静默兜底 ⇒ 弹窗字段全丢（实测 AI 把弹窗客户下拉错选成搜索区
   的"全部客户_c1_c2_c3_c4"）。修法：CLI 不再自行探测，只由 `ai_explore` 探一次。
3. **`_plan_to_steps` 静默丢元素**：AI 的 `semantic_name` 对不上清单时 `element=None` 且**零提示**
   ⇒ 步骤变成"没有目标的操作"，生成脚本必然定位失败。修法：精确匹配 → 规范化唯一模糊对齐
   （打印"自动对齐"）→ 仍对不上则明确告警 + 打印清单可用名；同时 `case_warnings` 增加
   「操作步骤没有绑定元素」拦截（实测当场抓到 7 步缺元素、并给出步骤清单）。

**副作用（好的）**：现在 AI 用例的典型缺陷在**落盘那一刻**就暴露（缺元素 / 断言回显 / 断言是猜的 /
不满足场景护栏），不再等跑挂才发现。

### 10.4 二期未做（保持设计，不阻塞）

`data` 参数化展开、`preconditions` 自动执行、`last_verified` 回写（场景健康度）、`tags` 定时回归（接 cron）。
