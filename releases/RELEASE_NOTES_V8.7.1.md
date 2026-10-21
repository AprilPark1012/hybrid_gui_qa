# V8.7.1 发行说明（2026-10-21）

> 承接 **V8.7**（同一天提交，未单独发版）：字段命名统一 + 登录链路 AI 化（L34 / L35）。
> 本版补 **L36**，并把版本号正式打到 `8.7.1`。

---

## 一、V8.7 主体（随本版一并生效）

### 1. 步骤字段命名统一为 `op` / `desc`（L34-a）
- `TestStep` / `_StepModel` / `cases/*.json` / `element_map_*.json` **一套名字**，删掉双读宽容垫片 7 处。
- 删 `_OP_MAP`（它只是 `action -> op` 的恒等映射）→ 改 `_STEP_OPS` 白名单 + **未知动作出声**：
  stderr 一行 + 进 `elementmap_warnings` 随重试闭环喂回 AI（旧行为是静默少一步，形成假绿）。
- 存量产物迁移：`build_tools/migrate_element_map_keys.py`（幂等 / `.bak` / `--check`），
  实测 **125 步 / 250 键**，逐字段对账 0 差异。
- 守卫：`tests/特性2-.../test_no_dual_step_field_names.py`（先红 57 处 / 后绿）。

### 2. 架构契约文档（L34-b）
- 新增 `docs/ARCHITECTURE.md`：四段契约表（输入 / 输出 / 失败出口 / 是否用 LLM）+ 数据流 + 「谁的产物是谁的输入」+ 模块边界与依赖方向。
- 判据 `tests/特性9-.../test_architecture_doc_contract.py`：章节齐 + 文档点名的产物必须在源码里有写入点 +
  段名与 `cli.py` 分发表一致 + 已删除的 `cli probe` 只能以「已删除」出现。

### 3. 登录链路 AI 化（L35）
- `login:` 段改为**自然语言**：`url` / `scenario` / `wait`；写 `steps` / `by` **加载期即报错**。
- 登录步骤由**同一个规划器**在登录页产出普通 `TestStep`（`login_flow_explore.plan_login` → `_ai_explore_async`），
  落 `output/login_maps/login_<hash>.json` 作决策档案，并**固化进 `cases[*].login`**（产物即输入）。
- 运行期走**同一套** `resolve_locator`，且**零 AI**（`_harness._login_flow`）。
- `by` 那套（`_BY_KEY` / `locator_of` / `perform_login` / `_login_do` / `_login_wait`）**全删**。
- 动作词表收敛成唯一权威 `framework/shared/step_ops.py`。
- 顺带修掉死代码：`login_failure_hint()` 定义了从没人调用，现接到执行期两处定位失败报错上。
- 新增 `index` 字段（`select` 的「第几项」）：提示词早就在教 AI 用 `index=0`，但 schema 没有这个字段，
  导致 AI 退化成 `value="0"` → `did not find some options` 超时。渲染器/执行器本来就支持，断的只是契约这一段。
- 判据 `test_login_stepwise_contract.py`（10 条）+ `test_login_priming_coverage.py` 口径更新。

---

## 二、V8.7.1 新增（L36）

### 断言「输入回显」升为**硬红线**
问题（L35 真跑暴露）：AI 重规划后断言 `全链路-20261021215943` —— 那正是本用例自己 `fill` 进去的订单名
（场景 `data:` 模板渲染）。执行时列表里 5s 内不可见 → **207s 才超时**；换个数据批次又可能"侥幸相等"地通过（假绿）。

提示词规则 6 早就写着「不得与 fill 的 value 相同」，但它只进 `case_warnings`（告警）——
**写了规矩、没有闸门**。

本版：
- `case_builder_generate.assertion_hard_errors()` → 进**落盘前**红线计算，命中即 `CaseQualityError` 拒绝落盘，
  并随重试闭环反馈给 AI 重写。
- 两处豁免（都必须是**人写的决定**）：
  - `kind = first_row`：它验的是「新建记录落在第一行」，期望值本来就该等于刚填的值；
  - 场景 `assert_guard.allow_input_echo: true`：确需验证「保存后值仍在」时显式豁免。
- 提示词收紧：明确「由本用例写入的名称 / 单号 / 客户名（含 data 模板渲染值）一律不许当断言」，
  并给出替代做法（`expect_first_row` / `expect_url` / 状态文案）。
- 判据 `tests/特性9-.../test_assertion_echo_gate.py`（6 条：拦得住 + 接进了落盘红线 + 两处豁免 + 提示词告知 + 负向自证）。

---

## 三、验证

| 项 | 结果 |
|---|---|
| 全量判据 | **1240 passed, 3 skipped, 0 failed** |
| E2E（`cli run`） | **1 passed**（202s，`_login_flow` 前导 + 48 步业务链路） |
| 离线回放体检（特性8） | **3/3 通过**（含 2 条负向证伪） |
| `feature_map --check` | 一致（11 特性 / 54 子特性） |

## 四、已知遗留

- **旧录像已删除**（`34b7902f…` / `3516231809…`，V8.6.4 旧提示词）。它们不会 strict 命中，
  但会走 `struct_key` 相似匹配 —— 实测因此产出过一份 64 步垃圾用例。改提示词/schema 后请**先删旧录像再重录**。
- AI 断言的**选择倾向**仍偏激进（喜欢断言运行期数据），本版已用硬闸门兜住"输入回显"这一类；
  「断言运行期计数 / 时间戳」那类仍靠 `_dynamic_assert_kind` 告警 + 重试闭环。
