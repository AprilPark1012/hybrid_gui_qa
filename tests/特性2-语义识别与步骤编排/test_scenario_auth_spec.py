"""场景「登录前置」声明（P22 批 5 · J6）—— 秒级，不需 demo / 浏览器。

背景（真值 · P22 §十）：目标系统需要登录 -> 探测与执行两侧都得"先登录"；而声明必须**由场景提供**
（框架不该懂任何具体系统的登录表单）。本判据钉住四件事：

  (1) 场景能声明 `auth:` 段并被正确解析（含 `password_env` 形式 —— 真实系统不该把口令写进场景文件）；
  (2) 声明**不合法 -> 当场报错**（静默忽略会变成"以为登录了、其实没登录"的假绿）；
  (3) [!] **凭据不许进 cases 产物**（`case_extra()` 不带 auth）—— `cases/` 是要入库、甚至要交付的；
  (4) 登录实现本身：URL 拼接正确 + **密码为空必须抛**（绝不静默当成"已经登录过"）。

跑法（秒级）：
    python -m pytest tests/特性2-语义识别与步骤编排/test_scenario_auth_spec.py -q
"""
from __future__ import annotations

import pytest

from framework.tools.generate.scenario import ScenarioError, load_scenario_file
from framework.tools.run import login as L

BASE_YML = """
id: t_auth
title: 登录前置判据用场景
pages:
  - name: 订单列表页
    url: http://localhost:8000/orders.html
    page: 订单列表页说明
scenario: |
  1. 打开订单列表页。
"""


def _write(tmp_path, extra: str):
    p = tmp_path / "t_auth.yml"
    p.write_text(BASE_YML + extra, encoding="utf-8")
    return p


def test_auth_parsed_with_defaults(tmp_path):
    """判据 1a：auth 段被解析，login_api 有默认值、token_key 原样带出。"""
    p = _write(tmp_path, """
auth:
  username: super
  password: super@123
  token_key: demo_token
""")
    sc = load_scenario_file(p)
    spec = sc.auth_spec()
    assert spec["username"] == "super", spec
    assert spec["login_api"] == "/api/login", f"login_api 应有默认值：{spec}"
    assert spec["token_key"] == "demo_token", spec
    assert spec["password"] == "super@123", spec


def test_auth_password_env_form(tmp_path):
    """判据 1b：`password_env` 形式（真实系统的推荐写法）也解析出来，且不落明文口令。"""
    p = _write(tmp_path, """
auth:
  login_api: /api/login
  username: admin
  password_env: MY_PWD
""")
    sc = load_scenario_file(p)
    spec = sc.auth_spec()
    assert spec["password"] == "" and spec["password_env"] == "MY_PWD", spec
    assert any("token_key" in w for w in sc.warnings), (
        f"未声明 token_key 应有一条告警（否则页面仍显示未登录）：{sc.warnings}")


@pytest.mark.parametrize("extra,因为", [
    ("\nauth:\n  password: x\n", "缺 username"),
    ("\nauth:\n  username: super\n", "既无 password 也无 password_env"),
    ("\nauth: not-a-map\n", "auth 不是映射"),
])
def test_negative_bad_auth_raises(tmp_path, extra, 因为):
    """判据 2（负向）：声明不合法必须当场报错（静默忽略 = 假的"已登录"）。"""
    p = _write(tmp_path, extra)
    with pytest.raises(ScenarioError):
        load_scenario_file(p)


def test_credentials_never_enter_case_artifacts(tmp_path):
    """判据 3（安全）：`case_extra()` 不许带 auth/口令 —— cases 产物是要入库的。"""
    p = _write(tmp_path, """
auth:
  username: super
  password: super@123
  token_key: demo_token
""")
    sc = load_scenario_file(p)
    extra = sc.case_extra()
    blob = repr(extra)
    assert "auth" not in extra, f"case_extra 不该带 auth 字段：{sorted(extra)}"
    assert "super@123" not in blob, "口令绝不能进 cases 产物"


def test_auth_spec_returns_copy(tmp_path):
    """判据 4：`auth_spec()` 返回副本（改它不该影响场景对象）。"""
    p = _write(tmp_path, "\nauth:\n  username: u\n  password: p\n")
    sc = load_scenario_file(p)
    sc.auth_spec()["username"] = "改坏了"
    assert sc.auth_spec()["username"] == "u", "auth_spec() 必须返回副本，否则调用方会污染场景对象"


def test_resolve_spec_url_join_and_env(monkeypatch):
    """判据 5：相对 login_api 拼成绝对地址；password_env 从环境变量取。"""
    monkeypatch.setenv("P22_PWD", "from-env")
    sp = L.resolve_spec("http://localhost:8000",
                        {"login_api": "/api/login", "username": "u",
                         "password_env": "P22_PWD", "token_key": "k"})
    assert sp["login_api"] == "http://localhost:8000/api/login", sp
    assert sp["password"] == "from-env", sp
    sp2 = L.resolve_spec("http://localhost:8000/",
                         {"login_api": "auth/login", "username": "u", "password": "x"})
    assert sp2["login_api"] == "http://localhost:8000/auth/login", sp2
    assert L.resolve_spec("http://localhost:8000", {}) == {}, "没有 auth 声明 -> 空 spec（不假装要登录）"


def test_negative_empty_password_must_raise():
    """判据 6（负向）：密码为空 -> 必须抛（不许静默当成"已经登录过"）。"""
    with pytest.raises(RuntimeError):
        L.login_token({"login_api": "http://127.0.0.1:9/api/login", "username": "u", "password": ""})


def test_describe_never_leaks_password():
    """判据 7（安全）：日志用的 describe() 不许出现口令。"""
    text = L.describe({"login_api": "/api/login", "username": "u",
                       "password": "超级机密口令", "token_key": "k"})
    assert "超级机密口令" not in text, f"日志描述泄漏了口令：{text}"
