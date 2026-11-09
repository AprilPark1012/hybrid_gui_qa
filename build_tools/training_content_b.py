# -*- coding: utf-8 -*-
"""培训页内容 · 后半（Part 3 HOW + Part 4 交付 + 附录）。"""
from __future__ import annotations

from build_tools.training_doc import B, C, Doc, section


# ============================================================ Part 3 · HOW
def sec_install() -> dict:
    d = Doc()
    d.p("第一次跑之前只有三件事，漏了第三步必报错（浏览器没装）：")
    d.code("""# 0) 建虚拟环境（Python 3.10+）
python -m venv .venv
.venv\\Scripts\\activate          # Windows
source .venv/bin/activate       # Linux / macOS

# 1) 装依赖
pip install -r requirements.txt          # 跑 run / generate 够用
pip install -r requirements-ai.txt       # 要跑真 AI 链路再装这个

# 2) 一条命令把剩下的事做完（装浏览器 + 自检）
python -m framework.cli setup""", lang="bash")
    d.table(
        ["漏了什么", "典型报错", "怎么补"],
        [["没装浏览器", C("Executable doesn't exist at .../ms-playwright/..."), C("python -m framework.cli setup")],
         ["没装 AI 依赖", C("ImportError: browser_use / openai"), C("pip install -r requirements-ai.txt")],
         ["没配模型 key", C("[llm] 没找到可用的 LLM 凭据"), "在 " + C(".env") + " 里配 " + C("LLM_API_KEY") + " 三项（见附录 B）"],
         ["没有图形界面（Linux 服务器）", "浏览器起不来 / 报 DISPLAY", "框架会自动无头运行；想留证加 " + C("--debug")]],
        md=[["没装浏览器", "`Executable doesn't exist at .../ms-playwright/...`", "`python -m framework.cli setup`"],
            ["没装 AI 依赖", "`ImportError: browser_use / openai`", "`pip install -r requirements-ai.txt`"],
            ["没配模型 key", "`[llm] 没找到可用的 LLM 凭据`", "在 `.env` 里配 `LLM_API_KEY` 等三项"],
            ["没有图形界面（Linux 服务器）", "浏览器起不来 / 报 DISPLAY", "自动无头运行；想留证加 `--debug`"]])
    d.note("ok", "模型只认 <b>OpenAI 兼容</b>端点，所以国内可用的 GLM / Kimi / 通义 / 豆包、"
                 "本地 vLLM·Ollama 都能接，改的是三个环境变量而不是代码。",
           md="模型只认 **OpenAI 兼容**端点，所以国内可用的 GLM / Kimi / 通义 / 豆包、"
              "本地 vLLM·Ollama 都能接，改的是三个环境变量而不是代码。")
    return section("3.1", "装环境：三件事", "装完就能跑，先别管 AI", d)


def sec_first_run() -> dict:
    d = Doc()
    d.p("仓库自带一个订单系统的 demo（端口 " + C("8000") + "），拿它练手最快。"
        "下面这条链路从零到出报告，一路都有东西可看：")
    d.code("""# 1) 起被测应用（另开一个终端，别关）
python -m demo.app                       # 浏览器打开 http://localhost:8000 能看到登录页

# 2) 配好模型（只跑 run 的话这步可跳过）
#    .env: LLM_API_KEY / LLM_BASE_URL / LLM_MODEL

# 3) 主线一把跑完：识别 -> 出用例 -> 生成脚本 -> 执行出报告
python -m framework.cli all --ai --scenario-file scenarios/orders/orders_invoice_full_lifecycle.yml""",
           lang="bash")
    d.p("每一步你该看到什么：")
    d.table(
        ["阶段", "日志长这样", "意味着"],
        [["探针", C("[explore] 录像目录为空 -> 本次实时调用并录制"), "这轮是真 AI（不是回放）"],
         ["探针", C("[explore] 跨页探测: [开票页] http://localhost:8000/invoice_create.html -> 21 个控件"),
          "页面被真的打开了、控件被采到了"],
         ["AI 出用例", C("[login] [OK] 登录步骤 4 步（AI 原始 4 步）-> login_xxx.json"),
          "登录步骤由 AI 用同一套语义识别生成，并落盘可审"],
         ["生成", C("[1/2] generate 结束（耗时 1.8s）"), "确定性翻译，不调 AI"],
         ["执行", C("[TEST] [step 48] select: 期次号 … （等可选项就绪 63ms）"), "运行期真在点、真在等"],
         ["结论", C("PASSED") + " / " + C("1 passed in 397.14s"), "报告在 " + C("log/latest/report.html")]],
        md=[["探针", "`[explore] 录像目录为空 -> 本次实时调用并录制`", "这轮是真 AI"],
            ["探针", "`[explore] 跨页探测: [开票页] ... -> 21 个控件`", "页面真被打开、控件被采到"],
            ["AI 出用例", "`[login] [OK] 登录步骤 4 步（AI 原始 4 步）`", "登录步骤落盘可审"],
            ["生成", "`[1/2] generate 结束（耗时 1.8s）`", "确定性翻译，不调 AI"],
            ["执行", "`[TEST] [step 48] select: 期次号 …（等可选项就绪 63ms）`", "运行期真在点、真在等"],
            ["结论", "`PASSED` / `1 passed in 397.14s`", "报告在 `log/latest/report.html`"]])
    d.note("warn", "开发期不想每次都跑执行段，加 " + C("--no-run") + " 停在「试跑校验」之后；"
                   "只想重跑已有用例，直接 " + C("python -m framework.cli run") + "（零 AI 调用）。",
           md="开发期不想跑执行段加 `--no-run`；只想重跑已有用例直接 `python -m framework.cli run`（零 AI 调用）。")
    return section("3.2", "30 秒跑通自带 demo", "从零到 report.html，一条命令", d)


