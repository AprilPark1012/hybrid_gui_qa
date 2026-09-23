# hybrid_gui_qa — LLM 驱动的混合 GUI 自动化测试框架

> 当前版本 **V8.2.4**（2026-09-23）· 版本号单一来源 = `build_tools/build_html.py` 顶部 `VERSION`
> · 变更记录见 [`releases/RELEASE_NOTES_V*.md`](releases/) · 团队培训页（**先看这个**）：[`docs/training.html`](docs/training.html)

**一句话**：把 **Browser Use（AI 智能探索）** 和 **Playwright（确定性执行）** 组合成一套混合测试框架 ——
AI 负责理解意图、规划步骤、挑元素；Playwright 负责精确定位、唯一性校验、可复现回归。

**核心哲学**：**让 AI 做理解和决策，让确定性代码做精确定位，绝不把「定位」交给 LLM。**

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

| 能力 | Browser Use（AI） | Playwright（确定性） |
|---|---|---|
| 理解自然语言测试意图 | ✅ 强 | ❌ |
| 规划步骤 / 挑元素 | ✅ 强 | ❌ |
| 精确定位元素 | ❌ 可能幻觉 | ✅ 准 |
| 唯一性校验 / 防误点 | ❌ | ✅ |
| 可复现回归 / 进 CI | ❌ | ✅ |

业界在做同一件事（Stagehand / Playwright Test Agents）：*"Selectors break. Natural language doesn't."* ——
但自然语言只能用于**理解**，真正执行必须落到确定性 locator。

**它服务两件事**：① 让测试同学少写代码（自然语言 → 用例 → 脚本，降人力）；② 让 AI 产出**可信**
（AI 只挑语义名，定位与校验全由确定性代码做 ⇒ **AI 不可能点错控件还报绿**）。

## 快速上手

### 0. 一条命令搞定环境（推荐；装依赖 + 装浏览器 + 自检）

```bash
pip install -r requirements.txt        # 核心三件套：playwright / python-dotenv / pytest
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
python -m framework.cli all --workers 2       # probe → generate → run 一条龙（确定性，零 token）
python -m framework.cli run --debug           # 调试开关：有屏幕弹浏览器；没屏幕录视频 + 逐步截图
python -m framework.cli run --case search_mixed        # 只跑指定用例（--case 可重复）
python -m framework.cli explore --ai --scenario "在搜索框输入'1005'点搜索，确认出现 HT-1005"
                                              # AI 链路：自然语言 → cases/ai_*.json（落盘后默认试跑）
python -m framework.cli prune --dry-run       # 归档保留（log/ 与 output/verify/ 按 30 个 ∪ 7 天清理）
python -m framework.cli --help                # 参数写错一律报错 + exit 2，绝不静默忽略
```

**两类验证**（改完东西跑这两条）：

