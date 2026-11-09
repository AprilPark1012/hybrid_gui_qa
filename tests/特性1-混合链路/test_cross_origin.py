# -*- coding: utf-8 -*-
"""特性 1.5「跨 origin 多业务系统」判据（V8.10.0）。

## 要钉住的三件事（每条都有真实事故背景）

1. **声明过的 origin 不许被压平**：真实业务里合同/订单/发票是不同业务系统（不同 origin），
   登录却只有一套 SSO。旧口径 `_rewrite_base` 会把**任何**地址换成单一 `HYBRID_BASE_URL`
   -> 一设 base，跨系统场景被压平成一套系统（实测：goto `localhost:8001` 实际落到 `8000`）。
2. **没声明 origin 的场景行为逐字不变**：单系统场景是绝大多数，这条口径改错会一次坑掉所有用例。
3. **会话要能铺到别的 origin**：会话在 localStorage 里是 per-origin 的，SSO 登录只落在登录那个
   origin —— 实测访问另一个 origin 的业务页会被踢回**它自己**的登录页
   （`localhost:8001/orders.html` -> `localhost:8001/login.html?next=%2Forders.html`）。

## 口径
- 生成期：场景 `origins:` 给每个系统起名，页面地址用 `${名字}` 引用；用例落盘带 `origins` 快照；
- 生成时：`goto` 的地址若属于某个声明的 origin -> 渲染成 `_goto(page, url, '名字')`；
- 运行期：`_rw(url, '名字')` 只按 `HYBRID_ORIGIN_MAP` 换那个 origin；**没映射就原样**；
- `name` 为空（单系统）-> 仍走 `_rewrite_base`（旧行为）。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
GEN = REPO / "framework" / "features" / "f02_semantic" / "generator_generate.py"
SCN = REPO / "framework" / "features" / "f02_semantic" / "scenario_generate.py"
HARNESS_TEMPLATE = GEN          # harness 是生成物，模板住在 generator 里


def _src(p: Path) -> str:
    return p.read_text(encoding="utf-8")


# ---------------------------------------------------------------- 1. 生成期：origin 反查
def test_origin_name_of_resolves_declared_origin():
    from framework.features.f02_semantic.generator_generate import _origin_name_of
    case = {"origins": {"order": "http://localhost:8001", "invoice": "http://localhost:8002/"}}
    assert _origin_name_of("http://localhost:8001/api/health", case) == "order"
    assert _origin_name_of("http://localhost:8002/invoice_list.html", case) == "invoice"


def test_origin_name_of_is_empty_without_declaration():
    """没声明 origins -> 空名 -> 渲染走旧口径（逐字不变）。"""
    from framework.features.f02_semantic.generator_generate import _origin_name_of
    assert _origin_name_of("http://localhost:8001/api/health", {}) == ""
    assert _origin_name_of("http://localhost:8001/api/health", {"origins": {}}) == ""


def test_origin_name_of_ignores_foreign_origin():
    """同一场景里出现「没声明过的 origin」-> 空名（原样，不当成声明过的）。"""
    from framework.features.f02_semantic.generator_generate import _origin_name_of
    case = {"origins": {"order": "http://localhost:8001"}}
    assert _origin_name_of("http://elsewhere:9999/x", case) == ""


# ---------------------------------------------------------------- 2. 运行期：_rw 语义
def _rw_impl(src: str) -> str:
    m = re.search(r"(?ms)^def _rw\(url, origin_name=None\):.*?(?=^def )", src)
    assert m, "harness 里找不到 `_rw(url, origin_name=None)` —— 跨 origin 改写入口没了"
    return m.group(0)


def test_harness_has_rw_and_origin_map():
    src = _src(HARNESS_TEMPLATE)
    assert "_ORIGIN_MAP" in src and "HYBRID_ORIGIN_MAP" in src, (
        "harness 没有 HYBRID_ORIGIN_MAP 映射加载 -> 跨 origin 只能靠生成期地址，换环境得重用例")
    body = _rw_impl(src)
    assert "_rewrite_base(url)" in body, "`_rw` 在「无 origin 名」时必须回落到 `_rewrite_base`（旧口径）"
    assert ("else url" in body) or ("return url" in body), (
        "`_rw` 在「有名字但没映射」时必须**原样返回**（不许压平）")


def test_rw_behaviour_no_flatten_without_map(monkeypatch):
    """行为判据：有名字、无映射 -> 原样（不压平到 base）。"""
    import importlib.util

    harness_py = REPO / "scripts" / "generated" / "_harness.py"
    if not harness_py.exists():
        pytest.skip("本机还没有生成的 harness")
    spec = importlib.util.spec_from_file_location("_h_rwtest", harness_py)
    h = importlib.util.module_from_spec(spec)
    monkeypatch.setattr(h, "_HYBRID_BASE", "http://localhost:8000", raising=False)
    spec.loader.exec_module(h)
    h._HYBRID_BASE = "http://localhost:8000"
    h._ORIGIN_MAP = {}
    url = "http://localhost:8001/api/health"
    assert h._rw(url, "order") == url, "声明过但没映射的 origin 被压平了 -> 跨系统场景会串成一套系统"
    # 旧口径：不给名字 -> 仍按 base 改写（单系统行为不变）
    assert h._rw(url) == "http://localhost:8000/api/health"


def test_rw_uses_map_when_present():
    import importlib.util

    harness_py = REPO / "scripts" / "generated" / "_harness.py"
    if not harness_py.exists():
        pytest.skip("本机还没有生成的 harness")
    spec = importlib.util.spec_from_file_location("_h_rwtest2", harness_py)
    h = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(h)
    h._ORIGIN_MAP = {"order": "http://order.example.com:8001"}
    assert h._rw("http://localhost:8001/api/health?x=1", "order") == "http://order.example.com:8001/api/health?x=1", (
        "映射后必须保留 path / query（只换 origin）")


# ---------------------------------------------------------------- 3. 场景声明
def test_scenario_expands_origin_refs(tmp_path):
    from framework.features.f02_semantic.scenario_generate import load_scenario_file
    f = tmp_path / "x_origin.yml"
    f.write_text("""id: x_origin
