# scenarios/ —— AI 语义识别的场景库

**一个文件 = 一个场景**；文件名 = 场景 id（小写蛇形 `^[a-z][a-z0-9_]*$`）。
`explore --ai` 读这些文件 → AI 语义识别 → 产出可执行用例 `cases/ai_<id>_<HHMMSS>.json`。

设计说明见内部设计文档「scenario 文件设计」（含字段表、设计逻辑、分期）。

## 用法

```bash
# 单个场景
python -m framework.cli explore --ai --scenario-file scenarios/contracts/contracts_search_by_no.yml

# 目录批量（递归扫；--tag 可重复，OR 语义；--limit 限流）
python -m framework.cli explore --ai --scenario-dir scenarios/ --tag smoke
python -m framework.cli explore --ai --scenario-dir scenarios/ --limit 3 --no-verify

# 内联（原样保留，不进场景库的临时想法用这个）
python -m framework.cli explore --ai --scenario "在搜索框输入'1005'点搜索，确认出现 HT-1005"
```

三者**互斥**：`--scenario` / `--scenario-file` / `--scenario-dir` 只能给一个，同时给会报错退出（exit 2）。
`--verify`（默认开）：用例落盘后立刻试跑，实测 FAILED → ❌ + exit 3（`--no-verify` 可跳过）。

## 字段（只有 `scenario` 必填）

| 字段 | 谁读 | 说明 |
|---|---|---|
| `id` | 框架/人 | 稳定标识（缺省取文件名）；用于 case_id 命名 + 溯源 |
| `title` / `description` / `owner` / `updated` / `notes` | 人 | 标题、说明、责任人、更新时间、备注 |
| `tags` | 框架 | `--tag` 过滤（如 `[合同, 搜索, smoke]`） |
| `priority` | 框架 | `P0/P1/P2`，目录批量时按此排序 |
| `target.url` | 框架 | 缺省用 `config.TARGET_URL` |
| `target.page` | AI | 页面的人话描述（喂 prompt） |
| `target.preconditions` | 人/AI | 前置条件（一期只作为 AI 上下文，不自动执行） |
| `scenario` | **AI（必填）** | 自然语言动作流（YAML 块标量 `|` 支持多行） |
| `business_context` | AI | 领域知识：字段含义、编号规则、易踩的坑 |
| `assert_guard.must_contain` | AI+质量闸 | 断言必须围绕的**稳定文本**（操作前可确定）；喂 prompt + 落盘硬校验 |
| `assert_guard.forbidden` | AI+质量闸 | 本场景禁止出现在断言里的内容 |
| `data` | ✅ 已支持（2026-09-21） | **参数化：一组数据 = 一条独立用例**（报告独立一行、失败能定位到具体数据集）。写法：场景文案里写 `{占位符}`，这里每组给一组值；组名可选（`id`，进报告用例名）。**组值必须恰好覆盖文案里用到的占位符**（少了会被拦——未解析的 `{xxx}` 会被原样填进页面） |

## 写作要点（血泪教训）

1. **断言必须"操作前可确定"**：写记录标识（`HT-1005`）或页面固定文案，**别写运行时才知道的计数**
   （`共 N 条`）。全局已禁计数/时间戳/随机值，`assert_guard` 里可再加本场景专属禁令。
2. **`business_context` 越具体，AI 挑控件越准**：把 placeholder、可选值、编号规则写进去。
3. `must_contain` 会**双向生效**：事前告诉 AI 该围绕什么写断言，事后校验断言是否真的验到了它。
4. 场景跑不通时，先改场景文件（这是正常的编写循环），而不是去改框架。

## 写场景前先知道被测应用（demo）的三件事（2026-09-14 起）

1. **数据在服务端**（`demo/app.py` 的 `/api/*`）：列表页与详情页读的是**同一条真实记录** ⇒
   预置数据的七个字段跨页一致，可以断言（如客户：列表页 `data-cust=c5` ⇔ 详情页 `data-cust=c5`）；
   查不到的编号会如实报「未找到」，**不会**编数据。
2. **每条用例开始前框架会复位数据**（`POST /api/reset`）⇒ 列表页固定 20 条预置；
   **别写「上一条用例新建的数据留给下一条用」这种跨用例依赖**（复位后就不存在了）。
3. **客户字段是「弹层列表里选一行」**：弹层里 6 个「选择」按钮文字完全相同 ⇒ 语义名形如
   `选择@北京华信科技有限公司`；列表页客户筛选是输入框 + **右模糊（前缀）匹配**（「华信」这种非前缀不命中）。
