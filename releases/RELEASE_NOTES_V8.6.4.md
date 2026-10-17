# V8.6.4 发行说明（2026-10-17）

> 上游路径：`releases/RELEASE_NOTES_V8.6.4.md`（交付时随代码包一并发出）

## 一句话

**合并重复判据（两批做完 5 组）—— 同一件事不再由两条判据分守：删 16 条重复/假绿、把 5 个文件合成 2 个（另 2 个改名）、补 3 条更强的新判据。**

## 缘起

V8.6.3（2026-10-16）做「以代码实现为基准的大扫除」时，审计同时发现 **5 组重复判据**
（同一件事被两条判据分别守着），并**明确登记为待办**、留到本版处理。

为什么要单独成版、而不是顺手删掉：**重复判据 = 一处改两处验** ——
改了一处，另一处**静默漂移**（不报错、只是判断悄悄变了）；
更坏的一种是它**永远绿**：看着在守，实际什么都没验（给假信心比没有判据更危险）。

本版**分两批把 5 组全部做完**（第一批 `wait_text` 渲染契约三合一 / 三个闸门 / 两档重试；
第二批 跨轮反馈通道 / 同因不重试遗留 / 用例场景来源三合一），
分两批是为了让 diff 可审、回归可归因（一次只改一类事）。

合并的三条硬口径（本版的判据）：

1. **留下的那条必须更强** —— 走**公开出口**、能**区分两种坏法**，不是"删一条凑数"；
2. **每条被删的判据都要写清由谁接手** —— 不许出现"保护真空"（见下面那张接手表）；
3. **全量判据一条都不许红** —— 合并会降总数，属预期；红一条就是回归。

## 怎么用

**对使用者：零影响、无需改配置。**

本版**没有新增能力、也没有行为变更** —— 改的全是 `tests/` 里的判据、判据登记、生成器与文档。
你照旧跑：

```bash
python -m framework.cli all --ai --scenario-file <场景.yml>   # 参数与上一版完全一致
```

> 唯一"看得到"的变化：培训页 `docs/training.html` 与 `docs/feature_map.md` 里
> 那几个判据文件名变了（3 个合成 1 个、1 个改名；第二批再 3 个合成 1 个、2 个改名）；
> 全量判据数 **1222 -> 1218**（净 -4 = 第一批 -2 + 第二批 -2）。

## ① 组 5：`wait_text` 渲染契约三合一（3 个文件 -> 1 个）

| 合并前 | 守什么 |
|---|---|
| `test_wait_text_kind.py`（6 条）| kind 在册 / 带超时渲染 / 有界默认超时 / 缺 expect 负向 / 非法超时负向 / 老 kind 回归 |
| `test_wait_text_refresh_policy.py`（3 条）| `refresh` 三态（none / reload / research）/ 缺省不出参数 / 非法值与错类型负向 |
| `test_wait_text_selector.py`（2 条）| `selector` 透传 / 不带 selector 的向后兼容（空 selector）|

合并后 = **`test_wait_text_render_contract.py`（11 条）**。

**为什么合成一条**：三者守的是**同一件事** ——「一条 `wait_text` 断言渲染成生成脚本里的调用行长什么样」，
只是各守其中一个字段。分成三个文件的结果是：改一处要三处验，且渲染入口有**三份 `_render` 副本** ——
其中两份是**手工塞 `_payload_ref`** 的（它们的注释里自己写着"不带它就等于测了个假形态"）。

**改法**：一律走**真管线** `_add_payload_refs(...)` -> `_render_assert(...)`，
期望值由框架自己抽成 `_data('expect_N', ctx)`，与 `generate` 真实链路同口径。

**两个负向合并成一条 parametrize**：`timeout_ms` 一组（负数 / 0 / 非数字 / 浮点）
+ `refresh` 一组（拼错 / 错类型）。合并的唯一依据是**它们共同的前提一样** ——
失败原因必须来自**值非法**，不能来自"kind 还没实现"；所以共同断言
「渲染出 `pytest.fail` 且**不含**『未知断言类型』」（否则两组负向都会恒真 = 假绿）。

