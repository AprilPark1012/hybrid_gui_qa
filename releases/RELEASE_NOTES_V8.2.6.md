# hybrid_gui_qa V8.2.6 升级说明（2026-09-28）

> 修的是「**行锚**」这一处：产物里的行锚原本是**整行文本**（`tr.textContent` 截 120 字符），
> 而 demo 数据含随机字段 ⇒ **demo 每次重启，行锚必然失配**，生成脚本静默退到语义兜底
> （用例照样 PASSED、每处白等 5 秒）。本版把行锚改成「**整表内恰好出现 1 次**的最短单元格文本」。

## 一、为什么要改（真实现象，可复现）

| 现象 | 真值 |
|---|---|
| 同一行，三份产物行锚各不相同 | HEAD 版产物 `HT-1005 合同5 0451 001 预po … bu_a` · 工作区产物 `… 1031 001 合同 … bu_c` · 当前 demo `… 0451 003 合同 … bu_a` |
| 绿着，但走的不是新能力 | `log/latest/ai_contracts_cross_page_011030.log:6` → `primary 等了 5000ms 仍是 0 个 → 语义兜底 HT_1005`，用例仍 **PASSED** |
| 谁受影响 | 交付包里的产物到**别人机器 100% 降级**（随机态不可能一致）—— 属「看着能下钻、实际没生效」的假绿 |

根因三处：采集端取整行 `tr.textContent`（`framework/tools/probe/probe.py`）· demo `seed()` 的
`mu / file / type / bu` 是 `random.choice` · 表达式合成把整行逐字塞进 `has_text=`。

## 二、本版改动

### ① 行锚选取（核心 · 修法 A）

- 采集端统计**整表**（`tbody`）每个单元格文本的出现次数 ⇒ 只保留「**恰好出现 1 次**」的候选 ⇒ 取**最短**者
  （等长取列序最小）。**纯数据驱动**，不猜哪一列是业务键，也不依赖列名语义。
- 取不到唯一候选 ⇒ **保持现状**（整行文本）+ 标记 `row_anchor_stable = False`（**绝不静默编锚**；
  生成期告警随批 3 落地）。
- 取最短的额外好处：表达式更短更可读（顺带缓解 L13「行锚文本优化」）。
- 纯函数落点：`framework/tools/probe/anchor.py::pick_row_anchor(cells, table_cells)`（无浏览器 ⇒ 可直接判据测）。

### ② 表达式合成加固

- `framework/tools/probe/scope_locate.py::step_expr` 行步：值里含**双引号 / 换行** ⇒ 直接返回 `None`
  （此前会把值原样插进 `has_text="…"` ⇒ 产出运行期炸掉的表达式，且属"静默炸"）。

### ③ 判据（R7-c 判据先行）

| 类型 | 判据 / 命令 | 结果 |
|---|---|---|
| 一类 | `tests/frameworkTest/test_row_anchor_selection.py`（5 条：选取 · 两条负向 · 表达式形态与引号拒绝 · 产物不得是整行文本） | **判据先行红态 4 failed / 1 xfailed** ⇒ 实现后 **4 passed / 1 xfailed** |
| 一类全量 | `python -m pytest tests/frameworkTest/ -q` | **567 passed / 1 xfailed / 43.6s** |
| R8 | `python tests/featureTest/verify_html_sync.py` | exit 0（培训页与代码可复现且逐字节一致） |

## 三、本版范围（诚实标注）

- **已做（批 1+2）**：框架代码（采集端 / 纯函数 / 表达式合成）+ 一类判据 + 文档三同步 + 版本号。
- **未做（批 3，计划随 demo 重构一起收口）**：
  1. 重跑 `probe` + `generate` ⇒ 仓里产物换上稳定行锚（**这就是产物判据现在标 `xfail(strict=True)` 的原因**，
     它是「待收口」提醒而不是通过）；
  2. 二类端到端验证：**重启 demo 两态**各跑一次 ⇒ 该 run 日志里「语义兜底」必须 **0 次**（现为 ≥1，铁证见上表）；
  3. 「整表无唯一值」夹具页 ⇒ 必须**降级 + 明确告警**（生成期告警）；
  4. 录像重录（与 demo 重构一并走统一重录链 `record_cassettes.py --missing-only` → `check_cassettes` → 打包闸门）。
- **未改动**：AI 链路的 `row_text`（AI 自产业务值，如 `退货订单-{datetime}`）与 `generator._click_row_cell`
  —— 本缺陷不涉及它们。

## 四、升级动作（拿到包的人）

```bash
python -m framework.cli setup              # 装依赖 + 装浏览器 + 自检
python -m framework.cli all --workers 2    # probe → generate → run：会重新采集行锚并重写产物
```

无需手工改产物：`generate` 按新采集结果重写；`row_anchor_stable=false` 的元素保持旧口径（**不静默**）。

## 五、验证真值（本机 · 2026-09-28）

- 一类：**567 passed / 1 xfailed / 43.55s**
- 判据先行红态：`test_row_anchor_selection.py` 首跑 **4 failed / 1 xfailed**（证据落盘
  `references/evidence/P18批1-判据先行红态-20260928.txt`）
- R8：`verify_html_sync` **exit 0**
- **未跑**（如实标注）：二类全量（需 `MemAvailable ≥550MB`）· E2E 三场景 · 打包 · 录像体检
