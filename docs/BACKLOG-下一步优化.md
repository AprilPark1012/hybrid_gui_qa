# BACKLOG · 下一步优化清单

> 维护约定：动一项就划掉一项并补「实测证据」。
> **当前基线：V7.5.3 + 订单场景批次（2026-09-18，未发版）**：17 用例全绿（12 手写 + 5 AI）·
> 框架自测 **158 条** · verify 脚本 4 个
> （断言正负向 / 跨页 / 弹层 / 慢目标；本批实跑 `verify_cross_page.py` ✅）。
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
| ② AI 语义准 | ✅ 已有：跨页面流程（D1~D4 全落地）+ **弱 url 断言质量闸**（2026-09-17）+ **元素歧义闸门**（2026-09-18，见〇-g：命名留痕 / 合并后统一重命名 / 运行期模糊兜底收敛）；⏳ 剩：变异注入闸门（量「AI 产出的断言有没有牙」，AprilPark1012 2026-09-14 裁定归此）|
| ① 降人力 | 数据参数化真展开（一份数据模板顶多条用例）｜~~CI 落点~~（**2026-09-17 AprilPark1012裁定：不做**，见〇-e）|
| ③ 稳定 | 队列内暂无专属项（V7.x 已达标：内存降级 / 看门狗 / 退避重试 / 会话级浏览器崩溃重启）—— 新发现的 ③ 风险立即插队 |
| ④ 脚本健壮 | V7.1~V7.4 已达标；遗留新能力（Test Agents / 视觉兜底 / 云矩阵）排末位 |

据此排定：**① 变异注入闸门（服务 ②）→ ② 数据参数化真展开（服务 ①）→ ③ ④ 类遗留新能力**
（**2026-09-17 更新**：跨页面流程 + 弱 url 质量闸已落地；CI 落点按AprilPark1012裁定从队列删除）

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

## 〇-c、⚠️ 现场问题（优先级高于排队顺序 · 2026-09-14 团队演示触发）· **已实施 + Windows 实测通过（2026-09-15）**

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
- F5 断言稳健化：**✅ 2026-09-17 完成**（见〇-e ⑤）——「全量 20 行」已换成与新增无关的基线断言
  （预置行 HT-1001 存在），全量 16 用例 PASSED 且逐用例日志可查。
  ⚠️ 本机内存口径（照此办，别硬跑）：跑浏览器前先 `free -m` 与 `limits.safe_workers()` 看余量；
  MemAvailable 掉到 ~360MB 时必须先腾内存（本轮实测：一个 pyright 语言服务就占 286MB，
  回收后回到 642MB 才够跑 generate + pytest）。
- 端到端验收：✅ **已通过（2026-09-15，Windows 实测）**
  · `python -m pytest tests/ -q` → 97 passed + 3 skipped（那 3 条是 GBK 复现类**条件跳过** ⇒ 已由 V7.5.1 的跨平台 guard 修掉）
  · `python -m framework.cli all --workers 16` → **全绿**
  · `python tests/verify_slow_target.py` → **全绿**（生成物刷新后；详见〇-d）
```

---

## 〇-d、⚠️ V7.5 **交付事故** + V7.5.1 修复（2026-09-15）· **已完成（本地）**

```
现象：Windows 上验收第 3 条 `python tests/verify_slow_target.py` → 5 failed / 1 passed（真红）。
真因：**交付包夹带的 `scripts/test_cases.py` 是坏产物** —— 100 处「元素未映射」存根
      （sha256 10afa0ef…，与 git 提交里那份完全相同）；正确产物 sha256 55d85d50…。
根因：现场探测不可用时，`generate` 只打一句警告就继续落盘、而且 **exit 0** ⇒ 产出一份「看着合法、
      跑起来全失败」的假脚本，被提交 / 被打包 / 被交付，真因无处可查。
      附带：打包环节那次「检查」本身还是**假绿** —— 本机没装 `unzip`，`unzip -p … | grep -c`
      收到**空输入**数成 0 命中，被当成「包是干净的」。
影响面：直接跑包内 `scripts/test_cases.py`（pytest / 慢目标闸门）的人会看到一堆「元素未映射」；
      跑 `cli all`（会重新 probe+generate）的人不受影响 —— 这正好解释了「all 全绿、闸门却红」。