def sec_commands() -> dict:
    d = Doc()
    d.p("六个子命令，日常只用得上前三个。区别在于「从哪一段开始、跑到哪一段停」：")
    d.table(
        ["命令", "从哪开始", "到哪结束", "什么时候用"],
        [[C("all --ai"), "场景", "执行 + 报告", "<b>主线</b>：新写/改了场景，要端到端验证"],
         [C("run"), "已经生成好的脚本", "执行 + 报告", "日常回归、改完框架自测（零 AI 调用）"],
         [C("verify"), "已有用例", "产出校验 + 实跑", "只想验「这批用例靠不靠谱」"],
         [C("generate"), "已有用例 JSON", "生成脚本", "手改过用例，要重新翻译成脚本"],
         [C("prune"), "—", "清理归档", "磁盘涨了，按保留策略清 snapshots / run 目录"],
         [C("config"), "—", "打印可调项", "想知道有哪些旋钮、当前值、从哪来的"]],
        md=[["命令", "从哪开始", "到哪结束", "什么时候用"],
            ["`all --ai`", "场景", "执行 + 报告", "**主线**：新写/改了场景，端到端验证"],
            ["`run`", "已生成的脚本", "执行 + 报告", "日常回归、改完框架自测（零 AI）"],
            ["`verify`", "已有用例", "产出校验 + 实跑", "只想验「这批用例靠不靠谱」"],
            ["`generate`", "已有用例 JSON", "生成脚本", "手改过用例，要重新翻译"],
            ["`prune`", "—", "清理归档", "磁盘涨了，按保留策略清"],
            ["`config`", "—", "打印可调项", "有哪些旋钮、当前值、从哪来"]])
    d.p("几个每天都在用的参数：")
    d.table(
        ["参数", "作用", "备注"],
        [[C("--scenario-file <yml>"), "指定场景文件（" + C("all") + " / " + C("explore") + " 用）", "最常用"],
         [C("--base-url"), "临时覆盖被测地址", "等价 " + C("HYBRID_BASE_URL") + "；explore 不接这个参数"],
         [C("--no-verify"), "跳过试跑校验", "只出用例不实跑，快但结论弱"],
         [C("--no-run"), C("all") + " 专用：停在 verify", "开发期省一半时间"],
         [C("--ai-retry N"), "AI 产出不合格时重试次数", "默认 2，上界 5"],
         [C("--debug"), "调试：有屏弹浏览器 / 无屏录视频 + 逐步截图", "等价 " + C("--headed") + "；并发强制降为 1"],
         [C("--case <case_id>"), "只跑一条用例", "排查单条必备"],
         [C("--workers N"), "并发数", "内存不够会自动降，别硬压"]],
        md=[["参数", "作用", "备注"],
            ["`--scenario-file <yml>`", "指定场景文件", "最常用"],
            ["`--base-url`", "临时覆盖被测地址", "explore 不接这个参数"],
            ["`--no-verify`", "跳过试跑校验", "快但结论弱"],
            ["`--no-run`", "`all` 专用：停在 verify", "开发期省一半时间"],
            ["`--ai-retry N`", "AI 产出不合格时重试次数", "默认 2，上界 5"],
            ["`--debug`", "有屏弹浏览器 / 无屏录视频+逐步截图", "并发强制降为 1"],
            ["`--case <case_id>`", "只跑一条用例", "排查单条必备"],
            ["`--workers N`", "并发数", "内存不够会自动降"]])
    d.p("全部参数（每个子命令一份）见附3；环境变量全表见附2。")
    return section("3.3", "命令速查：六个子命令", "先看这张表，再决定敲哪条", d)


