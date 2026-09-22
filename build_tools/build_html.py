# -*- coding: utf-8 -*-
"""构建培训 HTML：读取框架源码，注入模板，标注核心片段。运行: python build_tools/build_html.py
生成的 docs/training.html 是自包含单文件（内嵌 CSS），给新员工看。

⚠️ 本脚本住在 `build_tools/`（开发期工具目录，与 pack_release.py 同列）⇒ `BASE` 必须上溯一层。
"""
import html
import os
import re
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent      # build_tools/ 的上一层 = 仓库根
# 输出路径可用 BUILD_HTML_OUT 覆盖 —— 供「可复现性验证」在 /tmp 里生成、不污染仓库（tests/verify_html_sync.py）
OUT = Path(os.environ.get("BUILD_HTML_OUT") or (BASE / "docs" / "training.html"))

# ---------------- 轻量语法高亮 ----------------
# ⚠️ 必须是**单遍分词**（2026-09-19 重写）。老实现是三趟 re.sub 串起来跑，有三个真 bug：
#   ① 畸形嵌套：关键字那趟在**前一趟注入的 HTML 上**再跑，把 `<span class="k">` 里的 `class`
#      又包一层 → `<span <span class="k">class</span>="k">raise</span>`（已发布页实测 1520 处）；
#   ② 不可复现：KEYWORDS 是 set，`sorted(key=len)` 对**同长度**词按哈希序排，而哈希序每个进程
#      都不同 ⇒ 同一次提交重跑两次，html 的 md5 都不一样（实测差 140 行）⇒
#      「html 与代码是否同步」这条判据被废掉（重跑必出 diff，分不清同步还是没同步）；
#   ③ 字符串高亮早就死了：先 html.escape 把引号变成 &quot;/&#x27;，字符串正则 `['"][^'"]*['"]`
#      永远匹配不上（静默退化的功能）。
# 单遍分词三个一起修掉：注入的标签不再被扫；排序与哈希无关；先分词后转义 ⇒ 字符串真能高亮。
KEYWORDS = sorted({
    "def", "return", "if", "elif", "else", "for", "from", "import", "async",
    "await", "class", "with", "in", "not", "and", "or", "try", "except",
    "raise", "lambda", "pass", "yield", "None", "True", "False", "as", "global",
})
_KW_ALT = "|".join(KEYWORDS)
# 左起优先：`x = "a#b"` 走字符串（" 更靠左），`x = 1  # "q"` 走注释（# 更靠左）—— 正好都对
_TOKEN_RE = re.compile(
    r"(?P<comment>\#.*$)"
    r"|(?P<string>'[^']*'|\"[^\"]*\")"
    rf"|(?P<keyword>\b(?:{_KW_ALT})\b)"
)


def hl(line: str) -> str:
    """一行代码 → 高亮后的 HTML（单遍分词；注入的标签不会再被扫）。"""
    out, pos = [], 0
    for m in _TOKEN_RE.finditer(line):
        out.append(html.escape(line[pos:m.start()]))
        cls = {"comment": "c", "string": "s", "keyword": "k"}[m.lastgroup]
        out.append(f'<span class="{cls}">{html.escape(m.group(0))}</span>')
        pos = m.end()
    out.append(html.escape(line[pos:]))
    return "".join(out)




# ---------------- HTML 模板 ----------------

