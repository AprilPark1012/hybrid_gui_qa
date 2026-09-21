# hybrid_gui_qa — LLM 驱动的混合 GUI 自动化测试框架

> 当前版本 **V7.8**（2026-09-21）· 版本号单一来源：`tools/build_html.py` 顶部 `VERSION`/`CHANGELOG`
> （路径只在 `framework/config.py::VERSION_SOURCE` 定义一次，cli / llm_cassette / 打包器共用）
> （`python -m framework.cli --version` 也读它）。本次变更见 `releases/RELEASE_NOTES_V7.7.md`；
> 上一版见 `releases/RELEASE_NOTES_V7.6.md`（跨 tab 端到端 · 行内定位 · 首行断言）。
> 历次升级日志都在 `releases/RELEASE_NOTES_V*.md`，**每次交付包会一并带上**。

> 一个 Python 骨架，示范如何把 **Browser Use（AI 智能探索）** 和 **Playwright（确定性执行）**
> 组合成一套混合测试框架：AI 负责理解意图、规划步骤、挑元素；Playwright 负责精确定位、
> 唯一性校验、可复现回归执行。

核心哲学一句话：**让 AI 做理解和决策，让确定性代码做精确定位，绝不把"定位"交给 LLM。**

---

## 为什么是"混合"而不是二选一

| 能力 | Browser Use (AI) | Playwright (确定) |
|---|---|---|
| 理解自然语言测试意图 | ✅ 强 | ❌ |
| 规划步骤 / 挑元素 | ✅ 强 | ❌ |
| 精确定位元素 | ❌ 可能幻觉 | ✅ 100% 准 |
| 唯一性校验 / 防误点 | ❌ | ✅ |
| 可复现回归 / 进 CI | ❌ | ✅ |

业界标杆印证（Stagehand / Playwright Test Agents 的哲学）：
> *"Selectors break. Natural language doesn't."* —— 但自然语言只能用于**理解**，
> 真正执行必须落到确定性的 locator 上。

---

## 架构（AI 产用例 → 确定性执行：explore(--ai) → cases/ → generate → run）

```
┌────────────────────────────────────────────────────────────────┐
│ 执行链路（cli all 一条龙, 确定性、零token、可进CI）              │
│  probe.py   →  Playwright 扫描页面可交互元素 → 语义清单          │
│                (role/name/label/placeholder/test_id)            │
│  generator.py→ 读 cases/*.json(含 ai_*) → 优先用 element_map 快照 │
│                映射确定性locator(缺项回退现场probe) + 抽离字面值  │
│  cli.cmd_run→ 资源预检 + pytest 并发（web-first 断言             │
│                + Tier1→Tier2 定位 + Healer 自愈）                │
│  产物: scripts/test_cases.py + scripts/datasets/*.json(脚本分离)  │
├────────────────────────────────────────────────────────────────┤
│ AI 分支（cli explore --ai, 语义识别产用例, 需 DeepSeek key）      │
│  explorer.py→ 读自然语言场景 + probe清单 + DOM上下文              │
│                → ChatDeepSeek(function calling) 挑语义名          │
│                → ElementMap + ①语义校准                          │
│  产物: ElementMap + cases/ai_*.json（供 generate 消费）           │
└────────────────────────────────────────────────────────────────┘
```

关键点：**AI 只理解和决策（挑语义名 + 规划步骤），Playwright 精确定位执行**；`explore --ai` 的产物会落成 `cases/ai_*.json`（`ai_` 前缀隔离，绝不误删手写用例），与手写用例一起被 `generate` 消费（优先用 element_map 快照映射 locator，缺项才现场 probe）；执行端零 token、带 Healer 自愈，可进 CI。

### 两种业务场景（本框架的两条链路）

| # | 场景 | 入口 | 函数链路（细节见 `docs/training.html` 第 4 节图 A/图 B） | 花 token |
|---|---|---|---|---|
| ① | **自然语言用例 → AI 语义识别/编排 → 产出用例到 `cases/`** | `explore --ai --scenario "…"` / `--scenario-file scenarios/x.yml` / `--scenario-dir scenarios/` | `cli.cmd_explore` → `cli._explore_one` → `explorer.ai_explore` →（**同步**）`_collect_page_context`〔`probe.probe_page` ◀出场❶ + `_try_collect_modal_items` 弹窗二次探测 + `_collect_dom_context`〕→（**异步**）`_ai_explore_async`〔`_build_planner_prompt` → `ChatDeepSeek.ainvoke(output_format=_PlanModel)` → `_plan_to_steps`/`_match_item` → `_apply_semantic_calibration` → `_finalize_map`〕→ `case_builder.elementmap_to_cases_file` → `cases/ai_<scenario_id>_<HHMMSS>.json` → `cli._verify_cases`（立刻试跑，FAILED → exit 3） | ✅ 是 |
| ② | **手搓 case.json → 生成 playwright 脚本 + 数据分离 → 执行** | `generate` / `run`（`all` 一条龙） | `cli.cmd_generate` → `generator.generate_scripts`〔loc_map 三档：`_load_loc_map_from_element_map` ◀出厂快照 → `_load_loc_map_from_probe_snapshot` → 现场 `probe.probe_page` ◀出场❷；`_semantic_to_locator_expr`；`_render_pytest_case`（未映射 → `pytest.fail`）；`_extract_data`〕→ `scripts/test_cases.py` + `scripts/datasets/*.json` → `cli.cmd_run` → `limits.safe_workers` → `pytest -n N` → 运行期 `conftest._act` → `locator_bridge.resolve_locator`（Tier1→Tier2→意图复验）→ `healer.try_heal` | ❌ 零 token |

两条链路**只在 `cases/*.json` 汇合**：场景①的产物就是场景②的输入（同一套字段），所以 **AI 产的用例和你手搓的用例跑的是同一条确定性执行链**。
两者共享三样东西：`probe`（出场❶给 AI 看菜单 / 出场❷把语义名翻成 locator）、`semantic_name` 契约、执行层（`locator_bridge`+`healer`+`limits`+`conftest`）——**selector 全程不进 LLM**。



### 核心数据流：cases 自然语言用例 → 脚本 + 数据抽离

```
cases/用例.json(写死数据) ──┐                          ┌──▶ scripts/用例.py (playwright脚本)
  (自然语言步骤: op/desc/    │                          │       │
   element/value/asserts[]) ├─▶ generator.generate_scripts ─┤       ▼
                            │ (优先element_map:语义→定位+抽离字面值)│  scripts/datasets/用例.json (抽离数据→脚本分离)
                            └────────────────────────┘       │       ▼
                                                    ▸ cli.cmd_run: 资源预检 + pytest -n <安全并发> + HTML报告 + 逐用例日志
```

