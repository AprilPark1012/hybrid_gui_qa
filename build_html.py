# -*- coding: utf-8 -*-
"""构建培训 HTML：读取框架源码，注入模板，标注核心片段。运行: python build_html.py
生成的 training.html 是自包含单文件（内嵌 CSS），给新员工看。
"""
import html
import re
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUT = BASE / "training.html"

# ---------------- 轻量语法高亮 ----------------
KEYWORDS = {
    "def", "return", "if", "elif", "else", "for", "from", "import", "async",
    "await", "class", "with", "in", "not", "and", "or", "try", "except",
    "raise", "lambda", "pass", "yield", "None", "True", "False", "as", "global",
}


def hl(line: str) -> str:
    """一行代码 → 高亮后的 HTML（保守处理，不追求完美嵌套）。"""
    e = html.escape(line)
    c = re.sub(r'(#.*$)', r'<span class="c">\1</span>', e)
    c = re.sub(r'([\'"][^\'"]*[\'"])', r'<span class="s">\1</span>', c)
    for kw in sorted(KEYWORDS, key=len, reverse=True):
        c = re.sub(rf"\b{kw}\b", f'<span class="k">{kw}</span>', c)
    return c


# ---------------- 文件清单 ----------------
FILES = [
    dict(
        path="demo/app.py", badge="⚙️ 被测应用", color="gray",
        desc="跑在 8000 端口：静态页面 + 内存数据 API（客户 / 合同 / 复位）——列表页与详情页都从它取数，"
             "保证两页看到的是同一条记录；我们也拿它当「靶子」做测试。",
        anchors=[("DEFAULT_PAGE", "默认被测页面=contracts.html，可用环境变量切回旧 todo 页。"),
                 ("do_GET / do_POST", "路由：静态页面 + /api/customers｜/api/contracts｜/api/contract?no=｜/api/reset。"),
                 ("def reset_data", "把数据复位成预置 20 条 —— 用例间隔离（conftest 每用例前调它）靠这里。")],
    ),
    dict(
        path="framework/text_io.py", badge="⚙️ 基建", color="gray",
        desc="跨平台文本口径的唯一入口：凡「跨进程 / 落盘」的文本一律显式 UTF-8 —— 中文 Windows（cp936/gbk）下不崩、不乱码。",
        anchors=[("def utf8_env", "给子进程注入 PYTHONUTF8/PYTHONIOENCODING：子进程按 UTF-8 说，父进程按 UTF-8 听。"),
                 ("def force_stdio", "本进程 stdio 转 UTF-8 + Windows 控制台代码页切 65001（否则中文显示乱码）。"),
                 ("def run_capture", "收子进程输出：显式 encoding=utf-8（gbk 解码事故的根治点，别再裸用 text=True）。")],
    ),
    dict(
        path="framework/config.py", badge="⚙️ 配置", color="gray",
        desc="配置文件：目标 URL + 怎么选 LLM（Browser Use 探索阶段要用）。",
        anchors=[("def llm_from_env", "按 .env 里装的 key，自动挑一个 LLM。AI 阶段才花钱。")],
    ),
    dict(
        path="framework/element_map.py", badge="📄 数据契约", color="dodgerblue",
        desc="AI 和 Playwright 之间的『翻译件』：步骤 + 元素语义，两阶段无缝衔接。",
        anchors=[("class ElementRef", "元素语义：role/name/label... 都是人能看的，不是 CSS。"),
                 ("class ElementMap", "一次探索的完整产物：URL + 场景 + 步骤列表。")],
    ),
    dict(
        path="framework/probe.py", badge="✅ Playwright", color="seagreen",
        desc="第一步·探测：用代码扫页面，把可交互元素『翻译』成语义清单。不经过 LLM。",
        anchors=[("def _role_of", "用代码推断 ARIA 角色——定位的第一手信息，全靠确定性代码。"),
                 ("semantic_name", "给每个元素起个稳定小名，AI 后面只认这个小名。"),
                 ("def probe_page", "核心：遍历交互元素，抓 role/name/placeholder/label/test_id。")],
    ),
    dict(
        path="framework/explorer.py", badge="🤖 AI 层", color="royalblue",
        desc="第二步·探索：AI 听懂意图→规划步骤→从探测清单里挑元素。只引用语义，绝不写 CSS。（默认把 AI 用例落到 cases/ai_*.json，`--no-cases` 可关；`--to-cases` 是历史方案里的叫法，代码里没有这个开关）",
        anchors=[("def mock_explore", "无 key 也能跑的演示版：用固定规则拼出测试步骤（只有显式 --mock-fallback 才用，且不写 cases/）。"),
                 ("async def _ai_explore_async", "方案C：DeepSeek 读自然语言场景+probe清单 → 产轻量步骤 JSON。"),
                 ("def _build_planner_prompt", "构造给 LLM 的提示：场景+控件清单+轻量JSON格式约束。"),
                 ("def _parse_steps_text", "宽松解析 LLM 步骤：容忍 markdown/杂字/单双引号混用。"),
                 ("def _try_collect_modal_items", "点开新建弹窗，并**继续钻进它上面的弹层**（客户列表这类 picker）再 probe；"
                                                  "同名按钮按所在行命名（选择@<客户名>），探完逐层关掉；等待是有界轮询。"),
                 ("def _collect_page_context", "同步探测阶段：基础控件+弹窗字段+DOM 上下文（必须在事件循环外跑）。"),
                 ("def ai_explore", "真·AI 探索入口：读场景+清单，智能规划（需 DeepSeek key）。LLM 不可用时【报错退出】而非静默用 mock 顶替。")],
    ),
    dict(
        path="framework/case_builder.py", badge="🤖 转换层", color="royalblue",
        desc="场景①第三段·落盘：ElementMap → cases/ai_*.json（expect_text 转 asserts[]；element 原样带走语义名）+ 落盘前质量校验（防假绿）。",
        anchors=[("def elementmap_to_cases_file", "一站式：ElementMap → cases 文件，返回 (路径, 警告列表)。"),
                 ("_OP_MAP = ", "action → cases.op 的映射表（不在表内的动作不产出步骤，不静默造假）。"),
                 ("def case_warnings", "落盘前校验：回显断言 / 运行时计数 / 无断言 / 只有goto / 缺元素 / 护栏未覆盖。"),
                 ("def make_case_id_from_scenario_id", "用例命名 ai_<scenario_id>_<HHMMSS>（可 grep 同场景历史产物）。")],
    ),
    dict(
        path="framework/scenario.py", badge="🗂 场景库", color="gray",
        desc="scenarios/*.yml 的解析/校验/发现：一个文件=一个场景，只有 scenario 必填；business_context 喂 AI、assert_guard 既是护栏也进质量闸。需 PyYAML。",
        anchors=[("def load_scenario_file", "读+严格校验单个场景文件（缺 scenario/类型错/YAML 错 → 报错带路径）。"),
                 ("def discover_scenarios", "递归扫目录 + --tag 过滤 + priority 排序，任一文件不合法即中止。"),
                 ("def page_bg", "给 AI 的【页面背景】：页面说明 + 前置条件 + 领域上下文。")],
    ),
    dict(
        path="framework/locator_bridge.py", badge="✅ Playwright", color="seagreen",
        desc="技术核心·桥梁：把语义转成『唯一、稳定』的 Playwright locator。",
        anchors=[("def resolve_locator", "核心：按优先级依次尝试，返回第一个『唯一命中』的 locator。"),
                 ("if cnt == 1", "唯一命中才算数(cnt==1)——宁可报错，绝不用可能点错元素的 locator。"),
                 ("def _try_role", "第一首选：get_by_role + name，最贴近用户语义、最难被 UI 改版打破。")],
    ),
    dict(
        path="framework/generator.py", badge="✅ Playwright", color="seagreen",
        desc="主链路第二步·生成：读 cases/*.json（含 AI 用例）→ 优先用 element_map 快照映射确定性 locator（缺项才现场 probe）+ 按操作类型翻译 + 抽离数据到 scripts/datasets。元素映射不到时显式 pytest.fail，绝不静默跳过。",
        anchors=[("def _semantic_to_locator_expr", "从语义名推导出确定性 locator 源码字符串(test_id/role)。"),
                 ("def generate_scripts", "核心：读 cases → 生成 scripts/test_cases.py + 抽离 datasets。")],
    ),
    dict(
        path="framework/runner.py", badge="✅ Playwright", color="seagreen",
        desc="ElementMap 场景执行引擎（run_scenario）：按步骤跑唯一性校验 + web-first 断言 + 集成 Healer。★注意：cases→pytest 并发执行是由 cli.cmd_run 以 subprocess 拉起的（不是 runner.py）。",
        anchors=[("resolved = resolve_locator", "执行前先唯一性校验，拒绝歧义(防点错)。"),
                 ('loc = resolved["locator_obj"]', "用真实 Playwright Locator 对象执行——不是字符串！"),
                 ("def _run_step", "核心：goto/click/fill/select/check + 断言，一步步确定性地跑。")],
    ),
    dict(
        path="framework/healer.py", badge="🩹 自愈层", color="dodgerblue",
        desc="Phase 3·自愈闭环：定位失败不中断，再协商 locator + 业务断言兜底 + 可审 diff。",
        anchors=[("def try_heal", "自愈入口：定位失败时再协商 + 业务后置断言 + 记录可审 diff。"),
                 ("result = \"recovered\"", "业务断言通过 → 才算自愈成功。"),
                 ("else \"real_bug\"", "业务断言不过 → 判定疑似真 bug，拒用自愈 locator，不掩盖回归。"),
                 ("def dump", "把自愈记录落盘成 json + markdown，供人工 review（绝不静默改写）。")],
    ),
    dict(
        path="framework/data_driven.py", badge="🧩 数据驱动", color="dodgerblue",
        desc="数据驱动核心：占位符替换 + 动态占位符{datetime} + 用例级变量池，支撑脚本数据分离并发用例。",
        anchors=[("def resolve_dynamic_inputs", "动态占位符({datetime}/{date})一次解析固化——填表名==断言名，重跑不重名。"),
                 ("def format_template", "占位符替换：脚本里写 {contractName}，运行时从数据文件取实际值——改动数据不改脚本。"),
                 ("def new_vars", "构造用例级变量池：存运行过程动态数据（合同名/编号等），供断言 + 后续操作输入。"),
                 ("def seed_vars_from_input", "把输入字段回填变量池，作为后续用途(如按名称回搜)的预置值。"),
                 ("def new_case_ctx", "构造静态输入上下文(case_ctx)——与变量池分离，各用例独享。")],
    ),
    dict(
        path="framework/cli.py", badge="⚙️ 入口", color="gray",
        desc="命令行入口：probe / explore / generate / run / all / prune。两种业务场景都从这里进——explore 是「自然语言→AI 产用例」，generate+run 是「手搓用例→确定性生成与执行」。",
        anchors=[("def cmd_explore", "场景①入口：三选一（--scenario 内联 / --scenario-file / --scenario-dir）+ 交付即验证。"),
                 ("def _explore_one", "备 url/page_bg/guard/case_id → 交给 ai_explore（CLI 自己不探测）。"),
                 ("def _verify_cases", "交付即验证：generate 一次 + 逐条 pytest 单跑 → FAILED 则 exit 3。"),
                 ("def cmd_generate", "场景②阶段1：读 cases → 生成 scripts/（locator 翻译 + 数据抽离）。"),
                 ("def cmd_run", "场景②阶段2：资源预检 + pytest 并发执行 + HTML 报告。"),
                 ("def cmd_prune", "归档保留：element_map/probe 快照各留最近 N 个。")],
    ),
]

# ---------------- 渲染代码卡 ----------------
TOOL_COLOR = {"seagreen": "#0f8f6a", "royalblue": "#3b6fdd",
              "dodgerblue": "#2f7fd1", "gray": "#6b7280"}


def render_cards() -> str:
    chunks = []
    for f in FILES:
        p = BASE / f["path"]
        body = p.read_text(encoding="utf-8").splitlines()
        color = TOOL_COLOR[f["color"]]
        anchors = f["anchors"]
        lines_html = []
        for i, line in enumerate(body, 1):
            star = False
            note = None
            for sub, explain in anchors:
                if sub in line:
                    star = True
                    note = explain
                    break
            cls = f'class="code-line{" star" if star else ""}"'
            lines_html.append(f'<div {cls}><span class="ln">{i}</span>'
                              f'<code>{hl(line)}</code></div>')
            if note:
                lines_html.append(
                    f'<div class="code-note">⭐ <b>{note}</b></div>')
        code_html = "\n".join(lines_html)
        chunks.append(f"""
    <section class="card file-card">
      <div class="file-head">
        <span class="badge" style="background:{color}">{f['badge']}</span>
        <code class="file-path">{f['path']}</code>
      </div>
      <p class="file-desc">{f['desc']}</p>
      <div class="codebox">{code_html}</div>
    </section>""")
    return "\n".join(chunks)


# ---------------- HTML 模板 ----------------

