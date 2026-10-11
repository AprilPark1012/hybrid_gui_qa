# -*- coding: utf-8 -*-
"""前置动作**唯一执行引擎**（2026-10-10 · A 方案）。

背景（干净环境 E2E 实录）：场景声明了「身份前置」`probe_pre: [超, 切换为订单管理员]`——
探测期跑得好好的（`前置动作已执行：['超', '切换为订单管理员']`），**执行期没人跑**：
AI 只生成了「切换为订单管理员」这一步，漏了点开头像菜单那一步 ->
`Locator.click: Element is not visible`（菜单项在 DOM 里、未展开时不可见）。

真问题不是"AI 少写一步"，而是**同一个「怎么到达这个身份」的知识只活在探测侧**：
- 探测侧：`_run_pre_actions` 会按声明的序列执行；
- 执行侧：什么都没有 -> 两套口径 = 同一个能力两个入口（本项目明令禁止）。

修法（2026-10-10 定 A 方案）：**引擎抽到执行层成为唯一入口**，
探测期（explorer）与执行期（生成物 harness）都调它 —— 声明式、零业务词、
任何"语义名看不出依赖关系"的前置（点开容器/菜单才能点到子项）都随声明的序列一起复现。

口径（继承自探测期那版，勿改）：
  · 每项只按**控件的 accessibility name** 找（button 优先，其次精确文本、最后子串）；
    **不接受 CSS selector** —— 与"不给 AI 猜 CSS"同一条铁律；
  · 找不到/点不动 -> 如实告警并继续（`quiet_missing=False` 时），不猜别的控件、不换做法；
  · 常规点击被拒 -> 先挑**同名里可见的那个**（只排除、不猜），全不可见才退 force 一次；
  · 有界：最多 5 步、每步有界超时；点击前有界等待目标就绪（异步注入的导航/菜单）。
"""
from __future__ import annotations

MAX_STEPS = 5
DEFAULT_PRE_WAIT_MS = 15000