**登记落点改齐**：这条判据整体落 **9.6（就绪与等待契约）**，并从 **9.1** 摘掉原来那行 ——
它守的是**渲染契约**，不是布局/命名（9.6 的目标里也写明这一点）。

## ② 组 4：三个闸门**不合并文件**，只做 1 删 + 1 改名

**为什么"不合并"也是结论**：三个闸门文件测的是**三个互不调用的函数**，且
`test_generate_quality_gate.py` 带 autouse 隔离 fixture —— 合并会**改变无关判据的行为**
（那是把"合并重复判据"做成了"重排测试"）。所以分居格局保持不变。

| 动作 | 内容 |
|---|---|
| **删 1 条** | `test_case_quality_gate.py::test_g2_self_invented_url_fragment_is_redline` —— 与同文件的 `test_fabricated_fragment_is_redline_now` 守**同一件事**（自造换页片段 = 红线），但走**私有入口 + 内部常量名**（`_url_evidence_issues` / `REDLINE` / `WARN`）；实现一改名就**假红** |
| **留哪条** | 留走**公开出口** `case_errors()` 的那条 —— 不依赖内部常量名 |
| **改名** | `test_case_quality_gate.py` -> **`test_case_evidence_gate.py`**（名实相符：它守的是**换页证据**那一类，不是整个"用例质量闸"）|

> `test_case_evidence_gate.py:200-207` 的**提示词锁**原样保留（它守的是**根因层**：只修闸门不修提示词 = 每次 AI 跑都撞红线）。

## ③ 组 1：两档重试的重复判据收口（特性2 <-> 特性11）

| 动作 | 内容 | 接手方 |
|---|---|---|
| 删 | 特性11 `test_retry_is_bounded` | 特性2 `test_ai_retry_loop.py` 的 `_ai_retry_limit` 三条 —— **逐条严格覆盖**，且多了**脏值回落**（`"abc"` 不许抛异常、回落 2）与**负值**（`-3` -> 0）|
| 删 | 特性11 `test_replay_mode_does_not_retry`（只查"全文 >= 1 次"）| **换成强判据**（见「新增判据」）；"回放不重试"的行为面仍由特性2 `test_replay_mode_skips_retry` 守着 |
| 删 | 特性2 `test_quality_gate_not_weakened`（**假绿兜底**）| 特性11 `test_verify_failure_exit_codes_are_distinct` |
| 留 | 特性11 `test_verify_failure_exit_codes_are_distinct` | 独有 `SystemExit(3)`（实跑档退出码），无替代 |
| 改 | 特性11 文件 docstring 里**过期文案**：「现状（片 1 基线，本判据**应当红**）」| 今天早已全绿 —— 照旧读会让人以为有坑（R8 文档漂移）|

**那条假绿兜底为什么必须删**：断言写成
`assert "raise SystemExit(2)" in _fn_src(CLI, "_report_case_quality") or "SystemExit(2)" in src`，
而 `src` 取的是**整个 `cli.py`**、`SystemExit(2)` 全文有 **20 处** -> 后半句**恒真**：
前半句（真去 `_report_case_quality` 里找 `exit 2`）坏掉了也**不会红**。

## ④ 组 3：跨轮反馈通道两合一（特性2 内）

**为什么是一条**：两条判据守的是**同一条通道**（`_next_round_feedback` / `_quality_warn_feedback`
-> `_build_planner_prompt(retry_feedback=...)`）的**两端** ——

| 端 | 守什么 | 坏了会怎样 |
|---|---|---|
| 前端 | 上一轮的缺陷记账**不许跨轮残留** | AI 第 2 轮明明补好了，读到的却是第 1 轮旧账 -> 又拦 -> 重试用尽报错（实测白挨两轮）|
| 后端 | 记的账必须**真递给 AI** | 记了不递 = 记账等于白记，AI 连犯三轮同一个错（实测 GLM 两轮就死在同一个点上）|

通道断任一端，**现象完全一样**（AI 反复犯同一个错）—— 所以必须同一条判据守两端。

**合并后 = `test_retry_feedback_contract.py`（13 条）**：