# ================= 版本与更新记录（单一来源：改版本只动这里）=================
VERSION = "7.4.1"
VERSION_DATE = "2026-09-14"
CHANGELOG = [
    dict(
        version="7.4.1", date="2026-09-14", tag="当前版本",
        theme="空目录根因清理（目录声明必须「有使用者」）· 防复发测试",
        summary="仓库里出现<b>空目录残留</b>（generated_tests/ · output/plans/）—— 根因不是「忘了 rmdir」，"
                "而是 <code>config.py</code> <b>声明了没人使用的目录</b>：唯一「效果」就是被 "
                "<code>ensure_dirs()</code> 每次启动建出来（删掉也会复活）。⇒ 删掉 4 个死概念常量 + "
                "<b>收窄 ensure_dirs()</b> + 加一条<b>防复发测试</b>：任何「为了存在而存在」的目录声明都会让测试变红。",
        fixed=[
            "删除 4 个<b>已无任何使用者</b>的目录常量：<code>PLAN_DIR</code>(output/plans) · "
            "<code>GENERATED_TESTS_DIR</code>(generated_tests) · <code>TEST_SCENARIO_DIR</code>(testScenario) · "
            "<code>DATASETS_DIR</code>(datasets) —— 它们没有任何读写方，只被 <code>ensure_dirs()</code> 建目录",
            "<code>ensure_dirs()</code> <b>收窄急切创建范围</b>：只建「入口扫描/写入前不会自建」的 "
            "<code>output/</code> · <code>output/element_maps/</code> · <code>log/</code> · <code>scripts/</code> · "
            "<code>cases/</code>；<code>TRACE_DIR</code>/<code>HEALS_DIR</code> 由写入方"
            "（<code>runner.record_trace</code> / <code>healer.dump</code>）<b>使用前显式 mkdir</b> ⇒ 不再常驻空目录",
            "<code>tests/test_utf8_io.py</code> 的 <code>SKIP_DIRS</code> 去掉已不存在的 "
            "<code>generated_tests</code>；README 目录树去掉 <code>plans/</code>",
        ],
        added=[
            "<b>防复发测试 <code>test_ensure_dirs_only_declares_used_dirs</code></b>：解析 "
            "<code>ensure_dirs()</code> 的目录元组 → 静态校验每个常量在 <code>config.py</code> 之外"
            "<b>必须有真实使用者</b> → 四个死常量<b>不许复活</b>"
            "（判据与「未映射元素」同源：任何「少做一步还报绿」「为了存在而存在」都必须显式失败）",
        ],
        notes=[
            "验证基线：框架自测 <b>87 passed</b>（原 86 + 1 条新增）｜端到端 <code>cli all</code> "
            "<b>16 Passed / 0 Failed / 0 Error</b>（pytest 退出码 0）｜运行后 <code>find -type d -empty</code> 复查为空",
            "只清「空目录」与可再生缓存（<code>__pycache__</code>）；运行时证据目录 <code>output/</code> · "
            "<code>log/</code> 一个字节没动",
            "本版为 V7.4 的<b>补丁版</b>：功能与用例集不变，仅内部卫生（目录声明）+ 一条防复发测试",
        ],
    ),
    dict(
        version="7.4", date="2026-09-14", tag="上一版本",
        theme="客户字段改造（弹层选择）· 服务端数据源 · 用例间复位 · 挂死看门狗",
        summary="demo 的客户字段从「下拉框」改成「弹出客户列表层里选一行」（列表页的客户筛选同步改成"
                "<b>输入框 + 右模糊（前缀）匹配</b>）。顺势把 demo 的数据搬到服务端做<b>单一数据源</b>："
                "详情页读的是同一条真实记录（新建的合同在详情页也能看到正确的客户；查不到的编号"
                "<b>如实报「未找到」</b>，不再按编号编一份出来）；并补上两处工程性兜底 —— "
                "<b>用例间自动复位数据</b>、<b>用例级挂死看门狗</b>。",
        added=[
            "<b>demo 数据 API</b>（demo/app.py）：<code>GET /api/customers</code>｜<code>GET /api/contracts</code>｜"
            "<code>GET /api/contract?no=</code>（404=未找到）｜<code>POST /api/contracts</code>（必填校验 + "
            "<b>编号由服务端分配</b>）｜<code>POST /api/reset</code>（复位成预置 20 条）；列表页与详情页都改成读 API 渲染",
            "<b>用例间数据复位</b>：生成的 conftest 每条用例开始前 <code>POST /api/reset</code>"
            "（<code>HYBRID_RESET_URL</code> 可覆盖，设 off 关掉）—— 数据留在服务端后，不复位会让"
            "「列表恢复 20 行」这类断言被上一条用例的残留数据打乱（用例互相污染比用例失败更难查）",
            "<b>用例级看门狗</b>：超时把<b>所有线程的调用栈</b>写进 <code>log/&lt;run_id&gt;/watchdog.txt</code> 再退出"
            "（<code>HYBRID_CASE_TIMEOUT</code> 默认 120s）—— 挂死比失败更糟，绝不允许",
            "<b>tests/verify_picker_layer.py</b>：弹层（picker）端到端回归 —— 弹层里 6 个同名「选择」按钮"
            "必须<b>按所在行命名</b>收集到、探完必须把层关掉、轮询必须第一轮就命中",
            "<b>tests/verify_cross_page.py 新增第四段</b>：UI 新建 → 详情页读到的客户必须等于弹层里选的那个；"
            "对不存在的编号必须如实报「未找到」",
            "跨页用例新增「客户跨页一致」断言：列表页 <code>td[data-field=customer][data-cust]=c5</code> ⇔ "
            "详情页 <code>detail-cust[data-cust]=c5</code>（两页读同一条记录）",
        ],
        changed=[
            "<b>弹层探测与 explore 同源</b>：generator 原来自己点一遍「新建」、只探一层、而且<b>不关弹窗</b> ⇒ "
            "弹层里的控件永远看不到（手写用例直接报「元素未映射」）→ 现在统一走 "
            "<code>explorer._try_collect_modal_items</code>（含嵌套 picker 层，探完逐层关掉）",
            "点开弹窗/弹层后的<b>固定 <code>sleep(300)</code> → 有界轮询</b>（每 200ms 重探，探到就走，最坏 2.5s）："
            "固定 sleep 在机器吃紧时等不够，AI 会把「从列表里选一行」判成无法绑定的步骤",
            "客户字段的<b>语义名契约</b>：弹层里 6 个「选择」按钮文字完全相同 ⇒ 按所在行命名 "
            "<code>选择@&lt;客户名&gt;</code>（同名元素只能靠上下文区分）",
            "README / 培训页 / skill 按<b>代码基准</b>同步（差异逐条列）；跨进程文本口径统一 UTF-8（见 v7.3）",
        ],
        fixed=[
            "<b>崩溃/OOM 不再伪装成业务结论</b>：页面或渲染进程没了就明说「环境事故，不是页面没有弹层」"
            "（原来会打印「点开…没有出现新的可见控件（不是弹层？）」，把环境事故说成业务结论）",
            "<b>Playwright 驱动内部崩溃后 Python 侧 100% CPU 空转、永不退出</b>"
            "（实测 <code>coreBundle.js:463 Assertion error</code> 后卡了 11 分钟只能手工 kill）→ 看门狗兜底",
            "看门狗的转储<b>不能写 stderr</b>：pytest 的 fd 捕获会把 <b>fd 2 也换成临时文件</b> ⇒ 硬退出时那段调用栈"
            "随临时文件丢掉（实测一个字节都没有）→ 改为写专用文件、无缓冲",
            "生成器/探索器探测同一页面时的差异：两边各写一套弹层逻辑 ⇒ 手写用例探得到、AI 用例探不到（或反之），"
            "排查时会被「同名函数两种行为」误导",
        ],
        notes=[
            "测试基线：<b>16 用例全绿</b>（12 条手写 + 4 条 AI）；框架自测 <b>86 条</b>；三个 verify 脚本全过"
            "（跨页四段 / 弹层回归 / 断言正负向）",
            "反证留痕：塞一条脏数据 + <code>HYBRID_RESET_URL=off</code> 跑跨页用例 → 「20 行」断言 <b>FAILED</b>"
            "（说明复位确实在起作用）；看门狗用 <code>HYBRID_CASE_TIMEOUT=1</code> 实测 → 进程 exit 1 + 调用栈落盘",
            "已知待办（诚实清单）：AI 给「返回列表」产的 url 断言只是 host（两页 URL 都含 ⇒ 等于没验换页），"
            "计划给质量闸加静态检查；场景 <code>data</code> 参数化仍只解析不展开；跨页面流程仍不完整",
            "文档口径修正：生成物 <code>scripts/conftest.py</code> 会 <code>import framework.data_driven / framework.healer</code> ⇒ "
            "<b>要在项目内运行</b>，不是「拷到哪儿都能独立跑」",
        ],
    ),
    dict(
        version="7.3", date="2026-09-13", tag="上一版本",
        theme="统一 UTF-8 · 跨平台文本口径",
        summary="修掉一个「在中文 Windows 上必崩」的编码缺陷：`explore --ai` 默认带 --verify，"
                "而 --verify 里用 subprocess 收子进程输出时没指定编码 ⇒ 父进程按系统默认编码"
                "（中文 Windows = cp936/gbk）去解码子进程的 <b>UTF-8 中文输出</b>，"
                "报 `UnicodeDecodeError: 'gbk' codec can't decode byte 0xbb in position 13`"
                "（用例和脚本都生成了，偏偏校验这一步炸）。现在全链路显式 UTF-8，"
                "并且本机 <b>用 zh_CN.gbk locale 把原始报错复现到「同一个字节、同一个位置」</b>后再修，"
                "修完同一条命令实测通过。",
        added=[
            "<b>framework/text_io.py</b>：跨平台文本口径的唯一入口 —— `utf8_env()`（给子进程注入 "
            "PYTHONUTF8/PYTHONIOENCODING）、`force_stdio()`（本进程 stdio 转 UTF-8 + Windows "
            "控制台代码页切 65001）、`run_capture()`（收子进程输出，显式 UTF-8 解码 + errors=replace）",
            "<b>tests/test_utf8_io.py</b>（10 条）：含<b>用 zh_CN.gbk locale 精确复现AprilPark1012那条报错</b>"
            "（断言里就写着 `byte 0xbb in position 13`）+ <b>AST 全仓扫描</b>"
            "（谁再写出「靠系统默认编码」的 subprocess/read_text/open 就直接测试失败）",
            "生成的 scripts/conftest.py 自带 UTF-8 自举：裸跑 pytest（不经 cli）也不会因中文/✓ 崩或乱码",
            "limits.py 在 Windows 上用 GlobalMemoryStatusEx 读可用内存（以前读不到 /proc 就恒判 1 并发）",
            "启动期<b>文件系统编码告警</b>：文件系统编码不是 UTF-8（中文 Windows / GBK locale）时 cli 会"
            "大声提示「中文文件名会落成 GBK 字节名，请用 PYTHONUTF8=1 重跑」——实测踩到过 "
            "scripts/datasets/ 里留下一个 GBK 字节名残留（连工具读文件名都会 surrogate 报错）",
        ],
        changed=[
            "<b>cli.py</b>：`_verify_cases` 的两处 subprocess 改用 `run_capture()`；`cmd_run` 给 pytest "
            "子进程注入 UTF-8 口径（否则 cp936 控制台下 conftest 里的 ✓/⚠️ 会 UnicodeEncodeError，跑到一半崩）",
            "`cli.main()` 入口第一件事就是 `force_stdio()`：本进程 + 所有子进程 + 控制台一次性拉齐 UTF-8",
            "tests/verify_assert_kinds.py、tests/verify_cross_page.py、tests/test_cli_flags.py 的跨进程调用同口径改造",
        ],
        fixed=[
            "<b>--verify 在中文 Windows 上必崩</b>（gbk 解码 UTF-8 子进程输出）—— 三入口（内联 / "
            "scenario 文件 / scenario 目录）全部修复并实测",
            "<b>批量 --scenario-dir 的日志噪声</b>（根因已定位）：browser-use 的 `ChatDeepSeek._client()` 是"
            "<b>方法</b>——每次 ainvoke 都 new 一个 `AsyncOpenAI`，既不复用也不关闭 ⇒ 连接池绑在"
            "<b>本场景的 loop</b> 上，等它被 GC 时（往往下一个场景的 loop 正在跑）openai 的 "
            "`AsyncHttpxClientWrapper.__del__` 会 `create_task(self.aclose())`，在已关闭的旧 loop 上关 "
            "transport ⇒ stderr 一坨 `Task exception was never retrieved … Event loop is closed`。"
            "修法：连接池由框架自己持有（`client_params={'http_client': …}`）并在本场景 loop 还活着时关闭"
            "（`__del__` 里 `if self.is_closed: return`）。<b>实测噪声 3 处 → 0 处</b>，3/3 场景依旧全 PASSED。",
            "limits.py 的 `/proc/meminfo` 读取补上显式编码（Linux 上是 ASCII，但同样是「依赖默认编码」的隐患）",
        ],
        notes=[
            "三入口端到端实测（DeepSeek 真识别 + 真跑）：内联 --scenario ✅ / --scenario-file ✅ / "
            "--scenario-dir（--limit 1 与全量 3 场景）✅ —— 每条 AI 用例都过了 --verify 的实测闸门",
            "同一条 --verify 路径的 A/B：<b>旧代码在 GBK 环境下 EXIT=1（UnicodeDecodeError traceback）；"
            "新代码 EXIT=0 且校验通过</b>",
            "框架自测基线：<b>86 passed</b>（原 74 + 新增 12 条 UTF-8 / 文件名编码回归）",
            "边界（诚实清单）：`errors=replace` 是刻意的取舍 —— 极端情况下无法解码的字节会变成 U+FFFD 而不是让"
            "校验整条崩掉（验证闸门的第一职责是回答「用例过没过」）",
        ],
    ),
    dict(
        version="7.2", date="2026-09-13", tag="上一版本",
        theme="断言 11 种 · 执行提速 · 会话级浏览器",
        summary="D 项：断言从「只有文本」扩到 11 种（可见/隐藏/数量/属性/输入值/URL/勾选/禁用），"
                "手写用例终于能验「弹窗开合、结果行数、按钮禁用」这类无文案场景，且每种都做了"
                "「期望值写错必须失败」的负向验证。E 项：整个会话共用一个 Chromium，实测用例数 9→13 "
                "反而更快（10.49s → 7.01s）。",
        added=[
            "<b>断言 11 种 kind</b>：text / visible / hidden / count / attr / value / url / "
            "checked / unchecked / enabled / disabled（缺省 kind = text，老用例零改动）",
            "断言目标两种写法：<b>element</b>（probe 语义名 → 映射确定性 locator，AI 链路可用）与 "
            "<b>selector</b>（手写用例专用 CSS/Playwright 选择器，如 li:has-text('买牛奶')）",
            "<b>tests/</b> 框架自测目录：CLI 参数契约 + 断言 kind→代码翻译契约（秒级，不需浏览器）",
            "<b>tests/verify_assert_kinds.py</b> 正/负向端到端脚本：11 种 kind + 4 类结构性错误全部实测",
            "用例：cases/assert_kinds_*.json（search 全类型 / reset 验 value 清空 / modal 验 visible / todo 验 checked）",
            "demo 合同页加一个「导出（未接入）」禁用按钮 —— 让 enabled/disabled 断言有真页覆盖",
        ],
        changed=[
            "<b>E 项提速</b>：conftest 的浏览器改为<b>会话级</b>（_pool，session scope），每条用例只新建 "
            "context + page；逐条 setup 由 <b>0.57~0.66s → 0.04~0.06s</b>（首条 0.74s 起浏览器）",
            "断言成功统一 <b>[CHECK] ✓ 断言: …</b>（逐用例日志 + 调试模式截图），日志能直接看出验了什么、期望值多少",
            "probe 抓到的合同页交互元素 6 → <b>7</b>（多了禁用导出按钮）",
        ],
        fixed=[
            "<b>断言期望值 0 / 空串曾被吞掉</b>：旧逻辑用真值判断取 expect ⇒ 「期望 0 行」「期望输入框被清空」"
            "这类断言会静默失去期望值、变形为永远通过 → 改为按<b>字段存在与否</b>判定",
            "断言缺字段（count 缺 expect / attr 缺 name）、未知 kind、元素未映射 ⇒ 生成脚本 "
            "<b>pytest.fail</b>，绝不静默少验一步（与「未映射元素=显式失败」同一条假绿红线）",
            "会话级浏览器若被 OOM 杀掉：<b>大声告警 + 自动重启</b>，不静默拿坏句柄继续跑（否则后续用例连锁失败、原因不明）",
        ],
        notes=[
            "AI 护栏加强：<b>AI 断言只准 text 且不许出现 selector</b>（否则等于让 LLM 猜 CSS，整套混合架构的立足点就没了）；"
            "结构化 kind=count 会绕过「运行时才知道的期望值」文本检查，故 AI 链路一律禁止",
            "测试基线：<b>13 用例全绿</b>（10 条手写 + 3 条 AI）；框架自测 <b>62 条</b>（CLI 40 + 断言 22）",
            "负向验证：11 种 kind 期望值写错 + 4 类结构性错误，<b>15/15 全部 FAILED</b>（无假绿）",
            "边界（诚实清单）：runner.py 的 ElementMap 场景引擎仍只支持 expect_text（主链路的断言在生成脚本里，已扩展）；"
            "check 动作仍无真页覆盖",
        ],
    ),
    dict(
        version="7.1", date="2026-09-13", tag="上一版本",
        theme="CLI 参数契约 · 不许静默忽略",
        summary="把「看不懂的参数」从静默忽略改成明确报错：过去 --workres（--workers 拼错）会照常跑完并 exit 0，"
                "未知子命令也只打文档就 exit 0 —— 脚本调用方会误判成功。现在参数错一律 exit 2 并给出「想写哪个」的建议，"
                "同时补上 --help / --version。",
        added=[
            "<b>--help / -h</b>：总览 + 子命令帮助（<b>直接取函数 docstring</b>，文档与代码同源，不会漂）",
            "<b>--version / -V</b>：版本号读 build_html.py（版本单一来源；读不到就如实说 unknown）",
            "<b>tests/test_cli_flags.py</b>：参数契约回归（约 3 秒，不需要 demo / 不需要 AI key）——"
            "合法参数不许误杀 + 非法参数必须 exit 2",
        ],
        changed=[
            "<b>参数契约单一定义</b>：cli.py 顶部 FLAG_SPECS（值语义 value / opt / 纯开关）+ "
            "CMD_FLAGS（每个子命令允许哪些），未知参数给拼写建议（difflib）",
            "README 补「CLI 参数契约」说明 + --help / --version 用法",
        ],
        fixed=[
            "<b>拼错参数被静默忽略</b>：<code>prune --dry-run --workres 1</code> 照常跑完并 exit 0 → 现在 exit 2 + 提示",
            "<b>未知子命令 exit 0</b>：<code>frobnicate</code> 只打印文档（脚本会以为成功）→ 现在 exit 2 + 建议",
            "<b>explore 缺 --ai 静默空跑</b>：过去打印一句就 return（exit 0，等于什么都没做）→ 现在 exit 2",
            "<b>_arg_values 重复定义</b>（cli.py:92 与 :164，后者静默覆盖前者）→ 只留一处 + 自检测试防复发",
        ],
        notes=[
            "已移除的参数 <code>--to-cases</code> 会明确提示替代做法（落盘是默认行为，要关用 --no-cases）",
            "测试基线：<b>9 用例全绿</b>（generate / run / all 三条链路回归通过）+ CLI 契约自测全绿",
        ],
    ),
    dict(
        version="7.0", date="2026-09-11", tag="上一版本",
        theme="链路打通 · 资源安全 · 真实性保障",
        summary="把「AI 说它对」变成「实测通过」：AI 产的用例与手搓用例跑同一条确定性执行链；"
                "并发按内存自动降级（不再 OOM 误杀网关）；所有静默兜底（假 AI / 假绿 / 死代码）逐一清除。",
        added=[
            "场景库 <b>scenarios/*.yml</b>（一个文件 = 一个场景）+ 三个入口：<b>--scenario</b>（内联）/"
            "<b>--scenario-file</b>/<b>--scenario-dir --tag --limit</b>（三者互斥，参数错 exit 2）",
            "<b>explore --ai 默认落 cases/ai_&lt;id&gt;_&lt;ts&gt;.json</b>（--no-cases 可关）；<b>--verify</b> 交付即验证："
            "落盘后立刻 generate + pytest 单跑，FAILED → exit 3（日志 output/verify/）",
            "<b>cli prune</b> 归档保留策略（framework/retention.py，HYBRID_KEEP_SNAPSHOTS 默认 20；explore/probe 结束自动静默执行）",
            "<b>调试开关 --debug</b>（别名 --headed）：开了就「看得见」——有屏幕弹 Chromium 一步步跑；"
            "无屏幕自动录视频(webm) + <b>逐步截图</b> + trace 回放。配套 --case（只跑一条）/ --slowmo（放慢）",
            "<b>资源安全 P0</b>：limits.safe_workers() 按 MemAvailable 自动降并发 + browser.py 收敛启动参数 + 日志 run-id 隔离",
            "本文档新增「版本与更新记录」；第 4 节新增<b>函数级调用链路图</b>（图 A 图形化泳道图 + 图 B 明细）",
        ],
        changed=[
            "<b>generate 定位来源改为「快照优先」</b>：element_map → probe 快照 → 现场 probe（命中即停），"
            "并打印来源与命中率（实测 <b>8/12 命中 + 现场补齐 4/4</b>）",
            "<b>probe 消歧信号增强</b>：label 兜底（同容器前置 label）+ 容器 heading，缓解同名控件歧义",
            "<b>AI 规划更懂业务</b>：prompt 接入【页面背景】+【本场景护栏】，新增规则 2b 区域消歧；"
            "语义校准告警（AI 描述 vs 控件语义重叠 &lt;0.3 时提示「疑似选错」）",
            "<b>文档与代码做了一致性审计</b>（以代码为准）：README 新增「两种业务场景」章节、调试开关整段重写，共修正 24 处",
        ],
        fixed=[
            "<b>假 AI 产物</b>：LLM 失败时静默用 mock 冒充 AI（把待办页控件挂成合同页场景）→ 新增 AiExploreError，"
            "LLM 不可用直接 <b>exit 2</b>；只有显式 --mock-fallback 才降级且不写 cases/",
            "<b>编造断言</b>：AI 写「共 N 条」这类运行时才知道的计数（真实是「共 20 条合同」）→ prompt 禁止 + "
            "case_warnings 计数/时间戳告警",
            "<b>Sync API 跑在 asyncio loop 里</b>（最隐蔽的死代码）：弹窗字段补充、DOM 上下文增强<b>从来没生效过</b> → "
            "拆「同步探测 → 异步规划」两段",
            "<b>重复探测</b>：CLI 先探一次、explore 内部再探一次 → 两个 Chromium 抢内存，第二次静默失败 → 改为只探一次",
            "<b>静默丢元素</b>：AI 给的名字对不上清单时 element=None 且零提示 → 改为精确/唯一模糊对齐 + 明确告警 + 可用清单",
            "<b>假绿</b>：手搓用例元素名写错时生成脚本只留注释跳过，仍 PASSED → 改为 pytest.fail 显式失败",
            "<b>--headed 是空操作</b>：pytest -n 1 也会设 PYTEST_XDIST_WORKER=gw0 ⇒ conftest 判「并发⇒无头」（实测无 DISPLAY 也 9 passed）",
            "<b>录像只有 4KB 空壳</b>：webm 必须等 context.close() 才落盘 → 调整保存时序（修后 152KB）",
            "<b>_get_llm_text 死代码</b>：在协程里调 asyncio.run() 必崩 → 新增 await 版 _get_llm_text_async()",
            "文档漂移：probe.py docstring 声称的字段不存在；README 把 locator 优先级写反（实际 <b>data-testid 置顶</b>）",
            "DeepSeek function calling 间歇 JSON 抖动 → HYBRID_LLM_ATTEMPTS 退避重试（默认 3 次）",
        ],
        notes=[
            "测试基线：<b>9 用例全绿</b>（6 条手写 + 3 条 AI）；<b>零 AI key 也能跑</b>（AI 只影响「有没有用例」）",
            "已知边界（诚实清单）：单目标页面（跨多页面不完整）、data 参数化一期只解析不展开、"
            "并发受本机内存约束（1.87G 无 swap ⇒ 恒 1 worker）、check 动作代码支持但 demo 无 checkbox 未真页覆盖",
        ],
    ),
    dict(
        version="6.0", date="2026-09-04", tag="基线版本",
        theme="能跑通、能定位、能自愈",
        summary="v7.0 之前的可用基线：三层定位 + 用例驱动 + AI 语义识别链路 + 自愈，配套 10 节培训页。",
        added=[],
        changed=[],
        fixed=[],
        notes=[
            "三层定位（<b>data-testid 置顶</b>）+ web-first 断言 + trace 录制",
            "语义上下文消歧（nearby_text）；用例驱动 cases/*.json → generate 翻译 → pytest 并发",
            "<b>脚本与数据分离</b>（字面值抽到 scripts/datasets/*.json）；用例级变量池 case.vars",
            "AI 语义识别链路（方案 C：DeepSeek 直连，绕开 browser-use Agent 的 schema bug）",
            "自愈 healer.py（生成脚本接入自愈是 v7.0）；10 节新员工培训页（本文档）",
        ],
    ),
]

