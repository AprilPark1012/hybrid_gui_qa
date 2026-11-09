# -*- coding: utf-8 -*-
"""一类判据：**HYBRID_BASE_URL 覆盖必须对「登录」也生效**（2026-11-04 · L22 取证）。

## 这道闸防的是什么

`_goto` 一直支持用 `HYBRID_BASE_URL` 改目标（同一套用例跑本机 / 慢代理 / 预发 / 用户内网），
但**登录流 `_login_flow` 里是裸 `page.goto(...)`** —— 于是设了覆盖以后：

    · 业务步骤走 `_goto`        -> 打到 8012（慢代理/预发/用户系统）
    · 登录步骤走 `_login_flow`  -> **仍打生成期的 localhost:8000**

两个 origin 的会话 cookie 互不通用 => 业务页未登录 => 第一个业务步就「等了 15000ms 仍是 0 个」。
慢目标闸门（`verify_slow_target.py`）因此长期红着，而它测的其实是
**半套 8000 + 半套 8012 的混合物**，不是「慢目标」。

对交付更严重：用户把包拿到内网、改 `HYBRID_BASE_URL` 指向自己的系统时，
**登录会打到包里写死的地址** —— 功能性缺陷，不只是闸门问题。

## 口径

1. 改写走**唯一入口** `_rewrite_base()`，`_goto` 与 `_login_flow` 都调它（不许各写一份）
2. 没设 `HYBRID_BASE_URL` 时**原样返回**（不许凭空造 host）
3. 改写只换 scheme/netloc，**path/query 原样保留**
"""
from __future__ import annotations

import importlib.util
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HARNESS = REPO / "scripts" / "generated" / "_harness.py"
GEN = REPO / "framework" / "features" / "f02_semantic" / "generator_generate.py"


class _FakePage:
    """只实现登录流用到的导航面：goto / wait_for_url / url。"""

    def __init__(self):
        self.urls: list[str] = []
        self.url = "about:blank"

    def goto(self, u, **kw):
        self.urls.append(str(u))
        self.url = str(u)

    def wait_for_url(self, *a, **kw):
        return None


def _load_harness(base: str | None):
    """在指定 `HYBRID_BASE_URL` 下**重新导入**一次 harness。

    模块级 `_HYBRID_BASE` 是导入时读的 —— 不重载就测不到「设了 base」的分支。
    """
    old = os.environ.get("HYBRID_BASE_URL")
    try:
        if base is None:
            os.environ.pop("HYBRID_BASE_URL", None)
        else:
            os.environ["HYBRID_BASE_URL"] = base
        spec = importlib.util.spec_from_file_location("_harness_under_test", HARNESS)
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        if old is None:
            os.environ.pop("HYBRID_BASE_URL", None)
        else:
            os.environ["HYBRID_BASE_URL"] = old


# ---------------- (1) 改写只换 origin，path/query 不动 ----------------

def test_rewrite_base_swaps_origin_only():
    h = _load_harness("http://127.0.0.1:8012")
    got = h._rewrite_base("http://localhost:8000/order_new.html?contract_no=HT-1001#sec")
    assert got == "http://127.0.0.1:8012/order_new.html?contract_no=HT-1001#sec", got


# ---------------- (2) 没设 base -> 原样返回（不许凭空造） ----------------

def test_rewrite_base_is_noop_without_override():
    h = _load_harness(None)
    src = "http://localhost:8000/login.html"
    assert h._rewrite_base(src) == src


# ---------------- (3) 登录流两条路径都必须被改写（行为） ----------------

def test_login_flow_rewrites_both_paths():
    """① 有 goto 步  ② 无 goto 步（靠 login_url）—— 两条都不许留在生成期地址。"""
    h = _load_harness("http://127.0.0.1:8012")

    p1 = _FakePage()
    h._login_flow(p1, [{"op": "goto", "value": "http://localhost:8000/login.html"}],
                  {"url_not": "login.html"}, "http://localhost:8000/login.html")
    assert p1.urls, "登录流一次都没导航"
    assert all("127.0.0.1:8012" in u for u in p1.urls), f"带 goto 步仍打生成期地址：{p1.urls}"

    p2 = _FakePage()
    h._login_flow(p2, [], {"url_not": "login.html"}, "http://localhost:8000/login.html")
    assert p2.urls and all("127.0.0.1:8012" in u for u in p2.urls), \
        f"无 goto 步仍打生成期地址：{p2.urls}"


# ---------------- (4) 源码契约：登录段不许出现未经改写的裸 page.goto ----------------

def test_login_flow_source_has_no_bare_goto():
    """`_login_flow` 体里每个 `page.goto(` 都必须是 `page.goto(_rewrite_base(...`。

    为什么钉源码而不是只钉行为：行为判据只能覆盖我想到的两条路径；
    将来有人再加一个 `page.goto(...)` 分支，行为判据照样全绿 —— 源码契约能当场抓住。
    """
    src = GEN.read_text(encoding="utf-8")
    i = src.index("def _login_flow(page, steps")
    j = src.index("def ", i + 10)          # 下一个顶层 def = 函数体结束
    body = src[i:j]
    bad = [m.group(0) for m in re.finditer(r"page\.goto\([^)]*", body)
           if "_rewrite_base(" not in m.group(0)]
    assert not bad, f"登录流里有未经改写的裸 page.goto：{bad}"

    # 同时钉「只有一个改写入口」：_goto 也必须用它
    # V8.10.0：跨 origin 后 `_goto` 改为走 `_rw(url, origin_name)`；
    # `_rw` 在「无 origin 名」时**逐字回落** `_rewrite_base(url)`（单系统行为不变），
    # 所以这里认两种形态，但**必须**是二选一（不许出现第三种写法）。
    assert ("target = _rw(url, origin_name)" in src) or ("target = _rewrite_base(url)" in src), \
        "_goto 既没走 _rw 也没走 _rewrite_base —— 改写入口被绕过了"