- 保留原 `test_quality_warnings_feed_next_round.py` 的 8 条（回炉文案本身 / 反向自证 /
  硬原因不重复说 / 硬原因与警告共存 / 真的进提示词 / 无反馈时干净 / `cmd_explore` 接线 / WARN 级取用）；
- **迁入 4 条**（原 `test_retry_leaves_no_stale_notes.py`，**一条不丢**，统一加 `test_notes_*` 前缀）：
  行为链（第 1 轮记账 -> 第 2 轮补全 -> notes 为空）· 缩进级源码兜底（`clear()` 必须在
  `_finalize_map` **函数体**里、缩进 == 4）· `SEMANTIC_MISMATCH_NOTES` 有清空点 ·
  `check_required_field_coverage` 报缺失条数；
  模块级状态改由 **autouse fixture** 清空（范式取自 `test_production_defects_gate_l1.py:29-36`）；
- **新增 1 条遍历式判据**（见「新增判据」）。

> 「缩进级源码兜底」这条相比原版**收紧了范围**：原版在全文件里找 `clear()`，本版限定在
> `_finalize_map` **函数体内**（这才是它 docstring 声称守的位置）—— 全容器遍历那条守
> 「每个容器都有一处」这个面，本条守「这两处在正确的位置、正确的层级」这个面。

**两个字段级的细节（都写进了判据的注释里）**：

- **WARN 级取用的前提**：`_ai_gate_warn_entries()` 走 `AiOutputGate().check()`，
  **BLOCK 级非空时整个闸门是 `blocked=True`、连 WARN 都不返回** —— 所以判据里必须
  先清 BLOCK 级（`SEMANTIC_MISMATCH_NOTES`）才谈得上「WARN 级读得出来」。
  这条原本靠 try/finally 顺序隐式成立，现在写成了显式断言 + 注释。
- **合并两条断言取严**（`test_prompt_stays_clean_without_feedback`）：
  `"上一轮" not in flat`（宽口径，任何位置的「上一轮」字样都不许有）
  **+** `"上一轮框架识别出的" not in prompt`（窄但直指回炉段落段首）——
  只留一条都会漏：前者漏「段首改写成别的说法」，后者漏「段首没出现但别处塞了『上一轮』」。

## ⑤ 组 1 遗留：「同因不重试」下放 + 文件改名

| 动作 | 内容 | 接手方 |
|---|---|---|
| 删 | `test_ai_retry_loop.py::test_same_reason_stops_retrying` | 同目录 **`test_ai_retry_same_cause.py`**（5 条）—— 更强：走 `exec` **真函数体**（连 `_retry_reason_fingerprint` 一起 exec）+ **指纹源码断言** |
| 改名 | `test_ai_retry_loop.py` -> **`test_ai_retry_contract.py`** | 它现在守的是「**上限**（默认 2 / 可调 / 脏值回落 / 上界）/ **回炉**（原因进提示词）/ **接线**（`cmd_explore` 真用了）」三条契约，不只是 loop |
| 删 | `test_ai_retry_contract.py::test_prompt_without_feedback_is_clean` | `test_retry_feedback_contract.py::test_prompt_stays_clean_without_feedback`（两组断言**取严**合并，见 ④）|

**被删的那条「同因不重试」为什么弱**：它把同样的输入再喂一遍手写短原因
（`"假绿：换页证据用 index"`）—— 而真实事故是**日志路径自带时间戳**让「同因」永远判不出来：

```
…/verify/ai_xxx_20261009_073944.log
…/verify/ai_xxx_20261009_074246.log
```

旧版这条**抓不到**这个形态（它的样本里没有路径）；`test_ai_retry_same_cause.py` 用**真路径样本**
加指纹比较与源码断言，把这个洞钉死了。

## ⑥ 组 2：三处「用例 <-> 场景来源」收成一个（**本批最危险的一组**）

活下来：**`tests/特性9-质量闸门体系/test_scenario_case_script_hygiene.py`（保名）** ——
它已含**防空转守卫 + 覆盖告警**，是三者里最全的。