def _changelog_section() -> str:
    """渲染「版本与更新记录」章节（数据来自 CHANGELOG；按 新增/改进/修复/说明 分类着色）。"""
    kinds = (("added", "🚀 新增", "#15803d", "#dcfce7"),
             ("changed", "🔧 改进", "#1d4ed8", "#dbeafe"),
             ("fixed", "🐞 修复", "#b45309", "#ffedd5"),
             ("notes", "📌 说明", "#475569", "#f1f5f9"))
    out = ['  <section id="changelog">',
           '    <h2 class="sec-title"><span class="n">A</span>版本与更新记录（Changelog）</h2>',
           f'    <p class="sec-sub">当前版本 <b>V{VERSION}</b>（{VERSION_DATE}）——每次改动都写清「新增 / 改进 / 修复」，'
           '方便对着代码回溯。</p>']
    for rel in CHANGELOG:
        cur = " cl-cur" if rel.get("tag") == "当前版本" else ""
        out.append(f'    <div class="card cl{cur}">')
        out.append('      <div class="cl-head">'
                   f'<span class="cl-ver">V{rel["version"]}</span>'
                   f'<span class="cl-date">{rel["date"]}</span>'
                   f'<span class="cl-tag">{rel["tag"]}</span>'
                   f'<span class="cl-theme">{rel["theme"]}</span></div>')
        out.append(f'      <p class="cl-sum">{rel["summary"]}</p>')
        for key, label, fg, bg in kinds:
            items = rel.get(key) or []
            if not items:
                continue
            out.append(f'      <div class="cl-kind"><span class="chip" style="color:{fg};background:{bg}">{label}</span><ul>')
            out.extend(f'        <li>{it}</li>' for it in items)
            out.append('      </ul></div>')
        out.append('    </div>')
    out.append('  </section>')
    return "\n".join(out)


# ================= 图 A：两种场景的函数级调用链路（内联 SVG） =================
# 为什么用 SVG 而不是 ASCII：调用链关心"谁调谁 + 传什么数据"，图形化箭头/泳道比字符树直观。
# 自包含：只用 HTML 属性，不引外部字体/JS；颜色沿用页面色板。
# v2 修正（2026-09-11 视觉核验后）：① 箭头不再带压字标签（间隙只有 18px，放不下中文标签）
#   ② 实体不经二次转义（文本内容里的花括号直接写，escape 只处理 & < >）
#   ③ 行间距加大，竖直箭头留出呼吸空间
def _w(text, max_w):
    """按"视觉宽度"折行（CJK 记 1、ASCII 记 0.55），避免 SVG 文本溢出方框。"""
    lines, cur, w = [], "", 0.0
    for ch in text:
        cw = 0.55 if ord(ch) < 0x2E80 else 1.0
        if cur and w + cw > max_w:
            lines.append(cur)
            cur, w = "", 0.0
        cur += ch
        w += cw
    if cur:
        lines.append(cur)
    return lines


