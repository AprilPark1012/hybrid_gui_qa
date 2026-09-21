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
| 一类自测 | `pytest tests/ -q` | **242 passed**（238 → +4：新增 import 目标判据） |
| 端到端（确定性链路） | `cli run`（19 个节点，**分批** 5 批跑） | **19 passed / 5 批全 exit 0**（共 29.2s） |
| 二类特性验证 | `bash tests/run_verifications.sh` | **7 条 ✅ / 3 条 ⏭️ SKIP（内存闸，未通过）** ⇒ 见下方逐条真值；⚠️ **SKIP ≠ 通过**，本版如实列为未验项，待内存富余时补跑 |
| 培训页同步 | `python build_tools/build_html.py` + `tests/verify_html_sync.py` | **exit 0**（三条判据全绿） |
| CLI 版本一致性 | `python -m framework.cli --version` ⇄ `VERSION_SOURCE` | `v8.0` ⇄ `build_tools/build_html.py` **一致** |
| import 目标存在性 | `pytest tests/test_import_targets.py -q` | **4 passed**（含 3 条负向自证） |
| 旧路径残留 | 全仓 grep `framework\.(config\|probe\|…)\b` | **当前代码/文档 0 命中**（仅 V8.0 迁移对照示例与历史发行说明保留，属有意） |
| 交付打包 | `python build_tools/pack_release.py --with-cassettes` + `sha256sum -c` | **两件套 2/2 OK**（自检含「版本 ⇄ 发行说明配套」） |

> ⚠️ **本版尚未达成的判据（如实记）**：计划判据 2 要求二类「10/10 全绿 · 0 跳过」，本次实跑为
> **7 ✅ / 3 ⏭️ SKIP**（`data_expand` / `element_ambiguity` / `slow_target`，全是**内存闸如实跳过**）。
> 本机 MemAvailable 长期 520~550MB（hermes 本体占 ~1GB，1.87G 无 swap）⇒ 这三条**待内存富余时补跑**；
> **不接受把 SKIP 当通过**，所以这里不写「二类全绿」。

> 📌 **打包器这次真的拦下了一件事**：版本号升到 V8.0 后第一次打包，包内自检报
> 「包内没有本次版本的 RELEASE_NOTES_V8.0.md」⇒ 拒绝出包。也就是说「**改了版本号忘写发版说明**」
> 这条以前靠自觉的事，现在有闸门了（本文件就是被它逼出来的）。

### 二类逐条真值（`tests/run_verifications.sh`）

| 脚本 | 结果 |
|---|---|
| verify_assert_kinds.py | exit 0（正向 4 passed；**负向 15 条全部 FAILED**，无假绿） |
| verify_cross_page.py | exit 0 |
| verify_data_expand.py | ⏭️ **exit 3 SKIP**（内存闸 533MB < 550MB）—— **未通过，待腾内存补跑** |
| verify_element_ambiguity.py | ⏭️ **exit 3 SKIP**（内存闸 520MB < 550MB）—— 静态判据已过（5/5），浏览器级判据**未跑** |
| verify_html_sync.py | ✅ exit 0（本版从 exit 1 转绿 —— 三同步生效） |
| verify_offline_delivery.py | ✅ exit 0（两件套都能打出来 + 内容齐 + 清单与事实一致；本版首次被「版本 ⇄ 发行说明配套」闸门拦过一次） |
| verify_order_pages.py | ✅ exit 0（订单页与弹层，46 条判据全过） |
| verify_order_pick_create.py | ✅ exit 0（弹层选客户/销售员，58/58 判据） |
| verify_picker_layer.py | ✅ exit 0（弹层收集 6/6 + 探完关闭 + 有界轮询） |
| verify_slow_target.py | ⏭️ **exit 3 SKIP**（该脚本自带 650MB 闸门）—— **未通过，待腾内存补跑** |

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