| 迁入/删除 | 内容 | 说明 |
|---|---|---|
| 迁入 | `source_scenario` 字段级校验 + `_YML_REF` 正则 -> `test_ai_cases_have_resolvable_source_scenario` | **保持硬要求**（见下面的核实结论）|
| 迁入 | `scenario_fingerprint` 同步 + 它的负向自证（改一个字指纹必变、改回来必复原）| 原 `test_ai_case_scenario_sync.py` 的核心 |
| 迁入 | 两条负向（孤儿「无来源」/ 悬空「指向不存在场景」）-> **合并成一条 parametrize** | 合并依据：**共同前提一样**（都对同一个纯函数提同一种要求），不是「名字看着像」|
| 删 | 「合规不误伤」那条 | 接手 = 同文件 `test_negative_orphan_detected` 末句「正常用例不许误报」|
| 删 | 两处重复的「场景存在性」检查（原两个文件各一份）| 同文件 `orphan_ai_cases` 已在查 —— **同一件事只留一处口径** |

**`source_scenario` 不是死字段（已核实，所以不降级这条断言）**：

- `generator_generate.py:148` 真的读它 —— `_scenario_text_of(str(case.get("source_scenario") or ""))`，
  注释写明「声明等待时长要用它」；
- `generator_generate.py:713` 还拿它作 `scenario_id` 的回落取值；
- `kit_check_generate.py:82` 也消费它。

⇒ 字段缺失/悬空会让下游**悄悄退化成「没有场景原文」**，表现为「等待时长没按场景声明走」
这类**看着像业务问题**的故障。合并判据最容易犯的错是「顺手把不确定的断言放宽」，
正确姿势是先去代码里把「有没有人读它」查清楚。

**防空转哨兵加固（全仓唯一，见「验证真值」节的源码）**：
`test_scenario_and_case_dirs_are_nonempty` 原来只判「非空」——

- 只要 `cases/` 下还有任何 json（例如只剩手搓用例）就绿；
- 而 `ai_*.json` **归零**时，三条 AI 用例对账（孤儿 / 来源 / 指纹）**同时变成空转**，哨兵却不会响。

现在**分别**要求 `ai_*.json >= 1` **且** `scenarios/*.yml >= 1`，并在 docstring 里写清它为什么存在
（防「**循环体恒空的全绿假阳**」）。它同时兜着 `test_case_evidence_gate.py` 的仓库扫描
（那条同样遍历 `cases/**.json`）。真值余量极小（`cases/` 只有 **1** 条 AI 用例、
`scenarios/` 只有 **1** 个 yml），所以这条哨兵不是形式主义 —— 清一次产物就会踩到。

## 新增判据（3 条强判据）

| 判据 | 钉什么 | 先红后绿真值 |
|---|---|---|
| `test_wait_text_rendered_kwargs_match_real_signature`（组 5）| 解析 `generator_generate.py` 里 `def _assert_wait_text(...)` 的**真参数名**，与渲染出的 kwarg 名（`timeout_ms=` / `refresh=` / `desc=` / `selector=`）求**差集必须为空** | 真渲染差集 = `[]`；把 `refresh=` 改成 `refresh_typo=` -> 差集 = `['refresh_typo']`（判据自带这条负向自证）|
| `test_replay_is_skipped_in_both_retry_paths`（组 1）| 「录像回放模式：重试无意义」必须**出现 >= 2 次**，且分别落在**两个分支体内**：产出档那处分支体第一条语句是 `break`、实跑档那处是 `raise SystemExit(3)`。识别靠**缩进**（所在分支的判定头 + 该分支的下一条语句），**不写死行号** | 真代码 = 2 处（分支 `[('if replay:', 'break'), ('if replay:', 'raise SystemExit(3)')]`）；**删掉任一档** -> 旧判据（>= 1 次）照样绿、**新判据红** |
| `test_notes_every_module_level_container_has_unconditional_clear`（组 3 · **遍历式**）| 对 `explorer_explore.py` 里**所有**模块级 `*_NOTES` 容器断言「必有一处**无条件** `.clear()`」，名单**从源码动态收集**（不写死）。识别用 **AST + 父链**：`if 本轮有缺失: notes.clear()` 这种「条件清空」判红 | 真源码四个容器（`SEMANTIC_MISMATCH_NOTES` / `_HARDCODED_NOTES` / `_REQUIRED_COVERAGE_NOTES` / `_ROW_SCOPE_NOTES`）**各有一处无条件 clear** -> 绿；把 `_HARDCODED_NOTES.clear()` 挪进 `if hard:`（缩进 4 -> 8）-> **当场红**（报文：`_HARDCODED_NOTES：清空点全被包在分支里`），同时缩进级那条也红；判据**自带两条负向自证**（包进 `if` / 整段删掉）|

