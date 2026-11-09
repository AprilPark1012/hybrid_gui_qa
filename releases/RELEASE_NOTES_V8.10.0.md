# V8.10.0 发行说明 · 跨 origin 多业务系统（一套 SSO）

**日期**：2026-11-09　**类型**：特性版本（新能力 + 新契约）

> 一句话：真实生产里 **合同 / 订单 / 发票是不同业务系统（不同 origin），登录却是同一套 SSO**。
> 本版让框架能**在一个场景里跨多个 origin 跑通**，并且**登录一次就够**。

---

## 1. 之前为什么不行（两个缺口，都先在本机复现再动手）

| # | 缺口 | 实测证据 |
|---|---|---|
| ① | **地址被压平成一套系统** | 旧口径 `_rewrite_base()` 把**任何**地址的 origin 换成单一 `HYBRID_BASE_URL` ⇒ 设了 `base=8000` 后，`goto localhost:8001` **实际落到 8000**（`Actual value: http://localhost:8000/api/health`） |
| ② | **会话不跨 origin** | 会话在 `localStorage` 里是 per-origin 的。登录落在 8000，访问 `8001/orders.html` ⇒ 落到 `8001/login.html?next=%2Forders.html`（被踢回**它自己**的登录页） |

⚠️ ① 比「不支持」更糟：**探针扫的是真跨系统、运行打的是被压平的单 origin** ——
「探到的和跑的不是一回事」，而且默认就会发生（`.env` 默认就写着 base）。

---

## 2. 本版给的四个能力

### 2.1 场景层：给每个业务系统起名字

```yaml
origins:
  order:   http://localhost:8001
  invoice: http://localhost:8002

pages:
  - name: 合同列表页
    url: http://localhost:8000/            # 登录所在系统（也可是 ${sso}/…）
  - name: 订单列表页
    url: ${order}/orders.html
  - name: 发票列表页
    url: ${invoice}/invoice_list.html
```

- `${名字}` 会展开到 `pages[].url` / `pages[].probe_url` / `target.url` / `login.url` **四处**；
- **引用了没声明的名字 ⇒ 加载期硬红并点名**（不猜、不静默留空）；
- 不写 `origins` 的场景 = 单系统老行为，**一行都不用改**。

### 2.2 运行期：只换「声明过的那个 origin」

新唯一入口 `_rw(url, origin_name)`：

| 情况 | 行为 |
|---|---|
| 有名字 + `HYBRID_ORIGIN_MAP` 有映射 | 换成映射地址（path / query / fragment 原样保留） |
| 有名字 + 没映射 | **原样返回**（**绝不压平**到 `HYBRID_BASE_URL`） |
| 无名字（单系统老用例） | 逐字回落旧 `_rewrite_base(url)` —— 行为完全不变 |

换环境只改一处：

```bash
HYBRID_ORIGIN_MAP='{"order":"http://order.example.com:8001","invoice":"http://invoice.example.com:8002"}'
```

已登记进 `cli config` 可调项（`python -m framework.cli config`）。

### 2.3 会话铺开：登录一次，铺到各 origin

```yaml
login:
  url: http://localhost:8000/login.html
  scenario: 在登录页填写账号 super、密码 super@123，然后点「登录」
  wait: { url_not: login.html }
  session:
    token_from: url_param      # 从登录后地址的 ?token= 取会话
    param: token
    store: localStorage
    key: demo_token
    spread: [order, invoice]   # 铺到这两个 origin
```

- 唯一实现：`framework/shared/sso_session.py::spread_session()`；
- **探针期与执行期都挂**（只挂执行期 ⇒ `explore` 探跨 origin 页面只会探到各自登录页的 8 个控件，
  真业务页是 108 / 201 个 —— 探针不报错，最难发现）；
- 不声明 `session` ⇒ **零副作用**。

### 2.4 与既有权能的关系

| 能力 | 本版变化 |
|---|---|
| `HYBRID_BASE_URL`（单系统换环境） | **不变**，仍是唯一入口的回落分支 |
| 场景页名唯一 / 跨页同名控件 `原名@页名` | 不变（跨 origin 一样生效） |
| **多套互不相通的登录体系** | **仍做不到** ⇒ 拆多个场景（本版不涉及多段登录） |
| iframe 内部控件 | **仍不做**（诚实边界，见培训页 1.6） |

---

## 3. demo 改造（让能力可演示、可验收）

| 改动 | 说明 |
|---|---|
| `TARGET_PORTS=8000,8001,8002` | 单进程起多个 server 线程，**共享同一份数据**（订单系统必须能看到合同系统建的合同） |
| `TARGET_SSO_ORIGIN` | 给 HTML 注入 `window.DEMO_SSO_ORIGIN`：业务页未登录 ⇒ 跳**登录系统**并带 `next`（真实 SSO 形态） |
| 登录回跳带 token | 回跳地址拼 `?token=`，目标 origin 落地到自己的 localStorage |
| 不设新变量 | 行为与原来**完全一致**（单端口 `TARGET_PORT` 老路径保留） |