def sec_env() -> dict:
    d = Doc()
    d.p("旋钮有五十多个，但你日常只需要认识下面这几组（<b>常用项</b>，不是全集）。"
        "想看全量、当前值、以及「这个值是从哪儿来的」，跑这一条——它是可调项的"
        "<b>唯一权威入口</b>，不在文档里维护第二份清单：")
    d.code("python -m framework.cli config", lang="bash")
    d.table(
        ["组", "变量", "默认", "什么时候要动"],
        [["模型", C("LLM_API_KEY") + " · " + C("LLM_BASE_URL") + " · " + C("LLM_MODEL"),
          "—", "接哪个模型（国内：GLM / Kimi / 通义 / 豆包）"],
         ["模型", C("LLM_REASONING_EFFORT"), "high", "思考强度；GLM 只认 low / high / max，发 medium 直接 400"],
         ["地址", C("HYBRID_BASE_URL"), C("http://localhost:8000"), "被测系统换地址/端口"],
         ["地址", C("HYBRID_RESET_URL"), "空", "用例之间复位数据（" + C("auto") + " = 自动推导）"],
         ["超时", C("HYBRID_VERIFY_TIMEOUT"), "900", "单条用例试跑超时；含长时间等待的用例要够大"],
         ["超时", C("HYBRID_CASE_TIMEOUT"), "600", "执行阶段单条用例超时"],
         ["定位", C("HYBRID_LOCATE_TIMEOUT"), "5000", "慢系统上调大（毫秒）"],
         ["定位", C("HYBRID_READY_TIMEOUT"), "15000", "等页面就绪的上限；慢代理/慢机器上调大"],
         ["调试", C("HYBRID_SHOTS") + " · " + C("HYBRID_VIDEO"), "空", "逐步截图 / 录像（" + C("--debug") + " 会自动设）"],
         ["自愈", C("HYBRID_SELF_HEAL"), "1", "0 = 关掉定位失败时的语义兜底"],
         ["AI", C("HYBRID_AI_RETRY"), "2", "产出闸门不合格时的重试次数"],
         ["AI", C("HYBRID_PROMPT_LIST_CHARS"), "90000", "喂给 AI 的每条清单字符预算（页多时调大）"],
         ["并发", C("HYBRID_MB_PER_WORKER") + " · " + C("HYBRID_RESERVE_MB"), "550 · 450", "并发预算公式"],
         ["打包", C("HYBRID_ROW_ZONE_STRICT"), "0", "1 = 行区控件缺 " + C("row_index") + " 就拒绝出包"]],
        md=[["组", "变量", "默认", "什么时候要动"],
            ["模型", "`LLM_API_KEY` · `LLM_BASE_URL` · `LLM_MODEL`", "—", "接哪个模型"],
            ["模型", "`LLM_REASONING_EFFORT`", "high", "GLM 只认 low / high / max"],
            ["地址", "`HYBRID_BASE_URL`", "http://localhost:8000", "被测系统换地址/端口"],
            ["地址", "`HYBRID_RESET_URL`", "空", "用例间复位数据"],
            ["超时", "`HYBRID_VERIFY_TIMEOUT`", "900", "单条用例试跑超时"],
            ["超时", "`HYBRID_CASE_TIMEOUT`", "600", "执行阶段单条用例超时"],
            ["定位", "`HYBRID_LOCATE_TIMEOUT`", "5000", "慢系统上调大（毫秒）"],
            ["定位", "`HYBRID_READY_TIMEOUT`", "15000", "等页面就绪上限"],
            ["调试", "`HYBRID_SHOTS` · `HYBRID_VIDEO`", "空", "逐步截图 / 录像"],
            ["自愈", "`HYBRID_SELF_HEAL`", "1", "0 = 关掉语义兜底"],
            ["AI", "`HYBRID_AI_RETRY`", "2", "产出闸门重试次数"],
            ["AI", "`HYBRID_PROMPT_LIST_CHARS`", "90000", "清单字符预算"],
            ["并发", "`HYBRID_MB_PER_WORKER` · `HYBRID_RESERVE_MB`", "550 · 450", "并发预算公式"],
            ["打包", "`HYBRID_ROW_ZONE_STRICT`", "0", "1 = 行区缺 row_index 拒绝出包"]])
    d.note("warn", "优先级永远是 <b>CLI 参数 &gt; 环境变量 &gt; 默认值</b>。"
                   "别在代码里写死这些值——每一处硬编码都是「改配置只生效一半」的伏笔。",
           md="优先级永远是 **CLI 参数 > 环境变量 > 默认值**。别在代码里写死这些值。")
    return section("3.4", "环境变量与运行开关（常用项）", "全集看 cli config，这里只讲你会动的", d)


