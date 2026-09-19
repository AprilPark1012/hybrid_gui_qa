# hybrid_gui_qa V7.7.1 升级说明（2026-09-19）

> 版本号单一来源：`tools/build_html.py` 顶部 `VERSION` / `VERSION_DATE` / `CHANGELOG`
> （`python -m framework.cli --version` 读同一处；**路径只定义在** `framework/config.py::VERSION_SOURCE`）。
> 本文件随交付包一起发。
> 上一版：V7.7（元素歧义闸门 · 弹层两种选中方式 · 离线 AI 链路）。

## 一句话
本版**不加新能力**，只做三件事：① 把仓库结构按「框架代码 / 内部台账 / 门禁」**三层分开**；
② 工具收进 `tools/`、**版本号来源路径收敛成只定义一处**；③ 修掉**四处「静默退化」**——
共同特征是「看着正常、其实没在干活」，正是本项目一直在打的假绿。

## 一、结构：三层分离 + `tools/` 工具目录

| 层 | 在哪 | 随包交付 |
|---|---|---|
| 框架代码（含 demo / 用例 / 生成物 / 培训页） | 本仓库 | ✅ |
| 项目台账（BACKLOG）· 设计文档 | 已移出仓库（住内部知识库） | ❌ |
| 敏感词门禁与词表 | 内部知识库 | ❌ |

- 仓库 `docs/` 现在**只放一个文件**：`training.html`（唯一对外文档）。
- **`tools/` = 框架自己的工具**：`pack_release.py`（交付打包器）+ **`build_html.py`**（培训页生成器，本版从仓库根挪入）。

## 二、版本号来源路径收敛为一处

- 新增 `framework/config.py::VERSION_SOURCE`；`cli` / `llm_cassette` / `pack_release` **三个读者共用**。
- 为什么重要：原先三处各写一遍路径 —— 文件一挪位置，只要漏改一处，`--version` 或打包版本号就**静默变成
  `unknown`**。现在判据钉住：三读者必须读到同一版本（含负向：路径失效必须如实 `unknown`，**不许编**）。

## 三、四处静默退化（本版真正修的东西）

| # | 现象 | 根因 | 修法 |
|---|---|---|---|
| 1 | 培训页代码高亮**畸形嵌套**（已发布页实测 **2381 处** `<span <span`） | 三趟 `re.sub` 串着跑：关键字那趟在**已注入的 HTML** 上再跑，把 `class` 又包一层 | 改**单遍分词** |
| 2 | 培训页**生成不可复现**（同一份代码两次生成 md5 不同，差 140 行） | 关键字集合是 `set`，同长度词序由**哈希**决定 | 同上（排序与哈希无关）⇒ 现在「重跑无 diff」才能当作同步判据 |
| 3 | **字符串高亮一直是死的**（实测 0 处） | 先 `html.escape` 把引号变实体，字符串正则永远匹配不上 | 先分词、后转义 |
| 4 | 一条**负向验证段自 V7.5.1 起没跑过** | 负向用例故意用「不存在的控件名」⇒ 映射质量闸把整个 `generate` 拦成 exit 2 ⇒ 负向段**一步没跑**、脚本自己变红 | 负向段改走 `--allow-unmapped`（修后**负向 15 条全部 FAILED** = 预期） |
| 5 | 一条自测**隐式依赖环境**（1.16s ↔ **162.71s**） | GBK 解码用例会先 `generate` ⇒ 本机恰好有 demo 时真去 probe（起浏览器）= 二类悄悄混进一类 | 钉确定性不可达目标 + 收紧判据（必须真解码到中文） |

> 另修一个**误报**：打包器用当前必需项清单去审**结构变更前**的包，会报「缺 `tools/build_html.py` /
> `docs/training.html`」—— 历史包按当时结构打包本就正常。按「升级日志两种落点都认」的先例加**历史形态
> 别名**（命中时如实标出 `◐`、不拦），**真缺项仍照拦**（有负向判据）。

## 四、新增判据与入口（测试的测试）

- `tests/run_verifications.sh`：特性验证**统一入口** —— 逐个跑 `verify_*.py`、内存不足**如实 SKIP**
  （exit 3，**不当通过**）、跑完出汇总表；支持 `--only` / `--list` / `--no-demo`。
- `tests/verify_html_sync.py`：培训页必须 ① 可复现 ② 与代码**逐字节一致** ③ 零畸形嵌套。
- 仓库与敏感词门禁**解耦**判据（仓库零引用门禁路径/词表 + 三个钩子不得被跟踪）。
- 打包**历史形态**兼容判据（真假两面：历史包不误报 / 真缺项仍拦）。
- 培训页高亮器 9 条（含**跨进程可复现性**，旧实现必挂）。

## 五、离线 AI 链路：交付形态 = **两件套**（本版补齐）

连不上外网 LLM 的工作电脑，靠**录像回放**跑完整 AI 链路（V7.7 起的机制）。本版补齐的是**交付形态**：
此前录像包由一个**仓库外的独立脚本**打，没有判据、交付形态全靠人记 —— 实测后果是「把新代码包单独发给
团队，对方根本跑不起来（缺录像数据），而没人会发现」。

| 件 | 内容 | 打什么命令 |
|---|---|---|
| ① **代码包** | 回放引擎 `framework/llm_cassette.py` + 一键脚本 `tools/offline_explore_chain.py`（本版**收进仓库**） | `python tools/pack_release.py` |
| ② **录像包** | `llm_cassettes/*.json`（LLM 的 prompt→回答 原件）+ 用法说明（含三条铁律） | `python tools/pack_release.py --with-cassettes` |

- 录像包**独立**（`output/` 永不进代码包 —— 运行时数据不进交付物），清单与 sha256 由打包器
  **自动同步**到 `releases/SHA256SUMS.txt`（手抄 sha256 是典型错误源）。
- 交付形态有判据：`python tests/verify_offline_delivery.py`（两件都能打出来 · 内容齐 · 清单与事实一致）。
- **本机实测（2026-09-19）**：`python tools/offline_explore_chain.py --repo . --scenario
  scenarios/contracts/contracts_search_by_no.yml --run` → 前置检查全过 · 回放命中结构键
  `01639efd…`（端点指黑洞 `127.0.0.1:9`，证明没联网）· 用例带 `llm_source=cassette:…` ·
  `generate` 未映射 0 · **run 1 passed / exit 0**。

## 六、验证（都是真跑，可复现）

```
一类 框架自测    pytest tests/ -q                  → 217 passed
                 （有 demo 13.49s / 无 demo 12.98s —— 两环境一致）
二类 特性验证    bash tests/run_verifications.sh    → 8/8 通过（0 跳过 0 失败）
R8   文档同步    python tests/verify_html_sync.py   → ①✓ 可复现 ②✓ 逐字节一致 ③✓ 零畸形
打包 包内自检    python tools/pack_release.py       → 见 releases/SHA256SUMS.txt
门禁 端到端      敏感词门禁 28/28 · 推送闸门三层干净 · 对象对账 330/330
```

## 七、升级注意（会影响到你的命令）

1. **生成培训页的命令变了**：`python tools/build_html.py`（原来是 `python build_html.py`）。
2. 若你的脚本/CI 里引用旧路径，请改指 `tools/build_html.py`；**读版本号请走
   `framework.config.read_version()`**，别再自己拼路径读文件。
3. **本包不含敏感词门禁本体**（门禁与词表在内部知识库，仓库内零痕迹）—— 包内只有框架代码与对外文档。
4. 用例库与生成物（`scripts/`）与上版一致，**无需重新 `generate`**。