origins:
  order: http://localhost:8001
  invoice: http://localhost:8002
scenario: 打开订单页
pages:
  - name: 订单列表页
    url: ${order}/orders.html
  - name: 发票列表页
    url: ${invoice}/invoice_list.html
""", encoding="utf-8")
    sc = load_scenario_file(f)
    urls = {p.name: p.url for p in sc.pages}
    assert urls["订单列表页"] == "http://localhost:8001/orders.html"
    assert urls["发票列表页"] == "http://localhost:8002/invoice_list.html"
    assert sc.origins["order"] == "http://localhost:8001"


def test_scenario_unknown_origin_ref_is_hard_error(tmp_path):
    from framework.features.f02_semantic.scenario_generate import ScenarioError, load_scenario_file
    f = tmp_path / "y_origin.yml"
    f.write_text("""id: y_origin
origins: {order: http://localhost:8001}
scenario: 打开未声明的系统
pages:
  - name: 发票列表页
    url: ${invoice}/invoice_list.html
""", encoding="utf-8")
    with pytest.raises(ScenarioError) as ei:
        load_scenario_file(f)
    assert "invoice" in str(ei.value), "未声明的 ${origin} 必须硬红并点名是哪个名字"


def test_scenario_session_spread_must_be_declared(tmp_path):
    from framework.features.f02_semantic.scenario_generate import ScenarioError, load_scenario_file
    f = tmp_path / "z_origin.yml"
    f.write_text("""id: z_origin
origins: {order: http://localhost:8001}
scenario: 登录
login:
  url: http://localhost:8000/login.html
  scenario: 填账号密码后点登录
  wait: {url_not: login.html}
  session:
    token_from: url_param
    spread: [order, invoice]
pages:
  - name: 订单列表页
    url: ${order}/orders.html
""", encoding="utf-8")
    with pytest.raises(ScenarioError) as ei:
        load_scenario_file(f)
    assert "invoice" in str(ei.value), "session.spread 里未声明的 origin 必须硬红"


# ---------------------------------------------------------------- 4. 唯一入口 / 不许各写一份
def test_spread_session_is_the_single_implementation():
    src = _src(GEN)
    assert "def _spread_session(" in src, "跨 origin 会话铺开没有唯一实现 `_spread_session`"
    gen_scripts = REPO / "scripts" / "generated"
    if gen_scripts.exists():
        for py in gen_scripts.rglob("*.py"):
            body = py.read_text(encoding="utf-8", errors="replace")
            if "localStorage.setItem" in body and "_spread_session" not in body and "_harness" not in py.name:
                pytest.fail(f"{py} 自己实现了 localStorage 注入 —— 必须走 _spread_session 唯一入口")


def test_login_lines_append_spread_only_when_declared():
    from framework.features.f02_semantic.generator_generate import _login_lines_for
    plain = {"login": {"login_url": "/login.html", "scenario": "s", "wait": {"url_not": "login.html"},
                       "steps": [{"op": "fill", "element": "账号", "value": "u"}]}}
    joined = "\n".join(_login_lines_for(plain, "http://localhost:8000"))
    assert "_spread_session" not in joined, "没声明 session 的用例不该出现会话铺开（零副作用）"

    withspread = {"origins": {"order": "http://localhost:8001"},
                  "login": {"login_url": "/login.html", "scenario": "s",
                            "wait": {"url_not": "login.html"},
                            "steps": [{"op": "fill", "element": "账号", "value": "u"}],
                            "session": {"token_from": "url_param", "param": "token",
                                        "store": "localStorage", "key": "demo_token",
                                        "spread": ["order"]}}}
    joined2 = "\n".join(_login_lines_for(withspread, "http://localhost:8000"))
    assert "_spread_session" in joined2 and "'order'" in joined2, (
        "声明了 session.spread 就必须生成会话铺开调用（含生成期 origin 快照作为兜底）")