✅ V7.5.1 已实施（G1~G5；方案与证据：docs/P5-交付修复-V7.5.1-方案.md · RELEASE_NOTES_V7.5.1.md）
- G1 映射质量闸：拿不到定位 ⇒ **不写任何产物** + exit 2 + 人话（缺失清单 / 真因 / 下一步）；
      `--allow-unmapped` 仅作调试逃生口（产物永不允许进交付）。
- G2 目标可达性预检：`target_probe.reachability()` 三分（连不上 / 有响应但无 /api/health 仍算活 / 可达）；
      `cli probe` 不可达 → 人话 + exit 2（不再甩一屏 Playwright traceback）；顺手统一 TARGET_URL ⇄ HYBRID_BASE_URL。
- G3 `tests/verify_*.py` 补 `force_stdio()`（控制台中文乱码的根因）+ 源码级「一个都不许漏」判据。
- G4 交付前自检：`tests/test_artifacts_health.py`（未映射=0 / 无裸 page.goto / conftest 接线齐 / cases↔datasets 1:1）
      + `tools/pack_release.py`（打包即用**标准库 zipfile** 复扫包内产物；不达标 **删包 + exit 2**；`--check` 可审计历史包）。
- G5 跨平台 GBK guard：NT 分支读系统 ANSI 代码页 ⇒ 中文 Windows 上三条 GBK 复现用例不再跳过。
- 门禁证据：自测 **130 passed**（受限环境 127 + 3 skipped）｜负向对照：把坏产物放回 → 健康闸门当场红；
      `pack_release --check` 审计 V7.5 旧包 → 抓出 100 处未映射 + exit 2；不可达时 `cli probe` → 人话 + exit 2。
- 顺带更正：7.5 CHANGELOG 里「F5 已完成」是**不实表述**（那条 20 行断言至今仍在）⇒ 已改为如实记档。
- 交付物：`releases/hybrid_gui_qa_V7.5.1_20260915.zip`（96 文件 / 723 KB；**sha256 以交付消息打印的为准** —— 包里不写自己的 sha，否则改一次内容 sha 就变，永远自相矛盾）；
      提交 `4c99e55`（18 文件，noreply 身份）；仓库工作区干净。
      （2026-09-16 按新规矩修正路径：交付包落库到**仓库内 `releases/`**，不再用 `/tmp/pkg`。）
- 敏感信息例行闸门（用户 2026-09-15 定调）已落地：skill `public-repo-privacy-hygiene` 第〇节 +
      升级版 `scripts/scan_residue.py`（逐行/逐对象细节 + 清理指引）+ 本仓 `.git/hooks/pre-push` 实装（自测过拦/放两态）。

✅ 三项均已了结（2026-09-17 更新）
- **F5 断言稳健化**：已完成（见〇-c / 〇-e ⑤）。
- **已公开历史里 2 个旧 blob 含一处内部组织缩写**：**已彻底清零**（2026-09-16 走「本地重写历史 + 远端删仓重建 + 重推」：
  7 个提交全保留、新 SHA，工作树一字未动；对象对账全可达 · garbage 0 · 三层复扫全 0；远端为重建后的干净仓库）。
- **CI 落点**：**不做**（AprilPark1012 2026-09-17 裁定，见〇-e）。

---

## 〇-e、2026-09-17 批次：修「假绿」三项 + 三处裁定（AprilPark1012当日拍板）

