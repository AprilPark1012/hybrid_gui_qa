# hybrid_gui_qa V8.0 升级说明（2026-09-21）

> 版本号单一来源：`build_tools/build_html.py` 顶部 `VERSION` / `VERSION_DATE` / `CHANGELOG`
> （`python -m framework.cli --version` 读同一处；**路径只定义在** `framework/tools/common/config.py::VERSION_SOURCE`）。
> 本文件随交付包一起发。
> 上一版：V7.8（数据参数化「真展开」）。

## 一句话

本版**不加新能力**，只做一件事：把 `framework/` 从「平铺 17 个模块」改成**按业务流程分层**
（探测 → AI 识别 → 生成 → 执行），让目录结构自己讲清链路顺序。CLI 参数、断言体系、报告形态、
用例格式**零变化**。

> ⚠️ **这是本项目第一个破坏性变更（breaking change）**：模块 import 路径变了，且**不留兼容 shim**。
> 只有「自写脚本里 `import framework.xxx`」这一种情况需要你改一行；`cases/` / `scenarios/` / demo 一个字都不用动。

## 一、新结构（分层）

```
framework/
├── __init__.py
├── cli.py                          唯一入口（原样：probe / generate / run / all / explore / prune）
└── tools/                          运行期模块
    ├── common/                    基建（零业务语义）
    │   ├── config.py              配置 + 目录常量 + LLM 选择（含 VERSION_SOURCE）
    │   ├── text_io.py             跨平台文本口径唯一入口（显式 UTF-8）
    │   ├── browser.py             Chromium 启动参数唯一来源
    │   ├── limits.py              并发安全闸（按可用内存自动降级 worker 数）
    │   ├── retention.py           归档保留（快照各留最近 N 个）
    │   └── target_probe.py        目标可达性 / 并发安全预检
    ├── probe/                     ① 探测与定位
    │   ├── probe.py               ✅ [Playwright] 确定性元素探测
    │   ├── element_map.py         数据契约（ElementRef / TestStep / ElementMap）
    │   └── locator_bridge.py      ✅ [Playwright] 语义 → 唯一 locator（核心）
    ├── explore/                   ② AI 语义识别
    │   ├── explorer.py            🤖 [AI] 语义识别（读场景 + probe 清单 → 步骤）
    │   └── llm_cassette.py        LLM 录像/回放（离线机器：不联网、不需要 key）
    ├── generate/                  ③ 用例与脚本生成
    │   ├── generator.py           ✅ 按操作类型翻译 + 抽离数据 → scripts/
    │   ├── case_builder.py        🤖 ElementMap → cases/ai_*.json + 用例质量闸（防假绿）
    │   ├── scenario.py            🗂 scenarios/*.yml 解析/校验/发现（需 PyYAML）
    │   └── data_driven.py         🧩 占位符替换 + 变量池 + 数据真展开
    └── run/                       ④ 执行与自愈
        ├── runner.py              ✅ ElementMap 场景执行引擎（run_scenario）
        └── healer.py              🩹 自愈闭环（再协商 + 业务断言兜底 + 可审 diff）
```

**依赖方向**（AST 实测，全部单向、无环）：

```
common  ← 零内部依赖（retention → config 同层）
probe   ← common
explore ← common, probe（explorer → llm_cassette 同层）
generate← common, probe, explore（generator → explorer）
run     ← common, probe（healer → locator_bridge 在 probe 层）
cli     → 全部 12 个模块
```

## 二、唯一破坏点：import 路径

| 旧写法 | 新写法 |
|---|---|
| `from framework.config import …` | `from framework.tools.common.config import …` |
| `from framework.probe import …` | `from framework.tools.probe.probe import …` |
| `from framework.explorer import …` | `from framework.tools.explore.explorer import …` |
| `from framework.generator import …` | `from framework.tools.generate.generator import …` |
| `from framework.runner import …` | `from framework.tools.run.runner import …` |

（17 个模块同构映射：`framework/<模块>.py` → `framework/tools/<层>/<模块>.py`。完整映射表见内部设计文档 P11 §二。）

- **不留 shim**：旧路径 import 会直接 `ModuleNotFoundError` —— 故意的，避免「两套路径并存」长期漂移。
- CLI、生成物、`pytest scripts/test_cases.py` 的用法**完全不变**；`scripts/` 已用新路径重建。

## 三、开发期工具进 `build_tools/`

原仓库根 `tools/` → **`build_tools/`**：`pack_release.py`（交付打包器）· `build_html.py`（培训页生成器，
**版本号单一来源**）· `offline_explore_chain.py`（离线一条命令）。
改名理由：与运行期的 `framework/tools/` 区分 —— 这两个 `tools` 一个是「框架自己的开发工具」，
一个是「框架运行时按业务流程分层的模块」，同名会长期混淆。

**命令变化（只有路径前缀）**：

