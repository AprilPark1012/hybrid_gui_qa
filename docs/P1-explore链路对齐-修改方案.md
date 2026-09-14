# explore → generate → run 链路对齐方案（审计 + 修改计划）

> 状态：**待你确认**（本文只做审计与方案，**未改任何代码**）
> 基线：v6 + P0 资源安全改动（2026-09-11 17:2x）
> 审计方式：**真跑一遍**收集证据（explore/generate/run 各跑 1 次 + 漂移 A/B 实验），非纸面推断
> 作者：AprilPark1012 · 2026-09-11

---

## 0. 结论速览（对照你的 3 条要求）

| 要求 | 判定 | 一句话 |
|---|---|---|
| **1** explore：自然语言 → LLM 语义识别 → probe 识别控件 → 生成 element.map → **browser-use 编排** → 生成用例 → **输出到 cases/** | ⚠️ 部分达标 | LLM 识别 ✅、probe 控件 ✅、ElementMap ✅；**但落盘在 `output/element_maps/` 不是 `cases/`**；且**不是 browser-use Agent 编排**，是 `browser_use.llm.ChatDeepSeek` 直连（当年有意绕开的"方案C"） |
| **2** generate：读**上面生成的**用例 + 用 probe 的 element.map → 生成 Playwright 脚本 + 数据脚本分离（数据驱动） | ⚠️ 部分达标 | 数据驱动/脚本数据分离 ✅（实测 5 用例 + 5 datasets）；**但它读的是手写 `cases/*.json`，不读 explore 的产物**，也**不消费 element.map**（自己现场重新 probe） |
| **3** run：读脚本 → pytest 并发 → HTML 报告（含**脚本运行自愈**） | ⚠️ 部分达标 | 并发 ✅、HTML 报告 ✅、资源预检 ✅；**但生成的脚本是内联死 locator，零自愈**——漂移实验里 30s 超时硬失败 |

**一句话总纲**：现在有"两条腿"——**AI 腿**（explore→ElementMap→runner，有分层定位+自愈）和**确定性腿**（cases→generate→run，零 token 可进 CI，但无自愈）；你要的是一条**贯通的三段式**：explore 产出用例落 `cases/` → generate 消费 element.map → run 跑脚本且带自愈。**缺的正是两腿之间的桥**。

---

## 1. 实测证据（本次真跑，可复现）

### 1.1 第 1 步 explore（真调 DeepSeek）

命令：`python -m framework.cli explore --ai --scenario "在合同列表页面的搜索框输入'合同1'，然后点击搜索按钮查看结果。"`

```
[explore] 生成 ElementMap: 4 步
  - 1. goto      → (无)                              | http://localhost:8000 | 打开合同列表页面
  - 2. fill      → 合同编号_名称_管理单元_合同类型_帐套  | 合同1                  | 在关键字搜索框输入'合同1'
  - 3. click     → 搜索                               |                        | 点击搜索按钮触发查询
  - 4. expect_text → 搜索                             | 合同1                  | 断言搜索结果中包含'合同1'
          → output/element_maps/element_map_20260911_172514.json
```

- ✅ LLM 语义识别成功：控件挑得准（`tb-keyword` 文本框、`btn-search` 搜索按钮，与 probe 清单一致）
- ❌ **落盘位置是 `output/element_maps/`，`cases/` 目录无任何新增**（`diff` 实证：cases/ 无变化）
- ⚠️ **AI 语义质量瑕疵（重要，会导致"假绿"）**：第 4 步 `expect_text` 的 `element` 被 AI 选成了「搜索」按钮（断言步本不该带元素），
  断言值 `合同1` 其实**就是第 2 步输入框里填的值** → 断言实际在验"输入回显"，而非"搜索结果正确"。
  该 ElementMap 跑起来会"通过"（实测见 1.3），**但验证的是错的东西**。

### 1.2 第 2 步 generate

命令：`python -m framework.cli generate`

```
[generate] 读 cases/ → 生成 5 个用例到 scripts/:
          datasets: 5 个（脚本数据分离）
```

- ✅ 数据驱动达标：脚本 `scripts/test_cases.py` + 数据抽离 `scripts/datasets/<case_id>.json`（实测 5 对）
- ❌ **读的是手写 cases（5 个固定文件，mtime 9-04）**，与刚才 explore 的产物**无任何关系**
- ❌ **不消费 element.map**：`generator.generate_scripts()` 在 148~180 行**自己现场 probe 一次**拿 locator；
  全文件仅在 conftest 模板里 import `ElementRef` 类，**没有任何读取 `output/element_maps/*.json` 的代码**（grep 实证）

### 1.3 第 3 步 run

命令：`python -m framework.cli run --workers 2`

```
[gw0] PASSED ... test_create_bu_a_c1 / test_create_bu_b_c2 / test_search_customer_dropdown
      / test_search_mixed / test_search_name_fuzzy
- Generated html report: file:///home/admin/hybrid_gui_qa/log/20260911_172542/report.html -
============================== 5 passed in 6.32s ===============================
[run] 资源预检: MemAvailable=631MB ... 安全并发=1; 请求 2 → 降级 1
```

- ✅ pytest 并发（xdist）+ HTML 报告 + run-id 隔离目录 ✅ 资源预检自动降级 ✅
- ❌ **"脚本运行自愈"不存在**：见下方漂移实验

### 1.4 漂移 A/B 实验（关键证据：自愈只在一条腿上）

做法：把 `demo/contracts.html` 的 `data-testid="btn-search"` 改成 `btn-search-x`（制造 selector 漂移），
两条路径各跑一次，**做完立刻还原**（sha256 `596b293e…c0582b` 前后一致，已验证还原）。

| 路径 | 结果 | 说明 |
|---|---|---|
| **脚本路径**（`pytest scripts/test_cases.py -k search_mixed`） | ❌ **硬失败**：`Locator.click: Timeout 30000ms exceeded` | 全程**零自愈**、无 heal 记录；白等 30s。因为生成脚本是内联死 locator：`page.get_by_test_id("btn-search").click()` |
| **ElementMap 路径**（`run_scenario` 跑同一场景） | ✅ **自动降级并跑通**：`click → 搜索 [role+name exact conf=0.93]` | Tier1 `test_id` 失效后自动降级到 `role+name` 语义策略 |

**结论**：分层定位（Tier1/Tier2/意图复验）与 Healer 自愈**只存在于 ElementMap 路径**（`runner.py` + `locator_bridge.py`）；
生成的脚本路径**完全没有接入**。代码实证：`scripts/conftest.py` 里虽有 `_loc()`（走 `resolve_locator`），
但生成的 `test_cases.py` **完全不调用它**（grep 零命中），且 `_loc` 本身也**没接 healer**。

---

## 2. 差距清单（逐条对标）

| # | 你的要求 | 现状 | 差距性质 |
|---|---|---|---|
| G1 | explore 用例**输出到 cases/** | 只落 `output/element_maps/*.json`（ElementMap 格式） | **缺功能**：需要一个 ElementMap → cases 用例的转换器 + 落盘命令 |
| G2 | explore **用 browser-use 编排步骤** | 用 `browser_use.llm.ChatDeepSeek` 直连 `ainvoke(output_format=…)`（explorer.py:166-176） | **口径问题**（也是当年有意取舍）：真 Agent 因 `input_text` schema bug 在 DeepSeek 下不可用 |
| G3 | generate **读上面生成的用例** | 只读手写 `cases/*.json` | 依赖 G1（有了 G1 自然满足） |
| G4 | generate **用 probe 生成的 element.map** | 自己现场重新 probe，不读 map 文件 | **缺功能**：改为优先读 map（可指定/可回退现场 probe） |
| G5 | run **脚本运行自愈** | 生成脚本内联死 locator，零自愈 | **缺功能**：把 `_loc`+Healer 接进生成脚本（带防 false-heal 兜底） |
| G6 | AI 用例语义质量（隐含） | `expect_text` 带错 element、断言值取自输入值 | **质量问题**：会"假绿"，需 prompt 约束 + 落盘校验 |
| G7 | 文档一致性 | explorer docstring:7 写"走 Browser Use Agent + LLM"，与实现不符 | 文档漂移（低成本） |

---

## 3. 修改方案（分 A–F 六项，逐项可独立实施/回滚）

### A. explore 产出直接落 `cases/`（解决 G1、G3）★核心
- **做法**：新增 `framework/case_builder.py`
  - `elementmap_to_case(m: ElementMap, case_id: str) -> dict`：ElementMap → cases 用例结构
    - `name` ← `m.scenario`；`base_url` ← `m.url`
    - `steps[]`：`action` 直接映射 `op`（goto/fill/click/select/check/press_enter 同名）
      - `element` ← `step.element.semantic_name`；`value` ← `step.value`；`desc` ← `step.description`
      - **`expect_text` 步骤不产出 step，转成 `asserts[]`**（`{"desc": description, "expect": assertion}`）——顺带修掉 G6 的一半
  - `write_case(case: dict, cases_dir) -> Path`：写 `cases/<case_id>.json`
- **落点**：`framework/cli.py::cmd_explore` 增加 `--to-cases`（默认**开**，可 `--no-cases` 关；ElementMap 仍照旧存 `output/element_maps/` 作档案）
- **case_id 命名**：`ai_<场景slug>_<HHMMSS>`（**加 `ai_` 前缀**避免与手写用例混淆，见 Q2）
- **风险**：反复 explore 会让 `cases/` 堆积 AI 用例，且 generate 会把它们一起生成 → 见 Q2 的隔离策略；**回滚**：`--no-cases` 或删 `cases/ai_*`

### B. "用 browser-use 编排"的口径（解决 G2，**需你拍板**）
三个选项：
- **B1（推荐）保留 LLM 直连，但把文档/命名讲准**：编排能力等价（都是 LLM 读场景+控件清单产步骤），
  且绕开了 browser-use Agent 对 DeepSeek 的 `input_text` schema bug（skill 里已实测记录：0.13.8/0.13.10 未修）。
  成本：改文档 + 在 explore 输出里标注 provider；**0 代码风险**
- **B2 真上 browser-use Agent**：需换模型（OpenAI/Anthropic/Google）或等上游修 bug。
  成本高，且你现有 key 是 DeepSeek → **不推荐**
- **B3 折中**：直连 LLM，但把步骤 schema 换成 browser-use 风格的 `ActionModel`（自建精简版），
  接口语义更贴 browser-use；成本中（要重写 explorer 的 schema 与解析）
- **建议**：B1（如你坚持"必须真用 Agent"，告诉我，我按 B2 出子方案并列出前置条件）

### C. generate 消费 element.map（解决 G4）★核心
- **做法**：`generator.generate_scripts()` 增加 `element_map_path: Path | None = None` 参数
  - 优先：读指定/最新的 `output/element_maps/element_map_*.json` → 用其中的 `ElementRef`（含 role/name/placeholder/test_id/nearby_text）
    生成 locator 表达式（复用现有 `_semantic_to_locator_expr`）
  - 回退：map 缺元素或文件不存在 → **现场 probe 补齐**（保现状能力，不破坏老流程）
- **落点**：`framework/generator.py`（`generate_scripts` + `cli.cmd_generate` 加 `--element-map <path>` / `--latest-map`）
- **风险**：map 过期（页面已变）导致定位错 → 缓解：`--refresh-probe` 强制现场；或在生成时**校验 map 元素与现场 probe 是否一致并打警告**（不静默）
- **回滚**：不传 `--element-map` 即回现状

### D. 把自愈接进生成脚本（解决 G5）★核心 + **需你拍板**
- **现状根因**：生成器把 locator **内联成死字符串**（`page.get_by_test_id("btn-search")`），
  绕过了 `locator_bridge` 的分层定位与 `healer`
- **做法（D1，推荐）**：
  1. 生成脚本改为调用 conftest 的 `_loc(semantic_name, page)`（而非内联死 locator）→ 走 `resolve_locator` 分层策略（Tier1 多策略 → Tier2 指纹 → 意图复验）
  2. conftest 的 `_loc` **接入 Healer**：`resolve_locator` 失败时 `healer.try_heal()`；
     **业务后置断言兜底**（不通过 → 判真 bug、拒用自愈结果，不掩盖回归）；heal 落盘 `output/heals/` 可审 diff
  3. **性能优化（必须，否则并发不稳）**：不要每个动作都 `probe_page` 全页（skill 已记坑：并发下页面不稳会超时）
     → 改为**会话启动时 probe 一次建 `semantic_name → locator` 索引缓存**，运行时用缓存；仅在缓存未命中/定位失败时才重新 probe
  4. **开关**：`HYBRID_SELF_HEAL=0/1`（建议默认 **1**；CI 可关成"失败即报"，见 Q1）
- **收益**：漂移实验里"30s 超时硬失败"会变成"自动降级到 role+name 并跑通"（与 ElementMap 路径同等待遇）
- **风险**：false heal（点错元素）→ 靠"唯一命中 + 意图复验 + 业务断言兜底 + diff 可审"四道闸；
  **回滚**：`HYBRID_SELF_HEAL=0` 或把生成器切回内联模式（保留 `--inline-locator` 开关）

### E. AI 用例语义质量防"假绿"（解决 G6）
- **做法**：
  1. prompt 约束（`explorer.ai_explore`）：`expect_text` 步**禁止**填 `element`；`assertion` 必须是**验证结果的文本**，不得与任何 `fill.value` 相同
  2. 落盘校验（`case_builder`）：若 `assertion` 与某步 `value` 完全相同 → 打警告 `疑似断言输入回显，可能假绿`
  3. 兼容：老用例不受影响
- **收益**：避免"看着通过、其实没验到东西"

### F. 文档/培训页同步（解决 G7）
- `explorer.py` docstring:7 由"走 Browser Use Agent + LLM"改为"用 browser_use.llm 的 ChatDeepSeek 直连编排（方案C，绕开 Agent 的 DeepSeek schema bug）"
- README / build_html.py / training.html / skill 同步新链路（explore --to-cases → generate --element-map → run 自愈）

---

## 4. 改完后的验证清单（我会逐条跑给你看）

| # | 验证 | 期望 |
|---|---|---|
| 1 | `cli explore --ai --scenario "..."` | 同时产出 `output/element_maps/*.json` **和** `cases/ai_*.json` |
| 2 | `cli generate`（默认） | **只用** `cases/ai_*.json` 就能生成脚本；数据抽离正常 |
| 3 | `cli generate --element-map output/element_maps/element_map_*.json` | 按 map 映射 locator（日志标注"来源=element_map"）；map 缺元素时回退现场 probe |
| 4 | `cli run --workers 2` | 5 passed + `log/<run_id>/report.html`；资源预检降级 |
| 5 | **漂移 A/B 复测**（改 testid 再还原） | 脚本路径**应能自愈**（降级 role+name 并跑通），并产出 heal diff；还原后 sha256 校验一致 |
| 6 | `HYBRID_SELF_HEAL=0` 漂移复测 | 应恢复"失败即报、不自愈"（CI 语义） |
| 7 | 假绿校验 | 构造 assertion==value 的用例 → 落盘时出现"疑似假绿"警告 |
| 8 | 回归 | 手写 5 用例仍 5/5 通过（不被改造破坏） |

---

## 5. 待你拍板（4 个问题）

| # | 问题 | 我的建议 |
|---|---|---|
| **Q1** | 自愈默认**开**还是**关**？（CI 里通常希望"失败即报、别自愈掩盖"） | 默认**开**，`HYBRID_SELF_HEAL=0` 可关；CI 场景建议显式关 |
| **Q2** | AI 用例落 `cases/` 的隔离方式：① `cases/ai_*.json` 前缀 ② 子目录 `cases/ai/` ③ 不加前缀直接混放 | ① **前缀**（generate 可一眼分辨，AI 用例可批量清理；不会误删手写用例） |
| **Q3** | "用 browser-use 编排"是否**必须真用 Agent**？ | 建议接受 **B1**（LLM 直连编排，能力等价 + 绕开已知 bug）；要坚持真 Agent 我按 B2 出前置条件 |
| **Q4** | 接入自愈后，heal diff 是否**保留人工复核**环节？ | 建议**保留**（自愈只修 locator 漂移，业务断言不过仍判真 bug、绝不静默改写） |

---

## 6. 优先级与工作量

| 优先级 | 内容 | 预估 | 解决的差距 |
|---|---|---|---|
| **P0** | A（转换器 + 落 cases/）+ C（generate 消费 map） | 60~80 min | G1/G3/G4（Req1 字面 + Req2 字面） |
| **P1** | D（自愈接入生成脚本，含缓存优化 + 开关） | 90~120 min | G5（Req3 的"自愈"实质） |
| **P2** | E（防假绿）+ F（文档同步） | 40 min | G6/G7 |
| **P3** | B（口径确认/改造，视 Q3） | 0~180 min | G2 |

**建议**：先做 P0（能立刻满足你 Req1 的"输出到 cases/"和 Req2 的"用 element.map"），
验收通过后再做 P1 的自愈（这块改动最大、风险最高，建议单独一轮验证）。