```
[本轮范围] AprilPark1012 2026-09-17 裁定：「先做 1、5、10，把假绿的问题修掉」；
           CI 落点(3)、Windows 并发隔离证据(6) 直接从清单删掉、不做；V7.5.1 包(7) 可删。

① 弱 url 断言质量闸 —— ✅ 已完成（提示词根因 + 红线闸门 + 用例修正，详见上一节 ①）
⑤ F5 断言稳健化 —— ✅ 已完成：`cases/cross_page_detail.json` 的「列表恢复全量 20 行」→ 换成
   「预置基线行 HT-1001 在列表里」（与本次运行新建的数据无关 ⇒ 不再被顶掉）。
   实测：全量 16 用例 PASSED，逐用例日志里该断言真实执行（`【回到列表页·基线】…（count=1）`）。
⑩ 质量闸自身崩溃 —— ✅ 已修：`case_builder.case_warnings` 遇到**非字符串 expect**（如 `count` 的 `20`）
   直接 `TypeError: expected string or bytes-like object, got 'int'`。修法：文本形态检查只对 str 生效 +
   「断言回显输入」比较全程走字符串口径。回归：`test_warnings_never_crash_on_structured_expect`
   （11 种 kind × 7 种期望值形态 × 4 种定位写法）。**为什么算假绿**：守门人自己崩 ⇒ 这道栅栏等于不存在。

⑪ 顺手挖出并修掉的真问题（本轮最大收获）：`tests/verify_cross_page.py` 的负向段**自 V7.5.1 起就没跑起来**
   —— 负向用例 ④ 故意用不存在的元素名，而 V7.5.1 的映射质量闸会把**整个** generate 拦成 exit 2
   ⇒ 该段「N 条负向必须 FAILED」实际长期未执行（**机制失效比假绿更隐蔽**：脚本 exit 2 看着像失败，
   实际是它自己没跑完）。修法：负向段显式走 `generate --allow-unmapped`（逃生口；产物只服务负向验证，
   跑完 `_cleanup()` 不带逃生口重新生成干净产物），并在代码里写清原因。
   修后实测：**5 条负向全部 exit=1 FAILED**（含新增 ⑤「没回到列表页时，列表页独有文案断言必须失败」）。

✅ 裁决留档（AprilPark1012 2026-09-17）
· CI 落点：**不做**（原队列第 2 项，已从本文档删除）。理由：需重建带 workflow 权限的 token；
  且按目标优先级 ② AI 语义准 ≈ ① 降人力，先继续把「AI 产出的可信度」做扎实。
· Windows 并发隔离证据：**不再追补**（F6b 已有两条真跑 CLI 的行为测试，足够）。
· V7.5.1 包：**已删**（未发出的过渡版，已被 V7.5.2 收敛替代）；原 sha256 留在
  `releases/SHA256SUMS.txt` 注释里备查，`RELEASE_NOTES_V7.5.1.md` 仍保留。
```

---

## 〇-f、2026-09-17/18 批次：订单场景（跨 tab 端到端）· **AI 链路已跑通，改动待提交**

