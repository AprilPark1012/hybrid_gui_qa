# P1 explore→generate→run 链路对齐 · 完成 + 验收报告

> 收尾时间：2026-09-11 21:53（北京时间）· 基线：v6 + P0 资源安全改动
> 关联文档：`docs/P1-explore链路对齐-修改方案.md`（方案，17:27 落盘）、`docs/P0-资源安全-改动方案.md`
> 写法约定：**每条结论都附实测命令与产物路径**；没跑过的绝不写"通过"。

---

## 0. 一句话结论

方案的 A–F 六项**全部落盘并通过实测**；验收过程中额外抓到并修复 **1 个"假 AI 产物"缺陷（G8）**，并按实测失败加强了 E（断言禁止"运行时计数"）。
最终状态：`generate` + `run` 全量 **7 passed**（`log/20260911_215325/report.html`）。

---

## 1. 交付清单（对照方案 A–F）

| 项 | 落点 | 状态 | 实测证据 |
|---|---|---|---|
| **A** explore 产物落 `cases/` | 新增 `framework/case_builder.py`；`cli.cmd_explore` 默认 `--to-cases`，`--no-cases` 可关 | ✅ | `cases/ai_在合同列表页面的搜索框输入_1007_点击搜索按_215059.json` |
| **B** "browser-use 编排"口径 | `explorer.py` docstring / 函数 docstring 改口为"ChatDeepSeek 直连编排（方案C）" | ✅ | `grep -n ChatDeepSeek framework/explorer.py` |
| **C** generate 消费 element_map | `generator.generate_scripts(element_map_path=...)`；`cli generate --element-map <f>` / `--live-probe`；来源按 **element_map → probe 快照 → 现场 probe** 依次尝试并打印 | ✅ | `locator 来源: element_map(element_map_20260911_215059.json) 命中 2/11 + 现场probe补齐 9/9 项` |
| **D** 自愈接入生成脚本 | `scripts/conftest.py`：`_loc()` 走 `resolve_locator` 分层定位（Tier1→Tier2→意图复验），失败再 `Healer.try_heal()`；`HYBRID_SELF_HEAL` 默认 1（=0 即"失败即报"）；heal 事件落 `output/heals/` | ✅ | 漂移 A/B：改 `data-testid="btn-search"`→`btn-search-x` 后，改造前 30s 硬失败 / 改造后自动降级 `role+name exact conf=0.93` 跑通并出 heal diff；还原后 `sha256 596b293e…` 前后一致 |
| **E** 防假绿 | prompt 规则 5–8（断言不带元素、不得=fill 值、不得含运行时计数/时间戳、须能在清单/DOM 找到依据）+ `case_warnings()`（回显/计数/无断言/只有 goto） | ✅ | 见 §2、§3 |
| **F** 文档同步 | `README.md`（架构图/数据流/目录结构/用例质量闸）+ `build_html.py`（training.html 源头）并重新生成 `training.html` | ✅ | 旧口径（"explore 是可选 AI 分支"）残留计数 = 0 |

---

## 2. 验收中新发现并修复的缺陷：G8「假 AI 产物」

**现象**：21:50 重建 AI 用例时，场景明明是合同列表页，产物却是**待办页控件**（`todo_input` / `add_button` / "添加待办"），还照样被标成"AI 用例"写进了 `cases/`。

**根因**（修复前 `explorer.py` 尾部兜底）：LLM 调用抛 `ModelProviderError`（瞬时故障）后，`ainvoke(output_format)` 与文本解析**都失败 → 静默 `mock_explore` 兜底** → 一条挂着 AI 场景名的确定性 mock 用例落进用例库。**证据留档**：`output/element_maps/element_map_20260911_215007.json`（合同场景 / 待办控件）。

**修复**：
- 新增 `AiExploreError`；LLM 完全不可用时**默认 raise**（拒绝产出假 AI 用例），CLI 退出码 **2**；
- 只有显式 `--mock-fallback` 才降级，且**大声警告 + 不写 `cases/`**；
- 文本解析路径独立 try/except，不再裸抛。

**负向验证（都实跑过）**：

| 场景 | 期望 | 实测 |
|---|---|---|
| `DEEPSEEK_API_KEY=sk-bogus explore --ai` | 报错退出、cases 不变 | ✅ `exit=2`，`cases 7 → 7` |
| 同上 + `--mock-fallback` | 警告且不入库 | ✅ 打印"⚠️ mock 兜底产物 → 按约定【不落 cases/】"，`cases 7 → 7` |

---

## 3. 断言质量：一个真失败的完整闭环（含对我下午判断的更正）