def _svg_two_scenarios() -> str:
    """渲染「两种场景」的函数级调用链路图（泳道：场景① / 汇合点 / 场景② / 共享层）。"""
    import html as _h

    C1, BG1 = "#2563eb", "#eff6ff"      # 场景①：AI 链路（蓝）
    C2, BG2 = "#0f8f6a", "#ecfdf5"      # 场景②：确定性链路（绿）
    CM, BGM = "#b45309", "#fffbeb"      # 汇合点（琥珀）
    CS, BGS = "#7c3aed", "#f5f3ff"      # 共享层（紫）
    INK, MUT = "#0f172a", "#64748b"

    TRUNC = []      # 排版自检：宁可打警告，也不静默丢行
    out = ['<svg viewBox="0 0 1200 932" width="100%" role="img" '
           'aria-label="两种场景的函数级调用链路图" '
           'style="background:#fff;border:1px solid #e2e8f0;border-radius:14px">']
    out.append('<defs>')
    for mid, col in (("a1", C1), ("a2", C2), ("am", CM)):
        out.append(f'<marker id="{mid}" markerWidth="10" markerHeight="8" refX="9" refY="4" '
                   f'orient="auto"><path d="M0,0 L10,4 L0,8 z" fill="{col}"/></marker>')
    out.append('</defs>')
    out.append('<style>text{font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif}</style>')

    def band(y, label, col):
        out.append(f'<rect x="16" y="{y}" width="1168" height="36" rx="8" fill="{col}"/>')
        out.append(f'<text x="30" y="{y + 24}" fill="#fff" font-size="15.5" font-weight="700">'
                   f'{_h.escape(label)}</text>')

    def node(x, y, w, h, col, bg, badge, title, body, bsize=11.5):
        out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{bg}" '
                   f'stroke="{col}" stroke-width="1.5"/>')
        cx = x + 17
        out.append(f'<circle cx="{cx}" cy="{y + 19}" r="11.5" fill="{col}"/>')
        out.append(f'<text x="{cx}" y="{y + 23.5}" fill="#fff" font-size="12.5" '
                   f'font-weight="700" text-anchor="middle">{_h.escape(badge)}</text>')
        out.append(f'<text x="{x + 36}" y="{y + 24}" fill="{INK}" font-size="14" '
                   f'font-weight="700">{_h.escape(title)}</text>')
        yy = y + 24 + bsize + 7
        for ln in body:
            for wrap in _w(ln, (w - 26) / bsize):        # CJK 字宽 ≈ 字号 → 换算成"可容纳字符数"
                if yy > y + h - 8:
                    TRUNC.append(f"{title}｜{ln[:22]}")
                    break
                out.append(f'<text x="{x + 12}" y="{yy}" fill="{MUT}" font-size="{bsize}">'
                           f'{_h.escape(wrap)}</text>')
                yy += bsize + 4
        return yy

    def arrow(x1, y1, x2, y2, col, mid):
        out.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{col}" '
                   f'stroke-width="2" marker-end="url(#{mid})"/>')

    # ---------- 场景① 泳道 ----------
    band(20, "场景①  自然语言用例 → AI 语义识别/编排 → 输出测试用例到 cases/    入口: cli explore --ai", C1)
    W, GAP, X0 = 216, 18, 20
    xs = [X0 + i * (W + GAP) for i in range(5)]
    AR1, AR2 = 124, 256          # 两条节点行的箭头 y
    Y1, Y2 = 64, 210
    node(xs[0], Y1, W, 120, C1, BG1, "1", "输入：自然语言",
         ["cli.cmd_explore(rest)", "· --scenario \"…\" 内联",
          "· --scenario-file x.yml", "· --scenario-dir 批量（互斥）"])
    node(xs[1], Y1, W, 120, C1, BG1, "2", "备参数 + 交棒",
         ["cli._explore_one()", "scenario.load_scenario_file()", "explorer.ai_explore()",
          "（CLI 自己不探测）"])
    node(xs[2], Y1, W, 120, C1, BG1, "3", "感知［同步·0 token］",
         ["_collect_page_context()", "probe.probe_page() ◀出场❶",
          "_try_collect_modal_items()", "_collect_dom_context()"])
    node(xs[3], Y1, W, 120, C1, BG1, "4", "认知［异步·AI］",
         ["_ai_explore_async()", "_build_planner_prompt()",
          "ChatDeepSeek.ainvoke(…)", "_plan_to_steps()/_match_item()"])
    node(xs[4], Y1, W, 120, C1, BG1, "5", "编排结果",
         ["_apply_semantic_calibration()", "_finalize_map()",
          "＝ ElementMap", "（只含 semantic_name）"])
    for i in range(4):
        arrow(xs[i] + W, AR1, xs[i + 1], AR1, C1, "a1")
    node(xs[4], Y2, W, 92, C1, BG1, "6", "落盘为用例",
         ["elementmap_to_cases_file()", "→ cases/ai_<id>_<ts>.json", "（含 source_scenario 溯源）"])
    node(xs[3], Y2, W, 92, C1, BG1, "7", "交付即验证",
         ["cli._verify_cases()", "generate + pytest 单跑", "FAILED → ❌ exit 3"])
    # 左侧留白处补一块说明（把 6→7 这道闸门讲透）
    out.append(f'<rect x="{xs[0]}" y="{Y2}" width="{xs[3] - xs[0] - GAP}" height="92" rx="10" '
               f'fill="#f8fafc" stroke="{C1}" stroke-width="1.2" stroke-dasharray="6 4"/>')
    out.append(f'<text x="{xs[0] + 14}" y="{Y2 + 24}" fill="{C1}" font-size="13" font-weight="700">'
               f'💡 6 → 7 这道闸门（--verify，默认开）</text>')
    for k, ln in enumerate([
        "AI 写完用例不算完：立刻 generate + 逐条 pytest 单跑。",
        "实测 PASSED 才算「可用用例」；FAILED → ❌ + exit 3（日志 output/verify/）。",
        "目的：把「AI 说它对」变成「实测通过」——不让假用例进用例库（--no-verify 可跳过）。"]):
        out.append(f'<text x="{xs[0] + 14}" y="{Y2 + 48 + k * 16}" fill="{MUT}" '
                   f'font-size="11">{_h.escape(ln)}</text>')
    arrow(xs[4] + W / 2, Y1 + 120, xs[4] + W / 2, Y2, C1, "a1")
    arrow(xs[4], AR2, xs[3] + W, AR2, C1, "a1")
    arrow(xs[3] + W / 2, Y2 + 92, xs[3] + W / 2, 334, C1, "a1")

    # ---------- 汇合点 ----------
    out.append(f'<rect x="16" y="334" width="1168" height="72" rx="10" fill="{BGM}" '
               f'stroke="{CM}" stroke-width="1.8"/>')
    out.append(f'<text x="34" y="360" fill="{CM}" font-size="14.5" font-weight="700">'
               f'【汇合点】cases/*.json —— 两条链路共同的接口（同一套格式，所以手搓用例与 AI 用例能一起跑）</text>')
    out.append(f'<text x="34" y="384" fill="{MUT}" font-size="11.5">'
               f'字段：case_id / name / base_url / steps[op,desc,element,value,url] / asserts[kind?,desc,expect?,element|selector,name?]'
               f'　（AI 用例额外带 source_scenario / scenario_id 溯源字段，generator 会忽略）</text>')
    arrow(600, 406, 600, 434, CM, "am")

    # ---------- 场景② 泳道 ----------
    band(434, "场景②  手搓 case.json → 生成 playwright 脚本 + 数据分离 → 执行    入口: cli generate / run", C2)
    W2, G2, X2 = 276, 20, 18
    x2 = [X2 + i * (W2 + G2) for i in range(4)]
    Y3, Y4 = 478, 624
    AR3, AR4 = 538, 684
    node(x2[0], Y3, W2, 120, C2, BG2, "1", "输入：手写用例",
         ["cases/<case_id>.json", "element 写 semantic_name", "value 可写 {datetime}",
          "（格式与 AI 用例一致）"])
    node(x2[1], Y3, W2, 120, C2, BG2, "2", "读用例",
         ["cli.cmd_generate()", "generator.generate_scripts()", "glob cases/*.json",
          "needed = 全部 element"])
    node(x2[2], Y3, W2, 120, C2, BG2, "3", "语义名 → locator",
         ["Ⓐ _load_loc_map_from_element_map()", "Ⓑ _load_loc_map_from_probe_snapshot()",
          "Ⓒ 现场 probe_page() ◀出场❷", "命中即停，日志会打印来源"])
    node(x2[3], Y3, W2, 120, C2, BG2, "4", "确定性翻译",
         ["_semantic_to_locator_expr()", "test_id > role+name > text",
          "未映射 → pytest.fail", "（绝不静默跳过）"])
    for i in range(3):
        arrow(x2[i] + W2, AR3, x2[i + 1], AR3, C2, "a2")
    node(x2[3], Y4, W2, 120, C2, BG2, "5", "数据抽离",
         ["_extract_data(case)", "→ datasets/<case_id>.json",
          "脚本只留 _data(key, ctx)", "（脚本 ⇄ 数据 分离）"])
    node(x2[2], Y4, W2, 120, C2, BG2, "6", "生成产物",
         ["scripts/test_cases.py（脚本）", "datasets/*.json（数据）",
          "conftest.py（运行期)", "零 token，可进 CI；断言 11 种 kind"])
    node(x2[1], Y4, W2, 120, C2, BG2, "7", "执行",
         ["cmd_run() → safe_workers()", "pytest -n N --html=…",
          "资源预检自动降并发", "逐用例 .log + report.html"])
    node(x2[0], Y4, W2, 120, C2, BG2, "8", "运行期定位 / 自愈",
         ["conftest._act() →", "resolve_locator() Tier1→Tier2", "仍失败 → healer.try_heal()",
          "业务断言不过＝真 bug"])
    arrow(x2[3] + W2 / 2, Y3 + 120, x2[3] + W2 / 2, Y4, C2, "a2")
    arrow(x2[3], AR4, x2[2] + W2, AR4, C2, "a2")
    arrow(x2[2], AR4, x2[1] + W2, AR4, C2, "a2")
    arrow(x2[1], AR4, x2[0] + W2, AR4, C2, "a2")
    arrow(600, Y4 + 120, 600, 768, C2, "a2")

    # ---------- 共享层 ----------
    out.append(f'<rect x="16" y="768" width="1168" height="148" rx="12" fill="{BGS}" '
               f'stroke="{CS}" stroke-width="1.6" stroke-dasharray="6 4"/>')
    out.append(f'<text x="34" y="795" fill="{CS}" font-size="14.5" font-weight="700">'
               f'两条链路共享的三样东西（看懂框架的关键）</text>')
    sw = 372
    cards = [
        ("① probe.probe_page() 出场两次",
         ["出场❶ explore 时「给 AI 看菜单」：语义清单 + 消歧上下文",
          "出场❷ generate 时「把语义名翻成 locator」：优先吃快照",
          "同一个函数，两个时点，两种用途"]),
        ("② semantic_name 契约",
         ["probe 起名（保证唯一）→ AI 引用 → cases[].element",
          "→ generate 查 loc_map → 变成 locator",
          "selector 从头到尾不进 LLM"]),
        ("③ 执行层完全共用",
         ["locator_bridge + healer + limits + conftest",
          "AI 只决定「有没有用例」",
          "跑起来与手搓用例无差别"]),
    ]
    for k, (t, body) in enumerate(cards):
        x = 34 + k * (sw + 14)
        out.append(f'<rect x="{x}" y="810" width="{sw}" height="94" rx="9" fill="#fff" '
                   f'stroke="{CS}" stroke-width="1.2"/>')
        out.append(f'<text x="{x + 12}" y="832" fill="{INK}" font-size="12.5" '
                   f'font-weight="700">{_h.escape(t)}</text>')
        yy = 851
        for ln in body:
            for wrap in _w(ln, (sw - 26) / 10.5):
                if yy > 897:
                    TRUNC.append(f"{t}｜{ln[:22]}")
                    break
                out.append(f'<text x="{x + 12}" y="{yy}" fill="{MUT}" font-size="10.5">'
                           f'{_h.escape(wrap)}</text>')
                yy += 15
    if TRUNC:
        print("  ⚠️ SVG 排版告警（文字被截断）→", "; ".join(TRUNC))
    return "\n".join(out) + "\n</svg>"


