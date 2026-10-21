# 架构契约（V8.7）

> 这份文档回答**四个问题**，其余一概不写（设计史、踩坑细节在 `releases/` 与内部台账里）：
> ① 有哪几段？② 每段的输入 / 输出 / 失败出口 / 是否用 LLM？③ 数据怎么流？④ **谁的产物是谁的输入**？
>
> 维护口径：**这里只描述代码当前的事实**。改了产物路径/字段/段边界，必须同步改这份文档 ——
> 判据 `tests/特性9-质量闸门体系/test_architecture_doc_contract.py` 会拿文档里点名的产物
> 去源码里找写入点，找不到就红（防"文档写着一个没人产的产物"）。

---

## 一、四段契约

| 段 | 入口（CLI） | 输入 | 输出（产物） | 失败出口 | 用 LLM？ |
|---|---|---|---|---|---|
| **(1) explore** | `python -m framework.cli explore --ai --scenario-file <yml>` | ① 场景 `scenarios/**/*.yml`（**唯一人写输入**）② 被测站点（真浏览器）③ `output/llm_cassettes/*.json`（离线回放时） | `output/element_maps/element_map_<ts>.json`（= 决策档案）<br>`cases/<scenario_id>/ai_<scenario_id>_<HHMMSS>.json`（= 用例）<br>`output/llm_cassettes/<key>.json`（录制时） | `SystemExit(2)`：LLM 不可用 / 探测为空 / 产出闸门不合格（**拒绝产出假用例，无 mock 降级**）；`SystemExit(3)`：`--verify` 实跑不过 | **是**（语义识别 + 步骤编排） |
| **(2) generate** | `python -m framework.cli generate` | ① `cases/**/*.json`（explore 的产物，或离线回放的产物）② `output/element_maps/*.json`（定位来源）③ `scenarios/**/*.yml`（场景声明：pre / auth / data / probe_pre） | `scripts/generated/<scenario_id>/<case_id>.py`（一个用例一个脚本）<br>`scripts/generated/_harness.py`（共享运行时）<br>`scripts/generated/conftest.py`（只转发夹具）<br>`scripts/generated/index.json`（case → 脚本 + 四个指纹）<br>`scripts/generated/_probe_snapshot.json`（运行时语义名索引）<br>`scripts/generated/_pre.json`（执行期前置：场景身份前置 / 登录）<br>`scripts/datasets/*.json`（数据抽离） | `SystemExit(2)`：有语义名映射不上（**默认拒绝落盘**，`--allow-unmapped` 仅调试）；`CaseQualityError`：用例带假绿红线 | **否**（纯确定性渲染） |
| **(3) run** | `python -m framework.cli run --workers N` | `scripts/generated/**`（pytest 用例）+ `scripts/datasets/**` | `log/<run_id>/`（逐用例 .log、report.html、summary.json；`--debug` 另有 shots/ 与录像） | pytest 退出码；`_case_watchdog` 兜住超时；`HYBRID_SELF_HEAL=0` 时定位失败即红（不做推测） | **否**（执行期零 LLM；自愈也只在显式开启时用 LLM 重猜） |
| **(4) all** | `python -m framework.cli all --ai --scenario-file <yml>` | 同上 | 同上（三段依次跑） | 任一段非 0 即停 | 是（含 explore） |

**已删除的段（不要按旧文档去找）**：`cli probe` 在 V8.6 随手搓链路整条删除；
`cases/manual/*.json` 不再支持。现在进入框架的路径只有 `explore --ai` 一条。

### 产物字段口径（跨段契约，改一处必须三处同步）

| 产物 | 步骤对象的形状 |
|---|---|
| `output/element_maps/*.json` | `pages[]`，每页 `{page,url,scenario,steps[],probe_items[]}`；`steps[i]` 的键集 **== `TestStep.__dataclass_fields__`**（`order/op/desc/element/value/assertion/row_text/cell_field/cell_by/cell_index/row_index`） |
| `cases/**/*.json` | `{case_id,name,base_url,steps[],asserts[]}`；`steps[i].op` 与控件图层**同名同义**（L34-a 统一，无映射表）；断言进 `asserts[]` 而不是 `steps[]`（`kind/desc/expect/after_step`） |

另：`cases/*.json` 可带 `login` 字段（L35）= `{login_url, wait, steps[]}`，`steps[]` 与普通步骤**同形状**。
登录步骤由 explore 用**同一个规划器**在登录页产出、**固化进用例**，执行期零 AI（`_harness._login_flow` 走同一套 `resolve_locator`）。

判据：`tests/特性2-语义识别与步骤编排/test_no_dual_step_field_names.py`（一套字段名 + 键集锁 + 禁映射表）；
`tests/特性2-语义识别与步骤编排/test_login_stepwise_contract.py`（登录只有一套 schema/执行器）。

---

## 二、数据流

