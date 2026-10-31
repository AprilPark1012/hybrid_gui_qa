"""V8.7.18 判据：行容器内的**单实例**控件也必须被提示给行定位（方案 A）。

由来（2026-10-29 用户真链路日志，第 1 轮 434s 白跑）：
  `期次号@开票页` 在探测那一刻页面上只有 1 行 -> `multi_match=1` -> 框架不提示 AI 给行定位；
  而实跑到第 50 步时开票页已有 2 行 -> `RuntimeError: 本页有 2 个同名匹配（期次号@开票页）`
  -> 整个用例 FAILED。
  同页的「数量」「单位」因为探测时就有 3 个才被提示到 —— **只提示了它们，漏了期次号**。

根因是「探测时刻 != 运行时刻」：静态检测看不出会随行数增长的控件。

方案 A（用户 2026-10-29 选择）：
  **同一容器里只要有一个控件 `multi_match>1`，这个容器就是「行容器」** ——
  里面所有控件（哪怕是单实例）都可能随行数增长，都要提醒 AI 给 `row_index` / `row_text`。

守四件事：
  ① 行容器内的单实例控件 -> **必须**被提示（这是本判据存在的理由）；
  ② 不在行容器内的单实例控件 -> **不许**提示（否则满屏噪声，AI 会忽略真提示）；
  ③ 只提示、**不改数据**（`multi_match` 不许被改写，否则质量闸会误拦单行场景）；
  ④ 原有 `multi_match>1` 的提示**照旧**（不因放宽而丢失）。
"""
from __future__ import annotations

from framework.features.f02_semantic.explorer_explore import _collapse_row_repeats


def _item(name: str, *, page="开票页", heading="应收发票创建", token="",
          tag="select", role="combobox") -> dict:
    return {"name": name, "help_text": name, "page": page,
            "container_heading": heading, "ctx_token": token,
            "tag": tag, "role": role}


def test_single_instance_in_row_container_is_flagged(capsys) -> None:
    """① 行容器内的单实例控件（探测时 1 个）**仍要被提到**。

    复刻实测场景：开票页同一区域里「数量」「单位」各有 3 个（multi_match>1），
    「期次号」只有 1 个 —— 三者同容器。

    [!] V8.7.21 改了**呈现方式**（方案 A′+A，用户 2026-10-29 定）：
        V8.7.18 是「每个单实例控件打一条」，在真链路上 53 条稳定复现、全是噪音
        （登录页 18 条 + 订单详情页 35 条，其中 15 条是空名字的表格单元格）。
        现在改成**该区打一行汇总**，把单实例控件名列出来。
        => 本判据守的是「**信息不许丢**」（期次号必须出现在输出里），
           而不再钉死「建议」这个词 —— 措辞变了但结论没变。
    """
    items = [
        _item("数量"), _item("数量"), _item("数量"),
        _item("单位"), _item("单位"), _item("单位"),
        _item("期次号"),          # ← 只有 1 个，但它同样在行容器里
    ]
    _collapse_row_repeats(items)
    out = capsys.readouterr().out
    assert "期次号" in out, (
        "行容器内的单实例控件没被提到 —— 实跑到该步时行数变了就会多匹配，"
        "正是 2026-10-29 那次 434s 白跑的根因"
    )
    assert "行容器" in out, "提示里没说明它在行容器内，AI 不知道为什么要给 row_index"
    # 汇总行必须说明「这是单实例控件」（区别于点名必须给行定位的那些）
    assert "单实例控件" in out or "另有" in out, "没区分开「必须给行定位」和「单实例控件」两类"
    # 单实例控件不许被说成「必须」
    _line = next(l for l in out.splitlines() if "期次号" in l)
    assert "必须" not in _line, (
        f"单实例控件的提示口径不许是「必须」（探测时确实只有 1 个）：{_line.strip()[:100]}"
    )


def test_singleton_outside_row_container_is_quiet(capsys) -> None:
    """② 不在行容器里的单实例控件不许提示（防噪声）。"""
    items = [
        _item("数量"), _item("数量"), _item("数量"),          # 行容器
        _item("搜索", page="订单列表页", heading="工具栏", token="tm"),   # 另一容器，单实例
    ]
    _collapse_row_repeats(items)
    out = capsys.readouterr().out
    assert "搜索" not in out, "不同容器的单实例控件被误提示了 —— 会把真提示淹掉"


def test_multi_match_items_still_flagged(capsys) -> None:
    """④ 原有 multi_match>1 的提示不能因为放宽而丢失。"""
    items = [_item("数量"), _item("数量"), _item("数量")]
    _collapse_row_repeats(items)
    out = capsys.readouterr().out
    assert "multi_match=3" in out, "重复控件本身没被提示"
    assert "必须" in out, "重复控件的口径应是「必须」给行定位"


def test_does_not_mutate_multi_match(capsys) -> None:
    """③ 只提示不改数据：单实例控件的 multi_match 不许被写成 2。

    [!] 只检查**单实例控件**（期次号）。重复项（数量）收敛后本来就该带上 multi_match=3，
        之前写了个「所有原本无 multi_match 的项都不许有该键」的全量断言 —— 那是错的，
        会把正常的收敛结果判红（自查时被自己抓出来）。
    """
    items = [_item("数量"), _item("数量"), _item("数量"), _item("期次号")]
    _collapse_row_repeats(items)
    capsys.readouterr()
    peak = [it for it in items if it.get("help_text") == "期次号"]
    assert len(peak) == 1, "期次号被意外收敛/丢弃"
    assert int(peak[0].get("multi_match") or 1) == 1, (
        "单实例控件被改写了 multi_match —— 质量闸会据此误拦单行场景（只提示、不改数据）"
    )
    assert "multi_match" not in peak[0], (
        "给单实例控件加了 multi_match 键 —— 下游 `int(it.get('multi_match') or 1)` 虽能容错，"
        "但语义上它就不该被标成重复控件"
    )


def test_collapse_still_dedupes(capsys) -> None:
    """收敛本身不能坏：3 个「数量」仍要合成 1 条。"""
    items = [_item("数量"), _item("数量"), _item("数量")]
    _collapse_row_repeats(items)
    capsys.readouterr()
    assert len(items) == 1, f"重复控件没被收敛，剩 {len(items)} 条"
    assert items[0].get("multi_match") == 3
