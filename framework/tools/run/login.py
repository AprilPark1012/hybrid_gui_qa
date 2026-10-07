"""登录前置：**探测与执行两侧共用的唯一实现**（P22 批 5 · 方案 H）。

背景（真值 · P22 §十）：
  · demo 加了登录后，**未登录访问业务页会被 `auth.js` 踢到 `/login.html`** ⇒ 探针什么都探不到
    （拿到的是登录页控件）；
  · 而 `?demo_role=` 直连**不能切角色** —— `demo/app.py:670-671` 明确 400：
    「切换角色需要真实登录会话（测试角色头不支持切换）」⇒ 跨角色场景**必须走真登录**。

口径（为什么是"场景声明式"、而不是"框架去填登录表单"）：
  · 填表单要求框架懂每个系统的表单结构 ⇒ 不通用；
  · 场景声明「登录接口 + 账号 + token 写进哪个 localStorage 键」⇒ **业务细节归场景，框架保持通用**；
  · 注入方式用 `context.add_init_script` ⇒ 在**每个新文档创建前**执行，页面自己的 auth.js 读到的
    就是已登录态（比"先开页面再 setItem 再刷新"少一次刷新，也不与页面跳转逻辑抢跑）。

⚠️ 凭据：`password` 直写仅适用于**公开的演示凭据**；真实系统请用 `password_env`（从环境变量取），
   别把口令写进场景文件 / 生成物。
"""
from __future__ import annotations

import json
import os
import urllib.request


def resolve_spec(base_url: str, spec: dict) -> dict:
    """把场景声明的 `auth:` 段规范化成可用的登录参数（含按需从 env 取密码）。空 spec ⇒ {}。"""
    if not spec:
        return {}
    api = str(spec.get("login_api") or "/api/login").strip()
    if not api.startswith("http"):
        api = base_url.rstrip("/") + ("" if api.startswith("/") else "/") + api
    pwd = str(spec.get("password") or "")
    env_name = str(spec.get("password_env") or "").strip()
    if not pwd and env_name:
        pwd = os.environ.get(env_name, "")
    return {"login_api": api, "username": str(spec.get("username") or ""),
            "password": pwd, "token_key": str(spec.get("token_key") or ""),
            "password_env": env_name}


def login_token(spec: dict, timeout: int = 10) -> str:
    """POST 登录接口拿 token。**失败如实抛**（绝不静默当成"已经登录过"）。"""
    if not spec.get("username"):
        raise RuntimeError("登录前置：缺少 username")
    if not spec.get("password"):
        raise RuntimeError(
            f"登录前置：密码为空（password_env={spec.get('password_env') or '未声明'}"
            f"）—— 环境变量没设置？")
    body = json.dumps({"username": spec["username"], "password": spec["password"]}).encode("utf-8")
    req = urllib.request.Request(spec["login_api"], data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8"))
    tok = str((data or {}).get("token") or "")
    if not tok:
        raise RuntimeError(f"登录前置：{spec['login_api']} 未返回 token"
                           f"（响应字段：{sorted((data or {}).keys())[:8]}）")
    return tok


def install_token(ctx, token_key: str, token: str) -> bool:
    """把 token 注入浏览器上下文的 localStorage（**每个新文档生效**）。未声明键名 ⇒ False。"""
    if not token_key or not token:
        return False
    ctx.add_init_script(
        f"try {{ localStorage.setItem({token_key!r}, {token!r}); }} catch (e) {{}}")
    return True


def ensure_logged_in(ctx, base_url: str, spec: dict) -> dict:
    """组合动作：拿 token → 注入上下文。返回摘要 dict（供日志与判据使用，不抛）。"""
    out = {"attempted": False, "ok": False, "reason": ""}
    sp = resolve_spec(base_url, spec or {})
    if not sp:
        return out
    out["attempted"] = True
    try:
        tok = login_token(sp)
    except Exception as e:                                          # noqa: BLE001
        out["reason"] = f"{type(e).__name__}: {e}"
        return out
    if install_token(ctx, sp["token_key"], tok):
        out["ok"] = True
        out["token_len"] = len(tok)
    else:
        out["reason"] = "未声明 token_key ⇒ 只做了接口登录、未注入 localStorage（页面可能仍显示未登录）"
    return out


def describe(spec: dict) -> str:
    """一行日志用的人类可读描述（**不含口令**）。"""
    sp = spec or {}
    if not sp:
        return "（无登录前置）"
    src = "env:" + str(sp.get("password_env")) if sp.get("password_env") else "inline"
    return (f"登录 {sp.get('username')}@{sp.get('login_api')}"
            f"（口令来源 {src} · token 键 {sp.get('token_key') or '未声明'}）")