```
            scenarios/**/*.yml            ← 唯一人写输入（pages/pre/auth/data/probe_url/probe_pre/login）
                    │
                    │  ① explore --ai
                    ▼
   ┌────────────────────────────┐   产出决策档案（可审计、可回放）
   │ probe(scan_page) + AI 规划 │──► output/element_maps/element_map_<ts>.json
   └────────────────────────────┘──► output/llm_cassettes/<key>.json   （录制 / 回放双用）
                    │
                    │  case_builder（同名直映射：op/desc/element/value）
                    ▼
            cases/<scenario_id>/ai_*.json     ← ★ 两段之间**唯一的接口**
                    │
                    │  ② generate（确定性渲染，四指纹决定增量）
                    ▼
   scripts/generated/<sid>/<case>.py + _harness.py + conftest.py
   scripts/generated/index.json + _probe_snapshot.json + _pre.json
   scripts/datasets/*.json
                    │
                    │  ③ run（pytest）
                    ▼
            log/<run_id>/report.html + summary.json + <case>.log
```

三个"跨段耦合点"（改动最危险的地方，都在上面有判据）：

1. **`cases/*.json`**：explore 写、generate 读。字段口径一改，两边必须同步。
2. **`output/element_maps/*.json`**：explore 写；generate 读它做定位来源；`_probe_snapshot.json` 是它在运行时的**索引**。
3. **`scripts/generated/index.json` 的四指纹**（case / scenario / probe / 渲染模板）：任一变化都触发重写脚本 —— 这是"改了生成逻辑、产物却不刷新"的唯一防线。

---

## 三、谁的产物是谁的输入（归属表）

| 产物 | 生产者 | 消费者 | 进交付包？ |
|---|---|---|---|
| `scenarios/**/*.yml` | **人** | explore / generate | ✅ |
| `output/element_maps/*.json` | explore（AI 决策档案） | generate（定位来源）、判据 | ✅（只发最新 1 份） |
| `cases/**/*.json` | explore → `case_builder_generate` | generate | ✅ |
| `output/login_maps/login_<hash>.json` | explore（**登录页**的 AI 规划产物，L35） | `ensure_logged_in`（探测/生成期的登录执行） | ❌（决策档案；用例里已固化副本） |
| `output/llm_cassettes/*.json` | explore（录制） | explore（离线回放） | ✅（离线跑 AI 链路的唯一凭据） |
| `scripts/generated/<sid>/*.py` | generate | run（pytest） | ✅ |
| `scripts/generated/_harness.py` | generate（`_render_harness`，来自 `generator_generate._CONFTEST_TEMPLATE`） | 每个用例脚本 | ✅ |
| `scripts/generated/conftest.py` | generate（`_render_generated_conftest`） | pytest | ✅ |
| `scripts/generated/index.json` | generate | run（发现用例）、pack_release | ✅ |
| `scripts/generated/_probe_snapshot.json` | generate | `_harness._loc`（运行时语义名→元素） | ✅ |
| `scripts/generated/_pre.json` | generate | `_harness._maybe_scene_pre` / `page` fixture（身份前置、登录） | ✅ |
| `scripts/datasets/*.json` | generate（数据抽离） | 用例脚本（`_data()`） | ✅ |
| `log/<run_id>/*` | run | 人 / 报告 | ❌（运行证据，不进包） |
| `output/heals/*`、`output/traces/*` | run（自愈 / 取证） | 人 | ❌ |

---

## 四、模块边界与依赖方向

```
framework/
  shared/            通用底座：无业务、无特性依赖（config / browser / text_io / login /
                     pre_actions_run / waits_run / declared_wait / llm_compat / textutil / step_ops）
  features/
    f02_semantic/    explore 与 generate 的**决策层**：场景解析、AI 规划、用例落盘、脚本渲染
    f03_locate/      定位层：探测清单、元素映射、分层定位、页面内锚点/下钻
    f04_ambiguity/   选错控件兜底
    f05_layers/      分层快照（探测结果的归一化产物）
    f06_healer/      自愈（确定性再协商 / LLM 重猜）
    f07_concurrency/ 并发与资源安全、保留策略
    f08_replay/      离线回放（录像录制 / 命中 / 结构键）
    f09_gate/        判据规格（特性 ↔ 用例的登记表；不参与运行时）
    f10_cli/         命令行入口（只做参数解析与编排，不含能力实现）
    f11_verify/      交付即验证
```

依赖方向（**只允许自上而下，反向即违规**）：

```
f10_cli  →  f02 / f03 / f07 / f11  →  shared
f02      →  f03 / f08 / shared            （explore 需要探测与回放）
f03      →  shared
f06      →  f03 / shared
f09_gate →  （只被 tests/ 读；不 import 运行时代码）
```

三条铁律（都已由判据守着）：

1. **框架层零业务词**：`framework/` 里不出现被测系统的页面名/字段名/业务术语（都在 `scenarios/` 里）。
2. **不让 AI 产 selector**：AI 只产出语义名，定位由框架从语义合成（`f03_locate`）。
3. **一个能力只有一处实现**：前置动作（`shared/pre_actions_run`）、等待（`shared/waits_run`）、
   登录（`shared/login`）、步骤字段名（`shared/step_ops` + L34-a 判据）都是唯一入口；
   新增第二条实现要么被判据拦下，要么就是设计错误。