```bash
python -m pytest frameworkTest/ -q                    # ① 框架自测：秒级，不需要 demo / key
python featureTest/run_verifications.py             # ② 端到端特性验证：需 demo（会自己起停；SKIP ≠ 通过）
python featureTest/run_acceptance.py                # ③ 四项验收一条命令（闸门 → 新鲜度 → 自测 → E2E → 特性）
```

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
cases/*.json（自然语言用例）──generate──▶ scripts/test_cases.py + scripts/datasets/*.json
   ▲ 手写                                        │
   └── explore --ai ◀── AI 语义识别（场景/自然语言）  ▼
                                     cli run → pytest 并发 + web-first 断言
                                              + Tier1→Tier2 定位 + Healer 自愈
```

**两条链路**（汇合点 = `cases/*.json` —— AI 产的用例和你手搓的用例，跑的是同一条确定性执行链）：

| # | 场景 | 入口 | 花 token |
|---|---|---|---|
| ① | 自然语言场景 → AI 语义识别 → 产出用例 | `explore --ai --scenario` / `--scenario-file` / `--scenario-dir` | ✅ |
| ② | 手搓 `cases/*.json` → 生成脚本 + 数据分离 → 执行 | `generate` / `run` / `all` | ❌ 零 token |

**目录职责**（逐文件说明见培训页第 2 章）：

```
cases/        手写自然语言用例（源）· scenarios/  AI 场景库（一个 yml = 一个场景）
scripts/      generate 产物（可重建，别手改）· framework/  cli.py + tools/{common,probe,explore,generate,run}
demo/         被测 demo（合同/订单列表页 + 详情页 + 数据 API）
build_tools/  开发期工具：打包 · 培训页 · 录像体检/重录 · 离线链路
frameworkTest/  框架自验证：test_*（秒级、不需 demo/浏览器）+ 共享辅助
featureTest/    特性自验证：verify_*（端到端、需 demo）+ run_verifications.py / run_acceptance.py 两个入口
releases/     发行说明 RELEASE_NOTES_V*.md（变更日志的家）+ 交付包（包不入库）
docs/         training.html 培训页（仓库里唯一的对外文档）
output/ log/  运行时证据（element_maps / heals / traces / 逐用例日志 + report.html，可清理）
```

**断言 11 种**（`asserts[].kind`，缺省 = `text`）：`text` · `visible`/`hidden` · `count` · `attr` ·
`value` · `url` · `checked`/`unchecked` · `enabled`/`disabled`。定位用 `element`（探测语义名）或
`selector`（手写用例专用，**AI 链路禁用**）。契约与示例见培训页第 4 章 + `cases/assert_kinds_*.json`。

## 常见坑

新同学最容易踩的 8 条（完整清单见培训页第 8 章）：

1. **漏装浏览器** —— `pip install` 不装浏览器；跑 `python -m framework.cli setup`。
2. **改了 demo 不重启** ⇒ 验证跑在旧页面上（用例白跑）；二类入口会自己过新鲜度闸门。
3. **被测页面没声明就绪契约** ⇒ 慢页面上动作/断言早于渲染 ⇒ 假红。页面 `body` 置
   `data-hybrid-ready="1"`（**团队接自己系统时第一条要做的**，见培训页第 9 章）。
4. **AI 用例的断言不许依赖运行时计数**（如「共 N 条」）⇒ 落盘前会被质量闸拦下。
5. **未映射元素 = 显式失败**：`element` 必须是 `cli probe` 探到的语义名；映射不到会 `pytest.fail`，
   绝不静默跳过（少验一步还报绿 = 假绿）。
6. **别并发跑浏览器**（内存红线）：跑前确认 `MemAvailable ≥ 550MB`，不够就降并发，别用 `--force-workers` 硬闯。
7. **生成物别手改**：`scripts/` 是 `generate` 的产物；改了模板要重跑 `generate`（模板是唯一来源）。
8. **跨进程/落盘文本一律显式 UTF-8**（中文 Windows 默认 gbk，出过交付事故）。

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
  2 目录结构 · 3 整体流程 · 4 场景/用例怎么写 · 5 函数调用地图 · 6 关键设计图例 · 7 框架特性说明 ·
  8 常见坑 · 9 动手跑一遍（含**环境变量与运行开关**表）· 10 收尾
- **发行说明 [`releases/RELEASE_NOTES_V*.md`](releases/)**：每版改了什么（**变更日志都在这里**，随交付包一并发出）
- **字段契约**：`scenarios/README.md`（场景文件）+ 培训页第 4 章（用例文件）
- **框架判据**：`frameworkTest/`（框架自验证，`test_*` 秒级、不需要 demo）+ `featureTest/`（特性自验证，`verify_*` 端到端且含**负向证伪**）
- 想动手扩展：模块 docstring 即接口说明，`framework/tools/` 按业务流程分层（probe → explore → generate → run）

## 许可

**MIT License** —— 见 [`LICENSE`](LICENSE)。

```
Copyright (c) 2026 AprilPark1012
```

可自由使用、修改、分发（含商用），保留版权与许可声明即可。
