"""跨页同名元素的**汇报格式**（唯一入口）。

由来（2026-10-30 用户真机日志）：
    实测某场景刷了 **100+ 行**同构警告：

        [explore] [!] 跨页同名元素 'HT_1001' 出现在 合同列表页、订单列表页、订单详情页、发票列表页
          -> 已唯一化为 HT_1001@合同列表页、HT_1001@订单列表页、HT_1001@订单详情页、HT_1001@发票列表页
        [explore] [!] 跨页同名元素 'HT_1002' 出现在 ...（同样 4 行）
        ...（一直到 HT_1013）

    行为是**对的**（合同号在多个页面的列表里都有，框架必须做跨页唯一化），
    但**提示变成噪音就等于没提示**（与 V8.7.18 行容器 53 条同一个道理）：
    这 100 多行把「登录前置 ok」「行容器提示」等真信息全埋了。

口径（用户 2026-10-30 选 A）：
    **同前缀合并成一行汇总** —— 按「剥掉尾部数字得到的根」分组（`HT_1001`~`HT_1013`
    的根都是 `HT_`），一组打一行；根内只有 1 个时仍按原样逐个打（那不算噪音）。

    [!] 合并**不丢信息**：完整清单在 `ElementMap` 的 `pages[].probe_items` 里，
    日志只需要给出「有多少个、是哪一类、影响了哪些页」。

为什么放 shared：`explorer_explore`（探测期）与 `generator_generate`（生成期）
两处都要打这条警告 —— 各写一份必然漂移（V8.7.26 的教训就是「改了一个漏了另一个」）。
"""
from __future__ import annotations

import re

__all__ = ["root_of", "print_collisions", "format_collisions"]

_TRAILING_DIGITS = re.compile(r"\d+$")


def root_of(name: str) -> str:
    """取「根」：剥掉尾部数字。

    `HT_1001` -> `HT_`，`发票-12` -> `发票-`，`保存` -> `保存`（没有尾部数字 -> 原样）。
    """
    s = str(name or "").strip()
    if not s:
        return ""
    return _TRAILING_DIGITS.sub("", s)


def format_collisions(collisions: list | None, *, prefix: str = "[explore]") -> list[str]:
    """把 collisions 压成**少量**可打印行（每个前缀一行）。

    `collisions` 形如 `[{"semantic_name": "HT_1001", "pages": ["合同列表页", ...]}, ...]`
    （`uniquify_across_pages()` 的返回值）。返回要打印的行列表。
    """
    if not collisions:
        return []

    # 按「根」分组（保持首次出现的顺序，便于人读）
    groups: dict[str, list[dict]] = {}
    order: list[str] = []
    for c in collisions:
        nm = str(c.get("semantic_name") or "").strip()
        if not nm:
            continue
        r = root_of(nm)
        if r not in groups:
            groups[r] = []
            order.append(r)
        groups[r].append(c)

    pad = " " * len(prefix)
    lines: list[str] = []
    for r in order:
        items = groups[r]
        if len(items) == 1:
            # 单个 -> 原样（这不是噪音，合并反而让人多绕一层）
            c = items[0]
            nm = str(c.get("semantic_name") or "").strip()
            pages = [str(p) for p in (c.get("pages") or [])]
            lines.append(
                f"{prefix} [!] 跨页同名元素 {nm!r} 出现在 {'、'.join(pages)}"
                f" -> 已唯一化为 {'、'.join(f'{nm}@{p}' for p in pages)}"
            )
            continue
        names = [str(c.get("semantic_name") or "").strip() for c in items]
        all_pages: list[str] = []
        for c in items:
            for p in (c.get("pages") or []):
                if p not in all_pages:
                    all_pages.append(p)
        n_pairs = sum(len(c.get("pages") or []) for c in items)
        first, last = names[0], names[-1]
        span = first if first == last else f"{first} ~ {last}"
        lines.append(
            f"{prefix} [!] 跨页同名元素 {len(items)} 个（同前缀 {r!r}）：{span}"
        )
        lines.append(
            f"{pad}    影响 {len(all_pages)} 个页：{'、'.join(all_pages)}"
        )
        lines.append(
            f"{pad}    -> 已全部唯一化为 <名字>@<页名>，共 {n_pairs} 个"
            f"（完整清单见 element_map 的 pages[].probe_items，日志不再逐条刷）"
        )
    return lines


def print_collisions(collisions: list | None, *, prefix: str = "[explore]") -> int:
    """打印合并后的警告，返回打印行数（便于判据断言「噪音预算」）。"""
    lines = format_collisions(collisions, prefix=prefix)
    for ln in lines:
        print(ln, flush=True)
    return len(lines)