- **`cases/*.json`**：手写自然语言用例。步骤用 `op`(操作类型)+`desc`(自然语言描述)+`element`(探测语义)+`value`(写死测试数据)；断言用 `asserts[]` 数组。**用例里是写死的数据**。
- **`generate` 抽离**：读 cases → **优先用 `output/element_maps/element_map_*.json` 快照**建立 semantic_name→定位表达式映射（`--element-map <file>` 指定、`--live-probe` 强制现场；快照缺项才现场 `probe` 补齐，日志打印「locator 来源: element_map(...) 命中 x/y + 现场probe补齐」）→ 按操作类型翻译 Playwright 代码 → **把字面值抽离到 `scripts/datasets/<case_id>.json`**，脚本中仅留 `_data(key, ctx)` 引用（脚本数据分离）。
- **动态占位符**：数据里写 `{datetime}`/`{date}`/`{uuid}`/`{random}` 等 → 运行时 `_data` 解析并固化（填表名==断言名，**反复重跑不重名**）。
- **用例级变量池 `case.vars`**：运行过程动态数据（新建的合同名、系统返回的编号、抓取字段值），**既供检查点断言、也作后续操作输入**，function-scope 隔离，并发不污染。
- **检查点不依赖后端返回编号**：新建场景主检查点用"新建输入的合同名 + 各字段与输入一致"在列表核验生成成功；系统若返回编号，仅作**增强项**存入变量池并条件回搜（无编号则跳过，用例仍通过）。
- **操作类型→代码**：`op` 共 6 种（`goto/click/fill/select/check/press_enter`），翻译在 `generator._render_pytest_case`；**断言不是 op** —— `asserts[]` 由 `generator._render_assert()` 逐条翻译成 `conftest` 的断言辅助调用。ElementMap→case 的动作映射表在 `case_builder._OP_MAP`。定位走确定性 `get_by_test_id/role+name`（Tier1），彻底解耦 demo。
- **断言类型（2026-09-13 D 项，11 种，全部 web-first）**：`asserts[]` 每项可带 `kind`（缺省 = `text`，老用例不用改）+ 用 `element`（探测语义名→映射 locator）或 `selector`（**手写用例专用**，AI 链路由 `case_builder` 拦）指定目标：

  | kind | 字段 | 验什么 |
  |---|---|---|
  | `text` | `expect` | 页面出现该文本（原有类型，`get_by_text`） |
  | `visible` / `hidden` | `element`\|`selector` | 元素可见 / 不可见（弹窗开合） |
  | `count` | `element`\|`selector` + `expect` | 元素数量（结果行数）——`expect` 可为 `0` |
  | `attr` | `element`\|`selector` + `name` + `expect` | 属性值（`data-field`/`class`/`href`） |
  | `value` | `element`\|`selector` + `expect` | 输入框当前值——`expect: ""` 也是合法值（验"被清空"） |
  | `url` | `expect` | 页面 URL（以 `http` 开头=精确；否则按"包含"匹配） |
  | `checked` / `unchecked` | `element`\|`selector` | 勾选 / 未勾选 |
  | `enabled` / `disabled` | `element`\|`selector` | 可用 / 禁用 |

  **红线不变**：① 期望值必须"操作前可确定"（AI 侧禁止计数/时间戳；手写用例里行数这类只要数据固定就合法）；② 缺字段（`count` 缺 `expect`、`attr` 缺 `name`）、未知 `kind`、目标未映射 → 生成的脚本 `pytest.fail`，**绝不静默少验一步**；③ 断言成功统一打 `[CHECK] ✓ 断言: …`（逐用例日志可见，调试模式另存一张截图）。
- **并发与提速（2026-09-13 E 项）**：`pytest-xdist` 多进程，**每个 worker（会话）只起一个 Chromium**，每条用例仅新建 `context + page`（隔离性不变：cookie/存储/trace/录像都按 context 走）。实测 9→13 条用例：总时长 **10.49s → 7.01s**，逐条 setup 由 **0.57~0.66s 降到 0.04~0.06s**（首条 0.74s = 起浏览器）。浏览器若被 OOM 杀掉会**告警 + 重启**，不静默用坏句柄；**报告**：`pytest-html` 自动生成执行统计。
- **脚本自愈**：生成脚本走 `conftest._loc()` → `locator_bridge` 分层定位（Tier1 多策略 → Tier2 指纹 → 意图复验），仍失败才交 `healer.try_heal()`；`HYBRID_SELF_HEAL=0` 可关成「失败即报」（CI 语义）。heal 事件落 `output/heals/`（可审 diff）；业务断言不过仍判真 bug，绝不静默改写。
- **未映射元素 = 显式失败（不静默跳过）**：手搓用例的 `element` 必须是 probe 探测出的 semantic_name；generate 映射不到时打印 `⚠️ 仍未映射 [...]`，并在生成的脚本里对那一步 `pytest.fail(..., pytrace=False)`。⚠️ 这里以前只留一行注释就跳过，用例照样 `PASSED` —— 属"少做一步还报绿"的假绿，2026-09-11 已修。
- **AI 用例与质量闸**：`cli explore --ai` 默认把产物落 `cases/ai_*.json`（`--no-cases` 可关）。落盘前 `case_builder` 做质量校验：断言=输入回显、断言=运行时计数（"共 N 条"）都会告警；**LLM 不可用时直接报错退出（exit 2），拒绝用 mock 冒充 AI 产物**（`--mock-fallback` 才显式降级，且不写 cases/）。**落盘后默认 `--verify` 试跑该用例**（实测不过 → ❌ + exit 3，日志 `output/verify/`）；
- **归档保留策略**：`cli prune [--keep 20] [--dry-run]`，`output/element_maps/` 的 element_map/probe 快照各留最近 N 个（`HYBRID_KEEP_SNAPSHOTS` 可调）；explore/probe 每次结束自动静默清理。

> 需 DeepSeek key（AI 语义识别链路）：在项目根 `.env` 配 `DEEPSEEK_API_KEY`（见「快速上手·第4节」）。

---

## 2026-09-21 变更要点 —— 数据参数化「真展开」（V7.8）

**一组数据 = 一条用例**。以前场景的 `data:` 只解析不展开（一个场景只能跑一组数据，还会打警告）；
现在它**真的展开**：文案里写 `{占位符}`、`data:` 里给几组值，生成器就产出几条独立用例，
**报告里各占一行、失败能定位到具体数据集**，还能按键单跑某一组（`-k "<case_id> and <组名>"`）。
与既有的 `{datetime}` 动态占位符同一套机制，写场景的人不用学新东西。

| 项 | 内容 |
|---|---|
| 场景写法 | `scenario` 文案里写 `{关键词}`；`data:` 每组一个映射（`id` 可选，进报告用例名） |
| 数据文件 | `scripts/datasets/<cid>.json`（基础数据）**格式不变**；多组另落 `<cid>.sets.json`（基础 ⊕ 组值） |
| 报告形态 | `test_xxx[编号-1005]` / `[编号-1007]` …… 中文参数名**不被转义**（用 pytest 官方开关） |
| 校验（硬拦） | 组值**少给**占位符 ⇒ 未解析的 `{xxx}` 会被原样填进页面（看着在跑、其实全错）；**给了用不到的键** ⇒ 写了不生效 ⇒ 两者都 `exit 2` + 人话点名 |
| 样板 | `scenarios/contracts/contracts_search_by_no.yml`（3 组数据）+ 对应用例，可直接照抄 |
| 新增判据 | 一类 `tests/test_data_expand.py`（16 条）· 二类 `tests/verify_data_expand.py`（一组一条 · 坏组只红那一行 · 单组可跑） |
| 实测 | 样板场景 3 组 → **3 条独立用例 3 passed**；把第 2 组改成坏值 → **只有它 FAILED**、另两组仍 PASSED |

## 2026-09-19 变更要点 —— 结构归一与修复批次（V7.7.1）

**不加新能力**，三件事：① 仓库结构按「框架代码 / 内部台账 / 门禁」三层分开；② 工具收进 `tools/`、
**版本号来源路径收敛成只定义一处**；③ 修掉**四处静默退化**（培训页高亮器畸形嵌套 2381 处 + 生成不可复现 +
字符串高亮一直是死的 · 打包审计历史包误报 · 一条负向验证段自 V7.5.1 起没跑过 · 一条自测隐式依赖环境）。
本版还补齐了**离线链路的交付形态**：`tools/offline_explore_chain.py` 收进仓库、打包器支持
`--with-cassettes`（交付 = **代码包 + 录像包「两件套」**，且有判据 `tests/verify_offline_delivery.py`）。
完整说明见 `releases/RELEASE_NOTES_V7.7.1.md`。

| 项 | 结果 |
|---|---|
| 结构 | `docs/` 只留 `training.html`；`tools/` = 框架自己的工具（打包器 / 培训页生成器 / 离线一键脚本） |
| 版本来源 | `framework/config.py::VERSION_SOURCE` 一处定义，cli / llm_cassette / 打包器三读者共用 |
| 新增入口 | `tests/run_verifications.sh`（特性验证统一入口，内存不足**如实 SKIP** 不当通过） |
| 新增判据 | 培训页与代码同步 · 仓库与门禁解耦 · 版本单一来源（含负向）· 打包历史形态（含负向）· 交付两件套 |
| 实测 | 一类 `pytest tests/ -q` **221 passed** · 二类 `run_verifications.sh` **9/9** · 离线链路端到端 **exit 0** |

## 2026-09-18（第二次）变更要点 —— 元素歧义闸门 + 离线 AI 链路（V7.7）