```
[本轮范围] AprilPark1012 2026-09-17 22:35 提出：设计跨 tab 场景
           「合同页新建退货订单并查看订单详情」→ 要求 AI 端到端完成（用例生成 → 脚本生成 → 执行验证）。

① 框架新能力（为多 tab 与动态行而加）
   · probe：`opens_new_tab`（目标 `_blank` / window.open ⇒ 点击会开新 tab，不让 LLM 猜）
            + `probe_row_fields()`（表格行内列清单 field/header，供 AI 做行内定位）
   · element_map：TestStep 增 `row_text` / `cell_field`
   · case_builder：新动作 `click_new_tab` / `close_tab` / 断言 `expect_first_row`（kind=first_row + row_field）
   · generator/conftest：`_Tabs`（新 tab 切换/关闭 + 真的关了没）、`_click_row_cell`（行锚文本 + 列字段定位）、
                        `_assert_first_row`（验「第一条就是刚建的那条」—— text 断言证明不了位置）

② 本次修掉的两个真 bug（都是"看着对、其实点错/误伤"类）
   (a) **同字段·跨区域·不同名字 ⇒ AI 静默选错控件**（服务 ②，本轮最大收获）
       现象：AI 端到端连跑 6 次，6 次都把弹窗里的「订单名称」选成**筛选区**的框
             （`订单名称_全模糊` label=订单名称 / placeholder=订单名称（全模糊） / container_heading=空
               vs `请输入订单名称` label=订单名称 * / placeholder=请输入订单名称 / container_heading=新建订单）。
       为什么两个闸门都没拦住：名字**完全不同** ⇒ `_shadowed_names`（只看完全同名）报不出来；
             两个名字**都能映射到真实控件** ⇒ 不报「未映射」= **静默错映射**。
       定位手段（可复用）：解失败那次的 `trace.zip` → `trace.network` 里**没有 POST /api/orders**
             ⇒ 提交没发出 ⇒ 前端必填校验没过 ⇒ 弹窗字段根本没填进去（比读日志猜快得多）。
       修法：`explorer._field_identity()`（label 归一化：去 `*`、去结尾「（全模糊）」）+ `_same_field_pairs()`
             ⇒ 提示词里**显式列出**「同一字段的多个不同名字版本 + 各自所属区域」，并加规则 2c
             （说明选错不会报未映射、只会悄悄操作到别的控件）。
       证据：修后第 7 次 AI 端到端第 7 步自动变成 `请输入订单名称`；`--verify` 实测 **PASSED**；
             回归 `tests/test_name_alignment.py` 新增 5 条（含"提示词里必须真出现这段披露"的接线判据）。

   (b) **跨页重名告警按「全局并集」判定 ⇒ 误伤其它用例（假红）**（服务 ③ 底线）
       现象：`cli run` **15 passed / 2 failed** —— 手写跨页用例 `cross_page_detail`、
             `ai_contracts_cross_page_011030` 报「跨页用例的步骤用了跨页重名的原始名 'HT_1005'」。
       根因：订单场景带来「订单系统」页，它与「列表页」都有 HT_1001…HT_1020 链接 ⇒ `HT_1005` 进全局名单；
             而这两个用例自己声明的页面是「列表页+详情页」，**在它们范围内根本不重名**。
       修法：`_DUP_RAW_NAMES` 旁增 `_DUP_PAGES`（名 → 出现过的页集合）+ `_dup_raw_names_for_case()`
             ⇒ 判据改成「**本用例声明的页 ∩ 该名字出现的页 ≥ 2**」；`_render_assert(..., dup_raw=…)` 按用例透传。
       证据：回归 `tests/test_assert_kinds_render.py` 新增 3 条（含"真重名仍必须拦"的反向判据，防修成漏拦）；
             修后 `cli run` **17 passed / exit 0**。

③ 交付物与实测
   · `scenarios/orders/orders_return_from_contract.yml`（3 页 / 30 步 / 护栏 + 逐字语义名清单）
   · AI 用例 `cases/ai_orders_return_from_contract_004934.json`（AI 端到端产物，0 未映射）
   · **AI 端到端（真跑）**：`explore --ai --scenario-file …` → exit 0 · `--verify` 实测 PASSED（1 passed in 4.01s）
     逐步骤证据：新 tab 开订单系统 ✔ 4 个弹层选值 + 类型/客户/销售员 ✔
     首行断言「第一行订单名称 = 刚填的 退货订单-20260918005504」✔
     点该行合同编号 → 新 tab 合同详情（?no=HT-1001&from=order）显示 HT-1001/合同1 ✔
     点「返回」→ **tab 真的关了**(真的关了=True) 并回到订单列表 ✔
   · 回归：`pytest tests/ -q` **158 passed** · `cli run` **17 passed / exit 0** · `generate` 未映射 0
   · 内存纪律：本轮两次撞内存红线（一次 OOM 连杀 chrome + hermes ⇒ CLI 掉线）：跑浏览器前先看 MemAvailable，
     先杀掉占 ~350MB 的 pyright 语言服务；`console` 有 `dmesg | grep oom-kill` 可复核。

⏳ 待 AprilPark1012 拍板的三件：① 提交（框架改动 + 场景 + 用例 + 测试，走敏感词闸门）
   ② 推送公开仓 ③ 是否升 **V7.6**（按版本规则：新增能力 ⇒ 递增 x2，而不是 x3 修复位）。
```

---

## 〇-g、2026-09-18 批次：LLM 录像（离线跑 AI 链路）+ 元素歧义闸门（批次 2）· **代码已落地并验证，改动待提交**

### 1) LLM 录像（录制/回放）—— 让「连不上外网 AI」的机器也能跑 explore
- 代码：`framework/llm_cassette.py`（新）+ `explorer` 注入点 + `cli` 的 `--llm-record` / `--llm-cassette`
  / `--llm-cassette-strict`；模式**只由 CLI 参数决定**，不做自动降级。
- 两个键：**严格键**（逐字一致的 prompt，最高保真）+ **结构键**（场景文案 + 页面 url + 控件骨架，
  排除数据值）⇒ 数据换了也能命中，但命中时会大声告警（步骤是录制当时针对那批数据做的判断）。
- **验收（AprilPark1012指定口径）：工作电脑能「explore 语义识别 → generate 生成用例脚本」**——
  本机离线实测（端点指黑洞 `127.0.0.1:9`、不配 key）：回放命中 → 落 `cases/ai_*.json`（`llm_source: cassette:<键>`）
  → `generate` **未映射 0** → `run --case <id>` **1 passed**；
  并把录像包解到 `/tmp`、用**包里自带**的 `offline_explore_chain.py` + 包内录像再跑一遍 ⇒ 同样全通。
  证据：`~/deliver_scripts/out/offline_chain_evidence_20260918.txt`。