启动（三系统 + SSO）：

```bash
TARGET_PORTS=8000,8001,8002 TARGET_SSO_ORIGIN=http://localhost:8000 python -m demo.app
```

新增示例场景：`scenarios/multi_origin/orders_invoice_cross_origin.yml`。

---

## 4. 真 AI 实跑抓出的 5 个断点（都已修 + 有判据）

> 这 5 条都不是「能力没实现」，而是**新能力在链路某一段没接上**。列出来是因为
> 补任何横切能力都会遇到同一类问题。

| # | 断点 | 症状 | 修法 |
|---|---|---|---|
| 1 | 探针期没铺会话 | `explore` 探 8001/8002 只探到 8 个登录页控件 | 铺会话收口到 `sso_session.py`，`scan_pages()` 登录后也调它 |
| 2 | `login.session` 被「挑字段」丢掉 | 跳转写对了但执行期不铺会话 ⇒ 断言 5s 超时 | `login_flow_explore` 两处（规划结果 / 用例字段）都透传 |
| 3 | 页面自跳打断 `page.goto` | `interrupted by another navigation` ⇒ 同一用例 **4 跑 1 挂** | 新增容错导航唯一入口 `_nav()`，`_goto` 与登录流的裸 `goto` 都换掉 |
| 4 | 渲染出的 helper 没 import | `NameError: _spread_session`（生成期全绿、试跑才红） | 用例头部 import 名单补上；判据扩展到非 `_assert_*` helper |
| 5 | 场景 `pages` 里重复列登录页 | AI 从登录页开始排步骤 ⇒ 被「夹带登录步骤」闸门整条拦下 | 示例场景去掉；框架加**告警**（不硬红）点明后果 |

---

## 5. 验收结果（本机真 AI，`--llm-record`）

### 5.1 跨 origin 场景 · `all --ai` 全链路

```
[all] 链路 = 真 AI（主推）：explore --ai → generate → run
[explore] LLM 模式：实时调用 + 录制 → output/llm_cassettes
[explore] 跨页探测: [合同列表页] http://localhost:8000/            ->  78 个控件
[explore] 跨页探测: [订单列表页] http://localhost:8001/orders.html -> 108 个控件
[explore] 跨页探测: [发票列表页] http://localhost:8002/invoice_list.html -> 201 个控件
[OK] 【orders_invoice_cross_origin】校验通过：该用例实测 PASSED
[run] pytest 退出码 0
```

AI 自己排出的关键步（证明是 AI 排的，不是手写）：

| 步 | 动作 | 内容 |
|---|---|---|
| 2 | goto | `http://localhost:8001/orders.html` —— **设了 `HYBRID_BASE_URL=8000` 也没被压平** |
| 3 | expect_url | `orders.html`（到达证据） |
| 4 | expect_text | `订单系统`（**免二次登录直达**的旁证） |
| 8 | goto | `http://localhost:8002/invoice_list.html`（第三个 origin） |

### 5.2 会话铺开对照（同一台机器，同一份 demo）

```
登录后落在: http://localhost:8000/?token=…
[对照·不铺] 8001/orders.html -> http://localhost:8001/login.html?next=%2Forders.html   ← 缺口复现
[TEST] 跨 origin 会话已铺到 2 个 origin: order, invoice
[铺开后] 8001/orders.html -> http://localhost:8001/orders.html        ← 修好
[铺开后] 8002/invoice_list.html -> http://localhost:8002/invoice_list.html
```

### 5.3 单系统行为不变的验证（三条反向自证）

| 场景 | 结果 |
|---|---|
| 声明过 order(8001)，设 `base=8000` | **仍落 8001**（不压平）✅ |
| `HYBRID_ORIGIN_MAP` 把 order 指到 8002 | 落 8002（换环境只改一处）✅ |
| 老用例（无 `origins`） | **仍被 base 整体改写**（旧口径没变）✅ |

### 5.4 一类自测

**1644 passed / 3 skipped / 0 failed**（新增 15 条跨 origin 判据，并入子特性 1.4「地址覆盖」家族）。

---

## 6. 升级须知

1. **老场景零改动**：不写 `origins` / `login.session` 的场景行为完全不变；
2. **换环境**仍用 `HYBRID_BASE_URL`；跨系统再加 `HYBRID_ORIGIN_MAP`（JSON）；
3. **场景 `pages` 里不要再列登录页**（`login:` 段已声明登录前置）—— 现在框架会告警提醒；
4. **改场景 yml 后要重跑 `explore --ai`** 刷新用例（指纹会变，别手改指纹字段）；
5. 本版**不含** iframe 内部控件探测与多段登录（多套 SSO），仍按诚实边界处理。

---

*AprilPark1012 · 2026-11-09*
