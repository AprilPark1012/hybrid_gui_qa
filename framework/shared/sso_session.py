# -*- coding: utf-8 -*-
"""跨 origin 会话铺开 —— **唯一实现**（探针期与运行期共用）。

## 为什么需要
真实业务里合同 / 订单 / 发票是**不同业务系统**（不同 origin），登录却只有一套 SSO。
会话存在浏览器的 `localStorage` / cookie 里，**按 origin 隔离**：SSO 登录只落在登录那个 origin，
访问另一个 origin 的业务页会被踢回**它自己**的登录页。实测（本机 demo）：

    登录落在 8000 -> 访问 8001/orders.html -> 落到 8001/login.html?next=%2Forders.html

铺开之后：

    登录落在 8000 -> 铺到 order/invoice -> 8001/orders.html 停在 8001/orders.html（不再被踢）

## 唯一入口
`spread_session(context, spec, gen_origins, origin_map=None)`

- `context`：Playwright BrowserContext（探针期与 harness 都拿到同一个 context）；
- `spec`：场景 `login.session` 段 `{token_from, param, store, key, spread}`；
- `gen_origins`：用例里落下的生成期 `origins` 快照 `{名字: http://host:port}`（兜底地址来源）；
- `origin_map`：运行期 `HYBRID_ORIGIN_MAP` 解析出来的映射（**优先**，用于换环境）。

**不许在别处再写一份**（探针期和运行期各写一份 = 两份实现两份 bug）。
"""
from __future__ import annotations

import urllib.parse as _up


def spread_session(context, spec, gen_origins=None, origin_map=None, log=print) -> list:
    """把当前会话铺到 `spec["spread"]` 列出的各个 origin，返回成功的 origin 名单。

    - 取 token：`token_from=url_param` -> 从当前页地址的 `?param=` 里取；
      （扫码/接口登录等其它来源以后按需加分支，**不要在调用方各写一套**）
    - 落地方式：新标签页 + `add_init_script` 往该 origin 的 `localStorage` 写 key，然后访问一次；
    - 任何一个 origin 失败都只**告警不中止**（跨 origin 是增强能力，不该让整轮跑挂）。
    """
    spec = dict(spec or {})
    gen_origins = dict(gen_origins or {})
    origin_map = dict(origin_map or {})
    token = ""

    src = str(spec.get("token_from") or "url_param")
    if src == "url_param":
        cur_url = ""
        for pg in getattr(context, "pages", []) or []:
            cur_url = getattr(pg, "url", "") or cur_url
        q = _up.parse_qs(_up.urlsplit(cur_url).query)
        token = (q.get(str(spec.get("param") or "token")) or [""])[0]
    if not token:
        log("[warn] 跨 origin 会话铺开：没能从登录后的地址取到 token -> 跳过"
            "（后面跨 origin 的页面可能被判未登录，请查 login.session 的 param 与 SSO 回跳地址）")
        return []

    key = str(spec.get("key") or "demo_token")
    done: list[str] = []
    for name in spec.get("spread") or []:
        name = str(name)
        base = (_resolve(name, origin_map) or _resolve(name, gen_origins) or "").rstrip("/")
        if not base:
            log(f"[warn] 跨 origin 会话铺开：origin {name!r} 既没有 HYBRID_ORIGIN_MAP 映射、"
                f"生成期也没记地址 -> 跳过")
            continue
        page = context.new_page()
        try:
            page.add_init_script(f"try{{localStorage.setItem({key!r}, {token!r});}}catch(e){{}}")
            page.goto(base + "/", wait_until="domcontentloaded", timeout=15000)
            page.wait_for_timeout(120)
            done.append(name)
        except Exception as e:                                      # noqa: BLE001
            log(f"[warn] 跨 origin 会话铺开失败：{name} ({base}) -> {type(e).__name__}: {e}")
        finally:
            page.close()
    if done:
        log(f"[TEST] 跨 origin 会话已铺到 {len(done)} 个 origin: {', '.join(done)}")
    return done


def _resolve(name: str, table: dict) -> str:
    v = table.get(name) or ""
    return str(v).strip()
