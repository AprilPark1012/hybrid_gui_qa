# hybrid_gui_qa V7.5.3 交付说明（2026-09-17）

> 一句话：**假绿治理版** —— 修掉三处「用例照绿、其实没验到东西」的缺陷：
> ① 换页证据写成 `expect_url = localhost`（换页前后两个页面都含它 ⇒ 点击后立刻通过，等于没验换页）
> ② 质量闸自己碰到结构化断言的期望值就崩（守门人倒下 = 这道栅栏不存在）
> ③ 跨页用例里「列表恢复全量 20 行」这类**与要验的事无关**的脆弱断言（还会被本次运行新建的数据顶掉）。
> 另外修掉一段**自 V7.5.1 起静默失效**的负向验证。**定位与执行链路零改动**，升级只需替换代码
> （建议顺手重跑一次 `cli generate`）。

---

## 一、本版修了什么（五件）

| 编号 | 修复 | 关键点 |
|---|---|---|
| **G1** | **换页证据红线闸**（假绿） | `case_builder.case_errors()`：换页证据必须**只指向一页** —— 片段在用例声明的多页 URL 里都命中（典型 `localhost`），或跨页用例里只是 `host[:端口]` ⇒ **红线**。AI 落盘（`elementmap_to_cases_file`）与生成（`generator._gate_false_green`）**两条路都 raise `CaseQualityError`** ⇒ exit 2 + 人话（哪条用例 / 哪条断言 / 怎么改），**一个产物都不写**。口径同映射质量闸：**产物永不允许带假绿** |
| **G2** | **提示词根因修复** | 真根因是 `explorer` 的跨页规则**在教 AI 这么写**（原文：「列表页写 localhost 或留空不要写」）⇒ 只加闸门不修提示词，每次 AI 跑都会撞红线（假绿变假红）。现在写明：只准用**只出现在目标页**的片段；**禁止** `localhost` / `localhost:8000` / `127.0.0.1` 这类**每个页面都含**的片段；目标页没有独有片段（如列表页就是根路径 `/`）⇒ 改用**该页独有文案**做 `text` 断言 |
| **G3** | **F5 断言稳健化** | `cases/cross_page_detail.json` 的「列表恢复全量 20 行」（`count expect=20`）→「**预置基线行** `row-HT-1001` 在列表里」：与本次运行新建的数据无关，不会再被顶掉；「回到列表页」另有「新建合同按钮可见」作证 |
| **G4** | **质量闸自身崩溃**（安静而致命） | `case_builder.case_warnings` 遇到非字符串期望值（`count` 的 `20`）直接 `TypeError: expected string or bytes-like object, got 'int'` —— 旧写法把期望值喂给正则与哈希集合比较，只按字符串设计。修法：文本形态检查**只对字符串生效**、「断言回显输入」比较**全程走字符串口径** |
| **G5** | **负向验证段复活** | `tests/verify_cross_page.py` 的负向段**自 V7.5.1 起就没跑起来**：负向用例④故意用不存在的元素名 ⇒ 被映射质量闸拦成 exit 2 ⇒ 脚本 `return 2`，「N 条负向必须 FAILED」**长期未执行**（而且 exit 2 看着像「跑出来有问题」，实际是自己没跑完 ⇒ 更隐蔽）。修法：负向段显式走 `generate --allow-unmapped`（调试逃生口；产物只服务负向验证，收尾重新生成干净产物），并在代码里写明原因 |

**防误伤（宁漏不误伤）**：
- 单页用例里的 `host` 断言**只告警不拦** —— 手写用例可能是有意的（如 `assert_kinds_search` 专门验「URL 含 `localhost:8000`」）。
- `host` 判定不再用「像域名的正则」（`index.html` 会被它误判成 host）⇒ 改为两级：① 与已知页面 URL（`pages[].url` + `base_url`）的 `host[:端口]` / 裸主机名**精确比对**（主判据）；② 形态兜底只认「纯主机名或带端口」。

---

## 二、自测与验证证据（全部本机实测，2026-09-17）

| 验证 | 结果 |
|---|---|
| `python -m pytest tests/ -q` | **143 passed**（130 原有 + 13 条 `tests/test_case_quality_gate.py`） |
| `python -m framework.cli generate` | ✅ exit 0 · 未映射 **0** 处 · `_goto` 就绪契约接线 **32** 处 |
| `python -m framework.cli run --workers 1` | ✅ **16 passed / exit 0** |
| `python tests/verify_cross_page.py` | ✅ **exit 0**（三节判据 + **5 条负向全部 FAILED**） |
| 负向 CLI 证明（闸门真会拦） | 喂一条 `expect = localhost` 的跨页用例 → `cli generate` **exit 2** + 人话，且产物 `sha256` **一字未改**（确实一个产物都没写） |
| 证据链可查 | 两条改后的断言在 `log/<run_id>/<case_id>.log` 里**真实执行**（不再空验） |

新增的「测试的测试」`tests/test_case_quality_gate.py`（13 条，秒级、不需 demo）：
11 种断言 `kind` × 7 种期望值形态 × 4 种定位写法**都不许崩**；弱证据必须被拦；**真证据不许被误拦**；
仓库用例全量扫描无弱证据；两条产物路径（AI 落盘 / generate）的红线行为；AI 提示词不得再教弱证据。

---

## 三、升级注意

1. **只需替换代码**（定位、执行、断言渲染链路零改动）。包内已含重新生成的 `scripts/test_cases.py`；
   若你本地跑过 `cli generate`，建议再跑一次以同步本轮用例改动。
2. 两条用例有改动，**你本地若也改过要合并**：
   - `cases/ai_contracts_cross_page_011030.json`：「回到列表页」的证据从 `expect_url: localhost` → `text: 新建合同`；
   - `cases/cross_page_detail.json`：`count expect=20` → `row-HT-1001` 基线断言。
3. **新的红线闸会影响自建跨页用例**：若你的用例里有「跨页 + 只写 host[:端口] 的 `url` 断言」，
   `generate` 会 **exit 2** 并告诉你改哪一条 —— 按提示改成「目标页独有片段」，或改对该页独有文案做 `text` 断言。
   单页用例不受影响（只告警）。
4. `tests/verify_cross_page.py` 的负向段会自动带 `--allow-unmapped`（负向用例故意用不存在的元素名），
   **不需要你手工加参数**。

---

## 四、已知边界（如实记，不写假绿）

- **变异注入闸门**（往 demo 注入已知 bug，量「AI 产出的断言有没有牙」）**未做** —— 它是下一项（服务目标 ②）。
- **CI 落点**（`.github/workflows/ci.yml`）与 **Windows 侧并发隔离证据**按 2026-09-17 拍板**不做 / 不再追**：
  前者需重建带 `workflow` 权限的 token；后者的等价保护已在 `tests/test_ready_and_locate.py` 里由两条**真跑 CLI** 的行为测试覆盖。
- 质量闸是**词表/规则驱动的静态检查**，不是语义判断：它只能保证「换页证据有区分力」这一条，
  不能替代人工复核断言是否验了业务结果。
- 本机跑浏览器前先看内存余量（1 个 headless Chromium ≈ 515MB，**别并发跑**）；
  不足时如实跳过，**不硬跑、不假绿**。