| 项 | 内容 |
|---|---|
| 元素歧义闸门 S1 | `probe.assign_semantic_names()` 可重复调用并留痕（`base_name` / `ctx_token` / `name_source` / `base_conflict`）；`explorer._merge_items()` 改为「先按 test_id 去重 → 再在**合并后的全量清单**上重算命名」⇒ 同名控件不可能再被某一轮探测的裸名独占（`cli` / `explorer` 单页+跨页 / `generator` 四处同源） |
| 元素歧义闸门 S2 | 缺失名若正是某个同名冲突组的 base 名，`generate` 报错**直接给候选**（不再是一句干巴巴的「元素未映射」） |
| 元素歧义闸门 S3 | 生成物 `_item_for()` 模糊兜底收敛：候选唯一才接受并**写日志留痕**；候选 ≥2 **抛错并列候选**；`HYBRID_STRICT_LOCATE=1` 连唯一候选也不兜 |
| LLM 录像（新能力） | `--llm-record` / `--llm-cassette` / `--llm-cassette-strict`：**严格键 + 结构键**双键回放；离线机器**不需要 key、不联网**；未命中给「最接近那份从第几行起不同」，绝不静默降级 |
| 离线一条命令 | **`tools/offline_explore_chain.py`**（随**代码包**发，2026-09-19 起入仓库）：前置体检 → 回放识别 → `generate` → 试跑，全程把 LLM 端点指到黑洞以证「真没联网」 |
| 弹层两种选中 | 合同页搜索区 = 输入框 + 弹层按钮；**弹层选中 = 精确命中、手工输入 = 右模糊**（既有语义零破坏）；客户/销售员弹层内可「+ 新建」并回填当前字段 |
| 新增测试 | `tests/test_element_ambiguity_gate.py`（15 条，含**模板 ⇄ 生成物互锁**）· `tests/verify_element_ambiguity.py`（浏览器级复现事故形态）· `tests/verify_order_pick_create.py` |
| 实测 | `pytest tests/ -q` **202 passed** · `cli run --workers 1` **17 passed / exit 0**（模糊兜底 0 次触发）· `verify_element_ambiguity.py` **exit 0** |

### 离线跑 AI 链路（连不上外网 LLM 的机器怎么做）

详细口径见 `releases/RELEASE_NOTES_V7.7.md` 第二节；这里给最常用的命令：

```bash
# 1) 录像放好 + 起被测 demo
mkdir -p output && mv llm_cassettes output/      # 录像包解开后就是 output/llm_cassettes/
python -m demo.app                                # 另开一个窗口常驻
# 2) 一条命令跑通：前置体检 → 回放识别 → generate → 试跑
python tools/offline_explore_chain.py --repo . --run
# 3) 等价的手动三步
python -m framework.cli explore --ai --scenario-file scenarios/contracts/contracts_search_by_no.yml --llm-cassette
python -m framework.cli generate
python -m framework.cli run --workers 1
```

> ⚠️ **交付形态 = 两件套**（2026-09-19 定）：**代码包**（含回放引擎 + 一键脚本）+ **录像包**
> （含 `llm_cassettes/` 数据 + 用法说明）。只有代码包**跑不起来**（缺录像数据）；录像单独放进去也没用
> （功能在代码里）。两件一起打：`python tools/pack_release.py --with-cassettes`。
> 交付形态本身有判据：`python tests/verify_offline_delivery.py`（两件都能打出来 + 内容齐 + 清单与事实一致）。

**三条铁律**：① 代码必须是含 `--llm-cassette` 的版本（V7.7 起）；
② demo 与 `scenarios/` 必须与录制时**同版本**（回放键含场景文案 / 页面地址 / 控件骨架）；
③ 数据值不同没关系（结构键兜底时**会告警**），只认逐字一致就加 `--llm-cassette-strict`。

## 2026-09-18 变更要点 —— 跨 tab 端到端 · 行内定位 · 首行断言（V7.6）

| 项 | 内容 |
|---|---|
| 跨 tab（新能力） | 探针新增 `opens_new_tab`（`_blank` / `window.open` ⇒ 点击会开新 tab，**不让 LLM 猜**）；动作新增 `click_new_tab` / `close_tab`，生成脚本 `_Tabs` 负责句柄切换并**回读「真的关了没」** |
| 行内定位（新能力） | `probe_row_fields()` 探出表格行内列清单；`TestStep.row_text` / `cell_field` + `_click_row_cell()` —— 用于**运行时新建的那一行**（编号由服务端分配，语义清单里不可能有） |
| 首行断言（新能力） | 新 kind `first_row`（`row_field` + 期望值）→ `_assert_first_row()`。文本断言只能证明「页面上有这个值」，**证明不了它在第一行** |
| 修掉的安静缺陷① | **同字段·跨区域·不同名字 ⇒ AI 静默选错控件**：弹窗 `请输入订单名称` 与筛选区 `订单名称_全模糊` 名字完全不同 ⇒ 同名告警报不出来、又都映射得到真实控件 ⇒ 不报「未映射」（实测连跑 6 次 6 次全错）。修法：`_field_identity()` + `_same_field_pairs()` 把歧义**显式摊在提示词里**（含规则 2c 点明「选错不会报未映射」） |
| 修掉的安静缺陷② | **跨页重名告警按全局并集判定 ⇒ 误伤别的用例**（`cli run` 15 passed / 2 failed 假红）：改成按用例判定（`_DUP_PAGES` + `_dup_raw_names_for_case()`，判据 = 本用例声明的页 ∩ 该名字出现的页 ≥ 2），并用反向测试钉住「真重名仍必须拦」 |
| 定位手法留档 | 解失败那次的 `traces/<case>_trace.zip` → 读 `trace.network` 请求清单：一眼看出**没有 `POST /api/orders`** ⇒ 提交没发出 ⇒ 前端必填校验没过（比读日志猜快得多） |
| 实测 | AI 端到端 `explore --ai --scenario-file scenarios/orders/orders_return_from_contract.yml` → **exit 0 · `--verify` PASSED**（新 tab 开订单系统 / 4 个弹层选值 / **首行断言命中** / 点合同编号开新 tab 看详情 / 点「返回」**tab 真的关了**）；`pytest tests/ -q` **158 passed** · `cli run` **17 passed / exit 0** · `generate` 未映射 0 |
| 下一项 | **变异注入闸门**（往 demo 注入已知 bug，量「AI 产出的断言有没有牙」）—— 服务 ② AI 语义准 |

---

## 2026-09-17 变更要点 —— 假绿治理：换页证据闸 + 质量闸健壮性（V7.5.3）

| 项 | 内容 |
|---|---|
| 假绿（本版主线） | AI 用 `expect_url = localhost` 当「回到列表页」的证据 —— 换页前后**两页 URL 都含它** ⇒ 点击后立刻就能通过，等于没验换页。根因是**提示词在教 AI 这么写** |
| 三层修复 | ① 提示词：只准用**只出现在目标页**的片段；明确禁止 `localhost` / `localhost:8000` / `127.0.0.1` 这类每页都含的片段；列表页（根路径）没有独有片段 ⇒ 用**该页独有文案**做 `text` 断言。② 红线闸门 `case_builder.case_errors()`（片段命中 ≥2 页 / 跨页用例里只是 `host[:端口]`）。③ **拒绝产物**：AI 落盘与 `generate` 两条路都 `CaseQualityError` → exit 2 + 人话，一个产物不写 |
| 防误伤 | 单页用例里的 host 断言只**告警**（手写用例可能是有意的，如专门验 `host:port`）；host 判定改为「与已知页面 URL 的 host 精确比对」为主 —— 不再靠「像域名的正则」（`index.html` 曾被它误判成 host） |
| F5 断言稳健化 | `cross_page_detail` 的「列表恢复全量 20 行」→「预置基线行 `row-HT-1001` 在列表里」（与本次运行新建的数据无关，不会被顶掉） |
| 修掉的安静 bug | `case_warnings` 碰到非字符串期望值（`count` 的 `20`）直接 `TypeError` —— **守门人自己倒下 = 这道栅栏不存在**；「断言回显输入」比较改为全程字符串口径 |
| 复活的验证段 | `tests/verify_cross_page.py` 负向段**自 V7.5.1 起就没跑起来**（负向用例④用不存在的元素名 → 映射质量闸拦下整个 generate → 脚本 exit 2，看着像失败其实自己没跑完）。负向段改走 `--allow-unmapped` 并写明原因 ⇒ 实测 **5 条负向全部 FAILED**（含新增「没回到列表页时，列表页独有文案断言必须失败」） |
| 自测 | `pytest tests/ -q` → **143 passed**（+13 条 `tests/test_case_quality_gate.py`）· `cli run` → **16 passed / exit 0** · `verify_cross_page.py` → exit 0 · `generate` 未映射 0 处 / `_goto` 接线 32 处 |
| 不做（诚实清单） | CI 落点与 Windows 侧并发隔离证据按 2026-09-17 裁定不做 / 不再追；**变异注入闸门**（量「AI 产出的断言有没有牙」）仍是下一项 |