# r9-legacy-block:begin —— 版本史区（历史版本记录的旧路径 + 破坏性变更对照示例）
#   按 R9「搬家协议」口径：**冻结的历史记录原样保留、不回头改**（它们记录的是当时真实的路径）。
# ================= 版本与更新记录（单一来源：改版本只动这里）=================
VERSION = "8.2"
VERSION_DATE = "2026-09-22"
CHANGELOG = [
    dict(
        version="8.2", date="2026-09-22", tag="当前版本",
        theme="口径 C 对齐生产：<b>只有顶层容器才允许埋点</b>（页面与弹层同一口径）"
              "· 零 testid 下的定位与下钻",
        summary="把「埋点只顶层有」从<b>口头约定</b>变成<b>可执行判据</b>，并按这个口径改造 demo、"
                "补齐「没有埋点也能定位」的能力。演示站点撤掉 <b>115 处</b>控件级埋点（只留 "
                "<b>27 个顶层容器</b>），判据规则 <b>⑤⑥</b> 把「交互控件无论层级一律不许有 testid」"
                "和「弹层内部（非容器本身）一律不许」钉死；定位侧新增<b>字段步 / title 消歧 / "
                "元素身份</b>，让零 testid 下依然能唯一定位并下钻。<br>"
                "<b>这不是演示站点的洁癖，是生产口径对齐</b> —— 若两者口径不一致，框架在真实页面上的"
                "可用性、正确性、健壮性就都是空谈。",
        added=[
            "<b>判据规则 ⑤⑥</b>（<code>tests/testid_policy.py</code>）："
            "交互控件（<code>input/select/textarea/button/a/label/option</code>）<b>无论层级</b>一律不许有 "
            "<code>testid</code>；弹层<b>内部</b>（非容器本身）一律不许；<b>只有顶层容器</b>可保留埋点",
            "<b>字段步定位</b>：工具栏「…」按钮这类<b>无文本、无埋点</b>的入口，用「同容器内相邻字段"
            "（输入框/下拉）的语义」作为定位信号，并能<b>下钻</b>到目标控件",
            "<b><code>title</code> 消歧</b>：同名控件/裸图标按钮按 <code>title</code> 或邻近文本区分，"
            "歧义时<b>如实失败</b>（禁止按顺序猜第一个）",
            "<b>元素身份</b>= 容器锚点 + 相对路径 + <code>title</code>/邻近文本；新增 "
            "<code>framework/tools/probe/semantic_locate.py</code>（语义定位）",
            "<b>弹层收尾兜底</b> <code>_close_open_modal()</code>：框架自己开的弹层自己关，"
            "不让它挡住后续点击",
            "<b>二类预算与并发</b>：单脚本预算 600s→<b>1200s</b>（<code>--timeout-s</code> 可调；"
            "长用例此前是被预算杀掉的，不是断言失败）；新增 <code>--jobs N</code> 并发（默认 1 与原行为一致）"
            "—— <b>浏览器脚本必须过内存闸</b>（≥550MB × 已跑浏览器数，差一点绝不硬闯）、"
            "<b>独占屏障</b>（会重写共享产物的脚本独占，跑时谁也别起、要起时等场上清空）",
            "<b>产物质检</b>：<code>generate</code> 生成后<b>自洽闸</b>（引用了不存在的数据集 ⇒ "
            "抛 <code>DanglingDatasetError</code>、<b>拒绝落盘</b>）+ <b>陈旧数据集自愈</b>；"
            "二类 runner <b>每个脚本之间</b>做产物质检 ⇒ 弄脏产物的脚本<b>当场点名</b>；"
            "每个脚本的<b>完整日志落盘</b> <code>log/verify_logs/</code>（红项可自取证据）",
        ],
        changed=[
            "<b>demo 撤 115 处控件级埋点</b>：交互控件与弹层内部一律无 <code>testid</code>，"
            "只留 27 个顶层容器；<code>cases/</code> 里的 <code>data-testid</code> 残留 <b>归零</b>",
            "<b>用例对齐生产口径</b>：订单页采集 <b>96 → 140</b>（弹层 <b>0 → 61</b>），"
            "端到端 <b>19 passed / 0 failed</b>（189s，比改造前快一倍）",
            "文档同步（R8）：<code>README.md</code> 与培训页以<b>代码实现为基准</b>；"
            "「二类脚本个数」这类易腐数字改成<b>抗腐烂写法</b>（条数以 <code>--list</code> 输出为准，不写死）",
        ],
        fixed=[
            "<b>产物「悬空引用」窗口</b>：验证脚本临时写用例、归档后<b>没复原产物</b> ⇒ "
            "<code>scripts/test_cases.py</code> 留死引用 ⇒ 之后跑它的脚本全红，且报 "
            "<code>FileNotFoundError</code> + pytest 退出码 <b>2</b>（= 执行环境问题）"
            "⇒ <b>看着像「环境/偶发」</b>。现在四层设防（自愈 + 自洽闸 + 脚本间质检 + 一类缺口判据）",
            "<b>录像体检工具两个真 bug</b>：抠取正则非贪婪、遇场景内层引号提前截断 ⇒ 长场景"
            "永远误报「没录像」；覆盖判定严格相等 ⇒ 改「相等或完整包含」",
            "<b>负向判据不再「永远 SKIP」</b>：所有场景都有录像后，<code>e2e_scenario3</code> 的反例"
            "<b>自己造</b>（临时场景 + <code>try/finally</code> 零残渣），红线不再无人守",
            "并行模式引入的<b>写竞争假红</b>（<code>generate</code> 与并发脚本撞）⇒ 独占屏障修复",
            "新代码违反 <b>UTF-8 铁律</b>（<code>text=True</code> 跟随 locale，Windows 会炸）⇒ 显式 encoding，"
            "被一类当场抓出后修正",
        ],
        notes=[
            "<b>升级须知（口径）</b>：本版把「只有顶层容器才有 <code>testid</code>」写成<b>硬判据</b>。"
            "若你的页面里控件层仍带 <code>testid</code>，判据会<b>直接报违规</b> —— 这是<b>有意的</b>："
            "框架按生产口径校验，口径不一致时宁可报错，也不假装通过。",
            "<b>兼容性</b>：CLI 参数、用例格式、报告形态<b>零变化</b>；不带新开关时行为同旧版"
            "（<code>--jobs 1</code> = 改造前完全一致）。",
            "证据：一类 <b>421 passed / 0 red</b> · 二类 <b>16/16 全绿</b> · 端到端 <b>19/0</b> · "
            "<code>generate</code> <b>35/35 · 0 未映射</b>。",
        ],
    ),
    dict(
        version="8.1", date="2026-09-22", tag="上一版本",
        theme="归档保留策略（L5）：log/ 与 output/verify/ 不再只增不减 —— 分级清理，证据优先",
        summary="给两类「只增不减」的自动产物目录加保留策略：<b>保留最近 30 个 run ∪ 7 天</b>；"
                "超龄的 run <b>分两级</b>处理 —— 只有<b>能证明成功</b>的才整删，历史与失败<b>只瘦身</b>"
                "（删录像、留日志与报告）。CLI 参数 / 用例格式 / 报告形态<b>零变化</b>；"
                "不带 <code>--runs/--all</code> 时 <code>prune</code> 行为同旧版。",
        added=[
            "<b><code>summary.json</code></b>：<code>cli run</code> 收尾写进 run 目录"
            "（在退出码判断<b>之前</b>写 ⇒ 失败 run 也留证），记录 <code>exit_code</code> / 用例日志数 / "
            "失败数 / 录像体积 —— 归档策略据此判定「能否证明成功」",
            "<b><code>cli prune --runs|--all</code></b>："
            "<code>[--keep-runs 30] [--keep-days 7] [--max-delete 20] [--dry-run]</code>；"
            "环境变量 <code>HYBRID_KEEP_RUNS</code> / <code>HYBRID_KEEP_RUN_DAYS</code> / "
            "<code>HYBRID_MAX_DELETE_PER_PRUNE</code> / <code>HYBRID_MAX_FREE_MB</code> 可调",
            "<b><code>log/.protected_runs</code></b>：保护清单（每行一个 run_id + 理由）。"
            "框架只读仓库内文件（不读 skill 路径，守 R1）—— 台账/发行说明/交付邮件引用过的 run 登记在这里",
        ],
        changed=[
            "<b>两级处理</b>：超龄 run 里，<b>能证明成功</b>（有 <code>summary.json</code> 且全绿）⇒ 整目录删；"
            "<b>历史（无 summary）/ 失败</b> ⇒ 只瘦身（删 <code>traces/*.zip</code> 录像，"
            "保留 <code>.log</code> + <code>report.html</code> + <code>summary.json</code>）",
            "<b>保护规则（优先于任何旋钮）</b>：最近一次全绿 / 全红各保一个 · "
            "<code>.protected_runs</code> 登记过的完全不碰 · 不匹配 <code>YYYYMMDD_HHMMSS</code> 的命名一律不动"
            "（用户手工产物绝不误删）· <code>slowgate_*</code> 同口径",
            "<b>执行点</b>：<code>cli run</code> / <code>generate</code> 结束时自动清理（静默，无可清理不打印）；"
            "<code>HYBRID_NO_AUTO_PRUNE=1</code> 可整体关掉（排查现场时用）",
            "<b>安全默认</b>：单次删除上限 <b>20 个目录 / 100 MB</b>（防「策略写错、一夜清空」）· "
            "<code>--dry-run</code> 可预演 · 处置失败即停（fail-safe，不 fail-open）",
        ],
        notes=[
            "<b>兼容性</b>：零破坏。不带 <code>--runs/--all</code> 时 <code>prune</code> 行为与旧版一致"
            "（只清 <code>output/element_maps/</code> 快照）；旧 <code>--keep</code> 语义不变。",
            "<b>实测</b>：首次实际执行回收 <b>66.2 MB</b>（<code>log/</code> 213 MB → 146 MB："
            "瘦身 34 个 run / 281 个录像文件 + 清 45 个老 verify 日志；整删 0 —— 当时的 run 都是历史数据、"
            "不可证明成功，按保守口径只瘦身）。",
        ],
    ),
    dict(
        version="8.0", date="2026-09-21", tag="上一版本",
        theme="结构重构：framework/ 按业务流程分层（破坏性变更）· 开发期工具进 build_tools/",
        summary="本版<b>不加新能力</b>，只把 <code>framework/</code> 从「平铺 17 个模块」改成"
                "<b>按业务流程分层</b>，让目录结构自己讲清链路顺序（探测 → AI 识别 → 生成 → 执行）。"
                "CLI 参数 / 断言体系 / 报告形态 / 用例格式<b>零变化</b>。⚠️ <b>破坏性变更</b>："
                "模块 import 路径变了，且<b>不留兼容 shim</b>（升级请读下文「升级须知」）。",
        changed=[
            "<b>分层结构</b>：<code>framework/tools/{common,probe,explore,generate,run}/</code> —— "
            "<code>common</code>（config/text_io/limits/retention/browser/target_probe）· "
            "<code>probe</code>（probe/element_map/locator_bridge）· <code>explore</code>（explorer/llm_cassette）· "
            "<code>generate</code>（generator/case_builder/scenario/data_driven）· <code>run</code>（runner/healer）；"
            "<code>framework/</code> 只留 <code>cli.py</code> + <code>tools/</code>",
            "<b>导入路径变更（唯一破坏点）</b>：<code>from framework.probe import …</code> ⇒ "
            "<code>from framework.tools.probe.probe import …</code>（17 个模块同构映射）；"
            "<code>scripts/</code> 生成物已重建为新路径",
            "<b>开发期工具进 <code>build_tools/</code></b>（原仓库根 <code>tools/</code>）："
            "打包器 / 培训页生成器 / 离线一键脚本 —— 避免与运行期的 <code>framework/tools/</code> 混淆",
            "<b>依赖方向实测无环</b>：<code>common ← probe ← explore ← generate</code>、<code>common ← run</code>、"
            "<code>cli → 全部</code>（AST 扫描 + import 目标存在性校验，一次抓出所有漏改）",
            "版本号单一来源位置随之变为 <code>framework/tools/common/config.py::VERSION_SOURCE</code>"
            "（仍是<b>一处定义</b>，<code>cli</code> / <code>llm_cassette</code> / <code>pack_release</code> 共用）",
        ],
        fixed=[
            "<b>__file__ 层级推导随结构漂移</b>：<code>config.py::BASE</code> 原按 <code>parent.parent</code> "
            "推目录，模块挪深两层后会<b>静默指错</b>（不报错、只指到错地方）⇒ 改为「向上找 "
            "<code>pyproject.toml</code>」的标记法",
            "<b>体检脚本的版本探针漂移</b>（仓库外 <code>kickoff_check.sh</code>）："
            "<code>from framework.config import VERSION_SOURCE</code> 导入失败后<b>静默退回硬编码旧路径</b> ⇒ "
            "改为「取不到就如实报未验」并指向新模块路径",
            "<b>打包器审计历史包的误报</b>按「升级日志两种落点都认」的先例加<b>历史形态别名</b>"
            "（命中如实标 <code>◐</code>、不拦；真缺项仍照拦）",
        ],
        notes=[
            "判据：一类 <code>pytest tests/ -q</code> <b>238 passed</b>（与重构前逐条一致）· "
            "端到端 <code>cli run</code> 19 个节点<b>分批</b>跑 <b>19 passed / exit 0</b> · "
            "二类 <code>bash tests/run_verifications.sh</code> 全部 verify_*.py（条数以 <code>--list</code> 输出为准）· "
            "<code>build_tools/pack_release.py --with-cassettes</code> 打包自检通过",
            "⚠️ 本机内存红线（1.87G / 无 swap）：全量一次跑会触发 OOM（实测 Playwright 驱动崩溃 + 用例挂死），"
            "改用「每批 ≤5 条、独立进程、批间释放浏览器」；<b>SKIP 不等于通过</b>，内存不足要腾出来重跑",
            "<b>升级须知（v7.x → v8.0）</b>：① <code>cases/</code> / <code>scenarios/</code> / demo 一个字都不用改；"
            "② 自写的调试脚本若 <code>import framework.xxx</code>，按映射表改一行路径；"
            "③ 重跑 <code>python -m framework.cli generate</code> 重建 <code>scripts/</code>",
        ],
    ),
    dict(
        version="7.8", date="2026-09-21", tag="上一版本",
        theme="数据参数化「真展开」 · 一组数据 = 一条用例（L1）",
        summary="本版把<b>数据参数化</b>真正落地：场景 <code>data:</code> 里的一组数据会<b>展开成一条独立用例</b>"
                "（报告独立一行、失败能定位到具体数据集），不再是「只解析不展开」。写法沿用既有的占位符机制 —— "
                "文案里写 <code>{关键词}</code>、<code>data:</code> 里给几组值，写场景的人不用学新东西。",
        added=[
            "<b>一组数据 = 一条用例</b>：生成器对带 <code>data:</code> 的用例产出 "
            "<code>parametrize(indirect=True)</code>，报告里形如 <code>test_xxx[编号-1007]</code>，"
            "可按组单选（<code>-k \"&lt;case_id&gt; and &lt;组名&gt;\"</code>）",
            "<b>组名口径</b>：优先用组里的 <code>id</code>，其次取该组第一个占位符的值，最后回落 <code>ds1/ds2…</code>；"
            "重名自动加序号、去掉方括号等字符（否则报告里分不清哪组）",
            "两类判据：<code>tests/test_data_expand.py</code>（生成器契约，秒级 16 条）+ "
            "<code>tests/verify_data_expand.py</code>（端到端：3 组→3 passed · <b>坏组只红那一行</b> · 单组可跑），"
            "后者进 R7 统一入口",
            "<b>样板场景</b> <code>scenarios/contracts/contracts_search_by_no.yml</code> 改 3 组数据，照它写即可",
        ],
        changed=[
            "场景 <code>data</code> 字段从「二期 / 一期只解析不展开」变成<b>已支持</b>；"
            "<code>scenarios/README.md</code> 同步",
            "<code>scripts/datasets/&lt;cid&gt;.json</code>（基础数据）<b>格式不变</b>；多组另落 "
            "<code>&lt;cid&gt;.sets.json</code>（基础 ⊕ 组值）—— 所以没有 <code>data</code> 的既有用例"
            "产物<b>逐字节不变</b>",
            "<code>generate</code> 会<b>清扫过期</b>的 <code>.sets.json</code>（场景把 data 删了 / 用例删了 ⇒ "
            "旧组数据必须消失，否则用例会继续用上一版数据跑，属「改了没生效」的静默坑）",
            "用例条数基线随之变化：样板场景那条由 1 条变 3 条（17 → 19）",
        ],
        fixed=[
            "<b>描述里带 <code>{占位符}</code> 会把生成代码搞崩</b>：步骤描述被塞进生成代码的 f-string ⇒ "
            "运行时报 <code>NameError: name '关键词' is not defined</code>（实测踩到）。渲染时转义大括号、"
            "运行时还原成本文；不含花括号的描述转义前后一致 ⇒ 既有产物不受影响",
            "<b>参数名被 pytest 转义</b>：中文参数名默认变成 <code>[\u7f16\u53f7-1005]</code> ⇒ "
            "「失败定位到数据集」形同虚设。按 pytest 官方开关关掉 id 转义",
            "<b>两处「从节点名反解 case_id」都没考虑参数后缀</b>：<code>ctx</code> fixture（取数据集）与 "
            "<code>page</code> fixture（trace 文件名）用的都是 <code>re.search('test_(.+)')</code> ⇒ "
            "参数化后会把 <code>[组名]</code> 当成 case_id 的一部分。两处统一改 <code>re.match</code> 切后缀",
            "生成的测试文件<b>漏 import</b> <code>_ds_params/_ds_ids</code> ⇒ 收集期 NameError"
            "（正是既有判据 <code>test_artifacts_health</code> 盯的那类「模板渲染漏 import」）",
        ],
        notes=[
            "校验口径：组值**必须恰好覆盖**文案里用到的占位符 —— 少了 ⇒ 未解析的 <code>{xxx}</code> 会被"
            "原样填进页面（看着在跑、其实全错）；多了 ⇒ 写了不生效（静默误导）。两者都 "
            "<code>exit 2</code> + 人话点名是哪个键",
            "场景有 <code>data:</code> 但某条用例没用占位符 ⇒ <b>告警 + 不参数化</b>（不硬拦）："
            "避免误伤「一个场景 + 混合用例」的合理写法",
        ],
    ),
    dict(
        version="7.7.1", date="2026-09-19", tag="上一版本",
        theme="结构归一与修复批次 · tools/ 目录 · 版本来源收敛 · 文档可复现性",
        summary="本版<b>不加新能力</b>，只做三件事：把仓库结构按「框架代码 / 内部台账 / 门禁」三层分开；"
                "把散落在仓库根的工具收进 <code>tools/</code>，并把「版本号来源路径」收敛成<b>只定义一处</b>；"
                "修掉四处<b>静默退化</b>（培训页高亮器、打包审计、一条负向验证段、一条自测的环境依赖）—— "
                "共同特征是「看着正常、其实没在干活」，正是本项目一直在打的假绿。",
        fixed=[
            "<b>培训页生成器三处真 bug</b>（改单遍分词）：① 关键字趟在已注入的 HTML 上再跑 ⇒ "
            "把 <code>&lt;span class=\"k\"&gt;</code> 里的 <code>class</code> 又包一层，"
            "已发布页实测 <b>2381 处畸形嵌套</b>；② 关键字集合是 <code>set</code>，同长度词序由哈希决定 ⇒ "
            "<b>同一份代码重跑两次 md5 都不同</b>（差 140 行）⇒「html 与代码是否同步」根本没法用重跑比对判定；"
            "③ 先 <code>html.escape</code> 把引号变实体 ⇒ 字符串正则永远匹配不上，<b>字符串高亮一直是死的</b>",
            "<b>打包器审计历史包误报</b>：用当前必需项清单去审结构变更前的包会报「缺 build_tools/build_html.py / "
            "docs/training.html」—— 历史包按当时结构打包本就正常。按「升级日志两种落点都认」的先例加"
            "<b>历史形态别名</b>（命中时如实标出 <code>◐</code>、不拦），真缺项仍照拦",
            "<b>一条负向验证段自 V7.5.1 起就没跑起来</b>：负向用例故意用「不存在的控件名」，而映射质量闸会把"
            "整个 generate 拦成 exit 2 ⇒ 负向段一步没跑、脚本自己变红。负向段改走 <code>--allow-unmapped</code> "
            "并写明原因 ⇒ 修后<b>负向 15 条全部 FAILED</b>（预期）",
            "<b>一条自测的隐式环境依赖</b>：GBK 解码用例会先 generate ⇒ 本机恰好有 demo 时它就真去 probe"
            "（起浏览器），同一条用例 <b>1.16s → 162.71s</b>（占整套 93%，整包 13s → 175s）—— 等于二类"
            "（端到端）悄悄混进一类（秒级自测）。改为钉确定性不可达目标，并收紧判据（必须真解码到中文）",
        ],
        changed=[
            "<b>仓库结构三层分离</b>：框架代码在仓库；项目台账与设计文档移出仓库（住 skill）；"
            "仓库 <code>docs/</code> 现在<b>只放唯一的对外文档</b> <code>training.html</code>",
            "<b><code>tools/</code> = 框架自己的工具目录</b>：<code>build_html.py</code> 从仓库根挪入，"
            "与交付打包器 <code>pack_release.py</code> 同列；仓库根不再散放脚本",
            "<b>版本号来源路径收敛为一处</b>：<code>framework/tools/common/config.py::VERSION_SOURCE</code> —— "
            "<code>cli</code> / <code>llm_cassette</code> / <code>pack_release</code> 三个读者共用"
            "（原先三处各写一遍；漏改一处 <code>--version</code> 会静默变 unknown）",
            "README / 培训页 / 目录树同步，并把「逐条列文件名与数字」改成<b>抗腐烂写法</b>（减少文档漂移面）",
        ],
        added=[
            "<b>特性验证统一入口</b> <code>tests/run_verifications.sh</code>：逐个跑 "
            "<code>verify_*.py</code>、内存不足<b>如实 SKIP</b>（不硬跑、不当通过）、跑完出汇总表；"
            "支持 <code>--only</code> / <code>--list</code> / <code>--no-demo</code>",
            "<b>R8 判据</b> <code>tests/verify_html_sync.py</code>：培训页必须①可复现（换哈希种子 md5 相同）"
            "②与代码<b>逐字节一致</b>③零畸形嵌套 —— 把「文档与代码同步」变成可验证的",
            "判据补强：仓库与敏感词门禁<b>解耦</b>（仓库零引用门禁路径/词表）· <b>版本单一来源</b>"
            "（三读者同源，含「路径失效必须如实 unknown」负向）· 打包<b>历史形态</b>（含真缺项仍拦负向）· "
            "培训页高亮器 9 条（含跨进程可复现性）",
        ],
        notes=[
            "本版验证：一类框架自测 <b>217 passed</b>（有 demo / 无 demo 耗时一致）· 二类特性验证 "
            "<b>8/8</b>（0 跳过）· 敏感词门禁端到端 <b>28/28</b> · 推送闸门三层干净 + 对象对账 <b>330/330</b>",
            "敏感词门禁与词表住在 skill（<b>仓库内零痕迹</b>）：commit / push / 打包三层自动拦 + 自动修，"
            "钩子在 <code>.git/hooks/</code>（永不入库）",
        ],
    ),
    dict(
        version="7.7", date="2026-09-18", tag="上一版本",
        theme="元素歧义闸门（批次 2）· 弹层两种选中方式 · 离线 AI 链路（LLM 录像回放）",
        summary="本版两条主线。① 把「名字能对上就用」这条<b>静默点错控件</b>的路堵死 —— 事故形态是"
                "「同一个基础名落在两处、而探测是分轮做的」，复盘出四条路径（命名时机 / 合并去重 / "
                "留痕缺失 / 运行期模糊兜底），逐条按根因修，且都留下可复算的证据；"
                "② 让<b>连不上外网 LLM 的机器</b>也能跑完整 AI 链路：有网机器录一次「prompt → 回答」，"
                "离线机器回放，配一条命令脚本把链路与前置体检串起来。",
        added=[
            "<b>LLM 录像（录制/回放）</b>：<code>--llm-record</code> / <code>--llm-cassette</code> / "
            "<code>--llm-cassette-strict</code>，模式<b>只由 CLI 参数决定</b>、不做任何自动降级。"
            "两个键：<b>严格键</b>（prompt 逐字一致）+ <b>结构键</b>（场景文案 + 页面 + 控件骨架，"
            "刻意排除业务数据值）⇒ 数据不同的机器也能命中，但会<b>大声告警</b>"
            "「步骤是录制当时针对那批数据做的判断，请核对再用」；未命中给「最接近那份从第几行起不同」"
            "与两条出路，<b>绝不静默改走实时调用或 mock</b>",
            "<b>命名留痕</b>：<code>probe.assign_semantic_names()</code> 可重复调用，并留下 "
            "<code>base_name</code> / <code>ctx_token</code> / <code>name_source</code>"
            "（exact·ctx·seq·page）/ <code>base_conflict</code> ⇒ 下游能区分"
            "「本来就唯一」与「只是那一刻唯一」",
            "<b>一条命令脚本</b> <code>offline_explore_chain.py</code>（随录像包发）："
            "前置体检（代码是否含回放 / 录像份数 / demo 可达 / 依赖齐全）→ 回放识别 → generate → 试跑，"
            "全程把 LLM 端点指到黑洞 <code>127.0.0.1:9</code>，让「有没有偷偷联网」变成可证伪",
            "<b>合同页搜索区</b>改为「输入框 + 弹层按钮」，弹层选中与手工输入两种都支持"
            "（弹层选中 ⇒ 精确命中；手工输入 ⇒ 仍是右模糊，既有语义零破坏）；"
            "客户/销售员弹层内新增「+ 新建」叠层并回填当前字段",
        ],
        changed=[
            "<b>合并多轮探测后统一重命名</b>（S1）：<code>explorer._merge_items()</code> 改为"
            "「先按 test_id 去重 → 再在合并后的全量清单上重算命名」⇒ 同名控件不可能再被某一轮探测的"
            "裸名独占；<code>cli</code> / <code>explorer</code>（单页 + 跨页）/ <code>generator</code> 四处同源",
            "<b>映射质量闸的报错更有用</b>（S2）：缺失名若正是某个同名冲突组的 base 名，"
            "报错<b>直接给候选</b>（各自名字与定位），不再是一句干巴巴的「元素未映射」",
            "生成物 <code>_item_for()</code> 的模糊兜底收敛（S3）：候选唯一才接受并<b>写日志留痕</b>；"
            "候选 ≥2 <b>抛错并列候选</b>（含 test_id）；<code>HYBRID_STRICT_LOCATE=1</code> 连唯一候选也不兜",
            "跨页唯一化口径统一：<code>uniquify_across_pages</code> 也写 <code>name_source=page</code>",
            "README / 培训页 / <code>docs/P8-元素歧义闸门-方案.md</code> 同步本版两份改动",
        ],
        fixed=[
            "<b>静默点错控件</b>（本版主线）：同一基础名的两个控件分属<b>不同探测轮次</b>时，"
            "每轮都认为「只有我一个」⇒ 裸名被某一轮独占，用例引用裸名就落到<b>另一个</b>控件上；"
            "实测形态：搜索区按钮与弹窗按钮撞名 ⇒ 生成的 locator 指向被弹窗遮挡的那枚 ⇒ "
            "<code>Locator.click</code> 30 秒超时（demo 侧改名掩盖了症状，框架侧当时没修）",
            "<b>运行期模糊兜底会静默挑第一个</b>：<code>hint in k or k in hint</code> 命中多个时按 dict 顺序取，"
            "且零告警 ⇒ 语义名写错或过期时报的不是失败，而是操作到别的控件（点错还报绿）",
            "<b>录像与代码/demo 的版本配套</b>：回放键含控件骨架 ⇒ 改命名逻辑也会让整份录像失效"
            "（实测：45 个控件只差 1 个名字，结构键就对不上）⇒ 录像必须在最终版代码上录制，改动后重录重打包",
        ],
    ),
    dict(
        version="7.6", date="2026-09-18", tag="上一版",
        theme="跨 tab 端到端（订单场景）· 行内定位 · 首行断言 —— 并修掉两处「看着对、其实不在验」的缺陷",
        summary="本版主线：让框架能跑<b>真实的跨窗口业务流程</b>（点链接开新 tab → 在另一页填单 → "
                "回到原 tab），并把 AI 规划链路里两处<b>不会报错却会出错</b>的地方修掉。"
                "第一处（服务 ② AI 语义准）：同一个字段在<b>筛选区与弹窗里各有一个控件、名字却完全不同</b>时，"
                "AI 会把弹窗字段选成筛选区那个 —— 两个名字都能映射到真实控件，所以既没有「未映射」告警、"
                "也没有同名告警（实测连跑 6 次、6 次全错）。第二处（服务 ③ 稳定）：跨页重名原始名的告警按"
                "<b>全局并集</b>判定，会把别的用例带进来的重名算到本用例头上 ⇒ 两条手写跨页用例假红。",
        added=[
            "<b>跨 tab 能力</b>：探针新增 <code>opens_new_tab</code>（<code>_blank</code> / "
            "<code>window.open</code> ⇒ 点击会开新 tab，<b>不让 LLM 猜</b>）；动作新增 "
            "<code>click_new_tab</code> / <code>close_tab</code>，生成脚本里的 <code>_Tabs</code> 负责句柄切换，"
            "并<b>回读「真的关了没」</b>写进逐用例日志",
            "<b>行内定位</b>：<code>probe_row_fields()</code> 探出表格行内列清单（field/header），"
            "<code>TestStep</code> 增 <code>row_text</code> / <code>cell_field</code>，"
            "生成脚本用 <code>_click_row_cell()</code>「行锚文本 + 列字段」点到<b>运行时新建出来的那一行</b>"
            "（它的编号由服务端分配，语义清单里不可能有）",
            "<b>首行断言</b>：新断言 kind <code>first_row</code>（<code>row_field</code> + 期望值）→ "
            "<code>_assert_first_row()</code>。为什么单列一种 kind：文本断言只证明「页面上有这个名字」，"
            "<b>证明不了它就是第一条</b>，而「新建后列表第一条就是它」是需求原文",
            "<b>订单系统场景</b>：<code>scenarios/orders/orders_return_from_contract.yml</code>（3 页 / 30 步）"
            "+ AI 端到端产物 <code>cases/ai_orders_return_from_contract_*.json</code>",
            "<b>同字段·跨区域歧义披露</b>（<code>explorer._field_identity()</code> + "
            "<code>_same_field_pairs()</code>）：按 label 归一化（去 <code>*</code>、去结尾「（全模糊）」）找出"
            "「同一字段、不同区域、名字不同」的组合，<b>在提示词里显式列出</b>两个名字与各自区域，"
            "并加规则 2c 点明「选错不会报未映射、只会悄悄操作到别的控件」",
            "回归：<code>tests/test_name_alignment.py</code> 11 条（含「提示词里必须真出现这段披露」的"
            "<b>接线判据</b>，防止函数单测绿而功能没接上）",
        ],
        changed=[
            "<code>generate</code> 的跨页重名告警改为<b>按用例判定</b>：<code>_DUP_PAGES</code> 记「名字 → "
            "出现过的页集合」，判据 = 「<b>本用例声明的页 ∩ 该名字出现的页 ≥ 2</b>」；"
            "<code>_render_assert(..., dup_raw=…)</code> 按用例透传（防别的用例带进来的重名误伤）",
            "<code>cases/cross_page_detail.json</code> / <code>cases/ai_contracts_cross_page_011030.json</code> "
            "与订单场景并存时不再假红（用例本身一字未改，改的是判据口径）",
            "<code>docs/BACKLOG-下一步优化.md</code> 新增〇-f 批次记录（根因 / 修法 / 证据 / 内存纪律）",
        ],
        fixed=[
            "<b>AI 静默选错控件</b>（本轮最大收获）：弹窗字段 <code>请输入订单名称</code> 与筛选区 "
            "<code>订单名称_全模糊</code> 名字<b>完全不同</b> ⇒ 原「同名不同区域」告警报不出来；"
            "两者又都映射得到真实控件 ⇒ 不报「未映射」⇒ 用例一路跑到「提交后首行断言」才红。"
            "修法：把歧义<b>显式摊在提示词里</b>（清单 + 规则 2c）。证据：修后 AI 自动选对，"
            "<code>--verify</code> 实测 <b>PASSED</b>",
            "<b>跨页重名告警误伤别的用例</b>：全局并集判定 ⇒ <code>cli run</code> 15 passed / 2 failed；"
            "改为按用例判定后 <b>17 passed / exit 0</b>",
        ],
        notes=[
            "定位手法留档（比读日志猜快得多）：解失败那次的 <code>log/&lt;run&gt;/traces/&lt;case&gt;_trace.zip</code>，"
            "读 <code>trace.network</code> 的请求清单 —— 本次一眼看出<b>没有 POST /api/orders</b> ⇒ "
            "提交根本没发出 ⇒ 前端必填校验没过 ⇒ 弹窗字段没填进去",
            "本机内存红线重申：跑浏览器前先看 <code>MemAvailable</code>（编辑 .py 后会被拉起的语言服务占 ~350MB，先关掉）。"
            "实测 OOM 会<b>连杀 chrome-headless 与 hermes 进程</b>，现象是「CLI 自己退出了」",
            "回归口径：<code>pytest tests/ -q</code> <b>158 passed</b> · <code>cli run</code> "
            "<b>17 passed / exit 0</b> · <code>generate</code> 未映射 0",
        ],
    ),
    dict(
        version="7.5.3", date="2026-09-17", tag="上一版",
        theme="假绿治理：换页证据闸（弱 url 断言）· F5 断言稳健化 · 质量闸健壮性 · 负向验证段复活",
        summary="本版<b>全是「假绿」类缺陷的修复</b>（用例照绿、其实没验到东西）："
                "① AI 用 <code>expect_url = localhost</code> 当换页证据 —— 换页前后两个页面都含它，"
                "点击后立刻就能通过，<b>「确实换页了」这条关键证据悬空</b>，而根因是<b>提示词在教 AI 这么写</b>；"
                "② 质量闸自己遇到非字符串期望值（<code>count</code> 的 <code>20</code>）就<b>崩溃</b> —— "
                "守门人倒下等于这道栅栏不存在；③ 跨页用例里「列表恢复全量 20 行」这类<b>脆弱断言</b>"
                "（与要验的事无关，还会被本次运行新建的数据顶掉）；"
                "④ 一段负向验证<b>自 V7.5.1 起静默失效</b>（脚本 exit 2 看着像失败，其实是它自己没跑完）。",
        added=[
            "<b>换页证据红线闸</b>：<code>case_builder.case_errors()</code> 判定「换页证据必须只指向一页」——"
            "片段在用例声明的多页 URL 里都命中（典型 <code>localhost</code>），或跨页用例里只是 "
            "<code>host[:端口]</code> ⇒ <b>红线</b>；AI 落盘（<code>elementmap_to_cases_file</code>）与生成 "
            "（<code>generator._gate_false_green</code>）<b>两条路都 raise <code>CaseQualityError</code></b> ⇒ "
            "exit 2 + 人话（哪条用例、哪条断言、怎么改），<b>一个产物都不写</b>（口径同映射质量闸：产物永不允许带假绿）",
            "<b>AI 提示词补规则（真根因）</b>：换页证据只准用<b>只出现在目标页</b>的片段；"
            "点明<b>禁止</b> <code>localhost</code> / <code>localhost:8000</code> / <code>127.0.0.1</code> "
            "这类<b>每个页面都含</b>的片段；目标页没有独有片段（如列表页就是根路径 <code>/</code>）⇒ "
            "改用<b>该页独有文案</b>做 <code>text</code> 断言",
            "<code>tests/test_case_quality_gate.py</code>（13 条，秒级不需 demo）：11 种断言 kind × 7 种期望值形态 × "
            "4 种定位写法<b>都不许崩</b> · 弱证据必须被拦 · <b>真证据不许被误拦</b> · 仓库用例全量扫描无弱证据 · "
            "两条产物路径的红线行为",
        ],
        changed=[
            "<code>cases/ai_contracts_cross_page_011030.json</code>：「确认已回到列表页」的 "
            "<code>expect_url</code> 从 <code>localhost</code> 换成<b>列表页独有文案</b> <code>新建合同</code>"
            "（<code>text</code> 断言；列表页 URL 是根路径、没有独有片段）",
            "<b>F5 断言稳健化</b>：<code>cases/cross_page_detail.json</code> 的「列表恢复全量 20 行」"
            "（<code>count expect=20</code>）→「<b>预置基线行</b> <code>row-HT-1001</code> 在列表里」——"
            "与本次运行新建的数据无关，不会被顶掉，且「回到列表页」另有「新建合同按钮可见」作证",
            "<code>tests/verify_cross_page.py</code>：第二节新增「弱证据必被红线拦 + 真证据不许误拦」两条判据；"
            "负向段改走 <code>generate --allow-unmapped</code>（<b>并写清原因</b>：负向用例故意用不存在的元素名，"
            "映射质量闸会拦下整个 generate；产物只服务负向验证，收尾会重新生成干净产物）",
            "<code>docs/BACKLOG-下一步优化.md</code> 基线/队列同步 + 新增〇-e 批次记录；"
            "<code>docs/P3-跨页面流程-设计.md</code> 状态由「待确认」改为<b>「已实施」</b>；<code>build_html.py</code> 文案同步",
        ],
        fixed=[
            "<b>质量闸自身崩溃</b>（安静而致命）：<code>case_builder.case_warnings</code> 遇到非字符串期望值"
            "（<code>count</code> 的 <code>20</code>）直接 <code>TypeError: expected string or bytes-like "
            "object, got 'int'</code> —— 旧写法把期望值喂给正则与哈希集合比较，只按字符串设计 ⇒ "
            "文本形态检查<b>只对字符串生效</b>、「断言回显输入」比较<b>全程走字符串口径</b>。"
            "教训：<b>守门人也要有守门人</b>（该函数此前只在 AI 链路跑过，一碰到手写 11 类断言用例就倒）",
            "<b>负向验证段静默失效</b>：<code>tests/verify_cross_page.py</code> 的负向段<b>自 V7.5.1 起就没跑起来</b>"
            "（负向用例④故意用不存在的元素名 ⇒ 被映射质量闸拦成 exit 2 ⇒ 脚本 return 2，"
            "「N 条负向必须 FAILED」长期未执行）。修正后实测<b>5 条负向全部 FAILED</b>，"
            "含新增「没回到列表页时，列表页独有文案断言必须失败」—— 证明替换后的证据<b>真的有牙</b>。"
            "教训：<b>一段验证只要没人真跑它，就会静默退化；复核清单必须「真跑」，不是「它存在」</b>",
            "<b>host 判定误判</b>：用「像域名的正则」判 host 会把 <code>index.html</code> 也判成 host ⇒ "
            "改为两级判定：① 与已知页面 URL（<code>pages[].url</code> + <code>base_url</code>）的 "
            "<code>host[:端口]</code> / 裸主机名<b>精确比对</b>（主判据）；② 形态兜底只认「纯主机名或带端口」",
        ],
        notes=[
            "<b>自测与端到端证据（都真跑）</b>：<code>pytest tests/ -q</code> → <b>143 passed</b>"
            "（130 + 13 新增）；<code>cli generate</code> → exit 0 · 未映射 <b>0</b> 处 · <code>_goto</code> 接线 32 处；"
            "<code>cli run --workers 1</code> → <b>16 passed / exit 0</b>；<code>verify_cross_page.py</code> → "
            "<b>exit 0</b>（三节判据 + 5 条负向全 FAILED）；两条改后的断言在逐用例日志里<b>真实执行</b>（不再空验）",
            "<b>负向 CLI 证明</b>：喂一条 <code>expect = localhost</code> 的跨页用例 → <code>cli generate</code> "
            "<b>exit 2</b> + 人话，且产物 <code>sha256</code> <b>一字未改</b>（确实一个产物都没写）",
            "<b>不做（诚实清单，2026-09-17 裁定）</b>：CI 落点（需重建带 workflow 权限的 token）与 "
            "Windows 侧并发隔离证据（本地已有两条真跑 CLI 的行为测试）—— 均按拍板从队列删除；"
            "<b>变异注入闸门</b>（量「断言有没有牙」）仍待做，排在下一项",
            "V7.5.1 包（未发出的过渡版，已被 V7.5.2 收敛替代）已按授权删除，原 sha256 留在 "
            "<code>releases/SHA256SUMS.txt</code> 注释里备查",
        ],
    ),
    dict(
        version="7.5.2", date="2026-09-16", tag="上一版本",
        theme="脱敏收敛 · 交付包落库（仓库内 releases/）· 闸门可移植性",
        summary="本版是<b>对外交付与流程的收敛版</b>：清掉树内最后一处内部组织缩写、"
                "把交付包从 <code>/tmp</code> 搬进仓库内 <code>releases/</code>（并挡住它不进包）、"
                "把 pre-push 敏感信息闸门的环境依赖修好（原先在 <code>python3 = 3.6</code> 的机器上会误拦）。",
        added=[
            "<b>交付包落库到仓库内 <code>releases/</code></b>：<code>build_tools/pack_release.py</code> 的 "
            "<code>--out</code> 默认从 <code>/tmp/pkg</code> 改为 <code>&lt;仓库&gt;/releases</code> —— "
            "此前交付包是<b>唯一副本却躺在 <code>/tmp</code></b>（重启即可能丢），本版按根因修",
            "<code>.gitignore</code> 加 <code>/releases/</code>、<code>pack_release.py</code> 的 "
            "<code>EXCLUDE_DIRS</code> 加 <code>releases</code>：打包按「已跟踪 + 未跟踪但不被忽略」收文件，"
            "漏挡会把<b>发布包套进发布包</b>",
            "命名约定：<code>releases/hybrid_gui_qa_V&lt;版本&gt;_&lt;YYYYMMDD&gt;.zip</code> + <code>SHA256SUMS.txt</code>；"
            "历次交付记录放 <code>releases/</code> 下子目录",
        ],
        changed=[
            "<code>docs/BACKLOG-下一步优化.md</code>：交付物路径按新规矩改为 <code>releases/…</code>（原 <code>/tmp/pkg/…</code>）",
            "<code>.git/hooks/pre-push</code> 的扫描解释器不再写死 <code>python3</code>，改为探测 3.7+ —— "
            "旧写法在 <code>python3 = 3.6</code> 的机器上会让扫描脚本 <code>TypeError</code>，"
            "闸门把<b>环境问题误报成「有残留」而拦下推送</b>",
        ],
        fixed=[
            "<b>树内脱敏清零</b>：删掉文档里唯一一处内部组织缩写（三个字母的部门代码），"
            "换成不含敏感词的描述；复扫 HEAD tree = <b>0 命中</b>",
        ],
        notes=[
            "<b>对象级残留仍在（如实记档）</b>：2 个<b>已推送</b>历史里的旧 blob 仍含该缩写；"
            "彻底清零需重写历史 + 删仓重建（force-push 不足以让远端对象消失），单列一件事等定",
            "<b>自测证据</b>：<code>pytest tests/ -q</code> → 130 passed；<code>pack_release.py --check</code> 通过；"
            "复扫 tree 0 命中；<code>git ls-files … | grep -c '^releases/'</code> = 0（包库不进包）",
        ],
    ),
    dict(
        version="7.5.1", date="2026-09-15", tag="上一版本",
        theme="交付修复：映射质量闸 · 目标可达性预检 · 交付包自检 · 跨平台 UTF-8/GBK guard",
        summary="<b>V7.5 的交付包夹带了坏产物</b>：包里的 <code>scripts/test_cases.py</code> 含 "
                "<b>100 处「元素未映射」存根</b>（每个步骤都是 <code>pytest.fail</code>），"
                "导致 Windows 验收第 3 条「慢目标闸门」<b>5 failed / 1 passed</b>（真红，不是慢目标时序问题）。"
                "根因：<b>现场探测不可用时，<code>generate</code> 只打一句警告就照样落盘、而且 exit 0</b> ⇒ "
                "一份「看着合法、跑起来全失败」的产物被提交、被打包、被交付，真因无处可查。"
                "本版把它做成机制：<b>拿不到定位就不产出产物 · 交付前自检包内产物 · 环境问题说人话</b>。",
        added=[
            "<b>映射质量闸（根因修复）</b>：<code>generate</code> 算完定位映射后仍有语义名对不上 ⇒ "
            "抛 <code>UnmappedElementsError</code>、<b>一个文件都不写</b>、CLI <b>exit 2</b>，"
            "并打印「缺哪些 + 真因（可达性预检结论）+ 下一步」；"
            "调试逃生口 <code>--allow-unmapped</code>（显式声明才允许产出带存根的脚本，产物永不允许进交付）",
            "<b>目标可达性预检</b>：<code>target_probe.reachability()</code> 把「连不上（带『先起 demo』动作）」"
            "「有响应但无 <code>/api/health</code>（老目标，算活）」「可达」分开；"
            "<code>cli probe</code> 预检不过就 <b>exit 2 + 人话</b>，不再甩一屏 Playwright traceback"
            "（旧行为：<code>net::ERR_CONNECTION_REFUSED</code> 长栈 + exit 1，看着像框架坏了）",
            "<b>交付前自检</b>：① <code>tests/test_artifacts_health.py</code>（未映射=0 · 无裸 "
            "<code>page.goto</code> · conftest 接线齐 · cases↔datasets 一一对应 · scripts/ 无杂物）；"
            "② <code>build_tools/pack_release.py</code> 打包并用 <b>标准库 zipfile</b> 复扫包内产物，不达标就删包 + exit 2"
            "（它也用来审计历史包：拿它验 V7.5 那个包，当场抓出 100 处未映射）",
            "<code>tests/test_generate_quality_gate.py</code> · <code>tests/test_target_reachability.py</code> · "
            "<code>tests/test_pack_release.py</code>：三个「测试的测试」（不启浏览器、秒级）",
        ],
        changed=[
            "<b>跨平台 GBK guard</b>：旧判据用 POSIX 专有的 <code>locale -a</code>，Windows 上没有该命令 ⇒ "
            "三条 GBK 精确复现用例在<b>中文 Windows（事故原发环境）上永远跳过</b>；"
            "现在 Windows 分支读系统 ANSI 代码页（中文系统 = 936），断言放宽成「GBK 家族」",
            "<code>tests/verify_slow_target.py</code> · <code>tests/verify_picker_layer.py</code> 补 "
            "<code>force_stdio()</code>：中文 Windows 控制台上中文曾显示成乱码（UTF-8 字节被 cp936 解释）",
            "目标地址口径统一：<code>TARGET_URL</code> ⇄ <code>HYBRID_BASE_URL</code> 等效"
            "（以前只设后者会发现 probe 仍在打 <code>localhost:8000</code>）",
            "并发闸归因纠偏：<code>probe_partitioned</code> 不再把「目标连不上」说成「未声明可并发隔离」",
        ],
        fixed=[
            "交付物与仓库不一致：<code>scripts/test_cases.py</code> 的<b>坏产物</b>曾同时存在于 git 提交与交付包中；"
            "本版提交正确产物，并加了防复发闸门（见上）",
            "复检流程的<b>假绿</b>：<code>unzip</code> 未安装时 <code>unzip -p … | grep -c</code> 会把<b>空输入</b>"
            "数成 0 命中、被误读成「包是干净的」⇒ 一律改用标准库 <code>zipfile</code> 自检",
        ],
        notes=[
            "<b>验收基线要按平台念</b>：框架自测在本机（有 <code>zh_CN.gbk</code>）与受限环境下条数不同，"
            "差别就在那三条 GBK 复现用例；本版起 Windows 上不再跳过",
            "不可达的退出码 = <b>2</b>（与「参数/用法错误」同码，暂不新增独立码；CI 落点排期中）",
            "<b>自测证据（本机）</b>：<code>pytest tests/ -q</code> → <b>130 passed</b>；"
            "受限环境（无 <code>locale</code> / 无 <code>git</code>）→ 127 passed + 3 skipped；"
            "真实 CLI 反证：目标不可达时 <code>probe</code> 给人话 + exit 2、不启浏览器",
            "<b>⏳ 待办（未在 7.5.1 完成，如实记档）</b>：F5 —— <code>cases/cross_page_detail.json</code> 的"
            "「列表恢复全量 20 行」（<code>count expect=20</code>）还没换成与新增无关的基线断言。"
            "本条**需要被测目标在跑 + 真浏览器**才能改完并验证（本机内存不够、不硬跑），故排到下一版。",
        ],
    ),
    dict(
        version="7.5", date="2026-09-14", tag="已由 7.5.1 替换（交付包夹带坏产物）",
        theme="慢目标/并发下的假红治理：页面就绪契约 · 定位有界等待 · 报错纠偏 · 每 worker 数据分区 · 慢目标闸门",
        summary="团队演示事故：同一份代码 <code>run all</code> 红 4 条、<code>--debug</code> 全绿。"
                "本机用「每请求 +400ms 的反向代理」确定性复现（<b>5 failed / 1 passed</b>），定位到两条根因："
                "<b>①</b> 页面异步取数却没有「就绪契约」，<code>goto</code> 之后立刻动作/断言，"
                "在慢机器与高并发下必假红（还会抛出自相矛盾的误导性报错）；"
                "<b>②</b> 被测服务是单一有状态 store + 每用例全局复位 ⇒ 多 worker 下精确计数断言互相踩。"
                "本版把两者都做成机制：<b>契约（page-ready）· 有界等待（定位）· 真隔离（每 worker 数据分区）· 闸门（慢目标）</b>。",
        added=[
            "<b>页面就绪契约（F1）</b>：被测页面在 <code>body</code> 上静态声明 "
            "<code>data-hybrid-ready=&quot;0&quot;</code>、数据渲染完成后置 <code>&quot;1&quot;</code>；"
            "生成脚本的每个 goto 都走 <code>_goto()</code> → 自动等就绪"
            "（没有契约的老页面用 <code>HYBRID_READY_SELECTOR</code> 退化，或只提醒一次、不阻塞）",
            "<b>定位有界等待（F2）</b>：<code>_act</code> / <code>_resolve</code> 的确定性主定位改成"
            "「等到 attached 再数」（<code>HYBRID_LOCATE_TIMEOUT</code> 默认 5s），不再用瞬时 <code>count()</code> 判生死；"
            "<code>count</code> 这类复数断言仍**瞬时**判定（「期望 0 个」是合法用例，等它只会白等一个超时）",
            "<b>每 worker 数据分区（F6a）</b>：demo 的 <code>/api/*</code> 认 <code>?w=&lt;分区&gt;</code>，"
            "<code>/api/reset</code> 只清自己那份；conftest 给每个 worker 注入 <code>window.__HYBRID_W</code>，"
            "页面把它带进所有 API 调用 ⇒ 并发 worker 读写各自的数据，不再互相踩",
            "<b>并发安全闸（F6b）</b>：<code>cli run</code> 探测目标 <code>/api/health</code> 是否声明 "
            "<code>partitioned</code>，<b>未声明就保守降级为 1 并发</b>并说明原因；"
            "确知目标已隔离可用 <code>--isolated-target</code> 显式放行",
            "<b>慢目标闸门 <code>tests/verify_slow_target.py</code></b>：自起 demo + 慢代理，"
            "用同一批生成脚本指向代理跑关键用例，必须全绿；内存不足时明确 SKIP（exit 3），<b>不报假绿</b>",
            "<b><code>HYBRID_BASE_URL</code> 目标地址覆盖</b>：同一套用例可跑本机 / 慢代理 / 预发（闸门与多环境都靠它）",
            "<code>tests/test_ready_and_locate.py</code>：13 条契约锁（模板 ⇄ 生成物互锁 + CLI 降级行为实测，秒级不需浏览器）",
        ],
        changed=[
            "<b>报错信息纠偏（F3）</b>：<code>元素语义未找到</code> 现在给出「真因链 + 下一步」；"
            "原「断言 locator 失效且无语义兜底（该断言既没 selector 也没 element）」<b>自相矛盾</b>"
            "（那条断言其实有 selector）⇒ 改为「等了 N 秒仍是 0 个元素 + 常见原因 + 排查动作」",
            # ⚠️ 这里原本写着「F5 已把『列表恢复全量 20 行』改成基线断言」——**实测不成立**（2026-09-15）：
            #    cases/cross_page_detail.json 里那条 count expect=20 至今仍在。CHANGELOG 不许说假话，
            #    故删除该条，改记到 7.5.1 的 notes 里作为**待办**（需目标可用时改完并重跑 generate）。
        ],
        notes=[
            "<b>为什么本地一直没发现</b>：本机 <code>safe_workers()</code> 恒为 1（内存闸；1.87G 无 swap）⇒ 从未真正并发；"
            "且本机目标快（goto 返回时数据已渲染，窗口 ~0ms）。两个盲区叠加，才会出现「本地 16 条全绿、上演示就红」",
            "<b>Windows 侧并发预算</b>：<code>safe_workers()</code> 读 GlobalMemoryStatusEx，实测 16 核 / 14.9G 可用 ⇒ 16 worker",
            "验收基线（见 docs/P4-慢目标与并发-修复方案.md 与 BACKLOG）：慢目标闸门全绿 · 框架自测 · "
            "<code>cli all</code> 16 例 · Windows 上 <code>-n 16</code> 全量绿",
        ],
    ),
    dict(
        version="7.4.1", date="2026-09-14", tag="上一版本",
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
            "已知待办（诚实清单）：AI 给「返回列表」产的 url 断言只是 host（两页 URL 都含 ⇒ 等于没验换页）"
            "—— <b>2026-09-17 已修掉</b>：提示词禁止 host 片段 + 质量闸红线（拒绝落盘/生成）+ 用例改「目标页独有证据」；"
            "跨页流程 D1~D4（pages 声明 / 原地断言 <code>after_step</code> / 跨页重名消解 / 换页证据闸）已全部落地；"
            "场景 <code>data</code> 参数化仍只解析不展开",
            "文档口径修正：生成物 <code>scripts/conftest.py</code> 会 <code>import framework.tools.generate.data_driven / framework.tools.run.healer</code> ⇒ "
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
            "<b>framework/tools/common/text_io.py</b>：跨平台文本口径的唯一入口 —— `utf8_env()`（给子进程注入 "
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
            "<b>--version / -V</b>：版本号读 build_tools/build_html.py（版本单一来源；读不到就如实说 unknown）",
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
            "<b>cli prune</b> 归档保留策略（framework/tools/common/retention.py，HYBRID_KEEP_SNAPSHOTS 默认 20；explore/probe 结束自动静默执行）",
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
# r9-legacy-block:end

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
├── <b>framework/</b>                核心框架(V8.0: 只留入口 + 按业务流程分层的 tools/)
│   ├── cli.py                       ⚙️ 命令行入口(explore/probe/generate/run/all/prune)
│   └── tools/                       ★ 运行期模块(区别于开发期的 build_tools/)
│       ├── common/                   基建(零业务语义)
│       │   ├── config.py             配置+目录常量+LLM选择(含 VERSION_SOURCE)
│       │   ├── text_io.py            跨平台文本口径唯一入口(显式 UTF-8)
│       │   ├── browser.py            ⚙️ Chromium 启动参数唯一来源(不降 RSS,保稳定)
│       │   ├── limits.py             🧯 并发安全闸(按可用内存自动降级,防 OOM)
│       │   ├── retention.py          🗄 归档保留:快照各留最近 N 个(cli prune)
│       │   └── target_probe.py       目标可达性/并发安全预检
│       ├── probe/                    ① 探测与定位
│       │   ├── probe.py              ✅ [Playwright] 探测元素
│       │   ├── element_map.py        数据契约(ElementRef/TestStep/ElementMap)
│       │   └── locator_bridge.py     ✅ [Playwright] 语义→唯一locator(核心!)
│       ├── explore/                  ② AI 语义识别
│       │   ├── explorer.py           🤖 [AI] 语义识别(读场景→规划；失败即报错,不静默降级)
│       │   └── llm_cassette.py       LLM 录像/回放(离线机器:不联网、不需 key)
│       ├── generate/                 ③ 用例与脚本生成
│       │   ├── generator.py          ✅ 按操作类型翻译+抽离数据→scripts/
│       │   ├── case_builder.py       🤖 ElementMap→cases/ai_*.json 转换 + 用例质量校验(防假绿)
│       │   ├── scenario.py           🗂 scenarios/*.yml 解析/校验/发现(需 PyYAML)
│       │   └── data_driven.py        🧩 占位符替换+变量池+数据真展开
│       └── run/                      ④ 执行与自愈
│           ├── runner.py             ✅ ElementMap 场景执行引擎(集成自愈)
│           └── healer.py             🩹 自愈闭环(再协商+业务断言兜底+可审 diff)
├── <b>demo/</b>                      被测应用(靶子,8000端口)
│   ├── app.py                       静态页面 + 内存数据 API(客户/合同/复位;/api/*)
│   ├── contracts.html               合同管理系统页(列表/客户右模糊筛选/新建+客户弹层)
│   └── contract_detail.html         合同详情页(读同一条真实记录;查不到的编号如实报"未找到")
├── <b>tests/</b>                     框架自身的回归测试(不是被测应用用例)
│   ├── run_verifications.sh         二类验证统一入口(逐个跑 verify_*.py + 汇总表 + 内存闸)
│   ├── test_*.py                    一类自测(秒级,不需 demo):CLI 契约 / UTF-8 / 断言翻译 / 质量闸 / 打包 / 门禁解耦
│   └── verify_*.py                  二类验证(需 demo,含负向证伪):断言正负向 / 跨页 / 弹层 / 元素歧义 / 订单 / 慢目标 / 培训页同步
├── <b>output/</b>                    ✅ 运行时证据(probe/plan/heal/trace,可清)
├── <b>log/&lt;run_id&gt;/</b>             本次运行 逐用例 .log + report.html + traces(可清)
├── README.md                       本框架文档
├── <b>build_tools/</b>               ★ 开发期工具(不属于被测应用,也不进运行链)
│   ├── pack_release.py             交付打包器: 组装 zip + 标准库自检包内产物(不达标不出包)
│   ├── build_html.py               生成 docs/training.html 培训页(**版本号单一来源**)
│   └── offline_explore_chain.py    离线一条命令: 录像回放 → generate → 试跑(无外网机器用)
└── docs/training.html              ★ 这份培训文档（docs/ 里唯一的对外文档）</pre>
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
      ├─ obj = framework/tools/common/config.<b>llm_from_env()</b> → browser_use.llm.<b>ChatDeepSeek</b>
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

<!-- ========== 5. 关键设计图例说明（含「设计要点」，2026-09-22 与「关键设计要点」合并） ========== -->
<section>
  <h2 class="sec-title"><span class="n">5</span>关键设计图例说明</h2>
  <p class="sec-sub">先看「端到端全链路主线」——这是新手理解框架的唯一主线；①②③ 是这条线上的三个关键细节。<b>每个图例下面挂着它对应的「设计要点」</b>（原来是单独一章的《关键设计要点》，现已并入本章，避免同一件事讲两遍）。</p>

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

    <!-- ⬇ 并入的设计要点（原《关键设计要点》①②⑤⑥） -->
    <div style="margin-top:14px;border-top:1px dashed var(--line);padding-top:12px">
      <p style="font-weight:600;margin-bottom:8px">📌 本图例对应的设计要点</p>
      <div style="border-left:3px solid var(--brand);padding-left:10px;margin-bottom:10px">
        <b>① AI 只理解，不定位</b>
        <p style="color:var(--muted);font-size:.9rem;margin:4px 0 0">绝不让 AI 写 <span class="code-inline">#mui-4821</span> 这类每次构建都在变的 ID。AI 只<b>引用语义</b>，定位交给代码。</p>
      </div>
      <div style="border-left:3px solid var(--brand);padding-left:10px;margin-bottom:10px">
        <b>⑤ ElementMap 数据契约</b>
        <p style="color:var(--muted);font-size:.9rem;margin:4px 0 0">AI 和 Playwright 之间用一份结构化"翻译件"传话（步骤+元素语义），换页面、换模型都不用改执行端。</p>
      </div>
      <div style="border-left:3px solid var(--brand);padding-left:10px">
        <b>⑥ 成本分层</b>
        <p style="color:var(--muted);font-size:.9rem;margin:4px 0 0">AI 只在<b>探索/规划</b>阶段花钱（每步一次推理）；一旦生成脚本，执行端 <b>零 token</b>、可无限次进 CI 回归。</p>
      </div>
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

    <!-- ⬇ 并入的设计要点（原《关键设计要点》②③④） -->
    <div style="margin-top:14px;border-top:1px dashed var(--line);padding-top:12px">
      <p style="font-weight:600;margin-bottom:8px">📌 本图例对应的设计要点</p>
      <div style="border-left:3px solid var(--brand);padding-left:10px;margin-bottom:10px">
        <b>② locator 稳定性优先级</b>
        <p style="color:var(--muted);font-size:.9rem;margin:4px 0 0"><b>我们实现（Tier1 顺序）：</b>
           <span class="code-inline">data-testid</span> &gt;
           <span class="code-inline">role+name</span> &gt;
           <span class="code-inline">label</span> &gt;
           <span class="code-inline">placeholder</span> &gt;
           <span class="code-inline">text</span> &gt;
           <span class="code-inline">CSS/路径</span>（几乎不用）</p>
        <p style="color:var(--muted);font-size:.9rem;margin:6px 0 0"><b>为什么 data-testid 置顶？</b>它是<b>契约锚点</b>——由团队约定保护"不随视觉/文案改版变"，确定性最强，是 locator 栈的<b>主路径</b>；自愈领域共识是让它当 Tier1，才能让自愈只在 &lt;5% 的运行里触发。</p>
        <p style="color:var(--muted);font-size:.9rem;margin:6px 0 0"><b>那 role 为什么仍第一重要？</b>它是<b>用户语义层</b>——可访问性对齐、开箱即用、无需被测应用埋点，是<b>没有 data-testid 时的首选</b>。</p>
        <p style="color:var(--muted);font-size:.9rem;margin:6px 0 0"><b>一句话：</b>有 <span class="code-inline">data-testid</span> 用它（最稳）；没有就用 <span class="code-inline">role+name</span>（语义最稳）；CSS/路径永远最后（绑 DOM 结构，一改就断）。</p>
      </div>
      <div style="border-left:3px solid var(--brand);padding-left:10px;margin-bottom:10px">
        <b>③ 防"假通过"</b>
        <p style="color:var(--muted);font-size:.9rem;margin:4px 0 0">每个 locator 必须 <span class="code-inline">count()==1</span> 唯一命中。歧义→降级更稳；找不到→跳过；全败→<b>报错，绝不蒙一个可能点错的</b>。</p>
      </div>
      <div style="border-left:3px solid var(--brand);padding-left:10px">
        <b>④ 同名元素靠"语义上下文"消歧</b>
        <p style="color:var(--muted);font-size:.9rem;margin:4px 0 0">列表/表格/卡片里常出现<b>同一 role+name 命中多个元素</b>（如两个 checkbox、多个"删除"按钮），单靠 <span class="code-inline">role+name</span> 无法区分。probe 会给每个元素抓三类语义上下文：<span class="code-inline">nearby_text</span>（所属逻辑单元关键文本，如该项"写周报"）价值最高；<span class="code-inline">container_heading</span>（所在栏目标题）次之；<span class="code-inline">help_text</span>（aria-describedby/title 帮助文本）兜底。</p>
        <p style="color:var(--muted);font-size:.9rem;margin:6px 0 0">定位时若 <b>nearby_text 能锚定唯一父单元</b>，就用 <span class="code-inline">父单元含文本 → 取 role</span> 的过滤表达式唯一命中（如 <code>page.locator("li").filter(has_text="写周报").get_by_role("checkbox")</code>）；无上下文的裸元素<b>诚实失败、绝不瞎选</b>（防 false-heal 兜底）。</p>
      </div>
    </div>
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

    <!-- ⬇ 并入的设计要点（原《关键设计要点》⑨ 的双保险 + 自愈定位） -->
    <div style="margin-top:14px;border-top:1px dashed var(--line);padding-top:12px">
      <p style="font-weight:600;margin-bottom:8px">📌 本图例对应的设计要点</p>
      <div style="border-left:3px solid var(--brand);padding-left:10px">
        <b>自愈的边界：兜底 ≠ 猜</b>
        <p style="color:var(--muted);font-size:.9rem;margin:4px 0 0">A 级只<b>放宽阈值</b>（确定性、无 LLM）重定位；B 级才请 LLM 重猜（需 key）。每次自愈都落 <span class="code-inline">output/heals/*.md</span> 成为<b>可审 diff</b>，并用业务后置断言裁决成 <b>recovered / real_bug / failed</b> 三态 —— <b>绝不静默改写脚本</b>。自愈率越高越要警惕：它可能掩盖真实缺陷。</p>
      </div>
    </div>
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

    <!-- ⬇ 并入的设计要点（原《关键设计要点》⑦） -->
    <div style="margin-top:14px;border-top:1px dashed var(--line);padding-top:12px">
      <p style="font-weight:600;margin-bottom:8px">📌 本图例对应的设计要点</p>
      <div style="border-left:3px solid var(--brand);padding-left:10px">
        <b>⑦ cases 自然语言用例 → 脚本 + 数据抽离</b>
        <p style="color:var(--muted);font-size:.9rem;margin:4px 0 0"><b>你在 <span class="code-inline">cases/*.json</span> 写自然语言用例</b>（步骤用 op 操作类型 + desc 描述 + element 探测语义 + value 写死数据；断言用 asserts[] 数组，<b>11 种 kind</b>：文本 / 可见 / 隐藏 / 数量 / 属性 / 输入值 / URL / 勾选 / 未勾选 / 可用 / 禁用）。</p>
        <p style="color:var(--muted);font-size:.9rem;margin:6px 0 0">generate 读 cases → <b>优先 element_map 快照</b>（缺项才现场 probe）映射语义→确定性 locator → <b>按操作类型翻译 Playwright 代码</b> → 把字面值<b>抽离到 <span class="code-inline">scripts/datasets/&lt;case_id&gt;.json</span></b>，脚本仅留引用（<b>脚本数据分离</b>、解耦 demo）。</p>
        <p style="color:var(--muted);font-size:.9rem;margin:6px 0 0"><b>动态占位符</b>：数据里写 <span class="code-inline">{{datetime}}</span>/<span class="code-inline">{{date}}</span>/<span class="code-inline">{{uuid}}</span> → 运行时解析固化（填表名==断言名，<b>反复重跑不重名</b>）。</p>
        <p style="color:var(--muted);font-size:.9rem;margin:6px 0 0"><b>用例级变量池 <span class="code-inline">case.vars</span></b>：存运行过程数据（新建合同名/系统返回编号/抓取字段值），供检查点断言 + 后续操作输入，function-scope 隔离。</p>
        <p style="color:var(--muted);font-size:.9rem;margin:6px 0 0"><b>检查点不依赖后端返回编号</b>：新建场景主检查点用「新建输入的合同名 + 各字段与输入一致」核验生成成功；系统返回编号仅作<b>增强项</b>条件回搜（无编号则跳过仍通过）。</p>
        <p style="color:var(--muted);font-size:.9rem;margin:6px 0 0"><b>并发</b>用 pytest-xdist 多进程，<b>每个 worker（会话）只起一个 Chromium 并全程复用</b>（每条用例只新建 context+page，逐条 setup 0.57~0.66s → 0.04~0.06s）；<b>报告</b>用 pytest-html 自动生成执行统计。运行：<code>python -m framework.cli run --workers 2</code>（cli 会先做<b>资源预检</b>，内存不够自动降并发）。</p>
      </div>
    </div>
  </div>
</section>

<!-- ========== 6. 框架特性设计实现说明（2026-09-22 新增） ========== -->
<section>
  <h2 class="sec-title"><span class="n">6</span>框架特性设计实现说明</h2>
  <p class="sec-sub">上面第 5 章讲的是「一条主线上有什么」；本章按<b>特性</b>横向讲清楚：每个特性 = <b>定位一句话 → 关键设计 → 实现图例 → 怎么用 → 测试验证用例设计</b>。新手按特性读一遍，既能看懂框架结构，也知道每个特性<b>拿什么证据证明它是好的</b>。</p>

  <div class="card" style="border-left:4px solid var(--brand);margin-bottom:18px">
    <h4>先看全局：验证资产总览（真值，随代码增长）</h4>
    <pre class="tree">一类「框架自测」  tests/test_*.py      24 个文件 / 337 条 —— 秒级、<b>不依赖 demo 与浏览器</b>、可离线跑
二类「特性自测」  tests/verify_*.py    15 个脚本 —— 端到端、<b>需 demo</b>、<b>必含负向证伪</b>
E2E 三场景        场景1 自然语言→AI 链路（离线回放可证伪）· 场景2 手写用例驱动 · 场景3 录制回放验证
统一入口          python tests/run_acceptance.py     ← R7 四项一条命令（便宜先跑 + fail fast；SKIP ≠ 通过）
                  python tests/run_verifications.py  ← 二类全量（唯一实现；内存不足如实 SKIP 并 exit 3）</pre>
    <p style="color:var(--muted);font-size:.88rem;margin-top:8px">下面每个特性都会列出<b>它自己的</b>判据文件与条数；条数以实跑输出为准（<code>pytest tests/ -q</code>、<code>run_acceptance.py</code>）。</p>
  </div>

  <!-- ============ 特性 1 ============ -->
  <div class="card" style="border-left:4px solid var(--brand);margin-bottom:18px">
    <h4>特性 1 · 混合链路：AI 探索 + 确定性执行</h4>
    <p style="color:var(--muted);font-size:.92rem"><b>定位：</b>把「想」和「做」拆开——AI 只负责把自然语言翻译成语义引用（花钱、一次性），确定性代码负责定位与执行（零 token、可无限回归）。</p>
    <p><b>关键设计</b></p>
    <ul style="margin-left:18px;font-size:.92rem;line-height:1.8">
      <li><b>两条业务链路在 <span class="code-inline">cases/*.json</span> 汇合</b>：① 自然语言 → <span class="code-inline">explore --ai</span> 产用例（花 token）；② 手搓用例 → <span class="code-inline">generate</span> → <span class="code-inline">run</span>（零 token）。下游 <b>probe → generate → run</b> 完全共用。</li>
      <li><b>ElementMap 是契约</b>：AI 只引用 <span class="code-inline">semantic_name</span>，绝不产 selector —— 换页面、换模型都不用改执行端。</li>
      <li><b>成本分层</b>：探索阶段每步一次推理；生成脚本后执行端零 token，可无限次进 CI。</li>
    </ul>
    <pre class="tree">自然语言场景 ──explore --ai──▶ cases/ai_*.json ─┐
                                              ├─▶ generate ─▶ scripts/ + datasets/ ─▶ run（零 token）
手搓 cases/*.json ──────────────────────────┘        ▲ 缺项才现场 probe；ElementMap 快照优先</pre>
    <p><b>怎么用：</b><code>python -m framework.cli explore --ai --scenario-file scenarios/contracts/contracts_search_by_no.yml</code> → <code>python -m framework.cli generate</code> → <code>python -m framework.cli run --workers 2</code></p>
    <div style="border:1px dashed var(--line);border-radius:8px;padding:10px;font-size:.9rem;margin-top:10px">
      <b>🧪 测试验证用例设计</b>
      <ul style="margin:6px 0 0 18px;line-height:1.75">
        <li><b>一类：</b><span class="code-inline">tests/test_offline_chain_python.py</span>（9 条：离线链 Python 化，跨平台）· <span class="code-inline">tests/test_no_gate_coupling.py</span>（2 条：框架自测与 demo 解耦）</li>
        <li><b>二类：</b><span class="code-inline">tests/verify_offline_delivery.py</span>（交付两件套形态）· <span class="code-inline">tests/verify_offline_chain_deps.py</span>（离线链依赖齐备）· <span class="code-inline">tests/verify_e2e_scenario1_offline.py</span>（<b>7 项，含 2 条负向证伪 + 归档零残留</b>）</li>
        <li><b>E2E：</b>场景1（自然语言→AI→cases→generate→run，日常走离线回放）· 场景2（手写用例驱动 <span class="code-inline">cli run</span>）</li>
      </ul>
    </div>
  </div>

  <!-- ============ 特性 2 ============ -->
  <div class="card" style="border-left:4px solid var(--brand);margin-bottom:18px">
    <h4>特性 2 · 语义识别 + 分层定位（probe → AI → Tier1/Tier2）</h4>
    <p style="color:var(--muted);font-size:.92rem"><b>定位：</b>让「人能读懂的语义名」变成「Playwright 能唯一命中的 locator」，且每一步失败都可解释、不瞎猜。</p>
    <p><b>关键设计</b></p>
    <ul style="margin-left:18px;font-size:.92rem;line-height:1.8">
      <li><b>probe 先出「词汇表」</b>：扫页面可交互元素，产 role/name/placeholder/test_id/nearby_text 等语义清单（AI 与 Playwright 共用）。</li>
      <li><b>Tier1 精确语义</b>（5 级顺序）：<span class="code-inline">data-testid</span> &gt; <span class="code-inline">role+name</span> &gt; <span class="code-inline">label</span> &gt; <span class="code-inline">placeholder</span> &gt; <span class="code-inline">text</span>，命中后还要<b>意图复验</b>（回读元素实际语义比对，阈值 0.15，不符降级）。</li>
      <li><b>Tier2 指纹 + 语义上下文</b>：nearby_text / container_heading / help_text 加权评分，<b>评分差距 &gt; 0.12（MINGAP）才唯一采用</b>，否则诚实失败。</li>
      <li><b>铁律</b>：<span class="code-inline">count()==1</span> —— 不唯一就降级，找不到就报错，绝不蒙一个可能点错的。</li>
    </ul>
    <pre class="tree">semantic_name ─▶ Tier1(精确语义) ──唯一命中?──▶ ▶ 意图复验(阈值0.15) ──符合──▶ ✅ 采用
                     │  不唯一 / 找不到 / 复验不过
                     ▼
                 Tier2(指纹 + 语义上下文) ──评分差距&gt;0.12?──▶ ✅ 唯一采用
                                          └── 否则 ──▶ ❌ 诚实失败（进 Healer）</pre>
    <p><b>怎么用：</b><span class="code-inline">explore --ai</span> 产 ElementMap → <span class="code-inline">generate</span> 时优先吃 element_map 快照（缺项才现场 probe）→ <span class="code-inline">run</span> 时逐动作先 Tier1 再 Tier2。</p>
    <div style="border:1px dashed var(--line);border-radius:8px;padding:10px;font-size:.9rem;margin-top:10px">
      <b>🧪 测试验证用例设计</b>
      <ul style="margin:6px 0 0 18px;line-height:1.75">
        <li><b>一类：</b><span class="code-inline">tests/test_ready_and_locate.py</span>（13 条：ready 契约、_goto/_wait_ready 接线、误导性报错消失）· <span class="code-inline">tests/test_element_ambiguity_gate.py</span>（15 条）· <span class="code-inline">tests/test_name_alignment.py</span>（11 条：精确名优先 / 模糊命中留痕 / 歧义必须 fail loud / 严格模式拒绝近似）· <span class="code-inline">tests/test_import_targets.py</span>（4 条：内部 import 都能解析）</li>
        <li><b>二类：</b><span class="code-inline">tests/verify_picker_layer.py</span>（弹层 picker 链回归）· <span class="code-inline">tests/verify_order_pages.py</span> / <span class="code-inline">tests/verify_order_pick_create.py</span>（真开浏览器点、真读页面与服务端状态，<b>不看「代码里写了」</b>）</li>
        <li><b>⚠️ 待补缺口（如实标注）：</b>Tier1 意图复验阈值（0.15）与 Tier2 MINGAP（0.12）目前<b>没有直接判据</b>——只有闸门层与命名层判据。阈值改动可能静默退化，建议补两条（复验不符必须降级 / 评分差距不足必须失败）。</li>
      </ul>
    </div>
  </div>

  <!-- ============ 特性 3 ============ -->
  <div class="card" style="border-left:4px solid var(--brand);margin-bottom:18px">
    <h4>特性 3 · 防「AI 选对名字、选错控件」的多层兜底</h4>
    <p style="color:var(--muted);font-size:.92rem"><b>定位：</b>AI 在复杂页面可能挑错控件（如把「合同名称输入框」选成「搜索框」）——用代码侧的多道防线把「AI 选错 → 框架点错」压到最低。</p>
    <p><b>关键设计</b></p>
    <ul style="margin-left:18px;font-size:.92rem;line-height:1.8">
      <li><b>防线①语义校准</b>（explorer）：AI 挑完元素后，用其描述与元素语义做字符级核心词重叠，<b>相似度 &lt; 0.3 打警告</b>「疑似选错控件」。</li>
      <li><b>防线③Tier1 意图复验</b>（locator_bridge）：Tier1 命中唯一后回读元素实际语义与 page_hint/semantic_name 比对（阈值 0.15），不符 → 降级下一策略 / Tier2。</li>
      <li><b>防线②Tier2 指纹消歧</b>：同名元素靠语义上下文（nearby_text 等）选出唯一；<b>无上下文的裸元素诚实失败</b>（防 false-heal）。</li>
      <li><b>兜底 Healer</b>：三道防线都失败才走自愈，且自愈结果要过业务后置断言裁决。</li>
    </ul>
    <pre class="tree">AI 挑控件 ─▶ ①语义校准(相似度&lt;0.3 → 告警)
                ▼
          locator 解析 ─▶ ③Tier1 意图复验(阈值0.15；不符→降级)
                ▼
          ②Tier2 指纹+上下文(差距&gt;0.12 才唯一；裸元素 → 失败)
                ▼
          Healer 自愈(A级放宽阈值 → B级LLM重猜) ─▶ 后置断言裁决 recovered / real_bug / failed
   —— 任一层不确定都<b>走失败</b>，宁可报错也不点错元素</pre>
    <p><b>怎么用：</b>无需额外开关——<span class="code-inline">explore --ai</span> 与 <span class="code-inline">run</span> 默认生效；告警出现在 explore 日志，自愈事件落 <span class="code-inline">output/heals/*.md</span>。</p>
    <div style="border:1px dashed var(--line);border-radius:8px;padding:10px;font-size:.9rem;margin-top:10px">
      <b>🧪 测试验证用例设计</b>
      <ul style="margin:6px 0 0 18px;line-height:1.75">
        <li><b>一类：</b><span class="code-inline">tests/test_element_ambiguity_gate.py</span>（15 条）· <span class="code-inline">tests/test_name_alignment.py</span>（11 条：<b>歧义裸名不许猜</b>、精确名优先、影子名要列出来）· <span class="code-inline">tests/test_llm_retry.py</span>（3 条：LLM 失败重试边界）</li>
        <li><b>二类：</b><span class="code-inline">tests/verify_element_ambiguity.py</span>（<b>12 项，含负向</b>）· <span class="code-inline">tests/verify_cross_page.py</span>（跨页场景：<b>每条错误都必须失败</b>——防假绿铁律）</li>
        <li><b>E2E：</b>场景1 的离线链本身就覆盖「AI 挑名 → 定位 → 执行」整条路（含 2 条负向）。</li>
      </ul>
    </div>
  </div>

  <!-- ============ 特性 4 ============ -->
  <div class="card" style="border-left:4px solid var(--brand);margin-bottom:18px">
    <h4>特性 4 · 用例 / 脚本 / 数据三层分离</h4>
    <p style="color:var(--muted);font-size:.92rem"><b>定位：</b>用例写自然语言、脚本只放逻辑、数据全部抽离——改数据不动脚本，改页面不动用例。</p>
    <p><b>关键设计</b></p>
    <ul style="margin-left:18px;font-size:.92rem;line-height:1.8">
      <li><b>cases/*.json</b>：op 操作类型 + desc 描述 + element 探测语义 + value 数据；断言用 <span class="code-inline">asserts[]</span>，<b>11 种 kind</b>（文本/可见/隐藏/数量/属性/输入值/URL/勾选/未勾选/可用/禁用）。</li>
      <li><b>scripts/ + datasets/</b>：generate 把字面值抽到 <span class="code-inline">scripts/datasets/&lt;case_id&gt;.json</span>，脚本只留引用。</li>
      <li><b>动态占位符</b>：<span class="code-inline">{{datetime}}</span> / <span class="code-inline">{{date}}</span> / <span class="code-inline">{{uuid}}</span> 运行时解析固化（填表名 == 断言名，反复重跑不重名）。</li>
      <li><b>用例级变量池</b> <span class="code-inline">case.vars</span>：存过程数据（新建名称/系统返回编号），function-scope 隔离；检查点主判据用「输入值一致性」，系统编号仅作增强项（没有也照样通过）。</li>
    </ul>
    <pre class="tree">cases/xxx.json  ──generate──▶  scripts/test_cases.py   （逻辑：操作类型 → Playwright 调用）
  (自然语言 + 数据)                scripts/conftest.py      （夹具：_goto/_wait_ready/_act…）
                                scripts/datasets/xxx.json（数据：字面值抽离 + 占位符）
                                        │
                                        └─ run ─▶ 逐用例 .log + report.html + 变量池隔离</pre>
    <p><b>怎么用：</b><code>python -m framework.cli generate</code> 后看 <code>scripts/datasets/&lt;case_id&gt;.json</code>；改数据只动 datasets（或改 cases 重生成）。</p>
    <div style="border:1px dashed var(--line);border-radius:8px;padding:10px;font-size:.9rem;margin-top:10px">
      <b>🧪 测试验证用例设计</b>
      <ul style="margin:6px 0 0 18px;line-height:1.75">
        <li><b>一类：</b><span class="code-inline">tests/test_data_expand.py</span>（16 条：占位符展开与固化）· <span class="code-inline">tests/test_assert_kinds_render.py</span>（25 条：11 种断言渲染正确）· <span class="code-inline">tests/test_case_quality_gate.py</span>（13 条：用例质量闸门）· <span class="code-inline">tests/test_generate_quality_gate.py</span>（4 条）</li>
        <li><b>二类：</b><span class="code-inline">tests/verify_data_expand.py</span>（全真跑）· <span class="code-inline">tests/verify_assert_kinds.py</span>（<b>防假绿铁律：每条断言在「期望值写错」时必须 FAIL</b>）</li>
      </ul>
    </div>
  </div>

  <!-- ============ 特性 5 ============ -->
  <div class="card" style="border-left:4px solid var(--brand);margin-bottom:18px">
    <h4>特性 5 · 自愈闭环 Healer</h4>
    <p style="color:var(--muted);font-size:.92rem"><b>定位：</b>只给「定位意外」兜底（工程上占比应 &lt; 5%），且<b>每一次自愈都可审</b>——绝不静默改写脚本、绝不把真 bug 治愈成绿。</p>
    <p><b>关键设计</b></p>
    <ul style="margin-left:18px;font-size:.92rem;line-height:1.8">
      <li><b>A 级（确定性、无 LLM）</b>：放宽阈值重定位（阈值 × 0.75 / MINGAP × 0.6）。</li>
      <li><b>B 级（可选，需 key）</b>：请 LLM 重猜；失败即记为真 bug。</li>
      <li><b>可审 diff</b>：事件落 <span class="code-inline">output/heals/*.md</span>，含改前/改后，人可复核。</li>
      <li><b>三态裁决</b>：自愈后跑业务后置断言 → <b>recovered / real_bug / failed</b>，只有 recovered 才算「自愈成功」。</li>
    </ul>
    <pre class="tree">定位失败 ──▶ A级 放宽阈值(×0.75 / MINGAP×0.6) ──成功?──▶ 后置断言裁决
                │ 失败                                        ├─ recovered（真兜底）
                ▼                                            ├─ real_bug（页面/数据真的坏了）
             B级 LLM 重猜(需key) ──成功?──▶ 同上              └─ failed（兜不住，如实失败）
                └─ 失败 ──▶ ❌ 失败（不静默跳过）        每次事件都落 output/heals/*.md（可审）</pre>
    <p><b>怎么用：</b><span class="code-inline">run</span> 时默认生效；跑完看 <span class="code-inline">output/heals/*.md</span> 复核，或看 <span class="code-inline">log/&lt;run_id&gt;/*.log</span> 里的自愈记录。</p>
    <div style="border:1px dashed var(--line);border-radius:8px;padding:10px;font-size:.9rem;margin-top:10px">
      <b>🧪 测试验证用例设计</b>
      <ul style="margin:6px 0 0 18px;line-height:1.75">
        <li><b>⚠️ 现状（如实标注）：本特性目前<b>没有自动化判据</b></b>（<span class="code-inline">tests/</span> 里搜 <span class="code-inline">healer</span> / <span class="code-inline">try_heal</span> / <span class="code-inline">heals/</span> 零命中），属于 R7 口径下的<b>待补项</b>。</li>
        <li><b>建议补的判据（一类，秒级可测）：</b>① A 级放宽阈值后能重新命中唯一元素；② B 级<b>只在 A 级失败后</b>才触发（不许一失败就烧 token）；③ 三态裁决正确（recovered / real_bug / failed 各一条）；④ <b>兜不住时必须如实失败</b>，不许静默通过或改写脚本。</li>
        <li><b>二类建议：</b>用 demo 造一个「元素改名」的临时场景，端到端验证「自愈成功 → 后置断言放行」与「真改坏 → real_bug」两条路。</li>
      </ul>
    </div>
  </div>

  <!-- ============ 特性 6 ============ -->
  <div class="card" style="border-left:4px solid var(--brand);margin-bottom:18px">
    <h4>特性 6 · 并发与资源安全（低内存机器保命）</h4>
    <p style="color:var(--muted);font-size:.92rem"><b>定位：</b>在内存紧张的机器上，宁可降并发也不许 OOM 连锁——实测 1 个 headless Chromium ≈ 515MB，1.87GB 无 swap 的机器强跑 2 并发会触发内核 global OOM（连无关进程一起被杀）。</p>
    <p><b>关键设计</b></p>
    <ul style="margin-left:18px;font-size:.92rem;line-height:1.8">
      <li><b>资源预检</b>：读 MemAvailable → <span class="code-inline">cap = max(1, min((MemAvailable - 保留) / 每 worker 预算, CPU 核数))</span>，不够<b>自动降级并打印理由</b>；<span class="code-inline">--force-workers</span> 可显式覆盖。</li>
      <li><b>worker 复用浏览器</b>：每个 pytest-xdist worker 只起一个 Chromium 全程复用（逐条 setup 0.57~0.66s → 0.04~0.06s）。</li>
      <li><b>日志 run-id 隔离</b>：<span class="code-inline">log/&lt;run_id&gt;/</span> 下 .log / report.html / traces / videos，重跑不覆盖历史。</li>
      <li><b>调试开关 <span class="code-inline">--debug</span></b>（别名 <span class="code-inline">--headed</span>，默认关）：有图形显示 → 真开窗口一步步跑；<b>无图形显示（服务器）→ 降级为录屏 + 逐步截图 + trace</b>，两种环境都<u>不报错退出</u>。</li>
      <li><b>跨平台铁律</b>：所有脚本显式 UTF-8（Windows 中文环境不乱码）；入口一律 Python（PowerShell 没有 bash）。</li>
    </ul>
    <pre class="tree">cli run ─▶ 资源预检: MemAvailable ─▶ cap = max(1, min(可用/每worker预算, CPU)) ─▶ 不够则降级(打印理由)
                                                                        │
        ┌───────────────────────────────────────────────────────────────┘
        ▼
  workers=1..N，每个 worker: 1 个 Chromium（复用） ─▶ 逐用例: 新建 context+page
  产物: log/&lt;run_id&gt;/{{run.log, report.html, traces/, videos/, shots/}}

  --debug: 有 DISPLAY ─▶ 真窗口(headed)  |  无 DISPLAY ─▶ 录屏 + 逐步截图 + trace（都不报错）</pre>
    <p><b>怎么用：</b><code>python -m framework.cli run --workers 2</code>（自动降级）· <code>--force-workers 1</code>（显式）· <code>--debug</code>（看得见这次执行）。</p>
    <div style="border:1px dashed var(--line);border-radius:8px;padding:10px;font-size:.9rem;margin-top:10px">
      <b>🧪 测试验证用例设计</b>
      <ul style="margin:6px 0 0 18px;line-height:1.75">
        <li><b>一类：</b><span class="code-inline">tests/test_env_adaptation.py</span>（22 条：Windows / 非 git 目录 / 无 demo 下的降级路径）· <span class="code-inline">tests/test_utf8_io.py</span>（20 条：UTF-8 机理 + 真实默认编码路径）· <span class="code-inline">tests/test_retention_runs.py</span>（14 条：run-id 日志隔离与保留策略）· <span class="code-inline">tests/test_cli_exit_codes.py</span>（10 条：退出码契约，跳过 ≠ 通过）</li>
        <li><b>二类：</b><span class="code-inline">tests/verify_retention_runs.py</span>（全真跑：日志保留）· <span class="code-inline">tests/verify_slow_target.py</span>（慢目标闸门：慢代理 300ms 下 6 条关键用例全绿；<b>内存不足如实 SKIP exit 3</b>）</li>
        <li><b>⚠️ 待补缺口：</b><span class="code-inline">--debug</span> 两态（有/无图形显示）目前只有手工验证，<b>无自动化判据</b>——建议至少补「无 DISPLAY 时不许报错退出、且产物清单里必须有录像/截图」。</li>
      </ul>
    </div>
  </div>

  <!-- ============ 特性 7 ============ -->
  <div class="card" style="border-left:4px solid var(--brand);margin-bottom:18px">
    <h4>特性 7 · 离线回放（LLM 录像）：无外网也能跑完整 AI 链路</h4>
    <p style="color:var(--muted);font-size:.92rem"><b>定位：</b>把 <span class="code-inline">explore --ai</span> 每次问 LLM 的「prompt → 回答」原件录下来，让<b>连不上外网的机器</b>也能跑完整 AI 链路（语义识别 → generate → run），全程无需 key、不联网。</p>
    <p><b>关键设计</b></p>
    <ul style="margin-left:18px;font-size:.92rem;line-height:1.8">
      <li><b>两种命中</b>：先试<b>严格键</b>（prompt 逐字），再用<b>结构键</b>（场景语义 + 页面清单 + 控件骨架）兜底；命中结构键时<b>大声告警</b>（步骤是录制时针对那批数据做的判断）。</li>
      <li><b>值归一化</b>：场景数据里的<b>引号内字面值</b>与 <span class="code-inline">花括号占位符</span>统一折成 <span class="code-inline">&lt;VAL&gt;</span> ⇒ 换数据、参数化都不再让录像失效；只有真改页面/控件/场景语义才需重录。</li>
      <li><b>多键兼容</b>：查询同时试「新算法 + 旧算法」两把结构键 ⇒ 框架升级<b>不会让已有录像集体失效</b>。</li>
      <li><b>录像运维三件套</b>：体检（<span class="code-inline">check_cassettes.py</span>，零成本：哪些场景没有可用录像）· 批量重录（<span class="code-inline">record_cassettes.py --missing-only</span>，需 key+外网）· <b>出厂闸门</b>（打包前强制体检，<b>不过就不产包</b>）。</li>
      <li><b>可证伪</b>：离线链把 LLM 端点指到黑洞 <span class="code-inline">127.0.0.1:9</span> ⇒「有没有偷偷联网」是可验证的。</li>
    </ul>
    <pre class="tree">有外网机器:  explore --ai --llm-record ─▶ output/llm_cassettes/*.json（prompt + 回答 + 键）
                                                    │  打包体检(每场景都有可用录像?) ─▶ 录像包
无外网机器:  output/llm_cassettes/ ◀── 解包        ▼
             explore --ai --llm-cassette（严格键 → 结构键兜底）─▶ generate ─▶ run
             一键: python build_tools/offline_explore_chain.py --repo . --run（端点指黑洞，可证伪）</pre>
    <p><b>怎么用：</b><code>--llm-record</code>（录）· <code>--llm-cassette</code>（放）· <code>--llm-cassette-strict</code>（只认逐字）· <code>build_tools/check_cassettes.py</code>（体检）· <code>build_tools/pack_release.py --with-cassettes</code>（打录像包，含出厂闸门）。</p>
    <div style="border:1px dashed var(--line);border-radius:8px;padding:10px;font-size:.9rem;margin-top:10px">
      <b>🧪 测试验证用例设计</b>
      <ul style="margin:6px 0 0 18px;line-height:1.75">
        <li><b>一类：</b><span class="code-inline">tests/test_llm_cassette.py</span>（30 条：键计算 / 归一化 / 多键兼容 / <b>负向：键不匹配必须报「没有这一份」、坏录像文件不许毁掉整次回放</b>）· <span class="code-inline">tests/test_offline_chain_python.py</span>（9 条）· <span class="code-inline">tests/test_pack_release.py</span>（含出厂闸门 3 条：接线锁 / 覆盖不全必须拦 / 逃生口必须有效）</li>
        <li><b>二类：</b><span class="code-inline">tests/verify_e2e_scenario1_offline.py</span>（场景1 离线端到端，<b>7 项含 2 条负向 + 归档零残留</b>）· <span class="code-inline">tests/verify_e2e_scenario3_cassette.py</span>（<b>场景3 = 录制回放验证</b>：覆盖体检 / 体检有效性负向 / 不匹配必须 fail loud / <span class="code-inline">--with-record</span> 时跑「录制→回放闭环」）</li>
        <li><b>E2E：</b>场景3 就是为这个特性单独立项的（录像对不上 = 无网机器整段跑不了，以前只有现场才会发现）。</li>
      </ul>
    </div>
  </div>

  <!-- ============ 特性 8 ============ -->
  <div class="card" style="border-left:4px solid var(--brand)">
    <h4>特性 8 · 质量闸门体系（把隐性问题变成当场变红）</h4>
    <p style="color:var(--muted);font-size:.92rem"><b>定位：</b>框架的可靠性不靠「记得检查」，靠闸门——每个曾经踩过的坑都变成一个会当场变红的判据。</p>
    <p><b>关键设计</b></p>
    <ul style="margin-left:18px;font-size:.92rem;line-height:1.8">
      <li><b>demo 新鲜度闸门</b>：跑用例前先确认 demo 是最新版（否则后面全白做）。</li>
      <li><b>元素歧义闸门</b>：同名元素必须消歧或诚实失败，不许瞎选。</li>
      <li><b>慢目标闸门</b>：慢代理 300ms/请求下 6 条关键用例必须全绿。</li>
      <li><b>录像包出厂闸门</b>：打包前强制体检，覆盖不全不产包。</li>
      <li><b>R7 四项验收 / SKIP ≠ 通过</b>：①框架自测 ②特性自测 ③新鲜度 ④E2E 三场景；任一段跳过 ⇒ 退出码 3（<b>跳过不算通过</b>）；新特性一律 <b>TDD 判据先行</b>（先落判据 → 留红态证据 → 再实现）。</li>
    </ul>
    <pre class="tree">python tests/run_acceptance.py        ← 一条命令跑完 R7 四项（便宜先跑 + fail fast）
  [0] 闸门自检（先验「闸门自己」）
  [1] ③ demo 新鲜度      [2] ① 框架自测 337 条     [3] ④ E2E 场景3→2→1     [4] ② 特性自测 15 脚本
  退出码: 0 通过 / 3 跳过(不算通过) / 其它失败 —— 任一项红就停手并报「哪一项」</pre>
    <p><b>怎么用：</b><code>python tests/run_acceptance.py</code>（日常）· <code>--with-record</code>（发版前含录制闭环）· <code>python tests/run_verifications.py</code>（只跑二类）。</p>
    <div style="border:1px dashed var(--line);border-radius:8px;padding:10px;font-size:.9rem;margin-top:10px">
      <b>🧪 测试验证用例设计（闸门自己也要被判据钉住）</b>
      <ul style="margin:6px 0 0 18px;line-height:1.75">
        <li><b>一类：</b><span class="code-inline">tests/test_acceptance_entry.py</span>（8 条：入口步骤顺序即契约 / 三场景齐全 / 跳过必须标出 / SKIP ≠ 通过）· <span class="code-inline">tests/test_demo_freshness_gate.py</span>（21 条）· <span class="code-inline">tests/test_pack_release.py</span>（16 条）· <span class="code-inline">tests/test_artifacts_health.py</span>（7 条：产物健康，坏产物给人话诊断）· <span class="code-inline">tests/test_target_reachability.py</span>（7 条：连不上时统一给「先起 demo」指引）· <span class="code-inline">tests/test_case_quality_gate.py</span>（13 条）</li>
        <li><b>二类：</b><span class="code-inline">tests/verify_demo_freshness.py</span>（<b>7 项含负向证伪 + 真重启 + 还原</b>：闸门自己也必须被证明「坏 demo 能抓、好 demo 不误伤」）· <span class="code-inline">tests/verify_slow_target.py</span> · <span class="code-inline">tests/verify_html_sync.py</span>（R8：培训页可复现 + 与代码逐字节一致）</li>
        <li><b>原则：</b>闸门类结论必须<b>先主动证伪</b>（实测漏洞 + 边界清单）再下结论；<b>宁漏不误伤</b>（误拦会诱发绕过工具）。</li>
      </ul>
    </div>
  </div>

  <div class="card" style="border-top:4px solid var(--brand);margin-top:18px">
    <h4>📌 读本章的顺序建议（新手路线）</h4>
    <p style="font-size:.94rem;line-height:1.8">
      1️⃣ 先读 <b>特性 1</b>（知道两条链路怎么汇合）→ 2️⃣ 再读 <b>特性 4</b>（知道用例/脚本/数据怎么分工，这是你日常改的东西）→
      3️⃣ 跑一遍第 5 章图例⓪ 的六个阶段对照代码 → 4️⃣ 遇到点不中元素时回读 <b>特性 2 / 3</b> →
      5️⃣ 交付或换机器前读 <b>特性 7</b>（录像与出厂闸门）→ 6️⃣ 改完代码用 <b>特性 8</b> 的入口自检。
    </p>
  </div>
</section>

<!-- ========== 7. 常见坑 ========== -->
<section>
  <h2 class="sec-title"><span class="n">7</span>新同学最容易踩的坑</h2>
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
         收子进程输出用 <code>framework.tools.common.text_io.run_capture()</code>，
         给子进程注入口径用 <code>utf8_env()</code>，本进程 stdio 用 <code>force_stdio()</code>
         （<code>cli.main()</code> 已经默认调了）。<code>tests/test_utf8_io.py</code> 会做 AST 全仓扫描，
         再写出「靠默认编码」的写法直接测试失败。</p></div>
  </div>
</section>

<!-- ========== 8. 动手上手 ========== -->
<section>
  <h2 class="sec-title"><span class="n">8</span>动手跑一遍</h2>
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
<span class="prompt">$</span> python -m framework.cli prune --keep 20  <span class="cmt"># ⑤ 归档保留：快照各留最近 N 个</span>
<span class="prompt">$</span> python -m pytest tests/ -q               <span class="cmt"># ⑥ 框架自测（一类）：秒级，不需要 demo / key</span></pre>
    <p style="margin-top:10px;color:var(--muted);font-size:.92rem">
      预期输出：<code>fill→在搜索框输入关键字</code>、<code>click→点击搜索按钮</code>、
      <code>断言→搜索完成 ✓ 全部通过</code>，<code>&lt;N&gt; passed</code>（<b>N 随 cases/ 里的用例数变化</b>，本文档写作时为 15 条：11 手写 + 4 AI），
      HTML 报告在 <code>log/&lt;run_id&gt;/report.html</code>（每次运行独立目录）。
    </p>
    <p style="margin-top:12px;color:var(--muted);font-size:.92rem;border-left:3px solid #999;padding-left:10px">
      <b>框架自测（一类）的环境前提</b>（2026-09-22 实测口径）：上面那条 <code>pytest tests/ -q</code>
      在 <b>Windows</b>、<b>非 git 目录（交付包解压目录）</b>、<b>demo 没起</b> 这三种情况下都要能跑 ——
      进程探测按平台取（Linux <code>/proc</code> · Windows PowerShell · 其它 <code>ps</code>）；
      文件清单在 git 不可用时降级为文件树扫描；<b>生成物缺失或为 0 字节</b>时直接告诉你
      「先跑 <code>generate</code> / 重新解压」，而不是甩一堆「缺接线」；<b>连不上被测目标</b>时文案一律带
      「先起 <code>python -m demo.app</code>」这一步。如实 <code>SKIPPED</code> 会打印原因（<b>SKIP ≠ 通过</b>），其余必须全绿。
    </p>
    <p style="margin-top:10px;color:var(--muted);font-size:.92rem">
      <b>二类（端到端特性验证）也用 Python 跑</b>（Windows / Linux 通用，Python 入口是唯一实现）：
      <code>python tests/run_verifications.py</code>（全部）·
      <code>--only &lt;子串&gt;</code> 只跑一个 · <code>--list</code> 先看跑哪些 · <code>--no-demo</code> 不起 demo ·
      <code>--timeout-s 1200</code> 单脚本预算（默认 1200s）·
      <code>--jobs 2</code> 并发（浏览器脚本各自过内存闸，不够自动退回串行）·
      内存不足会<b>如实 SKIP 并 exit 3（不是通过）</b>。
    </p>
    <p style="margin-top:10px;color:var(--muted);font-size:.92rem">
      <b>★ R7 四项验收：一条命令跑完</b> —— <code>python tests/run_acceptance.py</code>。<br>
      执行顺序（<b>便宜先跑 + fail fast</b>，编号 ≠ 顺序）：
      闸门自检 → ③ demo 新鲜度 → ① 框架自测 → ④ E2E → ② 特性自测。<br>
      ④ E2E 有<b>三个场景</b>：场景1 = 自然语言 → <code>explore --ai</code> → <code>cases/ai_*.json</code>
      → <code>generate</code> → <code>run</code>（日常走<b>离线录像回放</b>，不联网可证伪）；
      场景2 = <code>generate</code> → <code>run</code>（手写用例驱动）；
      <b>场景3 = 录制回放验证</b>（录像可用性体检 + 体检有效性负向 + 不匹配必须 fail loud；
      <code>--with-record</code> 时加跑「录制 → 回放闭环」，要 key + 外网）。<br>
      <b>录像运维</b>：<code>python build_tools/check_cassettes.py</code>（零成本体检：哪些场景没有可用录像）·
      <code>python build_tools/record_cassettes.py --missing-only</code>（批量重录缺的）。
      <b>SKIP ≠ 通过</b>：任一段跳过 ⇒ 整体退出码 3。<br>
      <b>★ 录像包出厂闸门</b>：<code>pack_release.py --with-cassettes</code> 打包<b>前</b>强制体检
      「每个场景都有可用录像」，<b>不过就不产包（exit 2）</b>并逐条列出缺哪个场景 + 修法命令 ——
      录像包不会再「发出去了才发现是废包」。调试绕过：<code>--allow-missing-cassettes</code>（交付永不用）。
    </p>
  </div>
</section>

<!-- ========== 9. 记住三点 ========== -->
<section>
  <h2 class="sec-title"><span class="n">9</span>收尾 · 记住这三点</h2>
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
  hybrid_gui_qa · AI 混合 GUI 测试框架培训页 · <b>V{VERSION}</b>（{VERSION_DATE}）· 由 build_tools/build_html.py 生成
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