# ---------------------------------------------------------------- 3.5 场景
def sec_scenario() -> dict:
    d = Doc()
    d.h3("3.5.1 放哪、怎么起名")
    d.p("场景文件住在 " + C("scenarios/<模块>/<场景id>.yml") + "；文件名就是默认 id，"
        "要求小写蛇形（" + C("^[a-z][a-z0-9_]*$") + "）。一个场景 = 一条端到端业务流，不是一条用例。")

    d.h3("3.5.2 一个能跑的最小场景（照着改就行）")
    d.code("""id: todo_basic            # 可省：默认取文件名
scenario: |
  在待办页新增一条待办，标题写「今天要跑回归」，然后确认它出现在列表里。
target:
  url: http://localhost:8000/todo.html
  page: |
    待办页：顶部一个输入框 + 「新增」按钮，下面是列表（每行有标题和一个「完成」勾选框）。
login:
  url: /login.html
  scenario: 在登录页填写账号 super、密码 super@123，然后点「登录」
  wait: { url_not: login.html }
probe_pre: [切换为订单管理员]
probe_pre_host: 登录页""", lang="yaml")
    d.p("三个关键点：" + C("scenario") + " 是人话（AI 读它排步骤）；" + C("page") +
        " 是给 AI 的<b>页面领域知识</b>（哪个字段必填、哪个按钮会开弹层）；"
        + C("wait") + " 必须是<b>可观测</b>条件——框架不允许用固定 sleep 判断登录成功。")

    d.h3("3.5.3 字段全表")
    d.p("「给谁」一列很重要：" + B("AI") + " = 会进提示词影响步骤编排；" + B("框架") +
        " = 只影响执行期行为（AI 看不到）；" + B("闸门") + " = 用来判定产出是否合格。")
    d.table(
        ["字段", "必填", "给谁", "说明 / 写错的症状"],
        [[C("scenario"), "<b>是</b>", "AI", "自然语言动作流。空 = 加载期直接红（不许静默跳过）"],
         [C("id"), "否", "框架", "默认取文件名；不合法加载期红；与文件名不一致会告警（以 id 为准）"],
         [C("title") + " / " + C("description"), "否", "人", "标题与说明，进报告"],
         [C("tags") + " / " + C("priority") + " / " + C("owner") + " / " + C("updated"), "否", "人",
          "归类与责任人；批量跑可用 " + C("--tag") + " 过滤"],
         [C("target.url"), "<b>二选一</b>", "框架", "单页场景的入口地址；与 " + C("pages") + " 互斥（同时写 = 加载期红）"],
         [C("target.page"), "否", "AI", "单页的页面说明（领域知识）"],
         [C("target.preconditions"), "否", "AI", "前置条件（人话），进提示词"],
         [C("pages[]"), "<b>二选一</b>", "框架+AI", "多页场景：每项 " + C("name") + " / " + C("url") + " / "
          + C("page") + " / " + C("pre") + " / " + C("probe_url") + "；页名<b>必须唯一</b>（元素唯一化靠它）"],
         [C("pages[].pre"), "否", "框架", "探测该页前要点的控件名（例：编辑 → 新增行），"
          "让「只在编辑态才存在」的控件能被采到"],
         [C("origins"), "跨 origin 时必填", "框架",
          "给每个业务系统起名：<br>" + C("{order: http://host:8001, invoice: http://host:8002}") +
          "<br>之后页面地址写 " + C("${order}/orders.html") + "；换了环境的地址<b>只改这一段</b>"
          "（或运行期用 " + C("HYBRID_ORIGIN_MAP") + " 覆盖）。"
          "引用了<b>没声明</b>的名字 = 加载期红（不猜）；不声明 = 单系统老行为，零改动"],
         [C("login"), "否", "框架+AI", C("url") + " / " + C("scenario") + " / " + C("wait") +
          " / " + C("session") + "；" + C("wait") + " 必须给 "
          + C("url|url_not|url_not_in|selector|text") + " 之一"],
         [C("login.session"), "跨 origin 时必填", "框架",
          "登录一次(SSO)后把会话铺到别的业务系统：<br>"
          + C("{token_from: url_param, param: token, store: localStorage, key: demo_token, spread: [order, invoice]}") +
          "<br><b>为什么必需</b>：会话在 localStorage 里是 per-origin 的，不铺就会被踢回"
          "那个系统<b>自己</b>的登录页（实测 8001 业务页 → 8001/login.html?next=…）"],
         [C("probe_pre"), "否", "框架", "探测期一开始就要做的动作（切身份/选角色），写控件语义名"],
         [C("probe_pre_host"), "用到 probe_pre 时必填", "框架", "这批前置在哪一页执行；漏写在加载期红"],
         [C("business_context"), "否", "AI", "领域上下文（业务规则、术语解释），对排步骤帮助很大"],
         [C("data[]"), "否", "框架", "数据驱动：一组 = 一条用例（占位符名: 值）；"
          "可选 " + C("id") + "，重复会红"],
         [C("assert_guard.must_contain"), "否", "闸门", "产出用例里<b>必须</b>出现这些关键词"],
         [C("assert_guard.forbidden"), "否", "闸门", "产出用例里<b>不许</b>出现的词（例：运行时才有的值）"],
         [C("notes"), "否", "人", "备注，不进提示词"],
         [C("auth"), "否（已淘汰）", "框架", "接口登录老写法（" + C("login_api") + " / " + C("username") + " / "
          + C("password|password_env") + " / " + C("token_key") + "）；新场景请用 " + C("login")]],
        md=[["字段", "必填", "给谁", "说明"],
            ["`scenario`", "**是**", "AI", "自然语言动作流；空 = 加载期红"],
            ["`id`", "否", "框架", "默认取文件名；要求小写蛇形"],
            ["`tags` / `priority` / `owner` / `updated`", "否", "人", "归类与责任人"],
            ["`target.url`", "**二选一**", "框架", "单页入口地址；与 `pages` 互斥"],
            ["`target.page`", "否", "AI", "单页页面说明（领域知识）"],
            ["`pages[]`", "**二选一**", "框架+AI", "多页：`name` / `url` / `page` / `pre` / `probe_url`"],
            ["`pages[].pre`", "否", "框架", "探测该页前要点的控件名"],
            ["`origins`", "跨 origin 时必填", "框架",
             "`{order: http://host:8001, invoice: http://host:8002}`，页面地址写 `${order}/orders.html`；"
             "引用了未声明的名字 = 加载期红；不声明 = 单系统老行为"],
            ["`login`", "否", "框架+AI", "`url` / `scenario` / `wait`（`url|url_not|url_not_in|selector|text`）/ `session`"],
            ["`login.session`", "跨 origin 时必填", "框架",
             "`{token_from, param, store, key, spread: [order, invoice]}` —— 登录一次后把会话铺到各 origin；"
             "会话是 per-origin 的，不铺会被踢回**那个系统自己**的登录页"],
            ["`probe_pre`", "否", "框架", "探测期前置动作（写控件语义名）"],
            ["`probe_pre_host`", "用到时必填", "框架", "前置在哪一页执行"],
            ["`business_context`", "否", "AI", "领域上下文"],
            ["`data[]`", "否", "框架", "数据驱动，一组 = 一条用例"],
            ["`assert_guard.must_contain` / `forbidden`", "否", "闸门", "产出用例必须/不许出现的关键词"],
            ["`auth`", "否（已淘汰）", "框架", "接口登录老写法；新场景用 `login`"]])

    d.h3("3.5.4 七条纪律（每条都有对应的真实事故）")
    d.ol([
        B("写「能力」就要写「必要性」") + "。只写「发票行（可新增行）」，AI 就会去点新增行——"
        "而页面其实已带入 1 行。多走一步的直接代价是<b>一轮 717 秒的白跑</b>。正确写法："
        "「已自动带入 1 行，<b>通常不需要</b>点新增行」。",
        B("只写事实，不写结论") + "。别写「列表里共有 20 条」——那是运行时值，换个环境就错。",
        B("断言的依据必须在页面上找得到") + "。要断「第一行的合同编号是 HT-1001」，"
        "前提是该页真有「合同编号」列；否则 AI 写的断言永远不成立。",
        B("pre 只写控件名") + "。它是「点一下」的清单（" + C("编辑") + " / " + C("新增行") + "），"
        "不是自然语言句子。",
        B("页面说明是写给 AI 看的领域知识") + "。它决定 AI 知不知道「必填」、"
        "「这个按钮会打开弹层」、「只能给已关闭订单开票」。",
        B("一个页面一个 name，且页名要唯一") + "。跨页同名控件会被自动改成 " + C("原名@页名") +
        "；页名重名直接加载期红。",
        B("别把口令写进场景") + "。用 " + C("password_env") + " 指向环境变量。",
    ])
    d.note("ok", "写完场景先只跑识别、不实跑：" + C("python -m framework.cli explore --scenario-file <yml>")
                   .replace("explore --scenario-file", "explore --scenario-file") +
           "（加 " + C("--ai") + " 才是真 AI，不加就是纯探针），确认「控件采到了、页面对了」再跑主线。",
           md="写完场景先只跑识别、不实跑：`python -m framework.cli explore --scenario-file <yml>`"
              "（加 `--ai` 才是真 AI，不加就是纯探针），确认控件采到了、页面对了再跑主线。")
    return section("3.5", "scenario 怎么写", "这是你唯一需要动脑子写的东西", d)