---

## 2026-09-16 变更要点 —— 脱敏收敛 + 交付包落库（V7.5.2）

| 项 | 内容 |
|---|---|
| 交付包落库 | `tools/pack_release.py --out` 默认改为**仓库内 `releases/`**（原默认 `/tmp/pkg` —— 交付包曾是唯一副本却躺在 /tmp，重启即可能丢，本版按根因修） |
| 挡住不入包 | `.gitignore` 加 `/releases/` + `pack_release.py` 的 `EXCLUDE_DIRS` 加 `releases`：打包按「已跟踪 + 未跟踪但不被忽略」收文件，漏挡会把**发布包套进发布包** |
| 命名 / 校验 | `releases/hybrid_gui_qa_V<版本>_<YYYYMMDD>.zip` + `SHA256SUMS.txt`；交付邮件就从这里取包 |
| 脱敏收敛 | 文档里最后一处内部组织缩写已清（复扫 HEAD tree = 0 命中）；`.git/hooks/pre-push` 解释器探测 ≥3.7，不再把环境问题误报成「有残留」 |
| 自测 | `pytest tests/ -q` → **130 passed**；包内自检通过；`releases/` 不进包（收集口径 0 命中） |
| 遗留（如实记） | 对象级残留：2 个**已推送**历史 blob 需重写历史 + 删仓重建才能彻底清（见 `docs/BACKLOG-下一步优化.md`） |

---

## 2026-09-14（第二次）变更要点 —— 慢目标/并发下的假红治理（V7.5）

**事故**：团队 Windows（16 核 / 16 worker）上 `run all` 红 4 条，`--debug` 却全绿。
本机用「每请求 +400ms 的反向代理」**确定性复现**（5 failed / 1 passed），根因两条：

| 根因 | 机制 | 修法 |
|---|---|---|
| **R1 页面就绪无契约** | 页面 `boot()` 异步取数后才渲染，而测试 `goto` 之后**立刻**动作/断言 ⇒ ① 弹层行还没渲染就点 → 命中 0 → 兜底也找不到（报「元素语义未找到」）② 早到的搜索在空数组上过滤，随后首屏渲染把结果**覆盖**成全量 ⇒ 计数断言永远等不到 | **F1 就绪契约** + **F2 定位有界等待** |
| **R2 有状态目标 + 全局复位** | 单一 store + 每用例 `POST /api/reset`（全局）⇒ 多 worker 下精确计数断言互相踩（实测：期望 20 行实得 23、期望 4 条实得 6） | **F6 每 worker 数据分区** + 并发安全闸 |

### 1) 被测页面要声明「就绪契约」（**给团队接自己系统时最重要的一条**）
页面在 `body` 上静态声明、数据渲染完成后置位：

```html
<body data-hybrid-ready="0">   <!-- 静态声明：本页遵守就绪契约 -->
<script>
  // ……你的取数 + 渲染……
  document.body.dataset.hybridReady = "1";   // 数据已就位，测试可以开始动作/断言
</script>
```
生成脚本的每个 `goto` 都会等它（`_goto()` 统一入口）。**没有契约的老页面**：
用 `HYBRID_READY_SELECTOR=<数据已就绪选择器>` 退化；两者都没有 → 只提醒一次、不阻塞
（后续动作/断言自带 F2 的有界等待）。想让「就绪超时」直接失败：`HYBRID_READY_REQUIRED=1`。

### 2) 定位判定改为「有界等待」
`_act` / `_resolve` 的确定性主定位不再用**瞬时** `count()` 判生死，而是先等元素 `attached`
（`HYBRID_LOCATE_TIMEOUT`，默认 5s）再判 —— 慢机器/高并发下元素「晚到」不再被误判成「不存在」。
`count` 这类复数断言仍**瞬时**判定（「期望 0 个」是合法用例，等它只会白等一个超时）。

### 3) 报错信息纠偏
旧文案「断言 locator 失效且无语义兜底（该断言既没 selector 也没 element）」**与事实相反**
（那条断言其实有 selector）⇒ 现在报「等了 N 秒仍是 0 个元素 + 常见原因 + 排查动作」；
「元素语义未找到」也补上真因链与下一步。

### 4) 并发必须「数据隔离」
- demo 侧：`/api/*` 都认 `?w=<分区>`，`/api/reset` **只清自己那份**；`GET /api/health` 声明 `partitioned`；
- conftest 侧：给每个 worker 注入 `window.__HYBRID_W`，页面把它带进所有 API 调用；
- CLI 侧：目标未声明可并发隔离时，**并发保守降级为 1** 并说明原因；确知已隔离用 `--isolated-target` 放行。

### 5) 新增闸门：慢目标
```bash
python tests/verify_slow_target.py          # 自起 demo + 慢代理，关键 6 条必须全绿
SLOW_MS=800 python tests/verify_slow_target.py   # 更极端的"拥挤机器"
python tests/verify_slow_target.py --full   # 全部用例（慢）
```
> 内存不足（本机 <650MB 可用）时它明确 **SKIP 并 exit 3** —— 绝不给假绿。

---

## 2026-09-14 变更要点（客户字段 · 服务端数据 · 用例间复位 · 挂死看门狗 · UTF-8）

### 1) 客户字段：从下拉框 → 弹层列表里选一行
新建弹窗里的客户是 **只读输入框「请选择客户」+ 按钮「选择客户」**，点按钮再弹一层**客户列表**（两列：客户名称 / 客户地址），
点该行的「选择」按钮回填并关层。列表页的客户筛选同步改成 **输入框 + 右模糊（前缀）匹配**
（客户名称前缀或客户编号前缀；输入「华信」这种**非前缀不命中** —— 用来证明是右模糊而不是包含匹配）。

> **语义名契约（改 UI 会踩的地方）**：弹层里 6 个「选择」按钮**文字完全相同**，只能靠所在行区分 ⇒
> 探测后它们的语义名形如 `选择@北京华信科技有限公司`。用例里写这个名字，generate/explore 才定位得到。

### 2) demo 数据搬到服务端（单一数据源）
`demo/app.py` 现在既是静态服务器也是数据 API：

| 接口 | 说明 |
|---|---|
| `GET /api/customers` | 6 个客户主数据（名称 + 地址） |
| `GET /api/contracts` | 全部合同（含 `custName`） |
| `GET /api/contract?no=HT-1005` | 单条；查不到 → **404 `{"error": "未找到该合同: ..."}`** |
| `POST /api/contracts` | 新建（6 项必填校验；**编号由服务端分配** HT-2xxx） |
| `POST /api/reset` | 复位成预置 20 条（**测试用例间隔离**用） |

两个页面都改成 `fetch` 渲染 ⇒ **列表页与详情页读的是同一条记录**：预置数据七个字段跨页完全一致（可断言），
**新建的合同在详情页也能看到正确的客户**（改造前详情页按编号序号推导，新建合同的客户在详情页是错的），
查不到的编号**如实报「未找到」**（改造前会给任何编号编一份出来 —— 那种"看着像对的"假数据最坑）。

### 3) 用例间数据复位（数据留在服务端的必要配套）
生成的 `conftest.py` 有 autouse fixture `_reset_target_data`：**每条用例开始前 `POST /api/reset`**。

- 为什么必需：数据现在留在服务端，新建用例会真的写进去 ⇒ 不复位时「列表恢复 20 行」这类断言会被上一条用例的残留数据打乱（用例互相污染比用例失败更难查）。
- 口径：`HYBRID_RESET_URL` 可覆盖默认值；设为 `off`/`0`/空 则不复位（被测应用没有复位接口时）。成功/失败都打印 `[setup] 数据复位 …`，失败**大声告警**。
- 反证（实测）：塞一条脏数据 + `HYBRID_RESET_URL=off` 跑跨页用例 → 「20 行」断言 **FAILED**；开着复位则 16 条全绿。

### 4) 用例级看门狗（防「挂死」比防「失败」更要紧）
Playwright 驱动**内部崩溃**时（实测 `coreBundle.js:463 Assertion error`，机器内存吃紧时触发），它的同步 API 会一直等一个
永远不来的响应 ⇒ Python 侧 **100% CPU 空转、永不退出**（实测卡了 11 分钟只能手工 kill）。CI 里这意味着一直挂着、也没人知道卡在哪。