> **为什么组 3 这条要做成「遍历式」而不是点名**：这一形态的事故**在本项目已经犯了三次**
> （`_REQUIRED_COVERAGE_NOTES` 只在有缺失时清 / `_HARDCODED_NOTES` 只在有写死时清 /
> `SEMANTIC_MISMATCH_NOTES` 完全没有 clear）—— 每次都是「体检到哪个就修哪个」，
> 而**新加**一个跨轮记账容器时没人会想起回来补 clear：点名判据对**第四个容器天然失明**。
> 名单动态收集后，新加容器自动纳入、删掉容器自动退出（判据不该守着不存在的东西）。
> 自带的两条负向自证是必需的 —— 没有它们，「遍历式」完全可能是「遍历了个空集合」而永远绿。

> **为什么值得为它们各写一条**：前者守的是"渲染层字符串拼参数名 / 签名靠人眼一致"这个**看不见的缝**
> （写错名字在纯函数判据里完全看不出，实跑才 `TypeError: got an unexpected keyword argument`，
> 代价 = 一整轮端到端 + 一轮 AI 重试）；后者把"两档各自跳过回放"从一个**恒真的计数**变成**能区分两档**的结构断言。

## 删掉的判据 —— 保护由谁接手（本版硬要求）

| 删掉的判据（文件:用例）| 为什么要删 | 保护由谁接手 |
|---|---|---|
| `test_wait_text_kind.py`（整文件，6 条）| 与另两条同源（渲染契约三合一）| `test_wait_text_render_contract.py`（逐条迁入，含新增 1 条）|
| `test_wait_text_refresh_policy.py`（整文件，3 条）| 同上 | 同上（三态 / 缺省不出参数 / 负向都迁入；负向并入合并 parametrize）|
| `test_wait_text_selector.py`（整文件，2 条）| 同上 | 同上（selector 透传 / 向后兼容空 selector）|
| `test_case_evidence_gate.py::test_g2_self_invented_url_fragment_is_redline` | 等价双写 + 走私有入口与常量名 | 同文件 `test_fabricated_fragment_is_redline_now`（公开出口 `case_errors()`）|
| `test_verify_entry_contract.py::test_retry_is_bounded` | 被特性2 **严格覆盖** | 特性2 `test_retry_limit_default_is_two` / `test_retry_limit_configurable_and_zero_disables` / `test_retry_limit_is_bounded_and_forgiving_of_garbage` |
| `test_verify_entry_contract.py::test_replay_mode_does_not_retry` | 只查"全文 >= 1 次"，**删任一档都不会红** | 新 `test_replay_is_skipped_in_both_retry_paths`（两档各自在）+ 特性2 `test_replay_mode_skips_retry`（行为面）|
| `test_ai_retry_loop.py::test_quality_gate_not_weakened` | **假绿兜底**（`or` 后半句恒真）| 特性11 `test_verify_failure_exit_codes_are_distinct`（两档退出码真的存在且可区分）|
| `test_retry_leaves_no_stale_notes.py`（**整文件，4 条**）| 与「跨轮反馈通道」的另一端同源（两合一）| `test_retry_feedback_contract.py`（4 条**逐条迁入**，加 `test_notes_*` 前缀，一条不丢）|
| `test_ai_retry_contract.py::test_prompt_without_feedback_is_clean` | 与 `test_retry_feedback_contract.py::test_prompt_stays_clean_without_feedback` 守同一件事 | 后者（**两组断言取严合并**：`"上一轮" not in flat` + `"上一轮框架识别出的" not in prompt`）|
| `test_ai_retry_contract.py::test_same_reason_stops_retrying` | 与 `test_ai_retry_same_cause.py` 守同一件事，但样本里**没有日志路径**（抓不到真实事故形态）| `test_ai_retry_same_cause.py`（真函数体 `exec` + 指纹源码断言，5 条）|
| `test_case_scenario_contract.py`（**整文件，4 条**）| 与 hygiene 同源（「用例 <-> 场景来源」三合一）| `test_scenario_case_script_hygiene.py`：**2 条迁入**（`source_scenario` 可解析 + 两条负向合并成一条 parametrize）；**1 条删**（「合规不误伤」-> 接手 = 同文件 `test_negative_orphan_detected` 末句「正常用例不许误报」）；**1 条被覆盖**（「场景存在性」-> `orphan_ai_cases`）|
| `test_ai_case_scenario_sync.py`（**整文件，2 条**）| 同上（三合一）| `test_scenario_case_script_hygiene.py`（指纹同步 + 其负向自证**逐条迁入**；重复的「场景存在性」检查删掉）|