# ---------------------------------------------------------------- 3.6 用例
def sec_cases() -> dict:
    d = Doc()
    d.h3("3.6.1 它从哪来、能不能改")
    d.p("用例住在 " + C("cases/<场景id>/ai_*.json") + "，由 " + C("explore --ai") +
        " 落盘。能读能改，但要知道两件事：")
    d.ul([C("generate") + " 只读 " + C("case_id") + " / " + C("steps") + " / " + C("asserts") +
          " —— 其余字段随便加，不影响执行；",
          "场景一变（哪怕只改一句说明），用例里的 " + C("scenario_fingerprint") + " 就不同步，"
          "判据会红并提示「重跑 explore 刷新用例」。" + B("不要手改指纹") + "——那等于把「用例与场景同步」"
          "这件事做成假的。"])

    d.h3("3.6.2 顶层字段")
    d.table(
        ["字段", "说明"],
        [[C("case_id"), "用例 id（= 文件名去扩展名），" + C("--case") + " 用它挑单条"],
         [C("name"), "用例名（进报告）"],
         [C("base_url"), "生成期记录的地址；执行期会被 " + C("HYBRID_BASE_URL") + " 覆盖"],
         [C("steps[]"), "操作步骤（见 3.6.3）"],
         [C("asserts[]"), "断言（见 3.6.5）——" + B("断言不许写在 steps 里")],
         [C("scenario_id") + " / " + C("source_scenario"), "溯源：由哪个场景产出"],
         [C("scenario_fingerprint"), "场景指纹；不同步 = 用例该刷新了"],
         [C("pages") + " / " + C("probe_pre") + " / " + C("probe_pre_host") + " / " + C("login"),
          "从场景继承下来的执行期声明（供 harness 用）"],
         [C("llm_source"), "这轮是哪个模型/哪份录像产出的（审计用）"]],
        md=[["字段", "说明"],
            ["`case_id`", "用例 id（= 文件名去扩展名），`--case` 用它挑单条"],
            ["`name`", "用例名（进报告）"],
            ["`base_url`", "生成期地址；执行期被 `HYBRID_BASE_URL` 覆盖"],
            ["`steps[]`", "操作步骤"],
            ["`asserts[]`", "断言——**断言不许写在 steps 里**"],
            ["`scenario_id` / `source_scenario`", "溯源"],
            ["`scenario_fingerprint`", "场景指纹；不同步说明用例该刷新"],
            ["`pages` / `probe_pre` / `probe_pre_host` / `login`", "从场景继承的执行期声明"],
            ["`llm_source`", "哪个模型/哪份录像产出（审计用）"]])

    d.h3("3.6.3 steps[] 字段")
    d.table(
        ["字段", "说明"],
        [[C("order"), "步骤序号（从 1 起；省略时按数组顺序）"],
         [C("op"), "<b>动作</b>，见 3.6.4 词表"],
         [C("element"), "控件语义名（必须是元素清单里出现过的名字；跨页同名写成 " + C("原名@页名") + "）"],
         [C("value"), "填什么值；支持占位符 " + C("{datetime}") + " 这类运行时值"],
         [C("index"), C("select") + " 专用：选第几项（从 0 起，跳过空占位）"],
         [C("row_index"), "行内控件专用：第几行（" + C("1") + " 起；" + C("-1") + " = 最后一行）"],
         [C("by") + " / " + C("value"), "属性直定位（" + C("css") + " / " + C("testid") + " / " + C("role") + " 等），"
          "用于「语义名兜不住」的场合"],
         [C("desc"), "人话说明（进日志与报告，排查全靠它）"],
         [C("requires_open"), "这个控件藏在某个入口后面（必须先点开）——由探针标注，AI 会照做"]],
        md=[["字段", "说明"],
            ["`order`", "步骤序号（从 1 起）"],
            ["`op`", "**动作**"],
            ["`element`", "控件语义名（必须来自元素清单；跨页写成 `原名@页名`）"],
            ["`value`", "填什么值；支持占位符"],
            ["`index`", "`select` 专用：选第几项（从 0 起）"],
            ["`row_index`", "行内控件：第几行（`-1` = 最后一行）"],
            ["`by` / `value`", "属性直定位（css / testid / role）"],
            ["`desc`", "人话说明，进日志与报告"],
            ["`requires_open`", "控件藏在入口后面，必须先点开"]])

    d.h3("3.6.4 动作词表（唯一权威：" + C("framework/shared/step_ops.py") + "）")
    d.p("操作类八个，都会改变页面状态（除 " + C("goto") + " 外都必须落到真实控件上）：")
    d.table(
        ["op", "语义", "例子"],
        [[C("goto"), "打开地址", C("{\"op\":\"goto\",\"value\":\"http://host/todo.html\"}")],
         [C("click"), "点击（可点前会自动等可见/可用）", C("{\"op\":\"click\",\"element\":\"搜索@订单列表页\"}")],
         [C("fill"), "输入框填值（先清空再填）", C("{\"op\":\"fill\",\"element\":\"数量@开票页\",\"value\":\"10\",\"row_index\":1}")],
         [C("select"), "下拉选一项（未给 value 时选第一个真选项）", C("{\"op\":\"select\",\"element\":\"期次号\",\"index\":0}")],
         [C("check"), "勾选/取消勾选", C("{\"op\":\"check\",\"element\":\"选择订单_当前行\"}")],
         [C("press_enter"), "回车（常用于搜索框提交）", C("{\"op\":\"press_enter\",\"element\":\"订单名称@发票列表页\"}")],
         [C("click_new_tab"), "点会开新 tab 的控件并切过去", "跨 tab 流程"],
         [C("close_tab"), "关当前 tab 回上一个", "跨 tab 流程收尾"]],
        md=[["op", "语义", "例子"],
            ["`goto`", "打开地址", "`{\"op\":\"goto\",\"value\":\"http://host/todo.html\"}`"],
            ["`click`", "点击（自动等可见可用）", "`{\"op\":\"click\",\"element\":\"搜索@订单列表页\"}`"],
            ["`fill`", "输入框填值（先清空）", "`{\"op\":\"fill\",\"element\":\"数量@开票页\",\"value\":\"10\",\"row_index\":1}`"],
            ["`select`", "下拉选一项", "`{\"op\":\"select\",\"element\":\"期次号\",\"index\":0}`"],
            ["`check`", "勾选/取消勾选", "`{\"op\":\"check\",\"element\":\"选择订单_当前行\"}`"],
            ["`press_enter`", "回车", "`{\"op\":\"press_enter\",\"element\":\"订单名称@发票列表页\"}`"],
            ["`click_new_tab`", "点开新 tab 并切过去", "跨 tab 流程"],
            ["`close_tab`", "关当前 tab 回上一个", "跨 tab 流程收尾"]])
    d.p("断言类是另一套（不进 " + C("steps[]") + "）：AI 只会写这三种，框架保证<b>写了就执行</b>；"
        "生成器另外还认 13 种 " + C("kind") + "（手改用得上，见 3.6.5）。")

    d.h3("3.6.5 asserts[] 字段")
    d.table(
        ["字段", "说明"],
        [[C("kind"), "断言类型。AI 产出只用 " + C("text") + " / " + C("url") + " / " + C("first_row") +
          "；手改可用全部 13 种（" + C("text") + " " + C("wait_text") + " " + C("visible") + " "
          + C("hidden") + " " + C("count") + " " + C("attr") + " " + C("value") + " " + C("url") + " "
          + C("checked") + " " + C("unchecked") + " " + C("enabled") + " " + C("disabled") + " "
          + C("first_row") + "）；未知 kind 直接失败，绝不静默跳过"],
         [C("element"), "被断言的控件语义名（" + C("first_row") + " 用不到）"],
         [C("expect"), "期望值（" + C("text") + " / " + C("count") + " / " + C("attr") + " / "
          + C("value") + " / " + C("url") + " / " + C("first_row") + " 必填）"],
         [C("row_field"), C("first_row") + " 专用：验第一行的哪一列（必须是该页真实列名）"],
         [C("after_step"), "这条断言跟在第几步之后（执行顺序，不是装饰）"],
         [C("refresh"), "等待类断言的重取数策略：" + C("none") + " / " + C("reload") + " / " + C("research") +
          "（" + C("research") + " = 每轮重放最近一次搜索；列表页不会自己刷新时靠它）"],
         [C("timeout_ms"), "有界等待时长；缺省按「场景声明的业务时长」推导，不是写死的 30s"],
         [C("name"), C("attr") + " 专用：属性名"],
         [C("desc"), "人话说明"]],
        md=[["字段", "说明"],
            ["`kind`", "断言类型；AI 只用 text / url / first_row，手改可用 13 种；未知 kind 直接失败"],
            ["`element`", "被断言的控件语义名"],
            ["`expect`", "期望值（text / count / attr / value / url / first_row 必填）"],
            ["`row_field`", "`first_row` 专用：验第一行的哪一列（必须是真实列名）"],
            ["`after_step`", "跟在第几步之后（决定执行顺序）"],
            ["`refresh`", "`none` / `reload` / `research`（每轮重放最近一次搜索）"],
            ["`timeout_ms`", "有界等待时长；缺省按场景声明推导"],
            ["`name`", "`attr` 专用：属性名"],
            ["`desc`", "人话说明"]])

    d.h3("3.6.6 六条硬规则")
    d.ol([
        B("断言不许写进 steps") + "——" + C("op") + " 里出现 " + C("expect_") + " 开头的东西，"
        "说明结构放错了（步骤是「做」、断言是「验」）。",
        B("不许写运行时才知道的值") + "：发票号、共 N 条、当前时间戳。这些只能「反查稳定字段」"
        "（例：用合同编号 HT-1001 反查第一行）。",
        B("行内控件必须给 " + C("row_index")) + "：给 " + C("-1") + " 表示「刚新增的那行」，给正整数表示第几行。",
        B("列名必须是该页真实列") + "：" + C("row_field") + " 写错时，框架会列出该页实际列供你改。",
        B("一条用例一个业务闭环") + "：别把「建单 + 开票 + 对账」塞进一条，挂了不知道断在哪。",
        B("场景改了要重跑识别") + "：指纹不同步会被判据抓住，这是有意的。",
    ])
    return section("3.6", "cases 怎么写", "AI 产的，但你要会读、会改、会挑错", d)


