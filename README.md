# hybrid_gui_qa — LLM 驱动的混合 GUI 自动化测试框架

> 当前版本 **V8.5.1**（2026-10-12）· 版本号单一来源 = `build_tools/build_html.py` 顶部 `VERSION`
> · 变更记录见 [`releases/RELEASE_NOTES_V*.md`](releases/) · 团队培训页（**先看这个**）：[`docs/training.html`](docs/training.html)

**一句话**：把 **LLM 语义编排（AI 智能探索）** 和 **Playwright（浏览器采集证据 + 确定性执行）** 组合成一套混合测试框架 ——
AI 负责理解意图、规划步骤、挑元素；Playwright 负责精确定位、唯一性校验、可复现回归。

> **口径澄清（别被依赖名误导）**：AI 侧只借 `browser-use` 的 **LLM 客户端**
> （`browser_use.llm.ChatDeepSeek`）直连做结构化编排，**不使用它的 Agent** ——
> 不存在「AI 自己开浏览器、自己点」的循环。`browser-use` 是**可选**依赖
> （`requirements-ai.txt`，仅 AI 探索用）；`generate` / `run` 都不需要它。
> AI 没有浏览器的控制权，但它的**眼睛是浏览器**：判别依据全部来自 Playwright 采集的
> DOM 证据（可见性 / 禁用 / 可编辑 / 可访问名 / 重复个数），且最终由**真实浏览器试跑**裁决。
>
> **四段闭环（浏览器在两端）**：浏览器出证据 -> LLM 出编排 -> 确定性执行 -> 浏览器裁决。
> 其中「确定性执行」占全部日常运行：**运行期零 token、可复现、能进 CI**。

**核心哲学**：**让 AI 做理解和决策，让确定性代码做精确定位，绝不把「定位」交给 LLM。**

**兜底原则（2026-10-11 定 · 管四段链路 explore → probe → generate → run）**：
1. **explore 阶段 LLM 做不到的，由框架在后续三个阶段兜底** —— 但兜底**有边界**。
2. **能由事实/结构判死的才兜底**（例：刚新增的那一行 ⇒ `row_index=-1`）；判不出来的**一律报红**，
   绝不猜、绝不静默降级。
3. **兜底不许无限**：凡是**该在场景里说清楚的**（页面结构、权限与前置、行区/表格语义、期望值、
   数据的唯一锚），就**写进 scenario 场景描述作为约定** —— **约定优于兜底**：改场景比改框架成本低、
   更健壮、更通用，也更适配复杂生产页面。
4. **兜底必须可审计**：补了什么、依据哪条规则、还有哪些没推定 —— 全都要打出来（否则兜底会变成
   遮住真问题的遮羞布）。

## 目录

