# hybrid_gui_qa V7.6 交付说明（2026-09-18）

> 一句话：**跨窗口业务流程版** —— 框架第一次能跑「点链接开新 tab → 在另一个页面填单 → 回到原 tab」这类真实流程，
> 并顺手修掉两处**不会报错却会出错**的 AI 规划缺陷。
> ① 同字段在**筛选区与弹窗里各有一个控件、名字却完全不同**时，AI 会把弹窗字段选成筛选区那个
>   （两个名字都能映射到真实控件 ⇒ 既没有「未映射」告警，也没有同名告警；实测连跑 6 次、6 次全错）；
> ② 跨页重名原始名的告警按**全局并集**判定 ⇒ 把别的用例带进来的重名算到本用例头上，两条手写跨页用例假红。
> **定位链路与既有用例零改动**（用例文件一字未改），升级只需替换代码并重跑一次 `cli generate`。

---

## 一、本版新增能力（三块，都由订单场景逼出来）

| 能力 | 落点 | 为什么必须有 |
|---|---|---|
| **跨 tab（多窗口）** | 探针 `probe.opens_new_tab`（`<a target="_blank">` / `window.open` ⇒ 点击会开新 tab）· 动作 `click_new_tab` / `close_tab` · 生成脚本 `_Tabs`（切/关句柄 + **回读「真的关了没」**） | 「会不会开新 tab」是 DOM 事实，**不该让 LLM 猜**；猜错就会「点完还留在原页继续点」，后面全乱 |
| **行内定位** | `probe.probe_row_fields()`（表格行内列清单）· `TestStep.row_text` / `cell_field` · 生成脚本 `_click_row_cell()` | 运行时新建的那一行，编号由服务端分配 ⇒ 语义清单里**不可能有它**，只能「行锚文本（你刚填的值）+ 列字段」定位 |
| **首行断言** | 断言 kind `first_row`（`row_field` + 期望值）· `_assert_first_row()` | 文本断言只能证明「页面上有这个值」，**证明不了它在第一行**；而「提交后列表第一个就是新建的那条」是需求原文 |

配套场景与用例：`scenarios/orders/orders_return_from_contract.yml`（3 页 / 30 步 / 护栏 + 逐字语义名清单）·
AI 端到端产物 `cases/ai_orders_return_from_contract_004934.json`（0 未映射）。

---

## 二、本版修了什么（两处根因）

| 编号 | 缺陷 | 根因与修法 |
|---|---|---|
| **H1** | **AI 静默选错控件**（服务 ② AI 语义准，本轮最大收获） | 弹窗字段 `请输入订单名称`（`label=订单名称 *` / `container_heading=新建订单`）与筛选区 `订单名称_全模糊`（`label=订单名称` / `container_heading=空`）**名字完全不同** ⇒ 原有「同名不同区域」告警（只看完全同名）**报不出来**；两者又**都能映射到真实控件** ⇒ 不报「未映射」⇒ 用例一路跑到「提交后首行断言」才红。修法：`explorer._field_identity()`（label 归一化：去 `*`、去结尾「（全模糊）」）+ `_same_field_pairs()` ⇒ **把歧义显式摊在提示词里**（列出两个名字与各自区域），并加规则 2c 点明「选错不会报未映射、只会悄悄操作到别的控件」 |
| **H2** | **跨页重名告警误伤别的用例**（服务 ③ 稳定底线，回归时暴露） | `_DUP_RAW_NAMES` 是**所有**用例声明页面的并集：订单场景带来「订单系统」页，它与「列表页」都有 `HT_1001…HT_1020` 链接 ⇒ `HT_1005` 进名单；而 `cross_page_detail` / `ai_contracts_cross_page_011030` 自己声明的页面是「列表页+详情页」，**在它们范围内根本不重名** ⇒ `cli run` 15 passed / 2 failed 假红。修法：`_DUP_PAGES`（名 → 出现过的页集合）+ `_dup_raw_names_for_case()`，判据 = 「**本用例声明的页 ∩ 该名字出现的页 ≥ 2**」；`_render_assert(..., dup_raw=…)` 按用例透传（反向测试钉住「真重名仍必须拦」，防修成漏拦） |

**定位手法留档（比读日志猜快得多）**：解失败那次的 `log/<run>/traces/<case>_trace.zip`，读 `trace.network`
的请求清单 —— 本次一眼看出**没有 `POST /api/orders`** ⇒ 提交根本没发出 ⇒ 前端必填校验没过 ⇒ 弹窗字段没填进去。

---

## 三、自测与验证证据（全部本机实测，2026-09-18）

| 验证 | 结果 |
|---|---|
| AI 端到端 `explore --ai --scenario-file scenarios/orders/orders_return_from_contract.yml` | ✅ **exit 0 · `--verify` 实测 PASSED**（`1 passed in 4.01s`） |
| 端到端逐步骤证据（`output/verify/…004934_20260918_005508.log`） | 新 tab 开订单系统 ✔ → 4 个弹层选值 + 订单类型/客户/销售员 ✔ → **首行断言「第一行订单名称 = 刚填的 退货订单-20260918005504」** ✔ → 点该行合同编号 → 新 tab 合同详情（`?no=HT-1001&from=order`）显示 HT-1001 / 合同1 ✔ → 点「返回」→ **tab 真的关了**（`真的关了=True`）并回到订单列表 ✔ |
| `python -m pytest tests/ -q` | ✅ **158 passed**（含新增 8 条：5 条名称歧义披露 + 3 条跨页重名按用例判定） |
| `python -m framework.cli run` | ✅ **17 passed / exit 0**（12 手写 + 5 AI） |
| `python -m framework.cli generate` | ✅ exit 0 · 未映射 **0** 处 |
| 用例库卫生 | 同场景历史 AI 用例已归档到 `output/archived_cases_20260918/{cases,datasets}/`（一 scenario 只留最新一条） |

---

## 四、升级注意

1. 替换代码后**跑一次 `python -m framework.cli generate`**（生成脚本需带上 `_Tabs` / `_click_row_cell` / `_assert_first_row` 三个新辅助与首行断言渲染）。
2. 新能力的语义名契约不变：AI 仍只引用探针给出的 `semantic_name`；`row_text` / `cell_field` 是给「运行时新建行」用的，
   `cell_field` **只能取行内列清单里的字段**（生成期会拒绝自造）。
3. 跨页用例若引用**本用例多页都出现**的元素名，仍必须写成 `原名@页名`（告警如今**只针对本用例**，不会再牵连别的用例）。
4. 被测应用需支持：`POST /api/reset` 复位、`body[data-hybrid-ready]` 就绪标志、全量 `data-testid`（订单页沿用同一套契约）。

---

## 五、已知边界（如实记，不写假绿）

- **多 tab 与 `--debug` 录制**：`--debug` 的逐步截图/录像是**单 tab**口径（新 tab 的页面不会另存一套视频）；排跨 tab 问题建议直接看 `traces/*_trace.zip`。
- **弹层探测预算**：订单页有 6 个 picker 层（探测成本随层数上升，预算可环境变量调）；页面层数继续增长时需复核探测耗时。
- **本机内存红线**：跑浏览器前先看 `MemAvailable`（编辑 `.py` 后会被拉起的语言服务占 ~350MB，先关掉）。实测 OOM 会**连杀 chrome-headless 与 hermes 进程**，现象是「CLI 自己退出了」。
- **CI 落点仍是未做项**（2026-09-17 裁定）：团队级自动回归需要带 `workflow` 权限的 token，暂缓。