**必须更正的一句**：下午 17:36 我说"提示词约束实测有效、`assert=共 1 条` 是页面上真实的结果文本"——**那句话只看了 ElementMap 的打印，没验页面，属于过度声称**。铁证：17:38 那一轮 `log/20260911_173809/report.html` 里该用例就是 **Failed**（`waiting for get_by_text("共 1 条") → Timeout 5000ms`）。

**真因**：demo 预置 20 条合同，名称分别是"合同1…合同20"，关键字 `合同` 实际命中 **20** 条 → 页面真实文案是"共 **20** 条合同"。而 `共 1 条` 是 LLM **凭空编的运行时计数**——操作前页面 `#status` 为空，它没有任何依据能算出条数。这正是"假断言"的第二类（第一类是"断言=输入回显"）。

**处置**：
1. prompt 加规则 7/8（断言须"操作前可确定"：固定文案或可推出的记录标识；**严禁计数/时间戳/随机值**）；
2. `case_builder._DYNAMIC_ASSERT_PATTERNS` 落盘校验，命中"共 N 条 / 命中 N / 日期 / 时间"即告警；
3. 撤走坏用例（**备份**在 `/tmp/rejected_ai_cases/`，非硬删）；
4. 重建 grounded 用例：场景"输入 1007 → 确认出现 HT-1007"→ AI 产出 `assert=HT-1007`（≠输入值，零质量警告），实跑通过。

---

## 4. 最终验收清单

| # | 验证项 | 期望 | 结果 |
|---|---|---|---|
| 1 | `explore --ai --scenario "…"` | 同时产 `output/element_maps/*.json` **和** `cases/ai_*.json` | ✅ `element_map_20260911_215059.json` + `cases/ai_…_215059.json` |
| 2 | `generate`（默认） | 只用 cases（含 AI 用例）即可生成，数据抽离正常 | ✅ 7 用例 + 7 datasets |
| 3 | `generate --element-map <f>` | 按 map 映射 locator，日志标注来源；缺项回退现场 probe | ✅ `element_map(...) 命中 2/11 + 现场probe补齐 9/9` |
| 4 | `run --workers 2` | 全绿 + `log/<run_id>/report.html` + 资源预检降级 | ✅ **7 passed in 10.17s**，`MemAvailable=610MB → 安全并发=1`（请求 2 降级 1） |
| 5 | 漂移 A/B 复测 | 脚本路径应能自愈；还原后 sha256 一致 | ✅ 降级 `role+name exact conf=0.93` 跑通；`sha256 596b293e…` 一致 |
| 6 | `HYBRID_SELF_HEAL=0` 漂移复测 | 恢复"失败即报、不自愈" | ✅ 1.17s 快速失败（不再干等 30s） |
| 7 | 假绿校验 | 断言=输入回显 → 告警 | ✅ 对 `ai_…_173337` 实测告警："断言 '合同7' 与某 fill 步骤的输入值完全相同" |
| 8 | 手写 5 用例回归 | 5/5 通过、不被改造破坏 | ✅ 5/5 通过（含在 7 passed 中） |
| 9 | **新增**：断言含运行时计数 | 落盘告警 | ✅ `ai_…_173619`（"共 1 条"）触发计数告警 |
| 10 | **新增**：LLM 不可用 | 拒绝假 AI 产物、退出码非 0、cases 不变 | ✅ `exit=2`；`--mock-fallback` 下警告且不入库 |

---

## 5. 遗留与建议（P3，未做，等你拍板）

1. **AI 用例目前靠"人跑一遍"才知道真假**。建议加 `cli explore --verify`：生成后立刻 `generate + pytest -k <case_id>` 自动试跑，失败即标红（把"AI 说对了"变成"实测通过"）。这是补上"交付即验证"的最后一环。
2. **`Q4` heal diff 人工复核**：按你"暂时不改"，维持现状（heal 只修 locator 漂移，业务断言不过仍判真 bug）。
3. **归档目录增长**：`output/element_maps/` 快照会越攒越多（已有 9-04 至今 11 个 element_map + 8 个 probe），建议加保留策略（如保留最近 N 个）。
4. **本次未动架构文档以外的更深处**；`pyproject/requirements` 无变化。
5. `hybrid-gui-test-framework` 这个 skill 是**你自有**的（我不自动改）——要把"假 AI 产物""计数断言"这两条坑写进 skill，你说一声我就补。

---

## 6. 复现命令（一键回放）

