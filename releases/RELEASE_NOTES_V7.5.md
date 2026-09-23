# hybrid_gui_qa V7.5 交付说明（2026-09-14）

> 一句话：**修「慢目标 / 并发下的假红」** —— 团队 Windows（16 核 / 16 worker）上 `run all` 红 4 条、
> 同一份代码加 `--debug` 却全绿；根因是「页面就绪无契约」与「有状态目标 + 全局复位」两条。
> F1~F6 一起修，并新增**慢目标闸门**（把这类问题从「现场才发现」变成「跑一次就能拦」）。
>
> **补记说明（2026-09-23）**：本文件按当时 README 「变更要点」与项目台账**补写** ——
> V7.5 当时未单独出说明，而 `RELEASE_NOTES_V7.5.1.md` 记的是它之后的「坏产物交付事故」修复。
> 补写只为**历史可追**（README 重排时把变更史归并到发行说明）；已发出的内容一字未改。

---

## 一、事故与根因（先看不遮）

| 项 | 实情 |
|---|---|
| 现象 | 团队 Windows（16 核 / 16 worker）`python -m framework.cli run --workers 16` → **红 4 条**；加 `--debug`（自带 `--slowmo 200ms`）→ **全绿** |
| 为什么 `--debug` 能绿 | 它把时间窗拖过去了 —— **不是**证明代码没问题，恰恰说明红是「时序 + 状态」类 |
| 本机确定性复现 | 单进程、无并发，加「每请求 **+400ms** 的反向代理」⇒ **5 failed / 1 passed** |

| 根因 | 机制 | 修法 |
|---|---|---|
| **R1 页面就绪无契约** | 页面 `boot()` 异步取数后才渲染，而测试 `goto` 之后**立刻**动作/断言 ⇒ ① 弹层行还没渲染就点 → 命中 0（连兜底也找不到）② 早到的搜索在**空数组**上过滤，随后首屏渲染把结果**覆盖**成全量 ⇒ 计数断言永远等不到 | **F1 就绪契约** + **F2 定位有界等待** |
| **R2 有状态目标 + 全局复位** | 单一 store + 每用例 `POST /api/reset`（**全局**）⇒ 多 worker 下精确计数断言互相踩（实测：期望 20 行实得 23、期望 4 条实得 6） | **F6 每 worker 数据分区** + 并发安全闸 |

---

## 二、修了什么（F1~F6）

### F1 就绪契约 —— **给团队接自己系统时最重要的一条**
页面在 `body` 上静态声明、数据渲染完成后置位：

```html
<body data-hybrid-ready="0">   <!-- 静态声明：本页遵守就绪契约 -->
<script>
  // ……你的取数 + 渲染……
  document.body.dataset.hybridReady = "1";   // 数据已就位，测试可以开始动作/断言
</script>
```

生成脚本的每个 `goto` 都会等它（统一走 `_goto()`）。**没有契约的老页面**：用
`HYBRID_READY_SELECTOR=<数据已就绪选择器>` 退化；两者都没有 ⇒ 只提醒一次、不阻塞
（后续动作/断言自带 F2 的有界等待兜底）。想让「就绪超时」直接失败：`HYBRID_READY_REQUIRED=1`。

### F2 定位判定改为「有界等待」
`_act` / `_resolve` 的确定性主定位不再用**瞬时** `count()` 判生死，而是先等元素 `attached`
（`HYBRID_LOCATE_TIMEOUT`，默认 5s）再判 —— 慢机器/高并发下元素「晚到」不再被误判成「不存在」。
**复数断言（`count`）仍瞬时判定**：「期望 0 个」是合法用例，等它只会白等一个超时。

### F3 报错信息纠偏
旧文案「断言 locator 失效且无语义兜底（该断言既没 selector 也没 element）」**与事实相反**
（那条断言其实有 selector）⇒ 改为「等了 N 秒仍是 0 个元素 + 常见原因 + 排查动作」；
「元素语义未找到」也补上真因链与下一步。

### F4 新增闸门：慢目标
```bash
python tests/verify_slow_target.py               # 自起 demo:8011 + 代理:8012，关键 6 条必须全绿
SLOW_MS=800 python tests/verify_slow_target.py   # 更极端的"拥挤机器"
python tests/verify_slow_target.py --full        # 全部用例（慢）
```
内存不足（可用 < 650MB）时**明确 SKIP 并 exit 3** —— 绝不给假绿。

### F6 并发必须「数据隔离」
- **demo 侧**：`/api/*` 都认 `?w=<分区>`，`/api/reset` **只清自己那份**；`GET /api/health` 声明 `partitioned`；
- **conftest 侧**：给每个 worker 注入 `window.__HYBRID_W`，页面把它带进所有 API 调用；
- **CLI 侧**：目标未声明可并发隔离时，**并发保守降级为 1** 并说明原因；确知已隔离用 `--isolated-target` 放行。

### F5 断言稳健化 —— ⚠️ 本版**未完成**，如实记档
`cases/cross_page_detail.json` 的「列表恢复全量 20 行」（`count expect=20`）当时仍是脆弱断言
（需要目标在跑 + 真浏览器才能改完并验证）⇒ **V7.5.3 已补齐**（换成「预置基线行 `row-HT-1001` 在列表里」，
与本次运行新建的数据无关），见 `RELEASE_NOTES_V7.5.3.md`。

---

## 三、实测证据（当时，逐条可查）

| 项 | 证据 |
|---|---|
| F1 就绪契约 | 真浏览器验证：注入 `gw7` 分区 → **21 行** / 不注入 → **20 行**；详情页「正常 / 404 / 非法参数」三种情形都置就绪 |
| F2 有界等待 | `_count_attached()` 生效；复数断言（期望 0 个）保持瞬时判定 |
| F6a 分区隔离 | `gw0` 新建 → `gw0=21` / `default=20`；只复位 `gw0` → 两边都回到 20 |
| F6b 并发安全闸 | `tests/test_ready_and_locate.py` **13 passed**（含两条**真跑 CLI** 的行为测试：未声明 ⇒ 打印降级并降到 1；显式声明 ⇒ 保持 2 worker） |
| F4 慢目标闸门 | 每请求 300~400ms 下关键 6 条全绿；内存不足时 SKIP exit 3 |

---

## 四、已知遗留（如实记档）

1. **F5 断言稳健化**：本版未完成 ⇒ V7.5.3 补齐（见上）。
2. **CI 落点**：当时未做（2026-09-17 裁定**不做** —— 需重建带 workflow 权限的 token）。
3. **Windows 侧并发隔离证据**：不再追补（F6b 已有两条真跑 CLI 的行为测试，足够）。

---

## 五、改动面（当时路径 · 冻结记录不改）

```
demo/contracts.html · demo/contract_detail.html   body[data-hybrid-ready] 静态声明
framework/target_probe.py                          并发安全预检（partitioned 探测 + 降级理由）
framework/cli.py                                   资源预检 / --isolated-target / 就绪开关接线
framework/generator.py · framework/locator_bridge.py  有界等待（_count_attached）与报错文案
framework/healer.py                                兜底路径同步（不掩盖真 bug）
scripts/test_cases.py                              生成物重跑（32 处 goto 全走 _goto）
tests/test_ready_and_locate.py                     就绪契约 + 定位契约（13 条）
tests/verify_slow_target.py                        新增慢目标闸门
```

> 说明：上面的路径是 **V7.5 当时的目录结构**（`framework/` 平铺模块）；V8.0 起改为
> `framework/tools/{common,probe,explore,generate,run}/` 分层 —— 历史记录按 R9 口径**原样保留**，不回头改。