# ---------------- (5) 全仓导航契约：除了 `_goto` 内部那一处，所有导航都必须改写 ----------------

def test_every_navigation_in_harness_goes_through_rewrite():
    """harness 里**任何** `.goto(` 都必须经过 `_rewrite_base`（唯一例外：`_goto` 里 `page.goto(target)`）。

    为什么要有这条：登录流修完以后，实测立刻冒出**第二处**同类漏洞 ——
    fixture 的「场景身份前置」是裸 `pg.goto(_host)`（`_host` 是生成期记录的地址），
    设了 `HYBRID_BASE_URL` 后它打到别的实例：本机表现为 `ERR_CONNECTION_REFUSED`，
    有实例在时更糟（静默在错的身份下把整条用例跑完）。
    逐个修容易漏下一个 —— 所以用 **AST** 扫全部 `goto(...)` 调用点，注释/docstring 里的字眼不算。
    """
    import ast as _ast
    src = HARNESS.read_text(encoding="utf-8")
    tree = _ast.parse(src)
    offenders = []
    for node in _ast.walk(tree):
        if not (isinstance(node, _ast.Call) and isinstance(node.func, _ast.Attribute)):
            continue
        if node.func.attr != "goto":
            continue
        arg = _ast.get_source_segment(src, node.args[0]) if node.args else ""
        arg = (arg or "").strip()
        # 允许的形态：
        #   · 直接调 `_rewrite_base(...)`；
        #   · `_goto` 里已算好的 `target`；
        #   · `_rw(...)`（V8.10.0：跨 origin 安全版，内部按 origin 名决定改不改）；
        #   · `_spread_session` 里的 `base` / `base + "/"` —— 那里的 base 已经是
        #     **解析后的最终 origin**（HYBRID_ORIGIN_MAP 或生成期快照），再改写一次反而会被压平回 base。
        if (arg.startswith("_rewrite_base(") or arg.startswith("_rw(")
                or arg == "target" or arg == "base" or arg == 'base + "/"'):
            continue
        offenders.append(f"第 {node.lineno} 行 .goto({arg[:60]})")
    assert not offenders, f"这些导航点没走 _rewrite_base：{offenders}"


# ---------------- (6) select 的「可选项就绪」必须是有界等待，不是当帧判死 ----------------

class _FakeOpts:
    def __init__(self, values):
        self.values = list(values)

    def count(self):
        return len(self.values)

    def nth(self, i):
        v = self.values[i]

        class _O:
            def get_attribute(self, _n):
                return v
        return _O()


class _FakeSelect:
    """前 `empty_times` 次读到的 option 是空的（模拟异步填数据），之后才有值。"""

    def __init__(self, values, empty_times=3):
        self.values = list(values)
        self.empty_times = empty_times
        self.reads = 0

    def locator(self, _sel):
        self.reads += 1
        return _FakeOpts([] if self.reads <= self.empty_times else self.values)


def test_wait_real_options_waits_for_async_options():
    """选项还没到时不许当帧判死 —— 必须**有界等**，等到就继续。

    实测（2026-11-04 慢目标闸门）：`select 期次号` 在 300ms/请求下抛
    「按行定位的 select 未给 value，且该控件没有任何可选选项」，
    而快目标下同一步是通过的 —— 不是不支持行内 select，是**选项就绪观测不到**。
    """
    h = _load_harness(None)
    el = _FakeSelect(["", "1", "2"])          # 第一个是空占位
    real, n, waited = h._wait_real_options(el, deadline_ms=3000)
    assert real == [1, 2], f"没等到异步选项：{real}"
    assert n == 3 and waited >= 0
    assert el.reads > 1, "只读了一次就下结论（没有等）"


def test_wait_real_options_gives_up_at_deadline():
    """等到 deadline 仍空 -> 返回空，让调用方如实报错（**不静默取第一个**）。"""
    h = _load_harness(None)
    el = _FakeSelect([""], empty_times=10 ** 6)
    real, n, waited = h._wait_real_options(el, deadline_ms=300)
    assert real == [], f"没选项竟然返回了 {real}"
    assert waited >= 300, f"没等满 deadline 就放弃了：{waited}ms"


def test_select_paths_both_use_the_waiter():
    """两处 select（行内 / 非行内）都必须走 `_wait_real_options`（同一能力唯一入口）。"""
    src = HARNESS.read_text(encoding="utf-8")
    assert src.count("_wait_real_options(") >= 3, "要么没定义、要么某个 select 分支没接上"
    # 「当帧扫 option」的写法只允许出现在 `_wait_real_options` **自己的函数体里**
    i = src.index("def _wait_real_options(")
    j = src.index("\ndef ", i + 10)
    body = src[i:j]
    assert "_real = [i for i in range" in body, "helper 自己都没扫 option，判据写错了"
    outside = src[:i] + src[j:]
    bad = outside.count('_real = [i for i in range')
    assert bad == 0, f"还有 {bad} 处在**当帧**扫 option —— 慢目标下必红，必须改走 _wait_real_options"
