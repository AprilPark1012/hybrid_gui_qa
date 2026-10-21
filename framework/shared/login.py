"""登录前置：**探测与执行两侧共用的唯一实现**（P22 批 5 · 方案 H）。

背景（真值 · P22 §十）：
  · demo 加了登录后，**未登录访问业务页会被 `auth.js` 踢到 `/login.html`** -> 探针什么都探不到
    （拿到的是登录页控件）；
  · 而 `?demo_role=` 直连**不能切角色** —— `demo/app.py:670-671` 明确 400：
    「切换角色需要真实登录会话（测试角色头不支持切换）」-> 跨角色场景**必须走真登录**。

口径（L35 起）：`login:` 段写**自然语言**，登录步骤由**同一个规划器**在登录页上产出
（`framework/features/f02_semantic/login_flow_explore.py`），与业务步骤同一套 `op/desc/element`；
执行走**同一套定位栈**（`resolve_locator`）。本模块只保留"登录前置"这个**入口**与旧接口登录兼容分支。

历史口径（V8.5.1 的 `steps/by` 选择器写法，L35 已删除）：
  · 填表单要求框架懂每个系统的表单结构 -> 不通用；
  · 场景声明「登录接口 + 账号 + token 写进哪个 localStorage 键」-> **业务细节归场景，框架保持通用**；
  · 注入方式用 `context.add_init_script` -> 在**每个新文档创建前**执行，页面自己的 auth.js 读到的
    就是已登录态（比"先开页面再 setItem 再刷新"少一次刷新，也不与页面跳转逻辑抢跑）。

[!] 凭据：`password` 直写仅适用于**公开的演示凭据**；真实系统请用 `password_env`（从环境变量取），
   别把口令写进场景文件 / 生成物。
"""
from __future__ import annotations

import json
import os
import urllib.request


def resolve_spec(base_url: str, spec: dict) -> dict:
    """把场景声明的 `auth:` 段规范化成可用的登录参数（含按需从 env 取密码）。空 spec -> {}。"""
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
    """把 token 注入浏览器上下文的 localStorage（**每个新文档生效**）。未声明键名 -> False。"""
    if not token_key or not token:
        return False
    ctx.add_init_script(
        f"try {{ localStorage.setItem({token_key!r}, {token!r}); }} catch (e) {{}}")
    return True


def ensure_logged_in(ctx, base_url: str, spec: dict) -> dict:
    """登录前置的**唯一入口**（探针期与执行期共用）。

    [!] L35：登录声明写**自然语言**（`login.scenario`），登录步骤由同一个规划器在登录页上
    产出成普通 TestStep，再由 `login_flow_explore.run_login_steps` 用**同一套定位栈**执行。
    本函数是这条链的**唯一入口**（探测期 / 生成期 / 执行期都从这里进）。
    为什么必须两期共用一份实现：探针期登录失效时，探到的**只有登录页控件**，
    AI 手上没有业务页控件 => 它只能规划登录步骤（实测连写三次，被产出闸门拦下）。
    表现是"AI 不听话"，真因是**探针没登录**。

    旧口径（`login_api` + `token_key` 接口登录）作为兼容分支保留，但新场景应写 `login:`。
    """
    out = {"attempted": False, "ok": False, "reason": "", "mode": ""}
    spec = spec or {}
    if not spec:
        return out

    # ---- 新口径（L35）：自然语言登录 -> AI 规划的普通步骤 -> 同一套定位栈 ----
    # [!] 委托给 features 层（`login_flow_explore`）而不是自己实现：登录步骤用的定位栈
    #   （`resolve_locator`）住在 features/f03_locate，shared 不能反向依赖它 —— 所以这里
    #   只留**同签名的薄壳**（唯一入口不变，调用方零改动），实现在那边。
    if spec.get("scenario") or spec.get("steps"):
        out["attempted"] = True
        out["mode"] = "ui"
        try:
            page = None
            try:
                page = ctx.pages[0] if getattr(ctx, "pages", None) else None
            except Exception:                                       # noqa: BLE001
                page = None
            if page is None:
                page = ctx.new_page()
            from framework.features.f02_semantic.login_flow_explore import login_on_page
            r = login_on_page(page, spec, base_url)
            out["ok"] = bool(r.get("ok"))
            out["steps"] = r.get("steps", 0)
            if not out["ok"]:
                out["reason"] = str(r.get("reason") or "登录动作序列未完成")
        except Exception as e:                                      # noqa: BLE001
            out["reason"] = f"{type(e).__name__}: {e}"
        return out

    # ---- 旧口径：接口登录 + token 注入（兼容保留） ----
    sp = resolve_spec(base_url, spec)
    out["mode"] = "api"
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
        out["reason"] = "未声明 token_key -> 只做了接口登录、未注入 localStorage（页面可能仍显示未登录）"
    return out


def describe(spec: dict) -> str:
    """一行日志用的人类可读描述（**不含口令**）。"""
    sp = spec or {}
    if not sp:
        return "（无登录前置）"
    src = "env:" + str(sp.get("password_env")) if sp.get("password_env") else "inline"
    return (f"登录 {sp.get('username')}@{sp.get('login_api')}"
            f"（口令来源 {src} · token 键 {sp.get('token_key') or '未声明'}）")


# ==================== L35：登录链路 AI 化（原 V8.5.1 的 by 选择器口径已删除）====================
# 为什么另起这条：旧机制走 POST 接口 + token 注入，运行期还要读 `scripts/generated/_auth.json`
#   —— 那文件由生成期写出、却被 `.gitignore` 忽略 -> **不进交付包** -> 收包方 run 时登录前置
#   **静默失效**，报「元素语义未找到」而真因是"整条用例跑在登录页上"（排查方向被带偏）。
# 新口径（他 2026-10-11 定）：登录就是**登录页上的表单动作序列**，
#   探测期与执行期**共用同一份声明**，并且会**展开进用例**（跑挂了能直接看到"卡在登录"）。
# 框架层**零业务词**：不认识"账号/密码/登录"，只认"声明了一个 by 表达式 + 一个动作"。

class LoginSpecError(RuntimeError):
    """登录声明非法（缺值 / 定位表达式不认识）—— 一律**大声报**，绝不静默跳过。"""


def on_login_page(page, base_url="", spec=None):
    """判断当前是否**还停在登录页** —— 供报错文案用（把"卡在登录"直说出来）。

    为什么需要：实测真因是登录没生效，报错却指向"元素语义未找到"，把排查方向带偏一整天。
    """
    try:
        u = page.url or ""
    except Exception:
        return False
    u = u.lower()
    if "login" in u:
        return True
    # 还能在页面上解析到登录步骤的目标控件 -> 说明还在登录页（L35：步骤是普通 TestStep）
    from framework.features.f03_locate.element_map import ElementRef
    from framework.features.f03_locate.locator_bridge_locate import resolve_locator
    for s in ((spec or {}).get("steps") or []):
        el = (s or {}).get("element") if isinstance(s, dict) else None
        if not isinstance(el, dict) or not el.get("semantic_name"):
            continue
        try:
            if resolve_locator(page, ElementRef.from_dict(el)).get("ok"):
                return True
        except Exception:
            continue
    return False


def login_failure_hint(url=""):
    """卡在登录页时的标准提示：直指登录，不把方向带向"异步取数/弹层未渲染"。"""
    return (f"当前在**登录页**（{url}）—— 登录步骤未执行或失败，"
            "后续动作都在登录页上跑，所以报「元素未找到」是**表象**，真因是登录。"
            "请检查场景声明的登录动作序列（填账号 -> 填密码 -> 点登录 -> 等生效）。")
