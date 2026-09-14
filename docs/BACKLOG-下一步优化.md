# BACKLOG · 下一步优化清单

> 维护约定：动一项就划掉一项并补「实测证据」。
> **当前基线 V7.4.1（2026-09-14）**：16 用例全绿（12 手写 + 4 AI）· 框架自测 **87 条** · 三个 verify 脚本全过。
> 仓库：https://github.com/AprilPark1012/hybrid_gui_qa （Public · MIT · 单提交起步）。
> ⚠️ 本框架的定位是**交付给团队用的产品**（不是个人脚本）—— 排序一律按下面两条规则，不按「做起来容不容易 / 顺不顺手」。

## 〇、排序口径（2026-09-14 按目标优先级重排）

AprilPark1012 定调的四个目标优先级：**② AI 语义准 ≈ ① 降人力 > ③ 稳定 > ④ 脚本健壮**（≈ = 并列）。

**为什么 ②≈① 置顶**：AI 语义不准 ⇒ 产出「看着对、其实点错控件 / 断言没验到」的假绿 ⇒ 用例越多错得越多，
「降人力」变**负收益**（省了人力，赔了可信度）。⇒ **AI 产出可信度是降人力的前提**，两者必须并列最前。

两条规则（按序适用）：

1. **先按目标排**：服务 ② / ① 的在前 → ③ 次之 → ④ 最后。
2. **同目标内 tie-break**（测试架构师口径）：假绿风险 > 已知边界 / 功能缺失 > 新能力 > 机制自证 > 手工验证。
3. ③ / ④ **是底线不是低价值**：不达标立即修（会崩的 bug 不排期）；达标之后不因「顺手能改」插队。
   （④ 类 V7.1~V7.4 已达标：CLI 参数契约 / 退出码如实传递 / 统一 UTF-8 / 断言结构错误必 fail。）

**目标 → 事项映射**：

| 目标 | 本清单里服务它的项 |
|---|---|
| ② AI 语义准 | 跨页面流程（AI 跨页规划目前写不完整）、弱 url 断言质量闸（换页证据要真验到换页）、变异注入闸门（量「AI 产出的断言有没有牙」，AprilPark1012 2026-09-14 裁定归此）|
| ① 降人力 | CI 落点（团队级「每次改动自动验」= 产品交付门槛）、数据参数化真展开（一份数据模板顶多条用例）|
| ③ 稳定 | 队列内暂无专属项（V7.x 已达标：内存降级 / 看门狗 / 退避重试 / 会话级浏览器崩溃重启）—— 新发现的 ③ 风险立即插队 |
| ④ 脚本健壮 | V7.1~V7.4 已达标；遗留新能力（Test Agents / 视觉兜底 / 云矩阵）排末位 |

据此排定：**① 跨页面流程 + 弱 url 质量闸 + 变异注入闸门（同批，全服务 ②）→ ② CI 落点 → ③ 数据参数化真展开 → ④ ④ 类遗留新能力**

---

## 〇-b、⚠️ 底线项（✅ 已闭环 —— 内容 / 本地历史 / 远端对象 三层全 0 残留）