- 对策：生成的 `conftest.py` 里 autouse fixture `_case_watchdog`（stdlib `faulthandler`），超时把**所有线程调用栈**写进
  **`log/<run_id>/watchdog.txt`** 再退出。`HYBRID_CASE_TIMEOUT`（默认 120s）可调，`0/off` 关掉。
- 实现坑（别踩回去）：转储**不能写 stderr** —— pytest 的 fd 捕获把 **fd 2 也换成临时文件**，硬退出时那段调用栈会随临时文件丢掉（实测一个字节都没有）。

### 5) 弹层（picker）探测：generate 与 explore 同源 + 有界轮询
- **同源**：`generator` 原来自己点一遍「新建」、只探一层、而且**不关弹窗** ⇒ 弹层里的控件永远看不到（手写用例直接报「元素未映射」）。
  现在统一走 `explorer._try_collect_modal_items`（含嵌套 picker 层，探完逐层关掉）。
- **有界轮询**：点开一层后不再固定 `sleep(300)`，而是每 200ms 重探、**探到就走**，最坏 2.5s（`_LAYER_RENDER_WAIT_S`）。
  机器吃紧时固定 sleep 等不够，AI 会把「从列表里选一行」判成无法绑定的步骤。
- **环境事故不伪装成业务结论**：`_page_alive()` —— 页面/渲染进程没了就明说「环境事故，不是页面没有弹层」。

### 6) 统一 UTF-8（V7.3 起的铁律）
凡**跨进程 / 落盘**的文本一律显式 UTF-8，绝不依赖系统默认编码：`framework/text_io.py` 是唯一入口
（`utf8_env()` / `force_stdio()` / `run_capture()`）；`cli.main()` 入口第一件事就是 `force_stdio()`；
生成物 `scripts/conftest.py` 自带 UTF-8 自举。回归：`tests/test_utf8_io.py`（含用 `zh_CN.gbk` locale
**精确复现** `'gbk' codec can't decode byte 0xbb in position 13` + AST 全仓扫描禁止「靠默认编码」的写法）。

---

## 目录结构 & 谁负责什么（✅ 标注工具）

```
hybrid_gui_qa/
├── pyproject.toml          依赖
├── .env.example            LLM key 说明（含 DeepSeek 配置模板）
├── demo/
│   ├── app.py              被测 demo 应用：静态页面 + **内存数据 API**（/api/customers、/api/contracts、
│   │                       /api/contract?no=、POST /api/contracts、POST /api/reset）——数据口径唯一来源
│   ├── contracts.html      合同管理系统页（列表 / 客户右模糊筛选 / 新建+客户弹层）★ 主 demo
│   ├── contract_detail.html 合同详情页（读同一条真实记录；查不到的编号如实报「未找到」）
│   └── todo.html           旧 Todo 页（保留）
├── cases/                  ★ 自然语言用例（写死数据 + asserts[] 断言）
│   ├── search_name_fuzzy.json   手写用例（此处为示例；当前 12 条手写用例）
│   ├── create_bu_a_c1.json       手写用例（含 {datetime} 动态占位；客户走弹层列表选择）
│   ├── assert_kinds_*.json      断言类型示例（search 全类型 / reset 验 value 清空 / modal 验 visible / todo 验 checked）
│   ├── cross_page_detail.json   跨页流程（列表→详情→返回，含换页 url 断言 + 客户跨页一致断言）
│   └── ai_*.json                🤖 explore --ai 产出的 AI 用例（前缀隔离，可批量清理；当前 4 条）
├── tests/                  ★ 框架自身的回归测试（不是被测应用用例）· **两类验证**都在这里
│   ├── run_verifications.sh     ★ 特性验证统一入口：逐个跑 verify_*.py、内存不足如实 SKIP、跑完出汇总表
│   ├── test_*.py                ① 框架自测（秒级、不需要 demo/key）：CLI 参数与退出码契约 / 跨进程 UTF-8
│   │                            （含 AST 全仓扫描）/ 断言翻译 / 生成质量闸 / 元素歧义 / 打包契约 /
│   │                            LLM 重试与录像回放 / **门禁解耦** / **培训页高亮器** …
│   └── verify_*.py              ② 端到端特性验证（需 demo，**含负向证伪**）：断言正/负向 / 跨页 /
│                                弹层 picker / 元素歧义 / 订单页与弹层选值 / 慢目标 / **培训页与代码同步**
├── scenarios/              ★ AI 场景库（一个文件=一个场景，YAML；explore 的输入源）
│   ├── README.md                字段契约 + 用法
│   └── contracts/
│       ├── contracts_search_by_no.yml              按编号搜索（P0/smoke）
│       ├── contracts_create_bu_a.yml                新建合同（客户走弹层选择）
│       ├── contracts_create_and_filter_by_customer.yml  新建（弹层选客户）→ 客户右模糊筛选
│       └── contracts_cross_page.yml                跨页流程（列表↔详情，含「同一条记录」领域规则）
├── framework/
│   ├── config.py           配置 + LLM 选择 + 目录常量
│   ├── element_map.py      ElementRef / TestStep / ElementMap 数据模型
│   ├── data_driven.py      数据驱动核心：占位符替换/变量池/动态占位符
│   ├── probe.py            ✅ [Playwright] 确定性元素探测
│   ├── explorer.py         🤖 [AI] 语义识别（读场景+probe清单→步骤；失败即报错，不静默降级）
│   ├── case_builder.py     🤖 ElementMap→cases/ai_*.json 转换 + 用例质量校验（防假绿）
│   ├── locator_bridge.py   ✅ [Playwright] 语义→唯一 locator（核心）
│   ├── generator.py        ✅ [Playwright] 按操作类型生成脚本 + 抽离数据
│   ├── runner.py           ✅ [Playwright] ElementMap 场景执行引擎（run_scenario；集成 healer）
│   ├── healer.py           🩹 [自愈] locator 失败再协商 + 业务断言兜底 + 可审 diff
│   ├── scenario.py         🗂 scenarios/*.yml 解析/校验/发现（explore 的输入源，需 PyYAML）
│   ├── browser.py          Chromium 启动参数唯一来源（稳定/一致；实测不降 RSS）
│   ├── limits.py           并发安全闸：按可用内存自动降级 worker 数（防 OOM）
│   ├── retention.py        归档保留：快照各留最近 N 个（cli prune；explore/probe 自动静默执行）
│   └── cli.py              命令行入口（explore/probe/generate/run/all/prune，含资源预检与交付即验证）
├── tools/                  ★ 框架自己的工具（不是被测应用的一部分）
│   ├── pack_release.py          交付打包器：组装 zip + 标准库自检包内产物（不达标不出包）
│   │                            `--with-cassettes` 同时打**独立的录像包**（交付=代码包+录像包两件套）
│   ├── build_html.py            培训页生成器：读源码 → docs/training.html（**版本号单一来源**）
│   └── offline_explore_chain.py 离线一条命令：录像回放识别 → generate → 试跑（无外网机器用，随代码包发）
├── scripts/                ★ generate 产物（生成，可重建）
│   ├── test_cases.py       生成的 pytest 用例
│   ├── conftest.py         浏览器工厂/数据注入/变量池/日志
│   └── datasets/           抽离出的数据（脚本数据分离）
├── output/                 运行时证据：element_maps/（element_map_*.json 档案 + probe_*.json 快照）
│                           · heals/（自愈 diff）· traces/ · verify/（--verify 试跑日志）
│                           （heals/ 与 traces/ 由写入方用到时自建，平时不存在）
├── log/<run_id>/           本次运行的逐用例 .log + report.html + traces/（run-id 隔离）
└── docs/                   ★ 培训文档目录（仓库里唯一的对外文档）
    └── training.html       培训页（由 tools/build_html.py 生成，改代码后重跑即同步）
```

说明：`cases/` 是**你手写的源**；`scripts/` 是 **generate 生成的产物**（脚本+数据分离，可随时重建）；`output/`/`log/` 是运行时痕迹，可清理；
`docs/training.html` 是给新员工看的培训页，**改完代码跑 `python tools/build_html.py` 重新生成**（文档与代码同源，以代码为基准）；
判据（R8）：`python tests/verify_html_sync.py` —— 可复现 + 与代码逐字节一致 + 无畸形 span。

---

## 快速上手（Windows / Linux）