- 录像包（给无外网机器）：`hybrid_gui_qa_llm_cassettes_20260918.zip` · 55,485 B ·
  sha256 `e29c63670902294ab9dd589c0aeee665001c027f7c0be85b0b88dc945bd155a4` · 5 份录像 + README + 一条命令脚本。
- ⚠️ **版本配套铁律**：录像键含控件骨架 ⇒ 改 demo 页面 / 场景文案 / **命名逻辑** 都会让录像失效。
  本轮实测：S1 只改了「同名控件唯一化的时机」，某按钮语义名 `取消` → `取消@新建合同`，45 个控件差 1 个，
  结构键就整份对不上（回放 exit 2）。⇒ **录像必须在最终版代码 + 同版 demo 上录，改完就重录重打包。**

### 2) 元素歧义闸门（批次 2 · 方案见 `docs/P8-元素歧义闸门-方案.md`）
- 根因四条：R1 每轮探测各自命名（裸名归谁取决于探测那刻谁可见）/ R2 合并按名字字符串去重 /
  R3 同页唯一化不留痕 / R4 运行期包含关系模糊兜底（静默挑第一个）。
- S1：`probe.assign_semantic_names()` 可重算 + 留痕（`base_name`/`ctx_token`/`name_source`/`base_conflict`）；
  `explorer._merge_items()` 改为「先按 test_id 去重 → 再在合并后的全量清单上重算命名」，四个调用点同源。
- S2：缺失名若是同名冲突组的 base 名，报错**直接给候选**（`UnmappedElementsError.conflicts` + CLI 人话）。
- S3：生成物 `_item_for()` 的模糊兜底收敛 —— 候选唯一才接受且**留痕**；候选 ≥2 **抛错并列候选**；
  `HYBRID_STRICT_LOCATE=1` 连唯一候选也不兜。
- 证据：`tests/test_element_ambiguity_gate.py` **15 条**（含模板 ⇄ 生成物互锁；6 条测的是渲染出来的生成物）·
  `tests/verify_element_ambiguity.py` **浏览器级复现 exit 0**（用 `tests/fixtures/ambiguous_page.html` 造事故形态，
  旧算法裸名仍在 / 新算法裸名消失）· `pytest tests/ -q` **202 passed** · `cli run --workers 1` **17 passed / exit 0**
  且运行日志里模糊兜底 **0 次触发**（零误伤）· 敏感词闸门三层全 0。

⏳ 待拍板：① 提交（framework 4 文件 + scripts 生成物 + demo 三文件 + training.html + 新增 docs/tests）② 推送公开仓
   ③ 版本号定为 **V7.7**（cassette 新能力 + 批次 1 + 批次 2 合并一版）④ 录像包发到工作电脑的途径。

---

## 一、已排队（按上表顺序）

### ① 弱 url 断言质量闸 + 跨页面流程 ★ 服务 ② AI 语义准 —— ✅ **已完成（2026-09-17）**

```
[弱 url 断言质量闸]（假绿：AI 给「点返回列表回到列表页」产的 expect_url 只是 localhost —— 上一页 URL 也含它
      ⇒ 点击后立刻就能通过，根本没证明发生了换页）**根因级修复，三层一起**：
· 提示词（真根因）：`explorer._build_planner_prompt` 原先**在教 AI 这么写**（「列表页写 localhost 或留空不要写」）
  ⇒ 改为「只准用**只出现在目标页**的片段；**禁止** localhost / localhost:8000 / 127.0.0.1 这类每页都含的片段；
  目标页没有独有片段（列表页就是根路径 /）→ 对该页独有文案做 text 断言」。
· 闸门（红线）：`case_builder.case_errors()` —— 换页证据必须**只指向一页**（判据：片段在几页 URL 里命中；
  「命中 ≥2 页」或「跨页用例里只是 host[:端口]」= 红线）。AI 落盘（`elementmap_to_cases_file`）与
  生成（`generator._gate_false_green`）**两条路都拒绝出产物**（exit 2 + 人话），口径同映射质量闸：
  **产物永不允许带假绿**。单页用例里的 host 断言只告警（手写用例可能是有意的，如专门验 host:port）。
· 用例：`cases/ai_contracts_cross_page_011030.json` 的 `expect: localhost` → 改列表页独有文案 `新建合同`（text）；
  `cases/cross_page_detail.json` 保留 `contract_detail`（只出现在详情页，有区分力）。
· 实测证据：CLI 层负向 —— 喂一条 `expect: localhost` 的跨页用例跑 `cli generate` ⇒ **exit 2 + 人话 + 产物 sha 一字未改**；
  `tests/test_case_quality_gate.py` **13 条**（含「11 种 kind 全形态不崩」「真证据不许误拦」「仓库用例扫描」）；
  `tests/verify_cross_page.py` 第二节新增「弱证据必被红线拦 / 真证据不许误拦」两条判据；
  全量 16 用例 PASSED，逐用例日志里两条改后的断言都真实执行过（不再空验）。

[跨页面流程] D1~D4 **已落地**：`pages` 声明 · 原地断言 `after_step` · 跨页同名消解（`搜索@列表页`/`搜索@详情页`，
      重名不再静默丢）· 换页证据闸（上方）。设计见 docs/P3-跨页面流程-设计.md（该文档状态行仍写「待确认」，
      实际已实施 ⇒ 待改状态）。
```