```
[公开仓库隐私复扫 · 2026-09-14 漏网发现 → 已执行「内容清理 + 历史重写」]
发现时现状：三份方案的落款署名写了**助手昵称**（docs/P0 / P1 / P2）；`hermes-gateway-<profile>` 形态的 profile 名
      出现在 6 处（docs/P0 ×4、docs/P3 ×1、framework/browser.py ×1）。两类都已进公开仓库。
为什么是底线：对外公开的隐私要求是**对象级零残留**（tree + 历史 + 提交身份都要干净）—— 不是「功能」，是合规红线，
      不排进目标序列，发现即修。
裁决（2026-09-14，AprilPark1012）：**现在就重写历史 + force-push**，压成单一干净提交。

✅ 已完成（2026-09-14 实测证据）
1. 内容侧清理：上述 6 处 profile 名 → 占位形态；三份方案落款署名 → AprilPark1012。
2. 历史压平：备份 bundle（/tmp/hybrid_gui_qa_pre_rewrite*_20260914.bundle，**不入库**）→ `checkout --orphan` →
   压平为**单一干净提交** → reflog expire + `repack -a -d -f` + prune + gc → force-push。
   （**公开文档里不写具体 SHA** —— 写了等于给旧对象指路；审计用的 SHA 只留在本地记录。）
3. 复扫口径（两条缺一不可）：
   · 本地**对象级**：`git cat-file --batch-all-objects --batch` 里 12 类词 + 助手昵称 + profile 名 **全 0**；
     `rev-list --count HEAD`=1 · reflog 0 行 · `fsck --unreachable` 0 · in-pack 95 = 可达对象数 95。
   · 远端**全树**：按 sha 经 git blob API 逐个拉 85 个文件复扫 —— 全 0（PNG 里的假命中是
     `decode(errors="ignore")` 拼出来的，**按字节计数为 0**）。

⚠️ 三个真坑（都是「复扫当场抓出来」的，读代码发现不了）
· 坑1 · cruft pack：git ≥2.37 默认开 cruft pack ⇒ `git gc --prune=now` **不删不可达对象**（残留还在包里，
  而 `count-objects` 的 garbage 却显示 0）⇒ 正解 `git -c gc.cruftPacks=false repack -a -d -f` +
  `git reflog expire --expire=now --all` + `git prune --expire=now`。
· 坑2 · 远端跟踪 ref：force-push 后若没先 `git fetch --prune origin`，本地 `origin/main` 还指着旧提交 ⇒
  旧对象**仍算可达**，`repack -a -d` 当然不丢它们，复扫怎么清都有残留。**先 fetch 再 expire/repack** 才是清掉的那一步。
· 坑3 · 修复提交本身也会脏历史：在「清理记录」里把敏感 token 原文写回文档 ⇒ 历史又脏一次
  （本次连踩：昵称 1 次、profile 名 2 次）。⇒ 记录一律用**占位形式**；判据必须是**全历史对象扫**
  （本次出现过「HEAD 树 0 命中、历史 1 命中」）。

✅ 远端对象（GitHub 侧）· 走 ② 已完成（2026-09-14 实测验收）
- 执行：删仓库 → 同名新建 Public 空仓 → 重推**单一干净提交**（新仓 repo id 是新的 ⇒ 对象库为空，旧对象无处可留）。
- 验收：新仓 HEAD = 单提交 · 可达提交数 **1** · 作者/提交者全为 noreply；
  逐 blob 复扫 85 个文件 **全 0**（PNG 里的假命中是 `decode(errors="ignore")` 误报，**按字节为 0**）；
  旧提交按 SHA 查询 → **422 No commit found**（仓库在、该对象不存在）、旧 blob → **404** ⇒ 已取不到。
  （判据语义：**404** = 对象/仓库都不存在；**422** = 仓库在、但该 commit 不存在。）
- 换 token 的坑（同日实测）：fine-grained token **按 repo id 绑定** ⇒ 同名重建后必须换新 token；
  `pass insert` 在**非交互 stdin** 下会**静默写空值且 exit 0**（实测写进 1 字节空条目，把有效 token 覆盖掉）
  ⇒ 正解 `printf '%s\n%s\n' "$TOKEN" "$TOKEN" | pass insert -f <path>`（**必须两行**）或真终端里交互式插入；
  写完用 `pass show <path> | wc -c` 校验（**1 字节 = 空值**）。
```

---

## 〇-c、⚠️ 现场问题（优先级高于排队顺序 · 2026-09-14 团队演示触发）· **已实施，待浏览器验收**