def build() -> str:
    cards = render_cards()
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI 混合 GUI 测试框架 · 新员工培训（V{VERSION}）</title>
<style>
  :root {{
    --ink:#0f172a; --muted:#64748b; --line:#e2e8f0; --bg:#f1f5f9;
    --brand:#0891b2; --brand2:#2563eb; --star:#fbbf24;
  }}
  * {{ box-sizing:border-box; margin:0; padding:0; }}
  body {{ font-family:-apple-system,'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif;
          background:var(--bg); color:var(--ink); line-height:1.7; }}
  .wrap {{ max-width:1080px; margin:0 auto; padding:0 20px; }}

  /* hero */
  .hero {{ background:linear-gradient(135deg,#0f172a,#1e3a8a 60%,#0891b2);
           color:#fff; padding:56px 20px 40px; text-align:center; }}
  .hero h1 {{ font-size:2.3rem; margin-bottom:10px; }}
  .hero p {{ opacity:.85; font-size:1.12rem; max-width:760px; margin:8px auto; }}
  .pill {{ display:inline-block; background:rgba(255,255,255,.15);
           border:1px solid rgba(255,255,255,.3); border-radius:999px;
           padding:5px 16px; margin:6px 4px; font-size:.92rem; }}

  /* section */
  section {{ margin:38px 0; }}
  .sec-title {{ font-size:1.5rem; margin-bottom:6px; display:flex; align-items:center; gap:10px; }}
  .sec-title .n {{ background:var(--brand); color:#fff; width:32px; height:32px;
                   border-radius:8px; display:inline-flex; align-items:center;
                   justify-content:center; font-size:1.05rem; flex-shrink:0; }}
  .sec-sub {{ color:var(--muted); margin-bottom:18px; }}

  .card {{ background:#fff; border:1px solid var(--line); border-radius:14px;
           padding:22px; box-shadow:0 1px 3px rgba(15,23,42,.05); }}

  /* 对比 */
  .vs {{ display:grid; grid-template-columns:1fr auto 1fr; gap:16px; align-items:center; }}
  .vs-box {{ border-radius:12px; padding:18px; }}
  .vs-box.ai {{ background:#eef2ff; border:2px solid #3b6fdd; }}
  .vs-box.pw {{ background:#f0fdf4; border:2px solid #0f8f6a; }}
  .vs-box h3 {{ margin-bottom:8px; font-size:1.05rem; }}
  .vs-box ul {{ padding-left:18px; }}
  .vs-box li {{ margin:4px 0; font-size:.95rem; }}
  .plus {{ font-size:1.8rem; color:var(--brand); text-align:center; font-weight:700; }}

  /* 流程 */
  .flow {{ display:flex; gap:10px; flex-wrap:wrap; }}
  .flow-step {{ flex:1; min-width:180px; background:#fff; border:1px solid var(--line);
                border-top:4px solid var(--brand); border-radius:10px; padding:16px; }}
  .flow-step .tag {{ font-size:.78rem; color:var(--muted); text-transform:uppercase;
                     letter-spacing:.5px; margin-bottom:4px; }}
  .flow-step h4 {{ margin-bottom:4px; }}
  .flow-step p {{ font-size:.9rem; color:var(--muted); }}
  .flow-step .bdge {{ display:inline-block; font-size:.75rem; padding:2px 8px;
                      border-radius:6px; color:#fff; margin-bottom:8px; }}

  /* 要点 */
  .pts {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:14px; }}
  .pt {{ border:1px solid var(--line); border-radius:12px; padding:16px; background:#fff; }}
  .pt .ico {{ font-size:1.5rem; }}
  .pt h4 {{ margin:6px 0 4px; }}
  .pt p {{ font-size:.9rem; color:var(--muted); }}
  .pt .code-inline {{ background:#0d1117; color:#7ee787; padding:2px 6px;
                      border-radius:5px; font-family:ui-monospace,monospace; font-size:.85em; }}

  /* 调用关系树 */
  .tree {{ background:#0d1117; color:#d1d5db; border-radius:12px; padding:20px;
           font-family:ui-monospace,Consolas,monospace; font-size:.9rem; overflow-x:auto; }}
  .tree b {{ color:#8ab4f8; }}

  /* code card */
  .file-card {{ margin-bottom:22px; }}
  .file-head {{ display:flex; align-items:center; gap:10px; margin-bottom:8px; }}
  .file-path {{ background:#f1f5f9; padding:4px 10px; border-radius:6px; font-size:.88rem; }}
  .file-desc {{ color:var(--muted); font-size:.93rem; margin-bottom:12px; }}
  .badge {{ color:#fff; font-size:.78rem; padding:3px 10px; border-radius:999px; }}
  .codebox {{ background:#0d1117; border-radius:10px; overflow-x:auto; }}
  .code-line {{ display:flex; font-family:ui-monospace,Consolas,monospace;
                font-size:.85rem; line-height:1.6; padding:1px 8px; }}
  .code-line .ln {{ color:#3b475a; min-width:38px; text-align:right;
                    padding-right:12px; user-select:none; }}
  .code-line code {{ white-space:pre; color:#e6edf3; }}
  .code-line.star {{ background:#31250b; border-left:3px solid var(--star); }}
  .code-line.star code {{ color:#fef3c7; font-weight:600; }}
  .code-line.star .ln {{ color:#b78a2c; }}
  .k {{ color:#ff7b72; }} .s {{ color:#7ee787; }} .c {{ color:#8b949e; font-style:italic; }}
  .code-note {{ background:#fff7d6; border:1px solid #f5d76e; border-radius:8px;
                padding:8px 12px; margin:6px 0 10px; font-size:.9rem; }}

  /* 坑 */
  .pit {{ border-left:4px solid #ef4444; background:#fef2f2; padding:14px 16px;
          border-radius:6px; margin-bottom:14px; }}
  .pit h4 {{ color:#b91c1c; margin-bottom:4px; }}
  .pit p {{ font-size:.92rem; color:#7f1d1d; }}
  .pit code {{ background:#fecaca; color:#7f1d1d; padding:1px 5px; border-radius:4px;
               font-size:.87em; }}

  /* command */
  .cmd {{ background:#0d1117; color:#e6edf3; border-radius:10px; padding:16px;
          font-family:ui-monospace,monospace; font-size:.9rem; overflow-x:auto; }}
  .cmd .prompt {{ color:#4ade80; }} .cmd .cmt {{ color:#8b949e; }}

  /* 记住 */
  .mem {{ display:grid; grid-template-columns:repeat(3,1fr); gap:14px; }}
  @media(max-width:760px){{ .mem{{grid-template-columns:1fr}} .vs{{grid-template-columns:1fr}} }}
  .mem-item {{ border-radius:12px; padding:22px; text-align:center; color:#fff; }}
  .mem-item.a {{ background:#3b6fdd; }} .mem-item.b {{ background:#0f8f6a; }}
  .mem-item.c {{ background:#0891b2; }}
  .mem-item .big {{ font-size:1.6rem; margin-bottom:6px; }}
  .mem-item b {{ font-size:1.15rem; display:block; margin-bottom:6px; }}
  .mem-item span {{ font-size:.9rem; opacity:.9; }}

  /* 版本徽标 + 更新记录 */
  .ver {{ display:inline-block; margin:4px 0 10px; padding:5px 16px; border-radius:999px;
          background:rgba(255,255,255,.18); border:1px solid rgba(255,255,255,.42);
          color:#fff; font-weight:800; letter-spacing:.6px; font-size:.98rem; text-decoration:none; }}
          .ver:hover {{ background:rgba(255,255,255,.3); }}
  .card.cl {{ margin-bottom:16px; }}
  .card.cl.cl-cur {{ border-color:var(--brand); box-shadow:0 0 0 3px rgba(8,145,178,.10); }}
  .cl-head {{ display:flex; align-items:center; gap:10px; flex-wrap:wrap; margin-bottom:6px; }}
  .cl-ver {{ font-size:1.3rem; font-weight:800; color:var(--brand); }}
  .cl-date {{ color:var(--muted); font-size:.88rem; }}
  .cl-tag {{ background:var(--brand); color:#fff; font-size:.74rem; padding:3px 10px; border-radius:999px; }}
  .cl-theme {{ color:var(--muted); font-size:.9rem; }}
  .cl-sum {{ margin:4px 0 12px; }}
  .cl-kind {{ display:flex; gap:10px; align-items:flex-start; margin:9px 0; }}
  .cl-kind ul {{ margin:0; padding-left:20px; flex:1; }}
  .cl-kind li {{ margin:5px 0; }}
  .chip {{ flex:0 0 auto; font-size:.78rem; font-weight:700; padding:3px 10px; border-radius:999px; white-space:nowrap; }}
  footer {{ text-align:center; color:var(--muted); padding:34px 0 40px; font-size:.88rem; }}
</style>
</head>
<body>

<div class="hero">
  <h1>AI 混合 GUI 测试框架<sup>★</sup></h1>
  <a class="ver" href="#changelog" title="跳到版本与更新记录">V{VERSION} · {VERSION_DATE}　▼</a>
  <p>给新同学的一页通：<b>Browser Use 负责思考，Playwright 负责执行</b>，
     两者靠一份约定衔接，各干各的强项。</p>
  <div>
    <span class="pill">🤖 AI 理解意图</span>
    <span class="pill">✅ 代码精准定位</span>
    <span class="pill">📄 契约无缝衔接</span>
  </div>
</div>

<div class="wrap">

<!-- ========== 1. 为什么混合 ========== -->
<section>
  <h2 class="sec-title"><span class="n">1</span>为什么是「混合」？</h2>
  <p class="sec-sub">一桌子两把刀，各有锋利处，别只拿一把。</p>
  <div class="card vs">
    <div class="vs-box ai">
      <h3>🤖 Browser Use（AI）</h3>
      <ul>
        <li>✅ 听得懂人话</li>
        <li>✅ 会规划步骤、挑元素</li>
        <li>❌ 会"幻觉"，结果不总重复</li>
        <li>❌ 每步花一次模型钱（token）</li>
      </ul>
    </div>
    <div class="plus">1+1&gt;2</div>
    <div class="vs-box pw">
      <h3>✅ Playwright（确定）</h3>
      <ul>
        <li>✅ 精准、不猜、可回归</li>
        <li>✅ 免费、快、能进 CI</li>
        <li>❌ 不透人性，得人写 selector</li>
        <li>❌ UI 一改 selector 就断</li>
      </ul>
    </div>
  </div>
  <div class="card" style="margin-top:14px;">
    <b>生活类比：</b>AI 是<b>导游</b>——认得路、会安排行程，但可能带偏；<br>
    Playwright 是<b>导航仪</b>——绝对准、说走就走，但得先输入目的地。<br>
    🌟 导游负责<b>规划</b>，导航仪负责<b>走稳</b>——这就是我们要的配合。
  </div>
</section>

<!-- ========== 2. 目录结构说明 ========== -->
<section>
  <h2 class="sec-title"><span class="n">2</span>目录结构：文件都在哪，谁负责什么</h2>
  <p class="sec-sub">第一眼看这个，就知道该到哪个目录找什么。✅=确定性代码，🤖=AI 智能层。</p>
  <div class="card">
  <pre class="tree"><b>hybrid_gui_qa/</b>
├── <b>cases/</b>                  ★ 自然语言用例(写死数据)
│   ├── search_name_fuzzy.json       "搜索"用例模板(手写)
│   ├── create_bu_a_c1.json           "新建"用例模板(含{{datetime}}动态占位)
│   └── ai_*.json                    🤖 explore --ai 产出的 AI 用例(ai_ 前缀隔离,可批量清理)
├── <b>scenarios/</b>               ★ AI 场景库(一文件=一场景,YAML)
│   └── contracts/*.yml             场景=自然语言动作流+领域上下文+断言护栏
├── <b>scripts/</b>                 ★ generate 产物(可随时重建)
│   ├── test_cases.py                生成的 pytest 用例(按操作类型翻译)
│   ├── conftest.py                  会话级浏览器池/数据注入/变量池/断言辅助/日志
│   └── datasets/                    ▲ 抽离出的数据(脚本⇄数据分离)
├── <b>framework/</b>                核心框架
│   ├── cli.py                       ⚙️ 命令行入口(explore/probe/generate/run/all/prune)
│   ├── probe.py                     ✅ [Playwright] 探测元素
│   ├── explorer.py                  🤖 [AI] 语义识别(读场景→规划；失败即报错,不静默降级)
│   ├── case_builder.py              🤖 ElementMap→cases/ai_*.json 转换 + 用例质量校验(防假绿)
│   ├── locator_bridge.py            ✅ [Playwright] 语义→唯一locator(核心!)
│   ├── generator.py                 ✅ 按操作类型翻译+抽离数据→scripts/
│   ├── runner.py                    ✅ ElementMap 场景执行引擎(集成自愈)
│   ├── healer.py                    🩹 自愈闭环(再协商+业务断言兜底+可审 diff)
│   ├── element_map.py               数据契约(ElementRef/TestStep/ElementMap)
│   ├── data_driven.py               🧩 占位符替换+变量池+动态占位符
│   ├── browser.py                   ⚙️ Chromium 启动参数唯一来源(不降 RSS,保稳定)
│   ├── limits.py                    🧯 并发安全闸(按可用内存自动降级,防 OOM)
│   ├── retention.py                 🗄 归档保留:快照各留最近 N 个(cli prune)
│   ├── scenario.py                  🗂 scenarios/*.yml 解析/校验/发现(需 PyYAML)
│   └── config.py                    配置+目录常量+LLM选择
├── <b>demo/</b>                      被测应用(靶子,8000端口)
│   ├── app.py                       静态页面 + 内存数据 API(客户/合同/复位;/api/*)
│   ├── contracts.html               合同管理系统页(列表/客户右模糊筛选/新建+客户弹层)
│   └── contract_detail.html         合同详情页(读同一条真实记录;查不到的编号如实报"未找到")
├── <b>tests/</b>                     框架自身的回归测试(不是被测应用用例)
│   ├── test_cli_flags.py / test_utf8_io.py / test_cli_exit_codes.py / test_llm_retry.py / test_assert_kinds_render.py
│   └── verify_*.py                  正/负向端到端验证(需 demo):断言11种 / 跨页4段 / 弹层picker
├── <b>output/</b>                    ✅ 运行时证据(probe/plan/heal/trace,可清)
├── <b>log/&lt;run_id&gt;/</b>             本次运行 逐用例 .log + report.html + traces(可清)
├── README.md                       本框架文档
├── build_html.py                    生成 training.html 培训页
└── training.html                   ★ 这份培训文档</pre>
  </div>
  <div style="margin-top:12px;">
    <div class="pt"><div class="ico">🧭</div><h4>新员工怎么用这份地图找东西</h4>
      <p>① 想知道某步跑什么逻辑 → 看 <span class="code-inline">framework/</span> 对应模块；<br>
         ② 想改测试数据 → 改 <span class="code-inline">cases/*.json</span>（再跑 generate 重建 scripts/）；<br>
         ③ 想看脚本长啥样 / 数据在哪 → <span class="code-inline">scripts/</span>；<br>
         ④ 想确认这次跑的结果 → <span class="code-inline">output/</span>(证据) + <span class="code-inline">log/</span>(报告)。</p></div>
  </div>
</section>

<!-- ========== 3. 整体流程 ========== -->
<section>
  <h2 class="sec-title"><span class="n">3</span>整体流程：explore(AI 产用例) → cases/ → generate → run(带自愈)</h2>
  <p class="sec-sub">本框架有<b>两种业务场景</b>：<b>①</b> 自然语言 → `explore --ai` 语义识别/编排 → 用例落 <code>cases/ai_*.json</code>（花 token）；<b>②</b> 手搓 <code>cases/*.json</code> → `generate` 生成脚本+数据分离 → `run` 执行（零 token）。一条龙（`cli all`）跑的是<b>确定性执行</b>那条；两条链路在 <code>cases/*.json</code> 汇合。</p>
  <div class="flow">
    <div class="flow-step">
      <span class="bdge" style="background:#0f8f6a">✅ Playwright</span>
      <div class="tag">Step 1 · 探测</div>
      <h4>probe</h4>
      <p>扫页面，把可交互元素"翻译"成语义清单（role/name/placeholder/test_id等）。</p>
      <p style="margin-top:6px;font-size:.8rem;color:#94a3b8">→ 元素语义清单 JSON</p>
    </div>
    <div class="flow-step">
      <span class="bdge" style="background:#0f8f6a">✅ Playwright</span>
      <div class="tag">Step 2 · 生成</div>
      <h4>generate</h4>
      <p>读 cases/*.json → probe 映射确定性 locator + 按操作类型翻译 + 抽离数据。</p>
      <p style="margin-top:6px;font-size:.8rem;color:#94a3b8">→ scripts/test_cases.py + datasets/</p>
    </div>
    <div class="flow-step">
      <span class="bdge" style="background:#0f8f6a">✅ Playwright</span>
      <div class="tag">Step 3 · 执行</div>
      <h4>run</h4>
      <p>pytest 并发执行（Tier1→Tier2 定位 + web-first 断言 + Healer 自愈）。</p>
      <p style="margin-top:6px;font-size:.8rem;color:#94a3b8">→ 通过/失败 + report.html + .log</p>
    </div>
  </div>
  <div class="card" style="margin-top:14px;border-left:4px solid #3b6fdd;">
    <b>🤖 AI 分支：`cli explore --ai`（AI 语义识别，需 DeepSeek key）</b>
    <p style="color:var(--muted);font-size:.9rem;margin-top:4px">给一句自然语言场景，AI 读场景 + probe 语义清单 + DOM 上下文 → 挑对控件 → 产出 <b>ElementMap</b>（步骤+语义引用），并默认<b>同步落 <span class="code-inline">cases/ai_*.json</span></b>（--no-cases 可关）。generate 会读它、优先消费 element_map 快照，AI 用例与手写用例走同一条确定性执行链路。<br>三道防假安全感闸：① <b>交付即验证</b>——落盘后默认 <span class="code-inline">--verify</span> 立刻试跑该用例，实测 PASSED 才算出活，FAILED 就 <b>❌ + exit 3</b>（日志 <span class="code-inline">output/verify/</span>）；② <b>AI 失败即报错退出（exit 2）</b>，绝不静默用 mock 顶替（mock 只在显式 --mock-fallback 出现且不入库）；③ 落盘前<b>用例质量校验</b>拦「断言=输入回显」与「断言=猜出来的运行时计数（共 N 条）」。<br>另有：DeepSeek function calling 有间歇性 JSON 抖动 → 内置退避重试（HYBRID_LLM_ATTEMPTS 默认 3）；<span class="code-inline">cli prune</span> 给快照做归档保留（各留最近 N 个）。<br><b>场景文件</b>：<span class="code-inline">--scenario-file</span> / <span class="code-inline">--scenario-dir</span> 直接读 <span class="code-inline">scenarios/*.yml</span>（一文件=一场景，含 business_context 领域知识 与 assert_guard 断言护栏），与内联 <span class="code-inline">--scenario</span> 共用同一条下游链路。</p>
  </div>
</section>

<!-- ========== 4. 函数调用关系 ========== -->
<section>
  <h2 class="sec-title"><span class="n">4</span>函数调用关系（代码地图）</h2>
  <p class="sec-sub">cli 是总入口：explore(AI 产用例) 的产物与手写用例一起，被 probe→generate→run 三步确定性链路消费。</p>
  <div class="tree">
<b>cli.py 入口</b>   (python -m framework.cli <b>all</b> --workers 2)
│
├── <b>cmd_probe</b>      → probe.probe_page()                    [✅ Playwright]
│       └─ _role_of / _accessible_name / _placeholder → 元素语义清单
│
├── <b>cmd_explore</b>    → explorer.ai_explore()                 [🤖 AI · 需 DeepSeek key]
│       ├─ 入口三选一(互斥): --scenario 内联 / --scenario-file / --scenario-dir
│       ├─ _explore_one(): 备好 url + page_bg + guard + case_id(取自 scenario id)
│       ├─ ai_explore(): ①同步探测(probe+弹窗二次probe+DOM上下文) ②异步 LLM 挑 semantic_name
│       │                 ③落盘 case_builder → cases/ai_*.json（expect_text → asserts[]）
│       └─ _verify_cases(): 立刻 generate + pytest 单跑 → FAILED 则 exit 3
│
├── <b>cmd_generate</b>   → generator.generate_scripts()         [✅ Playwright]
│       ├─ 读 cases/*.json（手搓用例 + AI 用例，同一套格式）
│       ├─ loc_map 来源优先级: element_map 快照(explore产物) &gt; probe 快照 &gt; 现场 probe
│       ├─ element(语义名) → _semantic_to_locator_expr: test_id &gt; role+name &gt; placeholder &gt; text
│       ├─ 映射不到 → 打印 ⚠️ 仍未映射；该步生成 pytest.fail（绝不静默跳过）
│       ├─ 按操作类型翻译 Playwright 代码（goto/click/fill/select/check/press_enter）
│       └─ 抽离字面值 → scripts/datasets/&lt;case_id&gt;.json（脚本⇄数据分离）
│
└── <b>cmd_run</b>        → pytest scripts/test_cases.py -n N     [✅ Playwright]
        ├─ conftest.page fixture：启动浏览器(headless开关)
        ├─ _data() 从 datasets 取运行时值 → data_driven 占位符替换+变量池
        └─ 每动作 resolve_locator(Tier1→Tier2) + ③意图复验 + web-first断言 + 逐用例日志

数据流： cases/用例(自然语言) ──probe映射+抽离──▶ scripts/(脚本+datasets数据) ──pytest──▶ 结果+报告
  </div>
  <p style="margin-top:10px;color:var(--muted);font-size:.92rem">
    ⭐ 留意 <b>generator</b>：它把「自然语言步骤」翻译成「确定性 Playwright 代码」——这是整个
        框架"AI 只理解、代码精确定位"的落脚点。另一个核心是 <b>locator_bridge</b>，它是「语义」和
        「Playwright 定位」之间的桥，也是防"点错元素"的闸门。
  </p>

  <h3 style="margin:26px 0 6px">🖼 图 A：两种场景的函数级调用链路（图形化总览）</h3>
  <p style="color:var(--muted);font-size:.92rem;margin-bottom:10px">
    两条泳道：<b>场景①</b>把自然语言变成用例（花 token）；<b>场景②</b>把用例变成脚本并执行（零 token）。
    中间的琥珀色<b>【汇合点】cases/*.json</b> 是两条链路唯一的接口 —— 这正是"AI 产的用例"和"你手搓的用例"能跑同一条执行链的原因。
  </p>
  {_svg_two_scenarios()}
  <p style="color:var(--muted);font-size:.88rem;margin-top:6px">
    图例：箭头 = 函数调用 / 数据传递方向（同一条泳道内**从左到右**推进，到行末**折回**继续，泳道之间**向下**交接）。
    ★ 关键：【汇合点】那根琥珀色箭头是两条链路唯一相接的地方。每条箭头传递的具体数据，见下方 <b>图 B</b> 的函数级明细。
  </p>
  <h3 style="margin:26px 0 6px">🔗 图 B：函数级明细（每个函数的入参 / 产物 / 判定）</h3>
  <p style="color:var(--muted);font-size:.92rem;margin-bottom:10px">
    上图是<b>模块级</b>地图；这一张按<b>两种场景</b>拆成两条函数级链路（每个方框都是真实函数，箭头标出「谁调谁 + 传了什么数据」），
    两条链路<b>在 cases/*.json 汇合</b>。场景②那一侧的四个阶段：<span class="badge" style="background:#0f8f6a">✅ 同步感知（Playwright）</span>
    <span class="badge" style="background:#3b6fdd">🤖 异步认知（AI）</span>
    <span class="badge" style="background:#8b5cf6">📦 落盘（确定性）</span>
    <span class="badge" style="background:#b45309">🧱 确定性翻译/执行</span>
  </p>
  <pre class="tree">
<b>两条链路的分工（一句话）</b>：场景① 负责"把自然语言变成用例"（花 token、有 AI）；场景② 负责"把用例变成脚本并执行"（零 token、纯确定性）。
             两条链路<b>在 cases/*.json 汇合</b> —— 场景①的产物就是场景②的输入，格式完全一致。

╔══════════════════════════════════════════════════════════════════════════════════════════════╗
║ 场景①  自然语言用例 → AI 语义识别/编排 → 输出测试用例到 cases/      入口: cli explore --ai    ║
╚══════════════════════════════════════════════════════════════════════════════════════════════╝
 <b>① 输入（自然语言）</b>
    内联  --scenario "在搜索框输入'1005'点搜索，确认出现 HT-1005"      ← 原样保留的临时用法
    文件  --scenario-file scenarios/contracts/contracts_search_by_no.yml   ← 场景库（可版本化）
    批量  --scenario-dir scenarios/ [--tag smoke] [--limit N]              ← 三者互斥，同时给则 exit 2
      └─ cli.py::main() → <b>cli.cmd_explore(rest)</b>
           ├─ scenario.<b>load_scenario_file()</b> / <b>discover_scenarios()</b>   解析+校验 → text/url/page_bg/guard
           └─ <b>cli._explore_one(text, url, page_bg, guard, case_id, extra)</b>
                 └─► explorer.<b>ai_explore(scenario, items=[], url, ...)</b>       ★CLI 自己不探测，只传参

 <b>② 感知阶段（同步 · 纯 Playwright · 0 token）</b>   explorer.<b>_collect_page_context()</b>
      sync_playwright().chromium.launch(browser.launch_opts()) → pg.goto(url) → networkidle
      ├─ base = probe.<b>probe_page(pg)</b>                              ◀◀ <b>probe 出场❶</b>（给 AI 看菜单）
      │      遍历可见交互元素 → 11 字段语义 + semantic_name（重名自动 _2/_3 ⇒ 名字唯一在此保证）
      ├─ modal = explorer.<b>_try_collect_modal_items(pg, base)</b>      点开"新建/添加"类按钮 → 再 probe
      │      → 第1层只留 test_id 以 inp-/sel-/btn-/modal 开头(弹窗表单字段)
      │      → 再往弹窗里嵌的层钻(≤2层, 如"选择客户"弹层) ⇒ 同名按钮按所在行命名 选择@&lt;客户名&gt;
      │      → 探完逐层关掉(页面恢复干净); 等待是<b>有界轮询</b>(探到就走, 最坏 2.5s)
      ├─ items = explorer.<b>_merge_items(base, modal)</b>               按 semantic_name 去重
      └─ dom_ctx = explorer.<b>_collect_dom_context(pg)</b>              idx/visible/disabled/readonly/aria_label

 <b>③ 认知阶段（异步 · AI · browser-use LLM · 花 token）</b>   explorer.<b>_ai_explore_async()</b>
      ├─ prompt = explorer.<b>_build_planner_prompt()</b>
      │      目标URL →「场景原话」→【页面背景 page/preconditions/business_context】
      │      →【断言护栏 assert_guard】→ 控件清单 items[:60] → DOM 上下文[:80] → 规则 1~8
      ├─ obj = framework/config.<b>llm_from_env()</b> → browser_use.llm.<b>ChatDeepSeek</b>
      ├─ 重试≤3: r = await obj.<b>ainvoke(msgs, output_format=_PlanModel)</b>   ◀ function calling 结构化步骤
      │      └─ explorer.<b>_plan_to_steps(plan, items)</b> → <b>_match_item()</b>
      │             ①精确 ②规范化唯一模糊对齐 ③都不中→打印告警+可用清单名（不静默丢元素）
      │             命中 → ElementRef（role/name/placeholder/test_id/nearby/heading，全部取自 probe）
      ├─ 兜底 explorer.<b>_get_llm_text_async()</b> + <b>_parse_steps_text()</b>（同样过 _match_item）
      ├─ 全失败 → AiExploreError ⇒ cli <b>exit 2</b>（拒绝产假用例；--mock-fallback 才降级且不入库）
      ├─ explorer.<b>_apply_semantic_calibration()</b>   AI 的 desc vs 元素语义 重叠 &lt;0.3 → 告警"疑似选错"
      └─ explorer.<b>_finalize_map()</b>  首步非 goto 自动补 goto → <b>ElementMap</b>（只含 semantic_name）

 <b>④ 落盘 + 交付即验证（确定性）</b>
      ├─ ElementMap.<b>to_json()</b> → output/element_maps/element_map_&lt;ts&gt;.json   （决策档案）
      ├─ case_builder.<b>elementmap_to_cases_file(emap, case_id, extra, guard)</b>
      │      step.action ──_OP_MAP──▶ cases.steps[].op（同名直映射）
      │      step(action=expect_text) ──_ASSERT_ACTIONS──▶ cases.asserts[].desc/expect
      │      step.element.semantic_name ─▶ cases.steps[].element      ★契约传递★
      │      elementmap_warnings() + case_warnings(case, guard)       落盘前质量校验（防假绿）
      │      → <b>cases/ai_&lt;scenario_id&gt;_&lt;HHMMSS&gt;.json</b>（含 source_scenario/scenario_id 溯源字段）
      └─ cli.<b>_verify_cases()</b>  立刻 generate 一次 + pytest 逐条单跑 → FAILED 则 ❌ <b>exit 3</b>

                                        │
                                        ▼   【汇合】cases/*.json —— 两条链路共同的接口（格式一模一样）
╔══════════════════════════════════════════════════════════════════════════════════════════════╗
║ 场景②  手搓 case.json → 生成 playwright 脚本 + 数据分离 → 执行    入口: cli generate / run   ║
╚══════════════════════════════════════════════════════════════════════════════════════════════╝
 <b>① 输入（手写用例）</b>
    cases/&lt;case_id&gt;.json   =  case_id / name / base_url / steps[op,desc,element,value,url] / asserts[kind?,desc,expect?,element|selector,name?]
                              （element 写 probe 的 semantic_name；value 可写 &#123;datetime&#125; 等占位符）
      └─ cli.py::main() → <b>cli.cmd_generate(rest)</b>
           └─► generator.<b>generate_scripts(cases_dir, element_map_path=None, live_probe=False)</b>

 <b>② 语义名 → 确定性 locator（probe 出场❷，三档命中即停）</b>
      ├─ Ⓐ generator.<b>_load_loc_map_from_element_map()</b>  读 element_map_*.json   ← 场景①那次 probe 的快照
      ├─ Ⓑ generator.<b>_load_loc_map_from_probe_snapshot()</b> 读 probe_*.json        ← cmd_probe 的快照
      ├─ Ⓒ 现场探测: pg.goto(TARGET_URL) → probe.<b>probe_page()</b>                    ◀◀ <b>probe 出场❷</b>
      │        仅在 Ⓐ/Ⓑ 都没命中时才做（含再次点开弹窗补表单字段）
      └─ 每个语义名 → generator.<b>_semantic_to_locator_expr(item)</b>
            test_id │ role+name │ placeholder │ text(exact) │ 上下文锚点 li filter has_text
            （只在生成期算一次；运行期不再探测 ⇒ 并发稳定、零 token）

 <b>③ 翻译 + 数据抽离（脚本 ⇄ 数据分离）</b>
      ├─ generator.<b>_render_pytest_case(case, loc_map)</b>  按 op 翻译 _act(page, "fill", semantic=…, value=_data(…))
      │      映射不到 → 打印「⚠️ 仍未映射 [...]」+ 该步生成 <b>pytest.fail</b>（绝不静默跳过）
      ├─ generator.<b>_extract_data(case)</b> → scripts/datasets/&lt;case_id&gt;.json   （fill_0/select_1/expect_0…）
      └─ generator.<b>_render_conftest()</b> → scripts/conftest.py（会话级浏览器池/数据注入/变量池/断言辅助/日志/自愈）
            产物: <b>scripts/test_cases.py（脚本） + scripts/datasets/*.json（数据）</b>

 <b>④ 执行（零 token、可进 CI）</b>
      └─ cli.py::main() → <b>cli.cmd_run(workers, headed, force)</b>
           ├─ limits.<b>safe_workers()</b>  按 MemAvailable 自动降并发（防 OOM 杀 hermes 网关）
           └─ subprocess: pytest scripts/test_cases.py -n N --html=log/&lt;run_id&gt;/report.html
                 conftest.page fixture → conftest.<b>_act()</b> → locator_bridge.<b>resolve_locator()</b>
                       Tier1 语义精确/唯一命中 → Tier2 指纹+上下文加权 → 意图复验
                       仍失败 → healer.<b>try_heal()</b>（业务后置断言兜底；判真 bug 绝不掩盖）

╔══ 两条链路共享的三样东西（看懂框架的关键）═══════════════════════════════════════════════════╗
║ 1) <b>probe.probe_page()</b>    出场❶ 给 AI 看菜单 ｜ 出场❷ 把语义名翻成 locator                  ║
║ 2) <b>semantic_name 契约</b>    probe 起名(唯一) → AI 引用 → cases[].element → generate 查 loc_map ║
║ 3) <b>执行层完全共用</b>        locator_bridge + healer + limits + conftest（AI 只决定"有没有用例"）║
╚══════════════════════════════════════════════════════════════════════════════════════════════╝
</pre></pre>

  <div class="card" style="margin-top:14px">
    <h4>这四段为什么这么分工（记住这 6 句，谁的责任就清楚了）</h4>
    <div class="pts">
      <div class="pt"><div class="ico">🧭</div><h4>① cli 只做入口与串联</h4>
        <p><span class="code-inline">cli</span> 不写业务：解析参数（三入口互斥）→ 备好场景/URL/护栏/用例名 →
           交给 <span class="code-inline">_explore_one</span>；最后负责「交付即验证」与归档清理。</p></div>
      <div class="pt"><div class="ico">👀</div><h4>② probe = 眼睛（感知，0 token）</h4>
        <p>只回答「页面上有哪些控件、它们各叫什么、怎么区分」。产 <b>semantic_name + 消歧上下文</b>；
           <b>不决策、不规划、不产 selector、判不了唯一性</b>（唯一性是执行期 locator_bridge 的事）。</p></div>
      <div class="pt"><div class="ico">🧠</div><h4>③ explorer = 大脑（认知，花 token）</h4>
        <p>只回答「这一步该动哪个控件、填什么、拿什么当断言」。它<b>必须</b>先让 probe 探两次（基础页 + 弹窗），
           否则看不到表单字段；拿到清单后交给 LLM 决策，再把名字对齐成 probe 的元素引用。</p></div>
      <div class="pt"><div class="ico">🤝</div><h4>④ 两者靠一个契约见面：semantic_name</h4>
        <p>probe 起名（保证唯一）→ AI 引用它 → 写进 cases 的 <span class="code-inline">element</span> →
           generate 拿它查 loc_map → 变成 locator。<b>selector 从头到尾不进 LLM</b>，这就是"AI 理解、代码定位"的落地方式。</p></div>
      <div class="pt"><div class="ico">🔁</div><h4>⑤ probe 出场两次、同名不同用途</h4>
        <p>explore 时（出场❶）是「给 AI 看菜单」；generate 时（出场❷）是「把名字翻译成 locator」。
           默认优先用 explore 留下的 <span class="code-inline">element_map</span> 快照，避免重复探测、
           也躲开"弹窗要打开/元素时序不稳"的坑。</p></div>
      <div class="pt"><div class="ico">🛡️</div><h4>⑥ 三道闸门挂在哪</h4>
        <p>防假 AI：<span class="code-inline">ai_explore</span> 拒绝 mock 冒充（exit 2）；
           防假绿：<span class="code-inline">case_warnings</span>（回显/计数/缺元素/护栏）+ generate 的未映射即 fail；
           交付即验证：<span class="code-inline">_verify_cases</span> 实测通过才算数（exit 3）。</p></div>
    </div>
  </div>

  <div class="card" style="margin-top:14px;border-left:4px solid #dc2626;">
    <b>⚠️ 读这张图时最容易踩的 4 个坑（都实测过）</b>
    <p style="color:var(--muted);font-size:.9rem;margin-top:6px">
      1. <b>同步/异步边界</b>：阶段A（Playwright 同步 API）<b>必须</b>在事件循环之外跑。写进 async 函数里会抛
         "Sync API inside the asyncio loop"，再被静默兜底 → 弹窗字段和 DOM 上下文全丢（曾长期如此）。<br>
      2. <b>别重复探测</b>：cli 探一次、ai_explore 内部再探一次 = 连开两个 Chromium，内存紧时第二个起不来。
         现在只由 ai_explore 探一次。<br>
      3. <b>element 必须写 probe 的 semantic_name</b>（不是人话名，如"搜索"→ 探测名可能带前后缀）。
         写错不会静默通过：generate 会告警并在脚本里 <span class="code-inline">pytest.fail</span>。<br>
      4. <b>快照会过期</b>：element_map / probe 快照是"某一次探测的固化"，页面改版后要用
         <span class="code-inline">--live-probe</span> 或重新 explore 刷新。
    </p>
  </div>
</section>

<!-- ========== 5. 关键设计图例说明 ========== -->
<section>
  <h2 class="sec-title"><span class="n">5</span>关键设计图例说明</h2>
  <p class="sec-sub">先看「端到端全链路主线」——这是新手理解框架的唯一主线；①②③是这条线上的三个关键细节。</p>

  <!-- 图例⓪：端到端全链路主线（新手必看） -->
  <div class="card" style="margin-bottom:16px;border-top:4px solid var(--brand);">
    <h4>图例⓪ 端到端全链路：从 DOM 树 → 语义识别 → locator → 脚本 → 执行 → 自愈</h4>
    <p style="color:var(--muted);font-size:.9rem">框架的一整条生命周期。记住：<b>Playwright 的 probe 负责"看"（确定性探测），LLM 负责"想"（语义识别/编排），Playwright 的 locator_bridge 负责"找和做"（定位+执行）；ElementMap 是"想"与"做"之间的翻译件。</b></p>
    <pre class="tree">【阶段1】probe 构建 DOM 树                        → output/element_maps/probe_*.json
    probe.probe_page() 扫页面可交互元素
    role/name/placeholder/test_id/nearby_text...
    └─ 产物: 元素语义清单(给 AI 和 Playwright 用的\"词汇表\")
             ▼
【阶段2】Browser Use 语义识别挑控件                → ElementMap(步骤+语义引用)
    explorer.ai_explore(自然语言场景 + DOM上下文)
    DeepSeek(ChatDeepSeek) 读场景+清单 → 挑对 semantic_name
    只引用语义名, 绝不产 selector(防AI编脆弱CSS)
    └─ 产物: ElementMap = 计划步骤 + 每个动作的\"元素语义引用\"
             ▼
【阶段3】生成 locator(分层解析)                    → locator_bridge.resolve_locator()
    semantic_name → 先试 Tier1(精确语义)  → get_by_test_id / get_by_role...
                   └─ Tier1 失败 → Tier2(指纹+语义上下文) 加权评分+唯一性
    唯一命中(count==1) 才采用; 否则诚实报错
    └─ 产物: 一条唯一、稳定的 Playwright locator
             ▼
【阶段4】生成 Playwright 脚本                      → scripts/test_cases.py + datasets/
    generator: 按操作类型(goto/click/fill/select/assert)翻译
    + 优先吃 element_map 快照建 semantic→locator 映射(缺项才现场 probe) + 抽离字面值
    └─ 产物: 确定性脚本(零token) + 脚本⇄数据分离
             ▼
【阶段5】脚本执行: Tier1 → Tier2 指纹兜底           → runner._run_step()
    每个动作先 resolve_locator(Tier1) → 命中唯一▶执行
                     └─ Tier1 败 → Tier2 指纹(上下文消歧+intent判别) ▶唯一▶执行
    web-first 断言(expect 自动重试) + trace
             ▼
【阶段6】定位失败时走 Healer 自愈闭环               → healer.try_heal()
    定位失败 → A级: 放宽阈值(×0.75/×0.6)重定位(确定性,无LLM)
            → B级: LLM 重猜(需key,可选)
    自愈后业务后置断言裁决: recovered / real_bug / failed
    └─ 产物: output/heals/*.md 可审diff(绝不静默改写)</pre>
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:10px;margin-top:10px;">
      <div style="border:1px solid var(--line);border-radius:8px;padding:10px;font-size:.88rem">
        <b>🧠 谁在"看和想"</b><br>probe(看DOM) + Browser Use/AI(理解意图、挑语义名)。
        AI 只干"聪明"的活——把自然语言翻译成语义引用。</div>
      <div style="border:1px solid var(--line);border-radius:8px;padding:10px;font-size:.88rem">
        <b>✅ 谁在"找和做"</b><br>locator_bridge(找) + runner(做)。纯 Playwright，零token、可回归、进CI。</div>
      <div style="border:1px solid var(--line);border-radius:8px;padding:10px;font-size:.88rem">
        <b>📄 谁在"翻译"</b><br>ElementMap。一份结构化契约，让 AI 的规划无缝交给 Playwright。</div>
    </div>
  </div>

  <!-- 图例A：locator 决策 -->
  <div class="card" style="margin-bottom:16px;">
    <h4>图例① 细节：locator 分层定位（阶段3/5 的展开）</h4>
    <p style="color:var(--muted);font-size:.9rem">拿到一个元素要定位时，从上往下试，<b>命中唯一(count()==1)</b> 才采用；找不到就降级/跳过，<b>绝不蒙一个可能点错的</b>。</p>
    <pre class="tree">元素 → <b>Tier1 精确匹配</b>(快) ──命中唯一?──▶ ✅ 用
│            ├─ data-testid(契约锚点)    │
│            ├─ role+name(用户语义)      │
│            └─ label/placeholder/text   │
│            ⚠️ Tier1 命中唯一后还要<b>意图复验</b>(方向③): 回读元素实际语义,
│               与 page_hint/semantic_name 比对(阈值0.15), 不符→降级下一策略
└─ 不唯一/找不到/复验不过 → <b>Tier2 指纹+语义上下文</b>(稳)
             ├─ nearby_text(所属单元文本)★价值最高
             ├─ container_heading(栏目标题)
             └─ help_text(帮助文本)  → 加权评分
       评分差距&gt;0.12(MINGAP)? ──▶ ✅ 唯一采用
       否则 ──▶ ❌ 诚实失败(防 false-heal)</pre>
    <p style="color:var(--muted);font-size:.88rem">同名元素(两个checkbox/多个删除)靠<b>语义上下文</b>消歧，如 <code>page.locator("li").filter(has_text="写周报").get_by_role("checkbox")</code>。方向③ 专防"AI 选对名字但命中的长像素/同名控件语义不符"。</p>
  </div>

  <!-- 图例B：成本分层 / 自愈 -->
  <div class="card" style="margin-bottom:16px;">
    <h4>图例② 细节：成本分层 + 自愈闭环（阶段6 的展开）</h4>
    <p style="color:var(--muted);font-size:.9rem">AI 只在<b>探索/规划</b>花钱；生成脚本后执行端<b>零 token</b>、可无限次进 CI。自愈只兜底 &lt;5% 的意外。</p>
    <pre class="tree">探索/规划(花钱,一次性)      生成脚本后(零token,可重复)
      🤖 AI 思考  ──▶  📄 ElementMap ── ▶  ✅ Playwright 执行
      每步1次推理      (契约翻译件)      精确定位/断言/回归

    <b>自愈 Healer(兜底)</b>
    定位失败 ──▶ A级: 放宽阈值(阈值×0.75 / MINGAP×0.6) 重定位
            ──▶ B级: LLM 重猜(需key) → 成功/记为真bug
    事件落盘 heals/*.md → 区分 <b>recovered</b>/<b>real_bug</b>/<b>failed</b></pre>
    <p style="color:var(--muted);font-size:.88rem">自愈是"给流程兜底"，不是"让它瞎猜"——定位不出就<b>报错</b>，绝不蒙。</p>
  </div>

  <!-- 图例C：数据流 -->
  <div class="card">
    <h4>图例③ 细节：cases 用例 → 脚本 + 数据抽离（阶段2/4 的展开）</h4>
    <p style="color:var(--muted);font-size:.9rem">你在 cases/ 写<b>自然语言用例</b>(写死数据)；generate 现场 probe、翻译成确定性代码、并把字面值<b>抽离</b>到 datasets/——脚本和数据分离，改数据不用改脚本。</p>
    <pre class="tree">cases/用例.json(手写,自然语言)
   ├── op=click/fill/select...         ← generate 按"操作类型"翻译
   ├── desc=自然语言描述               ← 给人读
   ├── element=探测语义名               ← generate 映射成确定性locator
   └── value/expect=写死数据            ← 抽离到 datasets/
             ▼
generate(element_map快照→缺项现场probe)
   ├── 语义名→ get_by_test_id(...) 确定性定位
   ├── 操作类型→ Playwright 代码
   └── 抽离字面值 → scripts/datasets/&lt;case_id&gt;.json  (脚本⇄数据分离)
             ▼
pytest 并发执行 → 逐用例 .log + report.html + 变量池(用例隔离)</pre>
    <p style="color:var(--muted);font-size:.88rem">动态占位符{{datetime}}/{{date}}/{{uuid}} 运行时解析固化——<b>填表名==断言名，反复重跑不重名</b>。</p>
  </div>
</section>

<!-- ========== 6. 关键设计要点 ========== -->
<section>
  <h2 class="sec-title"><span class="n">6</span>关键设计要点</h2>
  <p class="sec-sub">把这些记住，就看懂这套框架了。</p>
  <div class="pts">
    <div class="pt"><div class="ico">🧠</div><h4>① AI 只理解，不定位</h4>
      <p>绝不让 AI 写 <span class="code-inline">#mui-4821</span> 这类每次构建都在变的 ID。
         AI 只<b>引用语义</b>，定位交给代码。</p></div>
    <div class="pt"><div class="ico">🥇</div><h4>② locator 稳定性优先级</h4>
      <p><b>我们实现（Tier1 顺序）：</b>
         <span class="code-inline">data-testid</span> &gt;
         <span class="code-inline">role+name</span> &gt;
         <span class="code-inline">label</span> &gt;
         <span class="code-inline">placeholder</span> &gt;
         <span class="code-inline">text</span> &gt;
         <span class="code-inline">CSS/路径</span>（几乎不用）</p>
      <p><b>为什么 data-testid 置顶？</b>它是<b>契约锚点</b>——由团队约定保护"不随视觉/文案改版变"，
         确定性最强，是 locator 栈的<b>主路径</b>；自愈领域共识是让它当 Tier1，才能让自愈只在
         &lt;5% 的运行里触发。</p>
      <p><b>那 role 为什么仍第一重要？</b>它是<b>用户语义层</b>——可访问性对齐、开箱即用、
         无需被测应用埋点，是<b>没有 data-testid 时的首选</b>。</p>
      <p><b>一句话：</b>有 <span class="code-inline">data-testid</span> 用它（最稳）；
         没有就用 <span class="code-inline">role+name</span>（语义最稳）；
         CSS/路径永远最后（绑 DOM 结构，一改就断）。</p></div>
    <div class="pt"><div class="ico">🛡️</div><h4>③ 防"假通过"</h4>
      <p>每个 locator 必须 <span class="code-inline">count()==1</span> 唯一命中。
         歧义→降级更稳；找不到→跳过；全败→<b>报错，绝不蒙一个可能点错的</b>。</p></div>
    <div class="pt"><div class="ico">🧩</div><h4>④ 同名元素靠"语义上下文"消歧</h4>
      <p>列表/表格/卡片里常出现<b>同一 role+name 命中多个元素</b>（如两个 checkbox、多个"删除"按钮），
         单靠 <span class="code-inline">role+name</span> 无法区分。P4 起 <b>probe 会给每个元素</b>抓三类语义上下文：</p>
      <p><span class="code-inline">nearby_text</span>（所属逻辑单元关键文本，如该项"写周报"）价值最高；
         <span class="code-inline">container_heading</span>（所在栏目标题）次之；
         <span class="code-inline">help_text</span>（aria-describedby/title 帮助文本）兜底。</p>
      <p>定位时若 <b>nearby_text 能锚定唯一父单元</b>，就用
         <span class="code-inline">父单元含文本 → 取 role</span> 的过滤表达式唯一命中
         （如 <code>page.locator("li").filter(has_text="写周报").get_by_role("checkbox")</code>）；
         无上下文的裸元素<b>诚实失败、绝不瞎选</b>（防 false-heal 兜底）。</p></div>
    <div class="pt"><div class="ico">📄</div><h4>⑤ ElementMap 数据契约</h4>
      <p>AI 和 Playwright 之间用一份结构化"翻译件"传话（步骤+元素语义），
         换页面、换模型都不用改执行端。</p></div>
    <div class="pt"><div class="ico">💰</div><h4>⑥ 成本分层</h4>
      <p>AI 只在<b>探索/规划</b>阶段花钱（每步一次推理）；
         一旦生成脚本，执行端 <b>零 token</b>、可无限次进 CI 回归。</p></div>
    <div class="pt"><div class="ico">🧩</div><h4>⑦ cases 自然语言用例 → 脚本 + 数据抽离</h4>
      <p><b>你在 <span class="code-inline">cases/*.json</span> 写自然语言用例</b>（步骤用 op 操作类型 + desc 描述 + element 探测语义 + value 写死数据；断言用 asserts[] 数组，<b>11 种 kind</b>：文本 / 可见 / 隐藏 / 数量 / 属性 / 输入值 / URL / 勾选 / 未勾选 / 可用 / 禁用）。</p>
      <p>generate 读 cases → <b>优先 element_map 快照</b>（缺项才现场 probe）映射语义→确定性 locator → <b>按操作类型翻译 Playwright 代码</b> → 把字面值<b>抽离到 <span class="code-inline">scripts/datasets/&lt;case_id&gt;.json</span></b>，脚本仅留引用（<b>脚本数据分离</b>、解耦 demo）。</p>
      <p><b>动态占位符</b>：数据里写 <span class="code-inline">{{datetime}}</span>/<span class="code-inline">{{date}}</span>/<span class="code-inline">{{uuid}}</span> → 运行时解析固化（填表名==断言名，<b>反复重跑不重名</b>）。</p>
      <p><b>用例级变量池 <span class="code-inline">case.vars</span></b>：存运行过程数据（新建合同名/系统返回编号/抓取字段值），供检查点断言 + 后续操作输入，function-scope 隔离。</p>
      <p><b>检查点不依赖后端返回编号</b>：新建场景主检查点用「新建输入的合同名 + 各字段与输入一致」核验生成成功；系统返回编号仅作<b>增强项</b>条件回搜（无编号则跳过仍通过）。</p>
      <p><b>并发</b>用 pytest-xdist 多进程，<b>每个 worker（会话）只起一个 Chromium 并全程复用</b>（每条用例只新建 context+page，逐条 setup 0.57~0.66s → 0.04~0.06s）；<b>报告</b>用 pytest-html 自动生成执行统计。运行：<code>python -m framework.cli run --workers 2</code>（cli 会先做<b>资源预检</b>，内存不够自动降并发）。</p>
      <p><b>调试开关(<span class="code-inline">--debug</span>，别名 <span class="code-inline">--headed</span>)</b>：<b>布尔开关，默认关，只在调试时用</b>——开了就一句话「<b>我要看得见这次执行</b>」：单浏览器、顺序跑、动作放慢(默认 200ms)。<b>两种情况都不报错</b>：① <b>有图形显示</b> ⇒ <span class="code-inline">headless=False</span>，Chromium 窗口弹出，看它一步步执行到用例结束；② <b>没图形显示</b>(服务器) ⇒ 改成「<b>录下来给你看</b>」：视频 <span class="code-inline">log/&lt;run_id&gt;/videos/&lt;case_id&gt;.webm</span> + <b>逐步截图</b> <span class="code-inline">log/&lt;run_id&gt;/shots/&lt;case_id&gt;/01_*.png</span>(序号=执行顺序) + trace 交互回放。关着(默认)=无头并发跑、不录像不截图。<br>⚠️ 两个实测坑：① 调试模式<b>不能带 <span class="code-inline">-n</span></b>(<span class="code-inline">pytest -n 1</span> 也设 <span class="code-inline">PYTEST_XDIST_WORKER=gw0</span>，conftest 判「在 worker 里 ⇒ 无头」⇒ 旧版 <span class="code-inline">--headed</span> 是<b>空操作</b>)；② 录像 webm <b>必须等 <span class="code-inline">context.close()</span> 才落盘</b>(提前 save_as 只拿到 4KB 空壳，修后 152KB)。</p></div>
    <div class="pt"><div class="ico">🤖</div><h4>⑧ AI 语义识别 + 确定性执行（真 AI 链路）</h4>
      <p>用 <b>browser-use 0.13.10 原生 `ChatDeepSeek`</b>（OpenAI 兼容、走 function calling）读「自然语言场景 + probe 语义清单 + <b>DOM 上下文</b>」→ 产出轻量步骤 JSON：</p>
      <p>AI 只做<b>理解意图 + 从 probe 清单里挑控件</b>（引用 <span class="code-inline">semantic_name</span>，绝不产 selector）；精确定位/执行交给确定性 Playwright，两者靠 ElementMap 契约衔接。</p>
      <p><b>DOM 上下文增强</b>：`_collect_dom_context` 抓元素全局索引/可见性/状态/可访问名喂给 AI，让它更准判别"该选哪个控件"。</p>
      <p><b>弹窗/弹层探测</b>：`_try_collect_modal_items` 点开新建弹窗后继续<b>钻进它上面的弹层</b>（客户列表这类 picker）再 probe —— 同名按钮按所在行命名（<span class="code-inline">选择@北京华信科技有限公司</span>），探完逐层关掉、页面恢复干净；等待是<b>有界轮询</b>（探到就走，最坏 2.5s），不是固定 sleep。断言支持<b>子串匹配</b>。</p></div>
    <div class="pt"><div class="ico">🛡️</div><h4>⑨ AI 选错控件的双保险（方向① + 方向③）</h4>
      <p>AI 在复杂页面可能<b>选对"名字"但对错"控件"</b>（如把"合同名称输入框"选成"搜索框"）。两道防线拦截：</p>
      <p><b>①语义校准</b>（explorer `_apply_semantic_calibration`）：AI 挑完元素后，用其描述与元素语义做<b>字符级核心词重叠</b>，相似度&lt;0.3 打警告"疑似选错控件"。</p>
      <p><b>③Tier1 意图复验</b>（locator_bridge `_intent_verify`）：Tier1 命中唯一后<b>回读元素实际语义</b>与 `page_hint/semantic_name` 比对（阈值0.15），不符→降级到下一策略/Tier2。</p>
      <p>①②③ 与 Tier2 指纹、Healer 自愈构成<b>多层兜底</b>，把"AI 选错 → 框架点错"的概率压到最低。</p></div>
    <div class="pt"><div class="ico">🧯</div><h4>⑩ 资源安全：并发自动降级（低内存保命）</h4>
      <p>跑测试前先读 <span class="code-inline">/proc/meminfo</span> 的 <b>MemAvailable</b>，
         按 <b>cap = max(1, min((MemAvailable - 保留) / 每worker预算, CPU核数))</b> 裁定并发数，
         不够就<b>自动降级并打印理由</b>；也可用 <span class="code-inline">--force-workers</span> 覆盖。</p>
      <p><b>为什么必须有</b>：实测 1 个 headless Chromium 实例 ≈ <b>515MB</b>；在 1.87GB / 无 swap 的机器上
         强跑 2 并发 ⇒ 内核 <b>global OOM</b> ⇒ 渲染进程被杀（<code>Target crashed</code>），
         <b>连 Hermes 网关进程也被连带杀掉</b>。单 worker 则稳定 5/5 通过。</p>
      <p><b>参数集中</b>：<span class="code-inline">framework/browser.py</span> 是 Chromium 启动参数唯一来源
         （原先 8 处裸 launch 各写各的）；生成物 <span class="code-inline">scripts/conftest.py</span> 用<b>内联</b>方式带上参数，
         免得再依赖框架常量。<br>⚠️ 口径澄清：生成物<b>不是「拷到哪儿都能独立跑」</b> —— conftest 会
         <span class="code-inline">import framework.data_driven / framework.healer</span>，
         所以<b>要在项目内（或把 framework/ 一起带上）运行</b>。
         <b>诚实提示</b>：这组参数实测<b>不降 RSS</b>，解决的是稳定性/一致性；<b>真正保命的是并发降级</b>。</p>
      <p><b>日志 run-id 隔离</b>：每次运行的 <span class="code-inline">.log</span> / <span class="code-inline">report.html</span> / <span class="code-inline">traces/</span>
         落在 <span class="code-inline">log/&lt;run_id&gt;/</span>，重跑生成新目录、历史不被覆盖（原先追加模式会跨运行累积，704 行混在一起无法定位本次）。</p></div>
  </div>
</section>

<!-- ========== 6. 参考代码走读 ========== -->
<section>
  <h2 class="sec-title"><span class="n">7</span>参考代码走读（含核心标注）</h2>
  <p class="sec-sub">下面是框架所有源码。⭐高亮行是<b>重点</b>，配了白话讲解，从上往下读。</p>
{cards}
</section>

<!-- ========== 7. 常见坑 ========== -->
<section>
  <h2 class="sec-title"><span class="n">8</span>新同学最容易踩的坑</h2>
  <p class="sec-sub">这些坑都是真实踩过的，碰到先对应这里。</p>
  <div class="card">
    <div class="pit"><h4>坑1 · 把 locator 字符串丢给 page.locator()</h4>
      <p>拿到的是一条 <code>page.get_by_role(...)</code> 这类的<b>方法调用</b>，
         不能整串丢给 <code>page.locator()</code>——那会被当 CSS 解析，永远匹配 0 个。
         正确做法：直接调真实方法拿 <b>Locator 对象</b>再 count() 校验。</p></div>
    <div class="pit"><h4>坑2 · 让 AI 去"猜" selector</h4>
      <p>AI 一写就会吐出 <code>#mui-4821</code>、<code>div:nth-child(3)</code> 这种
         一改版就废的脆弱玩意。要让它<b>只引用 probe 探测出的语义小名</b>。</p></div>
    <div class="pit"><h4>坑3 · 忽视唯一性 = 埋下"假通过"</h4>
      <p>如果不清点命中了几个元素，点错了 Delete 还可能报绿——这是最危险的。
         务必 <code>count()==1</code> 才放心用。</p></div>
    <div class="pit"><h4>坑4 · 中文 placeholder / 中文字段</h4>
      <p>语义小名不要把中文干掉（否则全变成 <code>el</code>），保留中文才可读、
         才和页面能对上。生成文件名也要处理中文，别挤成一片下划线。</p></div>
    <div class="pit"><h4>坑5 · 被测应用的重启与端口</h4>
      <p>demo 用 <code>http.server</code> 时：要加 <code>allow_reuse_address</code>
         避免 TIME_WAIT 卡端口；根路径要指到目标页，否则会列出目录、probe 抓到的全是文件链接。
         （今天就跑通了这条路，没踩的注意。）</p></div>
    <div class="pit"><h4>坑6 · 编码：别依赖「系统默认编码」（中文 Windows 上必崩）</h4>
      <p>实测事故：<code>explore --ai</code>（默认带 <code>--verify</code>）在中文 Windows 上报
         <code>UnicodeDecodeError: 'gbk' codec can't decode byte 0xbb in position 13</code>
         ——用例和脚本都生成了，偏偏校验这一步炸。<b>根因</b>：收子进程输出时写了
         <code>subprocess.run(..., capture_output=True, text=True)</code> 却<b>没指定 encoding</b>，
         于是父进程按系统默认编码（cp936/gbk）去解码子进程的 <b>UTF-8 中文输出</b>。<br>
         <b>规矩</b>：跨进程 / 落盘文本一律显式 UTF-8——
         收子进程输出用 <code>framework.text_io.run_capture()</code>，
         给子进程注入口径用 <code>utf8_env()</code>，本进程 stdio 用 <code>force_stdio()</code>
         （<code>cli.main()</code> 已经默认调了）。<code>tests/test_utf8_io.py</code> 会做 AST 全仓扫描，
         再写出「靠默认编码」的写法直接测试失败。</p></div>
  </div>
</section>

<!-- ========== 8. 动手上手 ========== -->
<section>
  <h2 class="sec-title"><span class="n">9</span>动手跑一遍</h2>
  <p class="sec-sub">先起被测应用，再跑链路。没 key 也能玩 mock。</p>
  <div class="card">
    <pre class="cmd"><span class="prompt">$</span> cd ~/hybrid_gui_qa && source .venv/bin/activate
<span class="prompt">$</span> python -m demo.app            <span class="cmt"># 起被测合同管理页 (8000)</span>

<span class="prompt">$</span> python -m framework.cli probe          <span class="cmt"># ① 探测页面交互元素</span>
<span class="prompt">$</span> python -m framework.cli generate       <span class="cmt"># ② 读 cases/*.json → 生成 scripts/(脚本+数据抽离)</span>
<span class="prompt">$</span> python -m framework.cli run --workers 2 <span class="cmt"># ③ 并发执行 + 资源预检(内存不够自动降级)</span>

<span class="prompt">$</span> python -m framework.cli run --debug  <span class="cmt"># ③' 调试开关：有屏幕弹浏览器；没屏幕录视频(webm)+逐步截图</span>
<span class="prompt">$</span> python -m framework.cli run --debug --case search_mixed <span class="cmt"># ③'' 只调试一条（--case 可重复；不传=整包跑）</span>
<span class="prompt">$</span> python -m framework.cli run --debug --slowmo 500 --case search_mixed <span class="cmt"># ③''' 放慢 500ms/动作，肉眼跟步</span>
<span class="prompt">$</span> python -m framework.cli run --force-workers <span class="cmt"># ③'' 无视资源预检(有 OOM 风险,慎用)</span>

<span class="prompt">$</span> python -m framework.cli explore --ai --scenario "输入1005点搜索确认出现HT-1005"
                                              <span class="cmt"># ④ AI 语义识别 → cases/ai_*.json（默认 --verify 立刻试跑）</span>
<span class="prompt">$</span> python -m framework.cli prune --keep 20  <span class="cmt"># ⑤ 归档保留：快照各留最近 N 个</span></pre>
    <p style="margin-top:10px;color:var(--muted);font-size:.92rem">
      预期输出：<code>fill→在搜索框输入关键字</code>、<code>click→点击搜索按钮</code>、
      <code>断言→搜索完成 ✓ 全部通过</code>，<code>&lt;N&gt; passed</code>（<b>N 随 cases/ 里的用例数变化</b>，本文档写作时为 15 条：11 手写 + 4 AI），
      HTML 报告在 <code>log/&lt;run_id&gt;/report.html</code>（每次运行独立目录）。
    </p>
  </div>
</section>

<!-- ========== 9. 记住三点 ========== -->
<section>
  <h2 class="sec-title"><span class="n">10</span>收尾 · 记住这三点</h2>
  <div class="mem">
    <div class="mem-item a"><div class="big">🧠</div><b>AI 思考</b>
      <span>理解意图、规划步骤、挑元素——只干"智能"的活。</span></div>
    <div class="mem-item b"><div class="big">🎯</div><b>代码定位</b>
      <span>唯一性校验、精准执行、可复现回归——只干"确定"的活。</span></div>
    <div class="mem-item c"><div class="big">📄</div><b>契约连接</b>
      <span>ElementMap 一份翻译件，让 AI 的规划无缝交给 Playwright。</span></div>
  </div>
</section>

{_changelog_section()}

<footer>
  hybrid_gui_qa · AI 混合 GUI 测试框架培训页 · <b>V{VERSION}</b>（{VERSION_DATE}）· 由 build_html.py 生成
</footer>

</div>
</body>
</html>
"""


if __name__ == "__main__":
    html_str = build()
    OUT.write_text(html_str, encoding="utf-8")
    print(f"✓ 已生成 {OUT}")
    print(f"  大小: {len(html_str.encode('utf-8'))/1024:.1f} KB")
    print(f"  代码卡: {len(FILES)} 个文件")