## 改了什么

| 文件 / 位置 | 改动 |
|---|---|
| `tests/特性9-质量闸门体系/test_wait_text_render_contract.py`（**新**）| 11 条：三合一后的 `wait_text` 渲染契约（走真管线；两个负向合一条 parametrize；新增 kwarg == 真签名 1 条）|
| `tests/特性9-质量闸门体系/test_wait_text_kind.py`（**删**）| 全迁 —— 无一条可丢 |
| `tests/特性9-质量闸门体系/test_wait_text_refresh_policy.py`（**删**）| 全迁 |
| `tests/特性9-质量闸门体系/test_wait_text_selector.py`（**删**）| 全迁 |
| `tests/特性9-质量闸门体系/test_case_quality_gate.py` -> `test_case_evidence_gate.py`（**改名**）| 删 1 条等价双写（保留公开出口那条）；docstring 写清改名与不合并的理由；13 条 |
| `tests/特性9-质量闸门体系/test_declared_wait_budget.py` | 注释里指向旧判据名的那处同步改对（R9：搬家要查调用方）|
| `tests/特性2-语义识别与步骤编排/test_ai_retry_loop.py` | 删 1 条假绿兜底（9 条，其余原样不动）|
| `tests/特性2-语义识别与步骤编排/test_retry_feedback_contract.py`（**新，由两文件合并改名而来**）| 13 条：质量警告回炉 8 条 + 迁入 4 条（`test_notes_*`，autouse fixture 清模块级状态）+ **新增 1 条遍历式**（全容器必须有无条件 clear）|
| `tests/特性2-语义识别与步骤编排/test_quality_warnings_feed_next_round.py`（**删**）| 与 `test_retry_leaves_no_stale_notes.py` 合成一份（通道两端）|
| `tests/特性2-语义识别与步骤编排/test_retry_leaves_no_stale_notes.py`（**删**）| 4 条全迁 —— 无一条可丢 |
| `tests/特性2-语义识别与步骤编排/test_ai_retry_loop.py` -> **`test_ai_retry_contract.py`**（**改名**）| 删 2 条（同因不重试下放 / 无反馈干净并入组 3），docstring 写清改名理由与接手方；9 -> **7 条** |
| `tests/特性9-质量闸门体系/test_scenario_case_script_hygiene.py` | 三者合一（**保名**）：从 5 条 -> **10 条**（9 个 `def`，其中一条 parametrize 展开 2 例：`source_scenario` 可解析 / 指纹同步 / 指纹负向 / 两条负向）；**防空转哨兵加固**；docstring 写清每条迁入的来历与接手关系 |
| `tests/特性9-质量闸门体系/test_case_scenario_contract.py`（**删**）| 同源三合一（见上）|
| `tests/特性9-质量闸门体系/test_ai_case_scenario_sync.py`（**删**）| 同源三合一（见上）|
| `framework/features/f09_gate/feature_spec.py` | 登记同步（两批）：9.1 摘掉 `test_wait_text_kind.py`（第一批）/ `test_case_scenario_contract.py`（第二批）；9.2 改名 `test_case_evidence_gate.py`、摘掉 `test_ai_case_scenario_sync.py`（并同步 9.2 目标里「AI 用例与场景同步」那一句）；9.6 换成 `test_wait_text_render_contract.py`、目标写明「用例 <-> 场景来源三者已合一」；**2.2 两处登记合成一行**（`test_retry_feedback_contract` / `test_ai_retry_contract`）、11.1 / 11.2 目标里的旧文件名改齐 |
| `tests/特性11-交付即验证/test_verify_entry_contract.py` | 删 2 条、**新增 1 条强判据**、docstring 过期文案改齐（5 条）|
| `framework/features/f09_gate/feature_spec.py` | （见上一行：两批登记同步合并说明）|
| `build_tools/build_html.py` | `VERSION` -> `8.6.4` + 本版 CHANGELOG 条目（两批；8.6.3 的 tag 改"上一版本"）|
| `README.md` | 判据数 1222 -> **1218**（两处）|
| `docs/training.html` · `docs/feature_map.md` | 两个生成器重跑后的产物（**禁止手改**）|