# ---------------------------------------------------------------- 3.7 故障
def sec_faults() -> dict:
    d = Doc()
    d.p("这张表是「症状 → 先看哪里 → 怎么修」。左边那列是你在日志里能直接搜到的字符串。")
    rows = [
        ["等可选项就绪 Nms", "下拉框选项异步填，已按有界等待拿到真选项",
         "正常留痕。若报「等了 Nms 仍无可选选项」= 页面确实没数据或控件选错"],
        ["行内定位命中 N 个 -> 按 row_index=-1 取行", "行定位生效（-1 = 最后一行）",
         "正常。若报「命中 0 个」= 行锚文本对不上，去看该页实际行"],
        ["重复控件 … 行定位缺失", "有控件在多行重复，但用例没给行定位", "回场景补说明，或重跑 explore 让 AI 重排"],
        ["表格没有第一行、或没有 'xxx' 列", "行断言写错列 / 页面还没数据",
         "看报错里列出的「该页实际列」，改成真实列名；页面没数据就查上一步是否真的建成功"],
        ["元素定位失败且自愈未成功", "语义名与运行时 DOM 对不上（改版/未登录/在另一页）",
         "先确认「在正确的页、已登录」（回放/换地址时最容易踩），再看快照里有没有这个控件"],
        ["登录步骤里有非操作动作，已跳过", "AI 想写的动作登录段不支持",
         "现在是唯一的断言入口在跑，若仍出现说明动作类型不在 " + C("ASSERT_OPS") + " 里"],
        ["试跑预算 Ns（按声明等待推导）", "执行预算按场景声明的业务时长算出来", "不用管；长期不够就调 " + C("HYBRID_VERIFY_TIMEOUT")],
        ["校验日志 …实测 FAILED", "某条用例真的没通过", "打开它指的那个 verify 日志，找第一条 " + C("E  ") + " 行"],
        ["PASSED 但第 1 轮 FAILED、第 2 轮过", "AI 排错一轮后自我修正成功", "算通过，但要回看第 1 轮报错——那是场景说明有歧义的信号"],
        ["[NG] 用例与场景不同步（指纹 …）", "场景改过，用例没刷新", "重跑识别生成：把这条用例删掉再跑主线，别手改指纹"],
    ]
    h = ['<table class="fault"><thead><tr><th>日志里搜这个</th><th>说明</th><th>怎么处理</th></tr></thead><tbody>']
    for r in rows:
        h.append("<tr><td>" + r[0] + "</td><td>" + r[1] + "</td><td>" + r[2] + "</td></tr>")
    h.append("</tbody></table>")
    d.raw("".join(h), md="| 日志里搜这个 | 说明 | 怎么处理 |\n|---|---|---|\n"
                          + "\n".join(f"| {a} | {b} | {c} |" for a, b, c in rows) + "\n")
    d.note("warn", "排查顺序永远是：" + B("先确认在正确的页、以正确的身份") + " → 再看控件在不在快照里 → "
                   "最后才怀疑定位算法。历史上「等 15 秒还是 0 个」的真因是<b>登录打到了另一个端口</b>，"
                   "不是定位坏了。",
           md="排查顺序：**先确认在正确的页、以正确的身份** → 再看控件在不在快照里 → 最后才怀疑定位算法。")
    return section("3.7", "故障对照表", "按症状查，别从报错栈开始读", d)