### ② 变异注入 · 测试有效性闸门 ★ 服务 ② AI 语义准（原与 ① 同批，① 完成后剩它）
```
动机：用例全绿 ≠ 测试有牙。AI 产出的断言「有没有牙」只能靠注入已知 bug 来量 —— 它是 ② 的直接度量，
      不是独立的 ③ 项（③ 现状已达标）。
做法：新增 tests/verify_mutation.py —— 往 demo 注入 N 个**已知 bug**（字段渲染错值 / 断掉跳转 /
      让某按钮失效 / 搜索改成包含匹配 / 详情页读错记录…），逐个跑用例集，统计「抓到几个」。
验收：每个注入的 bug 都必须被至少一条用例抓到（抓不到的 = 测试盲区，当场补用例）；输出命中矩阵。
价值：把「自己设计的东西自己验证、自己的狗粮自己吃」落成一条**可重复的闸门**；对外也是测试有效性的硬证据。
```

### ② 数据参数化「真展开」★ 服务 ① 降人力（增益，非门槛）
```
现状：scenarios/*.yml 的 data **只解析不展开** → 一个场景只能跑一组数据。
目标：生成 pytest parametrize，一组数据 = 一条用例 = 报告里独立一行（失败能定位到具体数据集）。
改动面：generator.py 模板 + case_builder.py；**不动定位逻辑**（回归风险小）。
验收：一个场景喂 3 组数据 → 3 passed 且报告 3 行；坏数据集 → 只该行 FAILED。
```

### ③ ④ 类遗留新能力（排列末位）★ 服务 ④ 脚本健壮 / 新能力
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
python -m pytest tests/ -q                 # 框架自测：期望 158 passed（含换页证据闸门 / 名称对齐 / 跨页重名按用例判定；秒级，不需 demo）
python tests/verify_slow_target.py         # ★ 慢目标闸门（自起 demo+代理，关键 6 条必须全绿；内存<650MB 会 SKIP exit 3）
python tests/verify_assert_kinds.py        # 断言正/负向端到端（需 demo；写错必须 FAILED）
python tests/verify_cross_page.py          # 跨页：三节判据 + 5 条负向必须全 FAILED（需 demo；内部负向段走 --allow-unmapped）
python tests/verify_picker_layer.py        # 弹层回归（需 demo）
python -m framework.cli all --workers 2    # 期望 17 passed + 预检降级为 1 worker
dmesg -T | grep -ci "out of memory"        # 不得新增
systemctl show hermes-gateway-<profile> -p NRestarts --value   # 应恒为 1
python build_html.py                       # 同步培训页（无排版告警）
git add -A && git commit && git push       # 版本纪律（推送凭据从 pass 现取，见 skill）
```

> ⚠️ 跑浏览器前先看 MemAvailable（本机红线见 skill）：先杀掉 ~350MB 的 pyright 语言服务再跑，别并发跑浏览器。
> 真值来源：`--version` 必须等于 `build_html.py` 里的 VERSION / VERSION_DATE（两处各写 = 漂移源，已有测试盯着）。
> ⚠️ 本机 1.87G 无 swap：**别并发跑浏览器**（explore / generate / run / verify 一个跑完再跑下一个）。
> 待 ① 批（含变异注入）落地后，复核清单增补 `python tests/verify_mutation.py`（需 demo；每个注入 bug 必须被抓到）。