## 验证真值（2026-10-17 本机实测）

| 项 | 结果 |
|---|---|
| 全量判据 | **1218 passed / 3 skipped / 0 failed**（基线 1222，净 **-4** = 第一批 -2 + 第二批 -2）|
| 3 skipped 是什么 | **仓库当前状态不满足**：① 没有探针快照可比对 ② 没有 `output/element_maps/probe_*.json` ③ 仓库当前没有带 `data:` 段的场景 —— 属**环境跳过、非失败** |
| 判据文件数 | **152 -> 149**（`test_*.py` + `verify_*.py`）：第二批删 3 个（`test_retry_leaves_no_stale_notes` / `test_case_scenario_contract` / `test_ai_case_scenario_sync`），2 个改名不计 |
| 两个生成器 | `build_html.py` 与 `build_feature_map.py` 均重跑成功（产物见 `docs/`）|

### 防空转守卫加固后的源码（全仓唯一哨兵）

```python
def test_scenario_and_case_dirs_are_nonempty():
    """★防空转哨兵（**全仓唯一**）—— 它守着本文件三条对账 + 另一条判据的仓库扫描。"""
    ai = sorted(CASES.rglob("ai_*.json"))
    scen = sorted(SCENARIOS.rglob("*.yml"))
    assert ai, (
        "cases/ 下一条 ai_*.json 都没有 -> 本文件三条 AI 用例对账（孤儿 / 来源 / 指纹）"
        "与 test_case_evidence_gate 的仓库扫描会**同时空转**（循环体恒空 = 全绿假阳）。"
        ...
    )
    assert scen, (
        "scenarios/ 下一个 yml 都没有 -> 场景侧对账（覆盖告警 / 孤儿判定）全部空转（假绿）。"
    )
```

（原文 docstring 里还写清了它守哪四条、以及「真值余量极小（`cases/` 只有 1 条 AI 用例、
`scenarios/` 只有 1 个 yml）」这个事实 —— 见 `tests/特性9-质量闸门体系/test_scenario_case_script_hygiene.py`。）

## 附：本版唯一想留下的口径

**重复判据 = 一处改两处验。**

合并的方向是「**留下的那条必须更强**」，不是「删到数量好看」：
两条判据守同一件事时，留**走公开出口**的、留**能区分两种坏法**的；
被删的每一条都要能**指名道姓**说出由谁接手。
而且 —— **合并重复判据时不许顺手重排测试**：三个闸门文件保持在原目录分居，
理由写进了文件 docstring（互不调用的三个函数 + autouse fixture 会外溢），
否则「合并」会变成「改变无关判据行为」，归因就没了。

第二批再补三条口径（都是这回真踩到的）：

1. **合并时「不确定的断言」先去查代码，不许顺手放宽** ——
   `source_scenario` 曾被视为历史字段，核实后三处代码真在读它，于是**保持硬要求**。
2. **「点名式」判据要升级成「遍历式」** —— 同一形态的事故犯过三次还在犯，
   说明问题不在「这次漏了哪个容器」，而在「点名」这种写法本身对新容器天然失明。
3. **防空转哨兵要按「哪几条判据靠它」精确加固** —— 「非空」不等于「不空转」：
   只要还剩一条手搓用例，`cases/` 就是非空的，而三条 AI 用例对账已经全空了。