# ============================================================ Part 4
def sec_delivery() -> dict:
    d = Doc()
    d.p("这一段是「交出去之前必须做的」。四条闭环一句话："
        + B("浏览器出证据 -> LLM 出编排 -> 确定性执行 -> 浏览器裁决") + "，"
        "交付物只是这条闭环的一次快照，所以每次交付都要重新走一遍。")

    d.h3("4.1 什么情况下不许出包")
    d.ul(["<b>敏感词</b>命中（雇主页/客户名/个人邮箱这类，对象级零残留）；",
          "<b>行区控件缺 " + C("row_index") + "</b> 且开了严格体检（" + C("HYBRID_ROW_ZONE_STRICT=1") + "）；",
          "<b>" + C("VERSION") + " 与发行说明不一致</b>，或包里缺最新发行说明；",
          "包含 <b>" + C("output/verify") + " / " + C("log/") + "</b> 这类运行现场（它们会带凭据，永不外发）。"])
    d.h3("4.2 交付验证四步")
    d.table(
        ["步", "做什么", "怎么确认真的做了"],
        [["① 产出自检", "用例 + 脚本 + 元素清单齐不齐", "verify 的产出那一档全绿"],
         ["② 实跑", "至少 1 条真跑过", "日志里有 " + C("PASSED") + " 与 " + C("N passed")],
         ["③ 打包体检", C("build_tools/pack_release.py"), "包内 " + C("VERSION") + " / 发行说明 / 敏感词全部对账"],
         ["④ 收件对账", "发出去再核一遍", "取回附件 sha256 逐字节比 + 无退信"]],
        md=[["步", "做什么", "怎么确认"],
            ["① 产出自检", "用例+脚本+元素清单齐不齐", "verify 产出档全绿"],
            ["② 实跑", "至少 1 条真跑过", "日志里有 PASSED 与 N passed"],
            ["③ 打包体检", "`build_tools/pack_release.py`", "包内 VERSION / 发行说明 / 敏感词对账"],
            ["④ 收件对账", "发出去再核一遍", "sha256 逐字节比 + 无退信"]])
    d.h3("4.3 新人交接清单（三页）")
    d.ol(["自己跑一遍 3.2 的命令，直到看见 " + C("log/latest/report.html") + "；",
          "读一条现成场景 + 它的用例，能把「场景第几句变成了用例第几步」对上；",
          "故意改坏一处（把场景里某页说明删掉），看框架怎么报错——比读十遍文档有用。"])
    return section("4", "交付与质量", "出门前的四条闭环", d, anchor="delivery")


# ============================================================ 附录
from build_tools.training_doc import inline_md as _inline  # 共享实现，别维护第二份