```bash
python build_tools/build_html.py                         # 培训页生成（原 tools/build_html.py）
python build_tools/pack_release.py --with-cassettes       # 打包（原 tools/pack_release.py）
python build_tools/offline_explore_chain.py --repo . --run  # 离线一条命令（原 tools/…）
```

## 四、顺带修掉的两处「静默指错」

| # | 问题 | 根因 | 修法 |
|---|---|---|---|
| 1 | `config.py::BASE` 指向错目录 | 原按 `parent.parent` 推仓库根；模块挪深两层后**不报错、只指错** | 改成「向上找 `pyproject.toml`」的标记法（结构再变也不会错） |
| 2 | 会话体检脚本版本探针失效 | `from framework.config import VERSION_SOURCE` 导入失败后**静默退回硬编码旧路径** | 取不到就如实报「未验」并指出新模块路径（仓库外脚本，随内部工具链） |

两处的共同特征还是本项目一直在打的那类问题：**看着正常、其实没在干活**。

## 五、新增判据（测试的测试）

| 判据 | 位置 | 验什么 |
|---|---|---|
| **AST import 目标存在性**（本版新增） | `tests/test_import_targets.py`（一类，秒级） | 全仓 `.py` 的 import 目标必须在磁盘真实存在 ⇒ 结构漏改一次抓出；含 **3 条负向自证**（旧路径 `framework.probe` 必须判不存在 · 假仓库里写坏的 import 必须被点名 · `framework/` 下不许再有平铺模块） |
| 培训页与代码同步 | `tests/verify_html_sync.py` | 可复现（换哈希种子 md5 相同）+ 与代码逐字节一致 + 零畸形 span |
| 打包器版本与发行说明配套 | `build_tools/pack_release.py` 包内自检 | **版本号改了但 `releases/RELEASE_NOTES_V<版本>.md` 没写 ⇒ 拒绝出包**（本版实测拦住过一次，见 §六） |

## 六、验证（都是真跑，2026-09-21 实机）

| 验证 | 命令 | 结果 |
|---|---|---|
| 一类自测 | `pytest tests/ -q` | **267 passed**（242 → +25：新增 R9 搬家判据 + demo 新鲜度闸门；2026-09-21 傍晚修订后实测） |
| 端到端（确定性链路） | `cli run`（19 个节点，**分批** 5 批跑） | **19 passed / 5 批全 exit 0**（共 29.2s） |
| 二类特性验证 | `bash tests/run_verifications.sh`（统一入口） | **11 条 ✅ / 0 ⏭️ SKIP（全绿）**（2026-09-21 傍晚修订后实测，含新增的 demo 新鲜度闸门；逐条真值见 §八） |
| 培训页同步 | `python build_tools/build_html.py` + `tests/verify_html_sync.py` | **exit 0**（三条判据全绿） |
| CLI 版本一致性 | `python -m framework.cli --version` ⇄ `VERSION_SOURCE` | `v8.0` ⇄ `build_tools/build_html.py` **一致** |
| import 目标存在性 | `pytest tests/test_import_targets.py -q` | **4 passed**（含 3 条负向自证） |
| 旧路径残留 | 全仓 grep `framework\.(config\|probe\|…)\b` | **当前代码/文档 0 命中**（仅 V8.0 迁移对照示例与历史发行说明保留，属有意） |
| 交付打包 | `python build_tools/pack_release.py --with-cassettes` + `sha256sum -c` | **两件套 2/2 OK**（自检含「版本 ⇄ 发行说明配套」） |

> ✅ **判据 2 达成路径（如实记）**：全量套件首跑时 3 条被内存闸 SKIP，随后逐条补跑转绿 ——
> `verify_element_ambiguity.py` exit 0 · `verify_data_expand.py` exit 0 ·
> `verify_slow_target.py` exit 0（这条要先腾到 ≥650MB：停 dashboard ≈108MB → 仍差 16MB（634MB）⇒
> 再临时停 `april` 网关 262MB → 718MB 才跑得起来；**两处服务跑完均已原样恢复**，验收为 active / HTTP 200）。
> 📎 补跑命令：`python tests/verify_<x>.py`（单条）或 `bash tests/run_verifications.sh --only <名字>`。
>
> ⚠️ **本机内存红线（别忽略）**：1.87G / 无 swap，hermes 本体常占 ~1GB ⇒ 浏览器类验证前必看 `MemAvailable`；
> 低于闸门的脚本会**如实 SKIP（exit 3）而不是硬跑**，**SKIP 不等于通过**；全量一次跑 19 条会 OOM
> （实测 Playwright 驱动内部崩溃 + 用例挂死）⇒ 正解是**每批 ≤5 条、独立进程、批间释放浏览器**。

> 📌 **打包器这次真的拦下了一件事**：版本号升到 V8.0 后第一次打包，包内自检报
> 「包内没有本次版本的 RELEASE_NOTES_V8.0.md」⇒ 拒绝出包。也就是说「**改了版本号忘写发版说明**」
> 这条以前靠自觉的事，现在有闸门了（本文件就是被它逼出来的）。