- [它解决什么问题](#它解决什么问题)
- [快速上手](#快速上手)
- [项目结构与链路](#项目结构与链路)
- [常见坑](#常见坑)
- [文档与资源](#文档与资源)
- [许可](#许可)

## 它解决什么问题

纯 AI 测试不可靠（会幻觉、点错控件、不可复现、每次烧 token）；纯脚本测试不可维护（UI 一改红一片）。
本框架把两者**按能力切开**：

| 能力 | LLM 编排（DeepSeek 直连 · 非 Agent） | Playwright（确定性） |
|---|---|---|
| 理解自然语言测试意图 | ✅ 强 | ❌ |
| 规划步骤 / 挑元素 | ✅ 强 | ❌ |
| 采集浏览器证据（DOM 上下文：可见/禁用/可编辑/可访问名） | ❌ 看不到页面 | ✅ 准 |
| 精确定位元素 | ❌ 可能幻觉 | ✅ 准 |
| 唯一性校验 / 防误点 | ❌ | ✅ |
| 可复现回归 / 进 CI（运行期零 token） | ❌ | ✅ |

业界在做同一件事（Stagehand / Playwright Test Agents）：*"Selectors break. Natural language doesn't."* ——
但自然语言只能用于**理解**，真正执行必须落到确定性 locator。

**它服务两件事**：① 让测试同学少写代码（自然语言 → 用例 → 脚本，降人力）；② 让 AI 产出**可信**
（AI 只挑语义名，定位与校验全由确定性代码做 ⇒ **AI 不可能点错控件还报绿**）。

## 快速上手

### 0. 一条命令搞定环境（推荐；装依赖 + 装浏览器 + 自检）

```bash
pip install -r requirements.txt        # 核心依赖：playwright / python-dotenv / pytest / pytest-xdist / pytest-html
python -m framework.cli setup          # 装依赖 → 装浏览器 → 真启 chromium 自检；就绪才说 OK
```

> ⚠️ **最容易漏的一步是「装浏览器」** —— `pip install` 不会装它。缺了会在 `probe/generate/explore/run`
> 时报 `Executable doesn't exist at …ms-playwright…`。`cli setup` 就是为这一步准备的：
> `--check` 只体检不安装 · `--force-browser` 换过 playwright 版本时强制重下 · `--with-ai` 连 AI 依赖一起装。

### 1. 起被测 demo 应用（开一个终端）

```bash
python -m demo.app         # http://localhost:8000：合同/订单列表页 + 详情页 + 内存数据 API
```

### 2. 跑通整条链路（另开一个终端）

```bash
# 两条链路**同一条命令**，用 `--ai` 区分（不另开命令）：
python -m framework.cli all --ai --scenario-file scenarios/orders/orders_invoice_full_lifecycle.yml
                                              # 真 AI 链路（主推）：explore --ai → generate → run 一条龙
python -m framework.cli all --workers 2       # 手搓链路（次选）：probe → generate → run，确定性，零 token
python -m framework.cli run --debug           # 调试开关：有屏幕弹浏览器；没屏幕录视频 + 逐步截图
python -m framework.cli run --case <case_id>          # 只跑指定用例（--case 可重复；case_id = cases/ 里的文件名）
python -m framework.cli prune --dry-run       # 归档保留（log/ 与 output/verify/ 按 30 个 ∪ 7 天清理）
python -m framework.cli --help                # 总览 = 子命令 + 每个子命令的全部参数（由代码注册表生成，不手写第二份）
                                              # 参数写错一律报错 + exit 2，绝不静默忽略；<子命令> --help 看详细用法
```

> **命令统一口径（AprilPark1012 2026-10-11 要求 4）**：真 AI 链路与手搓链路**共用 `all`**，
> **用 `--ai` 区分**，**不另开命令**。单独用 `explore` / `generate` / `run` 仍然可以
> （调参、只跑某一段时用），但那不是主线；主线一律 `all`。

**两类验证**（改完东西跑这两条）：

```bash
python -m pytest tests/ -q                            # ① 框架自测：秒级，不需要 demo / key
python tests/_runner/run_verifications.py             # ② 端到端特性验证：需 demo（会自己起停；SKIP ≠ 通过）
python tests/_runner/run_acceptance.py                # ③ 四项验收一条命令（闸门 → 新鲜度 → 自测 → E2E → 特性）
```

> **判据住哪**（2026-10-12 更正）：判据按**特性**分目录，在 `tests/特性1-…/` ... `tests/特性11-…/` 下
> （`test_*.py` 一类 + `verify_*.py` 二类混放同一特性目录，共 121 个 `test_*` / 24 个 `verify_*`）。
> `tests/_helpers/` 只是**共享辅助**（artifacts / demo_freshness / repo_files / testid_policy），
> **不含任何 `test_*.py`** —— 直接跑它会 `no tests collected`。

⚠️ **跑那条 AI 端到端用例（`ai_orders_invoice_full_lifecycle_<时间戳>`）建议显式带 `HYBRID_CASE_TIMEOUT`**：

```bash
HYBRID_CASE_TIMEOUT=600 HYBRID_STRICT_LOCATE=1 \
  python -m framework.cli run --case ai_orders_invoice_full_lifecycle_<时间戳>
```

**为什么**：该用例含 **150 秒真等待**（等订单自动关闭并落库，是 demo 的真实状态流转，不是卡住）。
**该值的默认已是 600**（2026-10-08 由 120 上调）—— 所以一般**不用设**；只有你要
**调小**、或想**显式固定**（不受将来默认值变化影响）时才写。设小了会在半途掐断，
**表现像用例失败，其实是超时设小了**。可调项全清单见 `python -m framework.cli config`。

**期望值对照（V8.5.1 基准 · 本机 1.87G 无 swap 实测）**：

| 命令 | 期望 | 耗时 |
|---|---|---|
| 上面那条端到端 | `1 passed` | ~220s |
| `pytest tests/ -q` | `1124 passed / 1 skipped`，0 failed | ~41s |
| `run_verifications.py` | 绝大部分通过；**唯一遗留 `verify_slow_target`**（慢环境缺陷，见 BACKLOG L22） | ~14 min |
| `run_acceptance.py` | 四项闸门全过 | — |

**手工走一遍（比看日志直观，5 步）**：

1. 浏览器开 `http://localhost:8000/orders.html?demo_role=order_admin`
2. 「+ 新建订单」→ 填 4 个行必填项（物料/产品/数量/行类型）→ 行保存 → 表单保存 → 提交
3. **等 150 秒**（订单自动关闭并落库 —— 真实状态流转，不是卡住）
4. 切角色到**发票管理员** → 订单列表勾选刚建那单 → 「去开票」→ 填客户/销售员/行类型/数量 → 行保存 → 提交发票
5. 去发票列表按订单名称搜 —— **能搜到那张发票** = 整条链路通 ✅

### 3. 配 DeepSeek key（**只有 AI 链路需要**）

```bash
# 项目根建 .env（可复制 .env.example）：
DEEPSEEK_API_KEY=sk-你的密钥
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-chat
```

> 用例驱动的主链路（probe → generate → run）**默认确定性、不需要 key**。
> 无外网机器要用 AI 链路 ⇒ 走**录像回放**（`build_tools/offline_explore_chain.py` + 随包发出的录像包）。

## 项目结构与链路

```
cases/（自然语言用例：manual/ 手写 · <场景id>/ AI）──generate──▶ scripts/generated/ + scripts/datasets/
   ▲ 手写（cases/manual/）                              │
   └── explore --ai ◀── AI 语义识别（场景/自然语言）      ▼
                                     cli run → pytest 并发 + web-first 断言
                                              + Tier1→Tier2 定位 + Healer 自愈
```

**两条链路**（汇合点 = `cases/` 下的用例文件 —— AI 产的用例和你手搓的用例，跑的是同一条确定性执行链）：

| # | 场景 | 入口 | 花 token |
|---|---|---|---|
| ① | 自然语言场景 → AI 语义识别 → 产出用例 → 执行 | **`all --ai`**（`--scenario` / `--scenario-file` / `--scenario-dir`） | ✅ |
| ② | 手搓 `cases/manual/*.json` → 生成脚本 + 数据分离 → 执行 | **`all`**（不带 `--ai`） | ❌ 零 token |

> **入口只有一条命令**：两条链路**共用 `all`**，**用 `--ai` 区分**，不另开命令。
> 单独用 `explore` / `generate` / `run` 仍可（调参、只跑某一段），但那是**辅助**，不是主线。

**目录职责**（逐文件说明见培训页第 2 章）：

```
cases/        用例（源）：manual/ 手搓用例 · <场景id>/ AI 用例（AI 产出也落这里，两者在此汇合）
scenarios/    AI 场景库：<模块>/<场景id>.yml（一个 yml = 一个场景）；字段契约见 scenarios/README.md
scripts/      generate 产物（可重建，别手改）：generated/（<场景id>/<用例id>.py + manual/ + _harness.py + conftest.py + index.json）· datasets/（抽离数据）
framework/    按**特性**聚合：features/f01..f11（每特性 api.py 是唯一入口，阶段看文件名后缀）· shared/（跨特性基础设施：配置/浏览器/登录/前置动作）· cli.py
demo/         被测 demo（合同/订单列表页 + 详情页 + 数据 API）
build_tools/  开发期工具：打包 · 培训页 · 录像体检/重录 · 离线链路
tests/        判据按**特性**分目录：特性1-…/ ... 特性11-…/（test_* 一类 + verify_* 二类同放一特性目录）
  ├─ _helpers/   共享辅助（artifacts / demo_freshness / repo_files / testid_policy）—— **不含 test_***
  └─ _runner/    run_verifications.py（二类入口）· run_acceptance.py（四项验收一条命令）
releases/     发行说明 RELEASE_NOTES_V*.md（变更日志的家）+ 交付包（包不入库）
docs/         training.html 培训页（对外文档）· feature_map.md 特性/子特性/用例映射表（自动生成，别手改）
output/ log/  运行时证据（element_maps / heals / traces / 逐用例日志 + report.html，可清理）
```

**断言 13 种**（`asserts[].kind`，缺省 = `text`）：`text` · `visible`/`hidden` · `count` · `attr` ·
`value` · `url` · `checked`/`unchecked` · `enabled`/`disabled` · **`first_row`**（表格第一行某列，
证明"它就是第一条"）· **`wait_text`**（有界等待式，等状态自动流转）。定位用 `element`（探测语义名）或
`selector`（手写用例专用，**AI 链路禁用**）。契约与示例见培训页第 4 章；样例用例见 `cases/orders_invoice_full_lifecycle/`（AI 用例）与 `cases/manual/`（手搓用例，按需自建）。

## 常见坑

新同学最容易踩的 10 条（完整清单见培训页第 7 章）：

1. **漏装浏览器** —— `pip install` 不装浏览器；跑 `python -m framework.cli setup`。
2. **改了 demo 不重启** ⇒ 验证跑在旧页面上（用例白跑）；二类入口会自己过新鲜度闸门。
3. **被测页面没声明就绪契约** ⇒ 慢页面上动作/断言早于渲染 ⇒ 假红。页面 `body` 置
   `data-hybrid-ready="1"`（**团队接自己系统时第一条要做的**，见培训页第 9 章）。
4. **AI 用例的断言不许依赖运行时计数**（如「共 N 条」）⇒ 落盘前会被质量闸拦下。
5. **未映射元素 = 显式失败**：`element` 必须是 `cli probe` 探到的语义名；映射不到会 `pytest.fail`，
   绝不静默跳过（少验一步还报绿 = 假绿）。
6. **别并发跑浏览器**（内存红线）：跑前确认 `MemAvailable ≥ 550MB`，不够就降并发，别用 `--force-workers` 硬闯。
7. **生成物别手改**：`scripts/generated/` 是 `generate` 的产物；改了模板要重跑 `generate`（模板是唯一来源）。
8. **跨进程/落盘文本一律显式 UTF-8**（中文 Windows 默认 gbk，出过交付事故）。
9. **改过框架的生成/探测代码后，必须先删产物再重跑**：`rm -f scripts/generated/*/*.py && python -m framework.cli generate`。
   原因：`generate` 的变化检测**认用例文件、不认框架代码升级** —— 不删会**静默跑旧产物**，白跑还看不出原因。
10. **demo 预置数据口径**：订单 **300 条（15 页 × 20）**、合同 200 条。跑测试会造脏数据，建议先复置：
    `curl -X POST 'http://localhost:8000/api/reset?purge=1'`（demo 自带隔离入口，**会先自动备份**）。

**报错 → 怎么办**：

| 报错 | 原因 | 怎么办 |
|---|---|---|
| `Executable doesn't exist at …ms-playwright…` | 没装浏览器 | `python -m framework.cli setup` |
| `先起被测应用：python -m demo.app` | 目标连不上 | 起 demo（或改 `HYBRID_BASE_URL` 指别的目标） |
| `仍未映射 [...]` | 语义名对不上 | 跑 `cli probe` 取正确语义名 |
| 元素「等了 5000ms 仍是 0 个」 | 页面慢 / 选择器漂移 | 查就绪契约；必要时调 `HYBRID_LOCATE_TIMEOUT` |
| 用例卡死不返回 | 目标无响应 | 看 `log/<run_id>/watchdog.txt`（看门狗写了调用栈） |

## 文档与资源

- **培训页 [`docs/training.html`](docs/training.html)**（团队主文档，由 `build_tools/build_html.py` 生成）：
  1 为什么是「混合」· 2 目录结构 · 3 整体流程 · 4 场景/用例怎么写 · 5 函数调用地图 ·
  6 框架特性设计实现（11 特性 / 49 子特性）· 7 常见坑 · 8 动手跑一遍（含**环境变量与运行开关**表）· 9 收尾
- **发行说明 [`releases/RELEASE_NOTES_V*.md`](releases/)**：每版改了什么（**变更日志都在这里**，随交付包一并发出）
- **字段契约**：`scenarios/README.md`（场景文件）+ 培训页第 4 章（用例文件）
- **框架判据**：`tests/_helpers/`（框架自验证，`test_*` 秒级、不需要 demo）+ `tests/_runner/`（特性自验证，`verify_*` 端到端且含**负向证伪**）
- 想动手扩展：模块 docstring 即接口说明，`framework/features/` 按**特性**聚合（f01..f11），
  阶段归属看**文件名后缀**（`*_explore/_probe/_generate/_run/_verify`，无后缀=阶段无关）；
  跨特性的基础设施（配置/浏览器/登录/前置动作）在 `framework/shared/`。同一特性只有 `api.py` 一个入口。

## 许可

**MIT License** —— 见 [`LICENSE`](LICENSE)。

```
Copyright (c) 2026 AprilPark1012
```

可自由使用、修改、分发（含商用），保留版权与许可声明即可。