```
[慢目标/并发下的假红]  ★ ③ 稳定类，但已导致"演示会红" ⇒ 属于底线，先修
现象：同版本代码 run all 红 4 条、--debug 全绿（debug 自带 --slowmo 200ms，把时间窗拖过去了）。
根因：R1 页面数据就绪无契约（goto 后立即动作/断言；晚到的首屏渲染还会覆盖搜索结果）；
      R2 单一有状态 store + 每用例全局复位 ⇒ 多 worker 下精确计数断言互相踩。
本机复现（单进程/无并发/~30s）：慢目标代理 400ms → 5 failed / 1 passed；加"等页面就绪"后 6 passed。
裁决：**A 全做 + F5 + F6 一起修**（2026-09-14）。
方案：docs/P4-慢目标与并发-修复方案.md（F1 page-ready 契约 / F2 定位有界等待 / F3 报错纠偏 /
      F4 慢目标闸门 / F5 断言稳健化 / F6 并发隔离）。

✅ 已实施（2026-09-14 晚，证据逐条）
- F1 就绪契约：demo/contracts.html·contract_detail.html 声明 body[data-hybrid-ready]；生成物 32 处 goto 全走 `_goto()`。
  证据：真实浏览器验证「注入 gw7 分区 → 21 行 / 不注入 → 20 行 / 详情页正常·404·非法参数三种情形都置就绪」。
- F2 有界等待：`_count_attached()` 生效；复数断言（期望 0 个）保持瞬时判定。
- F3 报错纠偏：两条误导文案已替换（旧文案自相矛盾，实测把人带偏）。
- F6a 分区隔离：`/api/*?w=` + 复位只清自己分区。证据：gw0 新建 → gw0=21 / default=20；只复位 gw0 → 两边都 20。
- F6b 并发安全闸：`framework/target_probe.py` + CLI 未声明即降级 + `--isolated-target`。
  证据：`tests/test_ready_and_locate.py` 里两条**真跑 CLI** 的行为测试通过（未声明 → 打印降级并降到 1；显式声明 → 保持 2 worker）。
- F4 闸门脚本：`tests/verify_slow_target.py`（自带 demo + 慢代理；内存不足明确 SKIP exit 3）。
- 契约锁：`tests/test_ready_and_locate.py` **13 passed**（另有既有 87 passed 全绿）。

⏳ 待补（不写假绿）
- F5 断言稳健化：`cases/cross_page_detail.json` 的「全量 20 行」断言改成与新增无关的基线断言 —— 需重跑 generate（要浏览器）。
- 端到端验收：慢目标闸门全绿 / 全量 16 例 / Windows `-n 16` 全量绿 —— 本机 MemAvailable 仅 ~345MB（1 个 Chromium ≈515MB），
  且此前跑浏览器已触发 OOM（chrome 被杀 + Hermes 网关被连带杀一次，NRestarts 1→2）⇒ 主动暂停，等内存释放。
```

---

## 一、已排队（按上表顺序）

### ① 跨页面流程 + 弱 url 断言质量闸 + 变异注入闸门（同批做）★ 服务 ② AI 语义准
```
[B. 跨页面流程]
现状：新增 → 跳列表页 → 搜索核验这类跨页面链路写不完整。
目标：runner / generator 支持多页面上下文 + 每步断言。
改动面：runner.py / generator.py；需新写 1~2 条场景做验收。
验收：跨页链路端到端 PASSED；中途断链能 FAILED（不许假绿）。
设计：docs/P3-跨页面流程-设计.md（2026-09-13 起草，含 D1~D4 决策点与文件级改动清单，待确认后实施）

[弱 url 断言质量闸]（假绿，2026-09-14 挖出，与上面同源 → 同批做）
现象：AI 给「点返回列表回到列表页」产的 expect_url 只是 localhost —— 而**上一个页面的 URL 也含 localhost**
      ⇒ 点击后立刻就能通过，根本没证明发生了换页（跨页用例的关键证据悬空）。
目标：case_builder.case_warnings 增加静态检查 —— 跨页用例的 url 断言若只是 host（多页都含）→ 告警；
      同时把该用例改成「列表页独有元素可见」（如 [data-testid='btn-new'] 这类断言）。
验收：把坏断言喂进去 → 必须告警；改后的用例 PASSED，且**没换页时必须 FAILED**。
分工理由：这条修的是「AI 产出能不能当证据」= ② 的核心；排在跨页功能同一批，避免AI 又要返工一遍。

[变异注入 · 测试有效性闸门]（2026-09-14 AprilPark1012 裁定：归 ②，与上面同批）
动机：用例全绿 ≠ 测试有牙。AI 产出的断言「有没有牙」只能靠注入已知 bug 来量 —— 它是 ② 的直接度量，
      不是独立的 ③ 项（③ 现状已达标）。
做法：新增 tests/verify_mutation.py —— 往 demo 注入 N 个**已知 bug**（字段渲染错值 / 断掉跳转 /
      让某按钮失效 / 搜索改成包含匹配 / 详情页读错记录…），逐个跑用例集，统计「抓到几个」。
验收：每个注入的 bug 都必须被至少一条用例抓到（抓不到的 = 测试盲区，当场补用例）；输出命中矩阵。
价值：把「自己设计的东西自己验证、自己的狗粮自己吃」落成一条**可重复的闸门**；对外也是测试有效性的硬证据。
```

### ② CI 落点：GitHub Actions + 失败重跑（合并原 F）★ 服务 ① 降人力（产品交付门槛）
```
现状：只能在本机跑；同事 / 新员工拿不到「每次改动自动验」的能力。
目标：.github/workflows/ci.yml —— push / PR 时：起 demo → pytest tests/ → 16 用例 → 三个 verify 脚本；
      任一失败 → 红叉。公开仓库 Actions 免费无限额度。
附带：失败重跑（pytest --lf，只重跑上次失败的用例）。
为什么排第二：它是「降人力」里**杠杆最大**的一项 —— 本机跑一次只省一个人的一次手工回归，
      CI 让团队每个人、每次提交都自动回归；也是把框架从「我这台机器能跑」变成「产品能用」的最小交付面。
⚠️ 约束：往 .github/workflows/ 推文件**需要 token 带 workflow 权限**（当前 token 只给了 Contents: R/W，
      当时按最小权限刻意收紧，要做这条得重建一个带 workflow 的 token）。
验收：远端 Actions 跑绿；故意改坏一条用例 → 必须红。
```

### ③ A. 数据参数化「真展开」★ 服务 ① 降人力（增益，非门槛）
```
现状：scenarios/*.yml 的 data **只解析不展开** → 一个场景只能跑一组数据。
目标：生成 pytest parametrize，一组数据 = 一条用例 = 报告里独立一行（失败能定位到具体数据集）。
改动面：generator.py 模板 + case_builder.py；**不动定位逻辑**（回归风险小）。
验收：一个场景喂 3 组数据 → 3 passed 且报告 3 行；坏数据集 → 只该行 FAILED。
```

### ④ ④ 类遗留新能力（排列末位）★ 服务 ④ 脚本健壮 / 新能力
```
- [ ] P5c: 接入 Playwright Test Agents / 视觉兜底 / 云浏览器矩阵（需先 spike）
- [ ] `check` 动作补真页覆盖
为什么排末位：属于新能力，不解决 ② 的可信度和 ① 的人力问题；④ 现状已达标（V7.1~V7.4），
      按口径「新能力」在同目标内也低于「功能缺失」。
```

---

## 二、已完成（保留实测证据，便于复盘）

- [x] **C. CLI 参数卫生** → **V7.1（2026-09-13）**（服务 ④）
      改前实测问题：拼错 flag 被静默忽略（`prune --dry-run --workres 1` → exit 0）；
      未知子命令 `frobnicate` → 只打 __doc__ 且 exit 0；`_arg_values` 在 cli.py 两处重复定义（后者静默覆盖前者）；无 --help/--version。
      已做：`FLAG_SPECS` + `CMD_FLAGS` 单一定义；未知参数 → 拼写建议 + exit 2；参数用错子命令 → 说明它只用于谁；
            缺取值 / 多余位置参数 → exit 2；已移除参数给替代做法；补 --help/-h、--version/-V；
            `explore` 缺 `--ai` 由「静默 return」改 exit 2；删重复定义。
      证据：`tests/test_cli_flags.py` **40 passed**（合法不误杀 + 非法必 exit 2 + help/version/契约自检）。

- [x] **D. 断言类型扩展** → **V7.2（2026-09-13）**（服务 ② + ④）
      11 种 kind：text / visible / hidden / count / attr / value / url / checked / unchecked / enabled / disabled；
      `element`（语义名）或 `selector`（手写用例专用）定位；缺字段 / 未知 kind / 未映射 → 生成脚本 `pytest.fail`。
      证据：`cases/assert_kinds_*.json` 全 PASSED；`tests/verify_assert_kinds.py` 负向 **15/15 全 FAILED**；
            `tests/test_assert_kinds_render.py` 22 条翻译契约。
      顺手挖出真 bug：期望值 `0` / `""` 被真值判断吞掉 → 断言静默变形（改判据为 `"expect" in a`）。

- [x] **E. 执行提速** → **V7.2（2026-09-13）**（服务 ① + ③）
      conftest 浏览器改**会话级**（`_BrowserPool`，session scope）+ 每条用例只建 context/page；崩溃/OOM → 告警 + 重启。
      证据：13 用例 **7.01s**（改前 9 用例 10.49s）；逐条 setup **0.57~0.66s → 0.04~0.06s**。

- [x] **V7.3 统一 UTF-8（2026-09-13）**（服务 ④）：`text_io.py` 跨进程/落盘文本唯一口径 + `tests/test_utf8_io.py` 含 AST 全仓扫描（禁止依赖系统默认编码）。
- [x] **V7.4 客户字段改造 / 服务端单一数据源 / 用例间复位 / 看门狗（2026-09-14）**（服务 ② + ③）：详见 skill 与 RELEASE_NOTES_V7.4.md。
- [x] **V7.4.1 空目录根因清理（2026-09-14）**（服务 ④）：删 4 个无人使用的目录常量 + 收窄 `ensure_dirs()` + 防复发测试。
- [x] **公开仓库化（2026-09-14）**（产品交付前置）：脱敏（业务群缩写 / 客户名 / 昵称）+ 历史压成单提交 + noreply 身份 + MIT + 推送并验证。
- [x] training.html 升 V7.1（2026-09-13 完成，随 C 项一起发）

---

## 三、复核（每次改动后）

```bash
cd ~/hybrid_gui_qa && source .venv/bin/activate
python -m demo.app &                       # 被测应用（8000）
python -m pytest tests/ -q                 # 框架自测：期望 100 passed（87 原有 + 13 条 F1/F2/F3/F6 契约锁；秒级，不需 demo）
python tests/verify_slow_target.py         # ★ 慢目标闸门（自起 demo+代理，关键 6 条必须全绿；内存<650MB 会 SKIP exit 3）
python tests/verify_assert_kinds.py        # 断言正/负向端到端（需 demo；写错必须 FAILED）
python tests/verify_cross_page.py          # 跨页四段（需 demo）
python tests/verify_picker_layer.py        # 弹层回归（需 demo）
python -m framework.cli all --workers 2    # 期望 16 passed + 预检降级为 1 worker
dmesg -T | grep -ci "out of memory"        # 不得新增
systemctl show hermes-gateway-<profile> -p NRestarts --value   # 应恒为 1
python build_html.py                       # 同步培训页（无排版告警）
git add -A && git commit && git push       # 版本纪律（推送凭据从 pass 现取，见 skill）
```

> 真值来源：`--version` 必须等于 `build_html.py` 里的 VERSION / VERSION_DATE（两处各写 = 漂移源，已有测试盯着）。
> ⚠️ 本机 1.87G 无 swap：**别并发跑浏览器**（explore / generate / run / verify 一个跑完再跑下一个）。
> 待 ① 批（含变异注入）落地后，复核清单增补 `python tests/verify_mutation.py`（需 demo；每个注入 bug 必须被抓到）。