### 1. 安装依赖（核心只需 3 个库）
> ✅ 已实测：**只装 `playwright + python-dotenv + pytest` 就能跑通"手搓用例 → 生成 → 执行"全链路**（场景②不需要 browser-use）。
> `requirements.txt` = 上面 3 个 + 并发/报告用的 `pytest-xdist`/`pytest-html`（共 5 个）。
> 场景① 的 AI 探索需要 `browser-use`；**场景文件（`scenarios/*.yml`）还需要 `PyYAML`** —— 两者都在 `requirements-ai.txt` 里
> （`requirements-ai.txt` 内含 `-r requirements.txt`，装了它就够跑场景①）。

**Windows（PowerShell）**
```powershell
cd hybrid_gui_qa
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt          # 核心三件套
playwright install chromium               # 下载浏览器
# 想用 AI 探索再加：pip install -r requirements-ai.txt
```

**Linux / macOS**
```bash
cd hybrid_gui_qa
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

> 注意：需要 **Python 3.11+**；Windows 下若 `playwright` 安装失败先 `pip install --upgrade pip`。

### 2. 起被测 demo 应用（开一个终端）
```bash
python -m demo.app        # 监听 http://localhost:8000：静态页面 + 数据 API（/api/customers、/api/contracts、/api/reset…）
                          # 列表页与详情页都从它取数；测试会用它做用例间数据复位