### 二类逐条真值（`tests/run_verifications.sh`）

| 脚本 | 结果 |
|---|---|
| verify_assert_kinds.py | exit 0（正向 4 passed；**负向 15 条全部 FAILED**，无假绿） |
| verify_cross_page.py | exit 0 |
| verify_data_expand.py | ✅ **exit 0**（补跑：3 组数据 → 3 条独立用例 · 参数名可读 · 坏组只红那一行 · 单组可跑 · 收尾仓库零残留） |
| verify_element_ambiguity.py | ✅ **exit 0**（补跑：静态判据 5/5 + 浏览器级「复现旧病形态 / 新行为拦得住 / 既有唯一名未误伤」） |
| verify_html_sync.py | ✅ exit 0（本版从 exit 1 转绿 —— 三同步生效） |
| verify_offline_delivery.py | ✅ exit 0（两件套都能打出来 + 内容齐 + 清单与事实一致；本版首次被「版本 ⇄ 发行说明配套」闸门拦过一次） |
| verify_order_pages.py | ✅ exit 0（订单页与弹层，46 条判据全过） |
| verify_order_pick_create.py | ✅ exit 0（弹层选客户/销售员，58/58 判据） |
| verify_picker_layer.py | ✅ exit 0（弹层收集 6/6 + 探完关闭 + 有界轮询） |
| verify_slow_target.py | ✅ **exit 0**（补跑：内存腾到 **718MB** 后跑起来 —— 300ms/请求 的慢目标下 **6 条全绿**，F1 就绪契约 + F2 有界等待生效；证据 `log/slowgate_20260921_172648/`） |

> ⚠️ **内存红线（本机 1.87G / 无 swap，别忽略）**：跑浏览器类验证前看 `MemAvailable`
> —— 低于闸门的脚本会**如实 SKIP（exit 3）而不是硬跑**；**SKIP 不等于通过**，要腾内存重跑。
> 本机 hermes 本体常占 ~1GB，全量一次跑 19 条用例会触发 OOM（实测 Playwright 驱动内部崩溃 +
> 用例挂死）⇒ 正解是**每批 ≤5 条、独立进程、批间释放浏览器**。

## 七、升级须知（会影响到你的命令）

1. **`cases/` / `scenarios/` / demo**：**一个字都不用改**。
2. **自写调试脚本**：若 `import framework.xxx`，按 §二 映射表改一行路径（或 `cli` 用法不变，直接用 `python -m framework.cli`）。
3. **重跑一次 generate**：`python -m framework.cli generate` —— 生成物 `scripts/` 里的 import 也是新路径。
4. **开发期命令**：路径前缀从 `tools/` 改为 `build_tools/`（见 §三）。
5. **离线机器**：录像包与代码包用法不变（两件套都在，一键脚本换成 `build_tools/offline_explore_chain.py`）。

## 八、本日修订（2026-09-21 傍晚）

本版在同日做了三处修订（**包已重打**，sha256 见 `releases/SHA256SUMS.txt`）：

| # | 内容 | 为什么（问题形态 → 处置） |
|---|---|---|
| 1 | **新增 R9「搬家协议」的自动判据** `tests/test_no_stale_paths.py` | 结构重构（`tools/` → `build_tools/`、模块按业务流程分层）之后，「**还有谁在指旧位置**」必须能自动回答，不能靠人工 grep。判据覆盖 6 种旧路径形态（旧平铺 import / 旧模块路径 / 旧开发工具目录 / 旧命令写法 / 指向已移出仓库的设计文档与台账）并逐条负向自证；历史记录与对照示例用行/块标记豁免，**豁免清单不许腐化**（条目不存在即判据报错） |
| 2 | **新增 demo 新鲜度闸门**（`tests/demo_freshness.py` + 一类判据 + 二类验证 + 统一入口接线） | demo 是常驻进程：改了 `demo/app.py` / `demo/*.html` 却没重启 ⇒ 端到端验证**跑在旧页面上** —— 用例白跑，而且给出「看着通过/看着失败」的误导性结论。现在跑二类前自动比对「demo 源码最新 mtime vs 进程启动时刻」（从 `/proc` 精确取）：不新鲜就自动重启并复检，重启后仍不新鲜则**停手**，绝不在旧版本上继续跑 |
| 3 | **修掉 7 处指向旧位置的活引用** | 含 2 处指向已移出仓库设计文档的**失效指针**（源码注释，含生成物模板同源句 ⇒ 已重建生成物）、2 处「照抄会失败」的命令提示（README 与测试里的 `python build_html.py`）、以及 `.gitignore` / `scenarios/README.md` / `requirements-ai.txt` 里的旧路径 |

**修订后的验证真值（都是真跑）**：一类 `pytest tests/ -q` → **267 passed** · 二类 `bash tests/run_verifications.sh` → **11/11 exit 0 · 0 SKIP** ·
培训页同步 `tests/verify_html_sync.py` → **exit 0** · 端到端 `cli run`（19 节点分批）→ **19 passed**。