def sec_appendix() -> list[dict]:
    # A 术语
    a = Doc()
    a.table(
        ["术语", "一句话"],
        [["元素清单 " + C("element_map"), "探针扫出来的「这页有哪些控件」，运行期名字的唯一来源"],
         ["语义名", "控件的可读名字（如 " + C("期次号") + "），跨页重名会自动加 " + C("@页名")],
         ["row_zone", "「这个区会长多行」的信号；区内当前唯一的输入类控件会被标上"],
         ["multi_match", "同名控件在一个容器里出现多个；用例操作它时必须给行定位"],
         ["cassette（录像）", "AI 原始回答的落盘文件，用于离线回放"],
         ["指纹 " + C("scenario_fingerprint"), "场景内容的哈希；用来判断用例是否该刷新"],
         ["产出闸门", "AI 给的步骤不合格时拦下 + 带原因重试的那一层"],
         ["自愈 " + C("healer"), "定位失败时放宽阈值再试一次；留痕，但不改判通过"],
         ["三态裁决", "自愈失败后的结论：" + C("real_bug") + " / 环境 / 用例"],
         ["有界等待", "「最多等到 N 毫秒」而不是固定 sleep；超时即失败并说明原因"]],
        md=[["术语", "一句话"],
            ["元素清单 `element_map`", "探针扫出来的「这页有哪些控件」，运行期名字唯一来源"],
            ["语义名", "控件的可读名字，跨页重名加 `@页名`"],
            ["row_zone", "「这个区会长多行」的信号"],
            ["multi_match", "同名控件在一个容器里出现多个"],
            ["cassette（录像）", "AI 原始回答的落盘文件，用于离线回放"],
            ["指纹", "场景内容的哈希，判断用例是否该刷新"],
            ["产出闸门", "AI 步骤不合格时拦下 + 带原因重试"],
            ["自愈", "定位失败时放宽阈值再试；留痕不改判通过"],
            ["三态裁决", "结论：真 bug / 环境 / 用例"],
            ["有界等待", "最多等到 N 毫秒，超时即失败并说明原因"]])
    sec_a = section("附1", "术语表", "看到不懂的词回来查", a)

    # B 全部可调项（从 cli.py 的 TUNABLE_CATALOG 生成 -> 与 cli config 同源、条数必然一致）
    b = Doc()
    from framework.features.f10_cli.cli import TUNABLE_CATALOG
    b.p("下面是<b>全部可调项</b>（共 " + str(len(TUNABLE_CATALOG)) + " 项），"
        "与 " + C("python -m framework.cli config") + " 同源生成 —— 条数、默认值、说明都不会漂。")
    rows, md_rows = [], []
    for env, default, desc in TUNABLE_CATALOG:
        rows.append([C(env), C(default), _inline(desc)])
        md_rows.append([f"`{env}`", f"`{default}`", desc.replace("`", "'")])
    b.table(["变量", "默认", "说明"], rows, md=md_rows)
    sec_b = section("附2", "全部可调项", str(len(TUNABLE_CATALOG)) + " 项，与 cli config 同源", b)

    # C CLI 全部参数
    c = Doc()
    from framework.features.f10_cli.cli import CMD_FLAGS, REMOVED_FLAGS
    c.p("每个子命令接受的参数一览（自动从 " + C("framework/features/f10_cli/cli.py") + " 的 "
        + C("CMD_FLAGS") + " 读出）。")
    rows, md_rows = [], []
    for cmd in sorted(CMD_FLAGS):
        flags = sorted(CMD_FLAGS[cmd])
        rows.append([C(cmd), C(" ".join(flags)) if flags else "—"])
        md_rows.append([f"`{cmd}`", " ".join(f"`{f}`" for f in flags) if flags else "—"])
    c.table(["子命令", "接受的参数"], rows, md=md_rows)
    c.h3("已经移除的参数（防你照着旧笔记敲）")
    c.table(["参数", "为什么没了 / 该用什么"],
            [[C(k), _inline(v)] for k, v in sorted(REMOVED_FLAGS.items())],
            md=[[f"`{k}`", v] for k, v in sorted(REMOVED_FLAGS.items())])
    sec_c = section("附3", "CLI 参数全表", "自动生成，不会漏", c)

    # E 速查卡
    e = Doc()
    e.p("打印这一块贴在显示器旁边就够了。")
    e.code("""# 主线（改了场景就跑它）
python -m framework.cli all --ai --scenario-file scenarios/<模块>/<场景>.yml

# 日常回归（零 AI 调用）
python -m framework.cli run
python -m framework.cli run --case <case_id> --debug

# 只看识别（不实跑）
python -m framework.cli explore --scenario-file scenarios/<模块>/<场景>.yml

# 有哪些旋钮
python -m framework.cli config""", lang="bash")
    e.table(
        ["写场景时", "写用例时"],
        [["<b>scenario</b> 写人话动作流", "断言落 " + C("asserts[]") + "，不进 " + C("steps[]")],
         ["<b>page</b> 写领域知识（必填/弹层/规则）", "行内控件给 " + C("row_index") + "（" + C("-1") + " = 最后一行）"],
         ["「可以 X」必须补「<b>通常不需要</b> X」", "不许写运行时值（发票号、共 N 条）"],
         ["<b>pre</b> 只写控件名", C("row_field") + " 必须是该页真实列"],
         ["不写运行时值", "场景改了要重跑识别（别手改指纹）"]],
        md=[["写场景时", "写用例时"],
            ["**scenario** 写人话动作流", "断言落 `asserts[]`，不进 `steps[]`"],
            ["**page** 写领域知识", "行内控件给 `row_index`（`-1` = 最后一行）"],
            ["「可以 X」必须补「**通常不需要** X」", "不许写运行时值"],
            ["**pre** 只写控件名", "`row_field` 必须是真实列"],
            ["不写运行时值", "场景改了要重跑识别"]])
    sec_e = section("附4", "一页速查卡", "可打印", e)

    return [sec_a, sec_b, sec_c, sec_e]


def build_sections() -> list[dict]:
    return [sec_install(), sec_first_run(), sec_commands(), sec_env(),
            sec_scenario(), sec_cases(), sec_faults(), sec_delivery(), *sec_appendix()]