def run_pre_actions(page, steps: list | None, page_name: str = "", *, per_step_ms: int = 5000,
                    quiet_missing: bool = False, require_all_resolvable: bool = False,
                    resolvable_wait_ms: int = 0, on_clicked=None, log_tag: str = "pre") -> list[str]:
    """按声明顺序执行前置动作，返回**实际点成功**的名字。

    :param page: playwright Page
    :param steps: 语义名序列（场景级 `probe_pre` 或页面级 `pages[].pre`）
    :param require_all_resolvable: **场景级**用 —— 只有本页能解析到**全部**名字时才整组执行，
        否则整组留给后面的页。为什么必需：逐页尝试会让"半个序列"在错误页面上假成功
        （实测：登录页上用子串匹配点到了「超级管理员」并报"已执行"，导致真正的业务页上
        只剩第 2 步、菜单没被点开、菜单项永远不可见）。
    :param on_clicked: 回调 `(语义名, locator)`，在**点击之前**调用。
        探测期用它记下"点击那一刻"的定位锚（点完之后控件的可访问名会变，事后再取不到）。
    :param log_tag: 日志前缀（探测期 "explore"，执行期 "setup"）。
    """
    done: list[str] = []
    seq = [str(x).strip() for x in (steps or []) if str(x).strip()]
    if not seq:
        return done
    if len(seq) > MAX_STEPS:
        print(f"      [{log_tag}] [!] [{page_name}] pre 声明了 {len(seq)} 步（上限 {MAX_STEPS}）"
              f"→ 只执行前 {MAX_STEPS} 步")
        seq = seq[:MAX_STEPS]

    def _resolve(nm):
        """按**可访问名**解析控件：button 优先 → 精确文本 → 子串文本（不接受 CSS，铁律）。"""
        loc = page.get_by_role("button", name=nm)
        if not loc.count():
            # 先**精确**文本匹配：`get_by_text` 默认子串匹配，页面异步内容未就绪时会命中
            # "碰巧含这个字"的无关元素（实测点了「超」报"已执行"，其实点的是别的元素）。
            loc = page.get_by_text(nm, exact=True)
        if not loc.count():
            loc = page.get_by_text(nm)
        return loc

    # 场景级整组语义（见 docstring 的 require_all_resolvable）
    if require_all_resolvable and seq:
        _unresolved = []
        # 「一个都解析不到」与「部分解析到」要分开（实测教训）：
        #   · 整组**一个都没有** -> 这页根本不是目标页（比如产物脚本第一次导航落在登录页）
        #     => 别白等满上限，给个短窗就走，留到后面的导航再试；
        #   · 有些解析到、有些没到 -> 页面是对的、异步注入还没完 => 等满上限。
        _any_now = any(_resolve(_nm).count() for _nm in seq)
        _deadline_ms = resolvable_wait_ms if _any_now else min(resolvable_wait_ms, 3000)
        for _nm in seq:
            # [!] 预检必须有界等待（2026-10-10 实测）：**执行期首次导航后立刻查 count 必然为 0** ——
            #   身份菜单/导航是 auth.js 拿 /api/me 之后**异步注入**的。不等就判「整组留到后面的页」，
            #   于是执行期一步都没跑（新口径下会当场抛：红得对，但没解决问题）。
            #   探测期 `resolvable_wait_ms=0`（保持即时：逐页探时不浪费）；执行期给 15s。
            _waited = 0
            while True:
                if _resolve(_nm).count():
                    break
                if _waited >= _deadline_ms:
                    _unresolved.append(_nm)
                    break
                page.wait_for_timeout(300)
                _waited += 300
        if _unresolved:
            if not quiet_missing:
                print(f"      [{log_tag}] [info] [{page_name}] 场景级前置"
                      f"「{'、'.join(_unresolved)}」本页解析不到 -> **整组留到后面的页**"
                      f"（不许只跑半个序列：假成功会污染后续步骤）")
            return done

    for nm in seq:
        try:
            loc = _resolve(nm)
            if not loc.count():
                if not quiet_missing:
                    print(f"      [{log_tag}] [!] [{page_name}] 前置动作「{nm}」没找到 -> 跳过"
                          f"（不猜别的控件去点）")
                continue

            # 点击前先**等目标就绪**：页面"就绪契约"达成 != 要点的东西已经存在 ——
            # demo 的导航（含身份菜单）是 auth.js 拿 /api/me 之后**异步注入**的。
            # 有界等待（上限由 HYBRID_PRE_ACTION_WAIT_MS 给，默认 15s），期间只观察不动作。
            _wait_ms = DEFAULT_PRE_WAIT_MS
            try:
                import os as _os
                _wait_ms = int(_os.environ.get("HYBRID_PRE_ACTION_WAIT_MS") or DEFAULT_PRE_WAIT_MS)
            except Exception:                                          # noqa: BLE001
                pass
            _w = 0
            while _w < _wait_ms:
                if any(loc.nth(_k).is_visible() for _k in range(loc.count())):
                    break
                page.wait_for_timeout(300)
                _w += 300

            # [!] 锚必须在**点击之前**取（点完控件的可访问名会变，事后取不到）。
            if on_clicked is not None:
                try:
                    on_clicked(nm, loc.first)
                except Exception:                                      # noqa: BLE001
                    pass

            try:
                loc.first.click(timeout=per_step_ms)
            except Exception as _first:                                # noqa: BLE001
                # 常规点击被拒的两条真实成因：
                #   (a) 权限上下文不同（目标 aria-disabled）=> TimeoutError；
                #   (b) **同名隐藏项挡路**（菜单项在 DOM 里有未展开的副本）=> .first 命中不可见
                #       => `Element is not visible`。
                # 口径：先挑**同名里可见的那个**（只排除、不猜），全不可见再退 force 一次。
                # [!] 这行提示必须印在**尝试之前**：旧写法印在 force 之后，force 也失败时
                #   它根本不出现，日志会误导人以为 force 没触发。
                _n = loc.count()
                _vis = [i for i in range(_n) if loc.nth(i).is_visible()]
                print(f"      [{log_tag}] [info] [{page_name}] 前置动作「{nm}」常规点击被拒"
                      f"（{type(_first).__name__}）-> 同名 {_n} 个 / 可见 {len(_vis)} 个")
                if _vis:
                    loc.nth(_vis[0]).click(timeout=per_step_ms)
                    print(f"      [{log_tag}] [info] [{page_name}] 前置动作「{nm}」已改用可见项点一次")
                else:
                    loc.first.click(timeout=per_step_ms, force=True)
                    print(f"      [{log_tag}] [info] [{page_name}] 前置动作「{nm}」全不可见 -> 改用 force 点一次")
            page.wait_for_timeout(350)
            done.append(nm)
        except Exception as e:                                        # noqa: BLE001
            print(f"      [{log_tag}] [!] [{page_name}] 前置动作「{nm}」执行失败"
                  f"（{type(e).__name__}: {str(e)[:80]}）-> 继续后面的步骤")
    if done:
        print(f"      [{log_tag}] [fast] [{page_name}] 前置动作已执行：{done}")
    return done
