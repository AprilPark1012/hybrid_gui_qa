# -*- coding: utf-8 -*-
"""特性2 · explore 提示词的「业务等待时长 + 页名口径」段必须**紧凑**（C3 · 2026-10-16）。

现场（实测）：这一段在真实提示词里是一条**信息密度极低**的长带，形态是 ——
    本场景原文声明的业务等待是 **150000ms（约 150 秒）**（例如「提交后 N 秒自动关闭」这类按时间自动推进的动作）。
    => 写这类「等它自己变」的断言时：
       1) desc 里写清**等什么、以及为什么值得等**；
       2) **等待时长由框架按本声明自动设置**（你不用猜、也不用给时长）；
       3) 绝不写固定 sleep 硬等，也绝不写成「只等几秒」——那必然失败。
    [!] **本场景的页名只有下面这几个**（来自场景声明，是权威口径）：「登录页」...「发票列表页」
      语义名里的 `@页名` 后缀**只能从这几个里选，一个字都不能改**。**下面这些都不是页名，不许当后缀用**：
        · 系统名 / 模块名 / 应用名（如场景文案里提到的别的叫法）；
        · **容器名 / 区块名 / 面板标题**（如「详细信息」「发票行」）；
        · 自己按语义近义造出来的词（如把「订单详情页」写成「订单详情」）。
      写错后缀会让该控件映射不上，框架会在生成期直接拦下整条链。

其中**真正约束 AI 的只有三样**：等待时长的数字、3 条做法、页名白名单。
「不是页名」的排除清单是**举例**（说教），不是约束 —— 举例可以砍到最少，约束一个字不能动。

判据口径（纯字符串级：不起浏览器、不联网、不调 LLM —— 只用组装函数的返回值）：
    段边界 = 组装出的提示词里，从 `===== 本场景声明的业务等待时长` 起，
             到页面清单开头（`你是 GUI 自动化测试规划师`）止的那一片连续文本。

[!] 这个边界**只覆盖上面说的那段**。紧随其后的页面清单（各页说明）、场景原文、跨页规则、
    「跨页同名控件」清单、身份前置**不属于本段** —— 把它们一起量会把它们的体积算到本段头上。
    实测：从本段开头一路量到控件清单头（「页面已探测出以下可交互控件」）是 9,910 字符，
    而其中本段只有几百，剩下的是页面清单 2070 / 场景原文 2062 / 跨页规则+同名控件+身份前置 5229。
    **按 9,910 去砍会砍错东西**（把场景本身当成冗余说教），所以本判据把边界钉死。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from framework.features.f02_semantic.explorer_explore import _build_planner_prompt  # noqa: E402

START = "===== 本场景声明的业务等待时长"
# 页面清单的开头（多页路径写「本场景跨 N 个页面」，单页路径写「目标页面:」）
END_MARKS = ("你是 GUI 自动化测试规划师", "目标页面:")

#: 最坏情况：页名很多（12 个）+ 声明了业务等待 —— 白名单是随场景变的，必须这条路也压得住
_WORST_PAGES = [{"name": f"第{i}页", "url": f"http://127.0.0.1:8000/p{i}.html",
                 "page": f"第 {i} 页的说明。"} for i in range(1, 13)]
_WAIT_SCENARIO = "提交后 150 秒自动关闭（履行频率 10 秒一档），期间不要重复提交。"


def _section(scenario: str, pages: list[dict] | None, url: str = "http://127.0.0.1:8000/") -> str:
    """把「等待 + 页名口径」段从**组装出的提示词**里切出来（不是另写一份拼法）。"""
    prompt = _build_planner_prompt(scenario, [], url, pages=pages)
    i = prompt.index(START)
    ends = [prompt.find(m, i) for m in END_MARKS]
    ends = [e for e in ends if e != -1]
    assert ends, f"本段后面没找到页面清单开头（提示词结构变了？）：\n{prompt[i:i + 400]}"
    return prompt[i:min(ends)]


# ---------------------------------------------------------------- ① 体积

def test_wait_and_page_rule_section_is_compact():
    """★ 核心判据：段字符数必须先 ≤ 1,500（最坏情况：12 个页名 + 150 秒等待）。"""
    seg = _section(_WAIT_SCENARIO, _WORST_PAGES)
    print(f"\n[C3] 本段字符数（12 页名 + 150 秒声明，最坏情况）= {len(seg)}")
    assert len(seg) <= 1500, (
        f"本段 {len(seg)} 字符，超过 1,500 上限 —— 这段只承担「时长数字 + 3 条做法 + 页名白名单」，"
        f"超出的部分多半是解释性说教（可以砍），或排除清单又长回来了。\n段全文：\n{seg}"
    )


def test_same_section_stays_compact_for_a_single_declared_page():
    """单页路径同样要短（段是同一个组装函数产出的，两条路径都不许长回来）。"""
    seg = _section(_WAIT_SCENARIO, [{"name": "订单页", "url": "http://127.0.0.1:8000/o.html"}])
    assert len(seg) <= 1500, f"单页路径下本段 {len(seg)} 字符：\n{seg}"


# ---------------------------------------------------------------- ② 语义不许丢

def test_section_keeps_wait_number_and_three_practices():
    """不丢语义：等待量数字 + 「有界等待 / 时长由框架自动设 / 不许固定 sleep」3 条做法必须都在。"""
    seg = _section(_WAIT_SCENARIO, _WORST_PAGES)
    assert "150000" in seg and "150 秒" in seg, f"声明的等待时长数字丢了：\n{seg}"
    assert "3)" in seg or "3）" in seg, f"3 条做法的编号没了（看不出是「做法」而不是别的）：\n{seg}"
    for kw in ("desc", "框架", "自动设置", "sleep", "有界"):
        assert kw in seg, f"做法里的关键字 {kw!r} 丢了 —— 压缩不许压掉约束：\n{seg}"


def test_page_name_whitelist_follows_the_scenario():
    """页名白名单是**权威口径**且随场景变：换一组页名，段里就必须是那一组（不许写死）。"""
    seg = _section(_WAIT_SCENARIO, _WORST_PAGES)
    for p in _WORST_PAGES:
        assert f"「{p['name']}」" in seg, f"页名 {p['name']!r} 没进白名单：\n{seg}"
    other = [{"name": "甲页", "url": "http://x/a"}, {"name": "乙页", "url": "http://x/b"}]
    seg2 = _section("等 30 秒自动关闭", other)
    assert "「甲页」" in seg2 and "「乙页」" in seg2, f"换一组页名后白名单没跟着变：\n{seg2}"
    assert "第1页" not in seg2, f"上一组页名串味了（白名单被写死了？）：\n{seg2}"


def test_exclusion_list_is_compressed_but_keeps_the_hard_constraint():
    """排除清单**可以砍举例**，但不许砍强度：压缩口径 + 「一个字都不能改」必须还在。"""
    seg = _section(_WAIT_SCENARIO, _WORST_PAGES)
    assert "一个字都不能改" in seg, f"「一个字都不能改」这个硬约束的强度丢了：\n{seg}"
    assert "一律不是页名" in seg, (
        f"排除清单没收敛成「除上面这几个外一律不是页名」这句 —— 说明还是老的一堆并列举例：\n{seg}"
    )
    assert "当后缀" in seg, f"「不许当后缀用」这层意思丢了：\n{seg}"
    # 反例最多 3 条：排除清单是**举例**，不是约束 —— 列多了纯占篇幅（超出/多余都要红）
    bullets = sum(1 for ln in seg.splitlines() if ln.strip().startswith("·"))
    assert bullets <= 3, f"排除清单列了 {bullets} 条反例（口径：最多 3 条最易误用的）：\n{seg}"


def test_no_declared_wait_means_no_wait_section():
    """**反向自证**：场景没声明业务等待 -> 不许凭空多出一段（否则等于每场景都在暗示要等）。"""
    prompt = _build_planner_prompt("点保存，然后返回列表页", [], "http://127.0.0.1:8000/",
                                   pages=_WORST_PAGES)
    assert START not in prompt, "场景没声明等待，等待段却出现了 —— 凭空造约束会让 AI 乱等"
