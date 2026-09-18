# AI 混合 GUI 测试框架 · 版本 7.0（2026-09-11）

本包为 **V7.0** 快照。培训页（training.html）附录 A 有同一份更新记录的图形化版本。

## V7.0 · 2026-09-11 · 当前版本

主题：链路打通 · 资源安全 · 真实性保障

把「AI 说它对」变成「实测通过」：AI 产的用例与手搓用例跑同一条确定性执行链；并发按内存自动降级（不再 OOM 误杀网关）；所有静默兜底（假 AI / 假绿 / 死代码）逐一清除。

### 🚀 新增
- 场景库 scenarios/*.yml（一个文件 = 一个场景）+ 三个入口：--scenario（内联）/--scenario-file/--scenario-dir --tag --limit（三者互斥，参数错 exit 2）
- explore --ai 默认落 cases/ai_<id>_<ts>.json（--no-cases 可关）；--verify 交付即验证：落盘后立刻 generate + pytest 单跑，FAILED → exit 3（日志 output/verify/）
- cli prune 归档保留策略（framework/retention.py，HYBRID_KEEP_SNAPSHOTS 默认 20；explore/probe 结束自动静默执行）
- 调试开关 --debug（别名 --headed）：开了就「看得见」——有屏幕弹 Chromium 一步步跑；无屏幕自动录视频(webm) + 逐步截图 + trace 回放。配套 --case（只跑一条）/ --slowmo（放慢）
- 资源安全 P0：limits.safe_workers() 按 MemAvailable 自动降并发 + browser.py 收敛启动参数 + 日志 run-id 隔离
- 本文档新增「版本与更新记录」；第 4 节新增函数级调用链路图（图 A 图形化泳道图 + 图 B 明细）

### 🔧 改进
- generate 定位来源改为「快照优先」：element_map → probe 快照 → 现场 probe（命中即停），并打印来源与命中率（实测 8/12 命中 + 现场补齐 4/4）
- probe 消歧信号增强：label 兜底（同容器前置 label）+ 容器 heading，缓解同名控件歧义
- AI 规划更懂业务：prompt 接入【页面背景】+【本场景护栏】，新增规则 2b 区域消歧；语义校准告警（AI 描述 vs 控件语义重叠 <0.3 时提示「疑似选错」）
- 文档与代码做了一致性审计（以代码为准）：README 新增「两种业务场景」章节、调试开关整段重写，共修正 24 处

### 🐞 修复
- 假 AI 产物：LLM 失败时静默用 mock 冒充 AI（把待办页控件挂成合同页场景）→ 新增 AiExploreError，LLM 不可用直接 exit 2；只有显式 --mock-fallback 才降级且不写 cases/
- 编造断言：AI 写「共 N 条」这类运行时才知道的计数（真实是「共 20 条合同」）→ prompt 禁止 + case_warnings 计数/时间戳告警
- Sync API 跑在 asyncio loop 里（最隐蔽的死代码）：弹窗字段补充、DOM 上下文增强从来没生效过 → 拆「同步探测 → 异步规划」两段
- 重复探测：CLI 先探一次、explore 内部再探一次 → 两个 Chromium 抢内存，第二次静默失败 → 改为只探一次
- 静默丢元素：AI 给的名字对不上清单时 element=None 且零提示 → 改为精确/唯一模糊对齐 + 明确告警 + 可用清单
- 假绿：手搓用例元素名写错时生成脚本只留注释跳过，仍 PASSED → 改为 pytest.fail 显式失败
- --headed 是空操作：pytest -n 1 也会设 PYTEST_XDIST_WORKER=gw0 ⇒ conftest 判「并发⇒无头」（实测无 DISPLAY 也 9 passed）
- 录像只有 4KB 空壳：webm 必须等 context.close() 才落盘 → 调整保存时序（修后 152KB）
- _get_llm_text 死代码：在协程里调 asyncio.run() 必崩 → 新增 await 版 _get_llm_text_async()
- 文档漂移：probe.py docstring 声称的字段不存在；README 把 locator 优先级写反（实际 data-testid 置顶）
- DeepSeek function calling 间歇 JSON 抖动 → HYBRID_LLM_ATTEMPTS 退避重试（默认 3 次）

### 📌 说明
- 测试基线：9 用例全绿（6 条手写 + 3 条 AI）；零 AI key 也能跑（AI 只影响「有没有用例」）
- 已知边界（诚实清单）：单目标页面（跨多页面不完整）、data 参数化一期只解析不展开、并发受本机内存约束（1.87G 无 swap ⇒ 恒 1 worker）、check 动作代码支持但 demo 无 checkbox 未真页覆盖

## V6.0 · 2026-09-04 · 基线版本

主题：能跑通、能定位、能自愈

v7.0 之前的可用基线：三层定位 + 用例驱动 + AI 语义识别链路 + 自愈，配套 10 节培训页。

### 📌 说明
- 三层定位（data-testid 置顶）+ web-first 断言 + trace 录制
- 语义上下文消歧（nearby_text）；用例驱动 cases/*.json → generate 翻译 → pytest 并发
- 脚本与数据分离（字面值抽到 scripts/datasets/*.json）；用例级变量池 case.vars
- AI 语义识别链路（方案 C：DeepSeek 直连，绕开 browser-use Agent 的 schema bug）
- 自愈 healer.py（生成脚本接入自愈是 v7.0）；10 节新员工培训页（本文档）