```bash
cd /home/admin/hybrid_gui_qa
# 1) AI 产用例（需 DeepSeek key）
.venv/bin/python -m framework.cli explore --ai --scenario "在合同列表页面的搜索框输入'1007'，点击搜索按钮，确认结果列表里出现编号为 HT-1007 的合同记录。"
# 2) 确定性生成 + 执行
.venv/bin/python -m framework.cli generate
.venv/bin/python -m framework.cli run --workers 2
# 3) 负向验证：AI 不可用必须拒绝产假用例
BROWSER_USE_API_KEY= OPENAI_API_KEY= ANTHROPIC_API_KEY= GOOGLE_API_KEY= DEEPSEEK_API_KEY=sk-bogus \
  .venv/bin/python -m framework.cli explore --ai --scenario "x"; echo "exit=$?"   # 期望 2
```

**证据留档**：`log/20260911_215325/`（最终全绿轮）、`log/20260911_173809/`（下午失败轮的 Failed 铁证）、`/tmp/rejected_ai_cases/`（两条被撤用例）、`output/element_maps/element_map_20260911_215007.json`（假 AI 产物样本）。

---

## 7. 追加交付（同日深夜场）：交付即验证 / 抖动重试 / 归档保留

### 7.1 `explore --verify`（默认开）—— 把"AI 说它对"变成"实测通过"

- **实现**：`framework/cli.py::_verify_case()` —— AI 用例落 `cases/` 后立刻
  `python -m framework.cli generate` → `pytest scripts/test_cases.py::test_<case_id>`；
  校验日志落 `output/verify/<case_id>_<时间戳>.log`。
- **正向实测**：`explore --ai --scenario "…输入'1005'…出现 HT-1005"` → 用例 `ai_…_215757` →
  `✅ 校验通过：该用例实测 PASSED`，`exit=0`。
- **负向实测**（打桩把 AI 计划换成必然失败的假断言，其余全走真实代码）：
  `❌ 校验失败：该用例实测 FAILED…` + **SystemExit code = 3**（闸门生效）。
- **边界**：`generate` 失败 → 打印"校验未执行"警告，不算判死刑（返回 None，用例仍在但标注未验证）；
  `--no-verify` 显式跳过（会打印"这条用例未经实测验证"）。

### 7.2 LLM 抖动重试（顺手挖出的真身）

- **实测现象**：同一 prompt 连续调两次 —— 第 1 次 OK，第 2 次
  `ModelProviderError: Extra data: line 1 column 550`（JSON 解析多出内容）。
  ⇒ 属 **DeepSeek function calling 间歇性抖动**，不是我们的代码错，更不是 key 失效。
- **修复**：退避重试（`HYBRID_LLM_ATTEMPTS` 默认 3，1.5s×n 递增），日志打印每次失败原因与"第 N 次重试成功"。
- **顺带修的真 bug**：文本兜底路径原本是**死代码** —— `_get_llm_text()` 内部用 `asyncio.run()`，
  在 `ai_explore` 的事件循环里调用必然 `RuntimeError` 且被 except 吞掉 ⇒ 兜底从来没兜住过。
  新增 `_get_llm_text_async()`（用 await），兜底才真正可用。

### 7.3 归档保留策略（`cli prune`）

- **实现**：新增 `framework/retention.py` + `cli prune [--keep N] [--dry-run]`；
  `explore` / `probe` 每次结束**自动静默执行**（无可清理就不打印）；默认保留数 `HYBRID_KEEP_SNAPSHOTS=20`。
- **动因**：旧快照会顶掉"最新那一份"（实测踩到：一条 mock 快照把 `generate` 的定位来源带偏到待办页）。
- **实测**：`prune --keep 3 --dry-run` 预演（将清理 16 个，只打印不删）→ 真删 `prune --keep 6`：
  `element_map 12→6`、`probe 11→6`，**今天的全部证据文件都保留**。

### 7.4 skill 已按要求补充

`~/.hermes/skills/devops/hybrid-gui-test-framework/SKILL.md` 新增三条实测坑（假 AI 产物 / 计数假断言 /
DeepSeek 抖动 + 死代码兜底）与 P6 链路对齐条目，并同步 `cli explore --to-cases --verify`、`cli prune` 用法。

### 7.5 最终状态

- 用例 **8 passed**（`log/20260911_215846/report.html`）：5 手写 + 3 条 AI 用例（其中 173337 为"输入回显"弱断言样本，质量闸会告警）。
- 文档三处同步：`README.md`、`build_html.py` → `training.html`（重新生成）、本报告。
- 全部产物均可复现；坏用例/假 AI 样本留档于 `/tmp/rejected_ai_cases/`、`/tmp/hybrid_qa_artifacts/`。