# 想用旧 todo 页：DEFAULT_PAGE=todo.html python -m demo.app
```

### 3. 跑整条链路（另开一个终端）
```bash
# 场景② 手搓用例驱动（推荐：先写 cases/*.json 自然语言用例）
python -m framework.cli generate                 # 读 cases → 生成 scripts/(脚本+数据分离)
python -m framework.cli run --workers 2          # pytest 并发执行 + HTML 报告
python -m framework.cli all --workers 2          # probe + generate + run 一条龙
python -m framework.cli run --debug              # 调试开关：有屏幕弹浏览器；没屏幕录视频+逐步截图
python -m framework.cli run --force-workers      # 无视资源预检，强行用请求的并发数
python -m framework.cli run --case search_mixed  # 只跑指定用例（--case 可重复）
python -m framework.cli run --debug --slowmo 500 --case search_mixed   # 调试+放慢，肉眼跟步
python -m framework.cli explore --ai --scenario "…"  # AI 语义识别（内联）→ cases/ai_*.json（默认 --verify 试跑校验）
python -m framework.cli explore --ai --scenario-file scenarios/contracts/contracts_search_by_no.yml  # 单场景文件
python -m framework.cli explore --ai --scenario-dir scenarios/ --tag smoke                          # 目录批量
python -m framework.cli prune --keep 20          # 归档保留：快照各留最近 N 个（--dry-run 预演，不删）
python -m framework.cli --help                   # 总览帮助（子命令一览）
python -m framework.cli run --help               # 单子命令帮助（直接取函数 docstring，与代码同源）
python -m framework.cli --version                # 版本号（读 tools/build_html.py = 版本单一来源）
# 或直接用 pytest 跑生成的用例（未设 HYBRID_RUN_ID 时日志落 log/latest/）：
pytest scripts/test_cases.py -v                  # 串行(无头)
pytest scripts/test_cases.py -n 1 --html=log/latest/report.html
pytest tests/test_cli_flags.py -q                # CLI 参数契约自测（不需要 demo/key，3 秒）
# ① 一类：框架自测（秒级，不需要 demo/key）—— 条数以实跑输出为准，随批次增长
python -m pytest tests/ -q                       # CLI 契约 / UTF-8 / 断言翻译 / 退出码 / 质量闸 / 打包 / 门禁解耦
# ② 二类：端到端特性验证（需要 demo —— 统一入口会自己起停，跑完给汇总表）
bash tests/run_verifications.sh                  # 全部 verify_*.py（内存 <550MB 会如实 SKIP，不硬跑）
bash tests/run_verifications.sh --only slow_target     # 只跑某一个；--list 列出全部
python tests/verify_slow_target.py               # 慢目标闸门：断言 11 种正向 + 负向 15/15 必须 FAILED（防假绿）
python tests/verify_html_sync.py                 # R8 判据：培训页能由代码可复现生成 且 与代码逐字节一致
```

> **CLI 参数契约（2026-09-13 起）：看不懂的参数一律报错 + exit 2，绝不静默忽略。**
> 起因是三个实测问题：`--workres`（`--workers` 拼错）被静默忽略照常跑完并 exit 0；未知子命令只打文档也 exit 0（脚本调用方误判成功）；`_arg_values` 重复定义后者静默覆盖前者。
> 现在的行为：① 未知参数 → `不认识的参数：--workres，是不是想写 --workers ？`；② 参数用错子命令 → `参数 --workers 对 probe 无效（它只用于 run/all）`；③ 缺取值 / 多余位置参数 → 明确报错；④ 已移除参数（如 `--to-cases`）→ 说明替代做法。
> 契约的单一定义处是 `framework/cli.py` 顶部 `FLAG_SPECS` + `CMD_FLAGS`，回归测试在 `tests/test_cli_flags.py`（改 CLI 后顺手跑一次）。

> **调试开关 `--debug`（别名 `--headed`）** —— **布尔开关，默认关**，只在调试时用（也支持显式写法 `--debug true|false`，方便脚本里当配置项）。
> 开了就一句话：**"我要看得见这次执行"** —— 单浏览器、顺序跑、动作放慢（默认 200ms，`--slowmo N` 可改），然后分两种情况，**都不报错**：
> · **有图形显示**（Windows 桌面 / 带 X 的 Linux）→ `headless=False`，**Chromium 窗口弹出来**，看它一步步执行到用例结束；
> · **没有图形显示**（服务器 / CI）→ **不改需求，改成"录下来给你看"**：
>   · 视频 `log/<run_id>/videos/<case_id>.webm`
>   · **逐步截图** `log/<run_id>/shots/<case_id>/01_*.png`（文件名序号=执行顺序，双击就能看"这一步长什么样"）
>   · 交互回放 `playwright show-trace log/<run_id>/traces/<case_id>_trace.zip`
>
> 关着（默认）= 无头并发跑（按内存预检裁并发），**不录像、不截图**（不占磁盘、不拖速度）；不写 `--debug` 时永远不会弹窗，`generate` 探测阶段也永远无头。
>
> ```bash
> python -m framework.cli run --debug                                    # 调试：全部用例（有屏幕就弹窗）
> python -m framework.cli run --debug --case search_mixed                # 只调试一条（--case 可重复）
> python -m framework.cli run --debug --slowmo 500 --case search_mixed   # 再放慢 500ms/动作，肉眼跟步
> python -m framework.cli run --debug false                              # 显式关（脚本里可配）
> ```
> · `--case` 的值就是 `cases/*.json` 里的 `case_id`（如 `search_mixed` / `hand_enter_search` / `cross_page_detail`）；名字对不上 → pytest 退出码 5 + 明确提示；不带 `--case` = 整包跑（当前 16 条；会话级浏览器复用，逐条顺序执行）。
> · **实现要点（两个实测坑，改代码别踩回去）**：
>   ① 调试模式**不能带 `-n`** —— `pytest -n 1` 也会设 `PYTEST_XDIST_WORKER=gw0`，而 conftest 判定"在 worker 里 ⇒ 无头" ⇒ 旧版 `--headed` 因此是**空操作**（实测本机无 DISPLAY 却照样 9 passed；2026-09-11 修复）；
>   ② 录像的 webm **必须等 `context.close()` 之后才落盘**（提前 `save_as` 只拿到几 KB 空壳：实测 4KB → 修后 152KB）。
> · 不用 cli 时的等价环境变量：`HYBRID_HEADED=1`（有头）/ `HYBRID_VIDEO=1 HYBRID_SHOTS=1`（录像+逐步截图）/ `HYBRID_SLOWMO=500`（放慢）——
>   例：`HYBRID_HEADED=1 HYBRID_SLOWMO=500 pytest scripts/test_cases.py -k test_search_mixed`（**不加 `-n`**）。
> · 服务器没屏幕又非要用 xvfb 跑"有头"：`xvfb-run -a … --debug` 能跑通，但 xvfb 是**虚拟显示、肉眼看不到窗口** → 这种场景更推荐上面的**录制模式**。

#### 资源预检（低内存保命机制）★

`run` 在启动 pytest 前会先读 `/proc/meminfo` 的 `MemAvailable`，按公式
`cap = max(1, min((MemAvailable - 保留) / 每worker预算, CPU核数))` 裁定并发数，
不够就**自动降级并打印理由**，避免"起 2 个浏览器把机器打爆"。

**并发还有第二道闸（2026-09-14 加）**：内存够不等于能并发 —— 还要看**被测服务是否按 worker 隔离数据**。
`cli run` 会探测目标 `/api/health` 的 `partitioned` 声明：
- 声明支持（本项目 demo 支持）→ 保持并发，框架给每个 worker 注入独立数据分区；
- 未声明 / 不支持 → **保守降级为 1**，并打印原因（多 worker 共享一份状态时，精确计数断言会随机红，
  而且失败原因会指向错误的地方 —— 这比"跑得慢"危险得多）；
- 确知目标已隔离：`--isolated-target`（或 `HYBRID_ISOLATED_TARGET=1`）显式放行。

实测教训（2026-09-11，本机 1.87GB / 无 swap）：强跑 `--workers 2` 触发内核 **global OOM**，
被杀的除了 Chromium 渲染进程（表现为 `Locator.click: Target crashed`），
**还有 Hermes 网关进程**。单 worker 则可稳定全绿通过（当前用例集 16 条）。

| 环境变量 | 默认 | 说明 |
|---|---|---|
| `HYBRID_MB_PER_WORKER` | `550` | 每 worker 内存预算（实测 Chromium 实例上界 ≈515MB，取保守值） |
| `HYBRID_RESERVE_MB` | `450` | 留给 Hermes 网关 + OS 的余量 |
| `HYBRID_JS_HEAP_MB` | 未设 | 限制渲染进程 V8 堆上限（**默认不开**，重业务页压狠了会把 tab 顶崩） |
| `HYBRID_RUN_ID` | 由 cli 自动生成 | 本次运行的日志目录名（`log/<run_id>/`） |
| `HYBRID_RESET_URL` | `http://localhost:8000/api/reset` | **用例间数据复位**（每用例前 POST 一次）；`off`/`0`/空 = 不复位 |
| `HYBRID_CASE_TIMEOUT` | `120` | **用例级看门狗**（秒）：超时把调用栈写进 `log/<run_id>/watchdog.txt` 并退出；`0`/`off` = 关掉 |
| `HYBRID_BASE_URL` | 未设 | **目标地址覆盖**：同一套用例可跑本机 / 慢代理 / 预发（生成脚本里的 goto 走 `_goto()`，自动替换 scheme+host） |
| `HYBRID_WAIT_READY` | `1` | **就绪等待开关**：`0` = 回滚到「goto 后不等就绪」的旧行为（排查用） |
| `HYBRID_READY_TIMEOUT` | `15000` | 等页面就绪的上限（毫秒） |
| `HYBRID_READY_SELECTOR` | 未设 | 被测页面没有就绪契约时，用这个选择器当「数据已就绪」信号 |
| `HYBRID_READY_REQUIRED` | `0` | `1` = 就绪超时直接失败（CI 想要「页面必须就绪」语义时用；默认只告警） |
| `HYBRID_LOCATE_TIMEOUT` | `5000` | **定位有界等待**（毫秒）：主定位等待「元素 attached」的上限，超时才降级语义兜底/自愈 |
| `HYBRID_PARTITION` | worker 名 | 手动指定数据分区（默认取 `PYTEST_XDIST_WORKER`；同一分区内数据共享） |
| `HYBRID_ISOLATED_TARGET` | `0` | `1` = 显式声明「目标已按 worker 隔离」，放行并发（等价 `--isolated-target`） |

> ⚠️ 诚实说明：Chromium 启动参数（`framework/browser.py`）实测**并不降低 RSS**
> （裸参与全参数版本同为 513~516MB，在噪声内）；它解决的是稳定性与一致性。
> **真正保命的是并发降级**。预算是启发式，确有把握时可用 `--force-workers` 覆盖。

> **运行产物**：每次运行的逐用例日志与报告落在 `log/<run_id>/`（如 `log/20260911_170224/`），
> 内含「每条用例一个 `<case_id>.log`」+ `report.html` + `traces/<case_id>_trace.zip`（数量随 `cases/` 变化，当前 16 条）；**重跑生成新目录，历史运行不被覆盖**。
> 另外：每条用例开始处会打印 `[setup] 数据复位 … → HTTP 200`（用例间隔离，见上文「2026-09-14 变更要点」）；
> 用例若卡死，看门狗会把调用栈写进 `log/<run_id>/watchdog.txt`。
> trace 按用例分文件命名（原先固定 `latest_trace.zip` 会被后一个用例覆盖，导致只有最后一个用例的轨迹留下）。

### 4. 配置 DeepSeek key（跑「探索式：AI 语义识别」必做）

`python -m framework.cli explore --ai`（和 `ai_explore`）需要真实 LLM 才能做**语义识别**——
DeepSeek 是 OpenAI 兼容接口，最省事（国内直连快、便宜，本框架已实测打通）。

**① 申请 key（1 分钟）**
> 去 https://platform.deepseek.com 登录 → 点「API Keys」→「创建 API Key」→ 复制那串 `sk-xxx`。

**② 配置 `.env`（在项目根目录 `hybrid_gui_qa/` 下创建 `.env`）**
> 直接复制下面内容，把 `sk-你的deepseek密钥` 换成你的：
```bash
DEEPSEEK_API_KEY=sk-你的deepseek密钥
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-chat
```
> `config.py` 会自动读这些变量。也可以把 `.env.example` 复制成 `.env` 再改。
> 注意：`config.py` 用 **browser-use 0.13.10 原生 `ChatDeepSeek`**（OpenAI 兼容、走 function calling），
> `base_url` 需带 `/v1`（DeepSeek 官方接口路径）。

**③ 验证 key 通了没（可选、快速）**
```bash
python -c "from framework.config import llm_from_env, auto_detect_llm; print('LLM可用:', auto_detect_llm())"
```
打印 `LLM可用: True` 即配置成功。

**④ 跑探索式 AI 语义识别**（`explore --ai`，需 DeepSeek key）
```bash
python -m demo.app                          # 终端1：起被测合同页(8000)
python -m framework.cli explore --ai --scenario "在合同列表页面的搜索框输入'1005'，点击搜索按钮，确认出现 HT-1005"
                                                # 终端2：读自然语言场景 → 语义识别 → ElementMap + cases/ai_*.json
                                                #   默认 --verify：落盘后立刻试跑该用例，实测不过 → ❌ + exit 3
python -m framework.cli prune --keep 20         # 归档保留：快照各留最近 N 个（--dry-run 预演，不删）
python -m framework.cli all --workers 2     # 终端2'：数据驱动主链路(确定性,无需key)
```

> 用例驱动的主链路（probe→generate→run）默认确定性、无需 key；DeepSeek key 仅当用
> `explorer.ai_explore`（`cli explore --ai`）做**自然语言→语义识别**时才需要。
>
> **AI 的防线（层层加码）**：
> - **①语义校准**（explorer `_apply_semantic_calibration`）：AI 挑完元素后，用其 desc 与元素语义
>   做**字符级核心词重叠**，相似度 <0.3 打警告"疑似选错控件"（不硬拦，交人工/Tier 兜底）。
> - **②Tier1 意图复验**（locator_bridge `_intent_verify`）：Tier1 命唯一后回读元素实际语义，
>   与 `page_hint/semantic_name` 比对（阈值 0.15），不符 → 降级到下一 Tier1 策略 / Tier2。
> - **③交付即验证**（`explore --verify`，**默认开**）：AI 用例落盘后立刻 `generate + pytest 单跑`，
>   实测 `PASSED` 才算出活；`FAILED` → 打印 ❌ 并 **exit 3**（校验日志 `output/verify/`）。`--no-verify` 可跳过。
> - **④防假 AI 产物**：LLM 不可用时 **exit 2 直接拒绝**，绝不静默用 mock 冒充（`--mock-fallback` 才显式降级且不入库）；
>   落盘前 `case_builder` 还拦「断言=输入回显」「断言=运行时计数（共 N 条）」。
> - **⑤上游抖动重试**：DeepSeek 的 function calling 有**间歇性 JSON 抖动**（实测同 prompt 第 1 次成功、
>   第 2 次 `ModelProviderError: Extra data: line 1 column 550`）→ 内置退避重试，`HYBRID_LLM_ATTEMPTS` 默认 3；
>   顺带修了文本兜底路径的 async bug（原 `_get_llm_text` 用 `asyncio.run`，在事件循环里必 RuntimeError → 兜底是死代码）。
>
> **DOM 上下文增强**：`ai_explore` 会用 Playwright 抓**完整版 DOM 上下文**（元素全局索引/可见性/
> 状态/可访问名）喂给 planner prompt，让 AI 更准地判别"该选哪个控件"。
> ⚠️ 注意实现细节：**探测必须在事件循环之外做**（Playwright Sync API 不能跑在 asyncio loop 里）。
> 2026-09-11 修了一个隐藏很久的 bug：探测被写在 async 函数内 ⇒ 必然抛错 → 被静默兜底成"只有基础控件"，
> 于是"弹窗字段补充"和"DOM 上下文"一直是**死代码**。现在拆成「同步探测 → 异步 LLM 规划」两段。

### 5. 用场景文件（推荐：把场景当资产沉淀）
场景放 `scenarios/`，**一个 YAML 文件 = 一个场景**，字段按"谁读它"分组（人 / 框架 / AI / 质量闸 / 数据），
**只有 `scenario`（自然语言动作流）必填**——内联 `--scenario "…"` 就等价于"只给 scenario 字段"，两条路共用同一套下游：
```bash
python -m framework.cli explore --ai --scenario-file scenarios/contracts/contracts_search_by_no.yml
python -m framework.cli explore --ai --scenario-dir scenarios/ --tag smoke --limit 5
```
- 三种入口**互斥**（`--scenario` / `--scenario-file` / `--scenario-dir`），同时给 → 报错退出（不猜）；
- 关键增量字段：`business_context`（领域知识喂 AI）、`assert_guard.must_contain / forbidden`
  （**事前约束 AI + 事后落盘硬校验**，把"断言必须操作前可确定"从通用规则升级为每场景硬约束）、`tags`/`priority`（批量筛排）；
- 产物可溯源：用例名 `ai_<scenario_id>_<HHMMSS>.json`，并回写 `scenario_id` / `source_scenario` 字段；
- 详细字段表与设计逻辑见 `scenarios/README.md` 和 `docs/P2-scenario文件设计.md`。

> ⚠️ **Windows 注意**：
> - `.env` 文件里 `DEEPSEEK_API_KEY` 的值不要有空格/引号，直接 `key=sk-xxx`。
> - `config.py` 已用 **browser-use 0.13.10 原生 `ChatDeepSeek`**（走 function calling 拿结构化输出，
>   兼容 DeepSeek），无需再手动 `dont_force_structured_output`。
> - DeepSeek 不支持视觉(vision)，`ai_explore` 已自动 `use_vision=False`。

分步执行：
```bash
python -m framework.cli probe        # 1) 探测页面交互元素
python -m framework.cli generate     # 2) 读 cases → 生成 scripts/(脚本+数据抽离分离)
python -m framework.cli run --workers 2   # 3) pytest 并发执行 + HTML 报告
```

### 6. 写一个用例（cases/*.json）—— 自然语言描述，写死数据

在 `cases/` 下新建 `case_id.json`，步骤用 `op`(操作类型) + `desc`(自然语言) + `element`(探测语义名)
+ `value`(写死测试数据)，断言用 `asserts[]`。字段值可含 `{datetime}` 等动态占位符（重跑不重名）：

```json
{
  "case_id": "search_name_fuzzy",
  "name": "按合同名称模糊搜索",
  "base_url": "http://localhost:8000",
  "steps": [
    {"op": "goto",  "desc": "打开合同列表页", "url": "http://localhost:8000"},
    {"op": "fill",  "desc": "在搜索框输入关键字'合同1'", "element": "合同编号_名称_管理单元_合同类型_帐套", "value": "合同1"},
    {"op": "click", "desc": "点击搜索按钮", "element": "搜索"}
  ],
  "asserts": [{"desc": "断言页面出现搜索结果", "expect": "搜索完成"}]
}
```

> 断言默认是**文本断言**（`kind` 省略 = `text`）。要验「弹窗开合/结果行数/属性/输入框值/URL/勾选/禁用」时，
> 给该条断言加 `kind`，并用 `element`（探测语义名）或 `selector`（手写用例专用的 CSS，如 `#modal-new`）指定目标：
>
> ```json
> "asserts": [
>   {"kind": "count",   "selector": "#tbody-contracts tr", "expect": 1, "desc": "搜索结果恰好 1 行"},
>   {"kind": "visible", "selector": "#modal-new", "desc": "弹窗已打开"},
>   {"kind": "value",   "element": "合同编号_名称_管理单元_合同类型_帐套", "expect": "", "desc": "重置后输入框被清空"},
>   {"kind": "disabled","selector": "[data-testid='btn-export']", "desc": "导出按钮未接入"}
> ]
> ```
>
> 现成例子见 `cases/assert_kinds_*.json`；11 种 kind 的字段契约见上文「断言类型」表。

- `op`：goto / click / fill / select / check / press_enter（操作类型→Playwright 代码由 generator 翻译）
- `element`：用 `probe` 探测出的**语义名**（跑一次 `python -m framework.cli probe` 查看），generate 时映射成确定性 locator
- `value` / `expect`：写死值 → generate 抽离到 `scripts/datasets/<case_id>.json`（脚本数据分离）

---

## 关键技术要点（业界最佳实践提炼）

### 1. Locator 稳定性优先级（自愈的基石）
只能做**绑定到用户可见语义**的定位，绝不能绑到脆弱的 DOM 结构。优先级：

```
get_by_test_id > get_by_role(role, name) > get_by_label > get_by_placeholder
    > get_by_text > 上下文锚点(nearby_text/heading) > CSS/XPath（几乎不用）
```
> 注：实现里 **`data-testid` 置顶**（团队契约锚点，最抗改版）；这条顺序与 `generator._semantic_to_locator_expr`
> 和 `locator_bridge` 的 Tier1 一致。

### 2. 防 "false heal"（自愈最大的坑）
一个自愈/生成逻辑如果"点了错的 Delete/Save 按钮还报绿"，就是假信心。
所以我们强制**唯一性校验**：每个候选 locator 在真实页面 `count()==1` 才接受；
`count>1`（歧义）→ 降级到更稳策略；`count==0` → 元素不存在、跳过；
全部失败 → 诚实报错，**绝不返回一个可能点错的 locator**。

### 3. AI 永远不输出 selector
（口径澄清：browser-use 的 **Agent** 走"索引化 DOM"；本框架**不用它的 Agent**——Agent 对 DeepSeek 有 input_text schema bug——只用它的 **LLM 层** `ChatDeepSeek` 做语义识别/编排，绕开 Agent 的强 schema。）
Browser Use 侧**不产 CSS selector**，也不该产。
本框架里 AI 只**引用 probe 探测出的语义**（`semantic_name`），真正 locator 由
`locator_bridge`（确定性）生成。杜绝 LLM 写 `#mui-4821` 这类每次构建都变的 ID。

### 4. 两阶段数据契约（ElementMap）
AI（探索）和 Playwright（执行）之间用一份结构化的 `ElementMap` 传递：
步骤序列（action）+ 目标元素的**语义**（role/name/...）。这样换模型、换页面都不改执行器。

### 5. 因果分层：token 成本可控
AI 只在**探索/规划**时花钱（每步一次模型推理）；一旦生成测试脚本，
回归执行 100% 确定性、零 token 成本、可进 CI 无限次跑。

---

## 扩展方向（留给你的钩子）

- **接入 Playwright Test Agents**（Playwright v1.56+）：用本框架的 explore 替代其 Planner，
  生成器对齐 Generator 的产物规范，runner 对齐 Healer 的失败诊断。
- **自愈闭环**：runner 失败时抓 DOM 快照 → LLM 猜新 locator → 校验唯一性 → 人工审 PR。
- **多 provider**：Browser Use 支持 OpenAI/Anthropic/Google，换模型不改架构。
- **准入控制**：把 probe 探出的元素清单做版本化，做 selector 漂移监控。

---

## 一句话总结

> **Browser Use 负责"迈出第一步"——理解要测什么；Playwright 负责"走稳每一步"——
> 精确、可复现、可回归。** 两者靠一份 ElementMap 契约无缝衔接。

---

## 许可 / License

**MIT License** —— 见 [`LICENSE`](LICENSE)。

```
Copyright (c) 2026 AprilPark1012
```

可自由使用、修改、分发（含商用），保留版权与许可声明即可。
