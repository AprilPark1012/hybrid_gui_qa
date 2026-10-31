"""V8.7.21 判据：行容器提示的**噪音预算**（方案 A′+A）。

由来（2026-10-29 用户两次真机实测，53 条稳定复现）：
  V8.7.18 的「同一容器里有一个重复控件 -> 整容器逐个提示」在真链路上是**纯噪音**：

    登录页 / container_heading='演示系统登录'（探针快照实测 7 个控件）
        账号、密码、登 录、用这个账号填入(x4)
        「用这个账号填入」是 demo 的 4 个**快捷登录链接**（并列按钮，不是行！）
        它一重复 -> 账号/密码/登录 全被牵连 -> **18 条噪音**

    订单详情页 / container_heading='详细信息'（探针快照实测 15 个控件）
        行内控件（行类型/单位/收入，各 x3）
        表格外按钮（保存/新增行/取消/关闭/全选，各 x1）
        空名单元格（role=cell，名字为空）
        -> **35 条噪音**，其中 15 条是「」空名字

  根因：`container_heading` 的粒度是「**区块标题**」，它不知道表格边界在哪 ——
    同一个 heading 里既装表格行、又装表格外按钮、还装空单元格。

修法（两道闸门）：
  A′ 判据：容器内 multi_match>1 的控件**种类数 >= 2** 才算「真行容器」。
            登录页只有 1 种 -> 不算 -> 整区不提；
            详细信息有 3 种 -> 算。
            （**空名字不算一种** —— 否则 `「」`x15 会让任意容器都"种类够"）
  A  汇总：真行容器**只打一行汇总**列出单实例控件名，不再逐个刷屏。

守六件事：
  ① 1 种重复的容器（克隆登录页场景）-> 只提那 1 个精准的，**不扩散**；
  ② >=2 种重复的容器（克隆详情页场景）-> 打**恰好一行**汇总，点名单实例控件；
  ③ **空名字控件永不提示**（`「」` 是 role=cell 的空单元格，提示无意义）；
  ④ **噪音预算**：把两个真实场景合起来跑，输出**总行数 <= 5**（V8.7.18 是 53 条）；
  ⑤ **不许改数据**：`multi_match` 原值不变、单实例控件不被加上该键；
  ⑥ **单实例控件不许被说成「必须」**（探测时确实只有 1 个，只能说「需要时请给」）。
"""
from __future__ import annotations

from pathlib import Path

from framework.features.f02_semantic.explorer_explore import _collapse_row_repeats

REPO = Path(__file__).resolve().parents[2]


def _item(name: str, *, page: str, heading: str, role: str = "textbox",
          multi_match: int | None = None, token: str = "") -> dict:
    it = {"name": name, "help_text": name, "page": page, "container_heading": heading,
          "ctx_token": token, "tag": "input", "role": role}
    if multi_match is not None:
        it["multi_match"] = multi_match
    return it


def _login_page() -> list[dict]:
    """克隆真实登录页：1 种重复控件（4 个快捷登录链接）+ 3 个单实例控件。"""
    return [
        _item("用这个账号填入 →", page="登录页", heading="演示系统登录", role="button"),
        _item("用这个账号填入 →", page="登录页", heading="演示系统登录", role="button"),
        _item("用这个账号填入 →", page="登录页", heading="演示系统登录", role="button"),
        _item("用这个账号填入 →", page="登录页", heading="演示系统登录", role="button"),
        _item("账号", page="登录页", heading="演示系统登录"),
        _item("密码", page="登录页", heading="演示系统登录"),
        _item("登 录", page="登录页", heading="演示系统登录", role="button"),
    ]


def _detail_page() -> list[dict]:
    """克隆真实订单详情页「详细信息」区：3 种重复控件 + 表外按钮 + 空名单元格。"""
    return [
        _item("单位", page="订单详情页", heading="详细信息", role="combobox"),
        _item("单位", page="订单详情页", heading="详细信息", role="combobox"),
        _item("单位", page="订单详情页", heading="详细信息", role="combobox"),
        _item("行类型", page="订单详情页", heading="详细信息", role="combobox"),
        _item("行类型", page="订单详情页", heading="详细信息", role="combobox"),
        _item("行类型", page="订单详情页", heading="详细信息", role="combobox"),
        _item("收入", page="订单详情页", heading="详细信息"),
        _item("收入", page="订单详情页", heading="详细信息"),
        _item("收入", page="订单详情页", heading="详细信息"),
        _item("保存", page="订单详情页", heading="详细信息", role="button"),
        _item("新增行", page="订单详情页", heading="详细信息", role="button"),
        _item("取消", page="订单详情页", heading="详细信息", role="button"),
        _item("", page="订单详情页", heading="详细信息", role="cell"),
        _item("", page="订单详情页", heading="详细信息", role="cell"),
        _item("", page="订单详情页", heading="详细信息", role="cell"),
    ]


# ---------------- ① 1 种重复 -> 不扩散 ----------------

def test_single_duplicate_kind_does_not_spread(capsys) -> None:
    """① 登录页那种「只有 1 种重复控件」的区**不扩散**（V8.7.18 在这里出了 18 条噪音）。"""
    _collapse_row_repeats(_login_page())
    out = capsys.readouterr().out

    # 那 1 个真重复控件仍要被精准点名（这是对的，它有 4 个）
    assert "用这个账号填入" in out, "真重复控件反而没提示了"
    # 3 个单实例控件一个都不许被牵连
    # [!] 必须用「」包住精确匹配 —— 第一版写成 "账号" not in out，
    #   结果被「用这个**账号**填入」这个真重复控件的名字误命中（判据自己报假红）。
    for nm in ("账号", "密码", "登 录"):
        assert f"「{nm}」" not in out, (
            f"「{nm}」被牵连提示了 —— 它在登录表单里，不是行内控件；"
            f"这正是 V8.7.18 那 18 条噪音的来源"
        )
    assert "行容器" not in out, "只有 1 种重复控件的区不该被当成行容器"


# ---------------- ② >=2 种重复 -> 恰好一行汇总 ----------------

def test_multi_kind_container_gets_exactly_one_summary(capsys) -> None:
    """② 详情页那种「>=2 种重复」的区要打汇总，且**只打一行**。"""
    _collapse_row_repeats(_detail_page())
    out = capsys.readouterr().out
    lines = [l for l in out.splitlines() if l.strip()]

    summary = [l for l in lines if "行容器" in l]
    assert len(summary) == 1, (
        f"汇总行应恰好 1 行，实际 {len(summary)} 行 —— 又变成逐个刷屏了:\n"
        + "\n".join(x.strip()[:110] for x in summary[:6])
    )
    sm = summary[0]
    # 汇总要说明有几种重复控件、并点名区内的单实例控件
    assert "3 种重复控件" in sm, f"汇总没说明重复控件种类数：{sm.strip()[:110]}"
    for nm in ("保存", "新增行", "取消"):
        assert nm in sm, f"汇总里没点名单实例控件「{nm}」：{sm.strip()[:110]}"


# ---------------- ③ 空名字永不提示 ----------------

def test_blank_name_is_never_flagged(capsys) -> None:
    """③ 空名字控件（role=cell 的空单元格）永不提示 —— V8.7.18 这里出了 15 条「」。"""
    items = [
        # 3 种真重复，同时混进一个空名字且它也重复
        _item("单位", page="P", heading="H", role="combobox"),
        _item("单位", page="P", heading="H", role="combobox"),
        _item("行类型", page="P", heading="H", role="combobox"),
        _item("行类型", page="P", heading="H", role="combobox"),
        _item("", page="P", heading="H", role="cell"),
        _item("", page="P", heading="H", role="cell"),
        _item("", page="P", heading="H", role="cell"),
    ]
    _collapse_row_repeats(items)
    out = capsys.readouterr().out
    assert "「」" not in out, f"空名字控件仍被提示了（无意义噪音）：{out.strip()[:200]}"


def test_blank_name_does_not_count_as_a_kind(capsys) -> None:
    """③ 空名字**不能**算「一种重复控件」—— 否则任意容器都能凑够 2 种、误判成行容器。"""
    items = [
        # 只有 1 种真重复（数量 x3）+ 一堆空名字
        _item("数量", page="P", heading="H", role="combobox"),
        _item("数量", page="P", heading="H", role="combobox"),
        _item("数量", page="P", heading="H", role="combobox"),
        _item("", page="P", heading="H", role="cell"),
        _item("", page="P", heading="H", role="cell"),
        _item("", page="P", heading="H", role="cell"),
        _item("保存", page="P", heading="H", role="button"),
    ]
    _collapse_row_repeats(items)
    out = capsys.readouterr().out
    assert "行容器" not in out, (
        "空名字被当成了一种重复控件 -> 1 种真重复凑成了 2 种 -> 误判成行容器"
    )
    assert "保存" not in out, "「保存」被牵连提示了"


# ---------------- ④ 噪音预算（核心） ----------------

def test_noise_budget_both_real_pages(capsys) -> None:
    """④ 把两个真实页面合起来跑，**总输出行数 <= 5**（V8.7.18 实测 53 条）。"""
    items = _login_page() + _detail_page()
    _collapse_row_repeats(items)
    out = capsys.readouterr().out
    lines = [l for l in out.splitlines() if l.strip()]
    assert len(lines) <= 5, (
        f"噪音超预算：{len(lines)} 行（V8.7.18 实测 53 条，预算 5 行）。实际输出:\n"
        + "\n".join(x.strip()[:110] for x in lines)
    )
    # 而且真实的那几条必须都在
    assert "用这个账号填入" in out, "登录页的真重复控件漏了"
    for nm in ("单位", "行类型", "收入"):
        assert nm in out, f"详情页的真重复控件「{nm}」漏了"


# ---------------- ⑤ 不许改数据 ----------------

def test_does_not_mutate_data(capsys) -> None:
    """⑤ 只提示、不改数据：`multi_match` 原值不变；单实例控件不被加上该键。"""
    items = _login_page() + _detail_page()
    _collapse_row_repeats(items)
    capsys.readouterr()

    by_name = {}
    for it in items:
        by_name.setdefault(it["name"], []).append(it)
    # 真重复控件：multi_match 应仍是收敛后的值（4 / 3），不许被改成别的
    assert by_name["用这个账号填入 →"][0]["multi_match"] == 4
    assert by_name["单位"][0]["multi_match"] == 3
    # 单实例控件不许被塞 multi_match（塞了会让质量闸误拦单行场景）
    for nm in ("账号", "密码", "保存", "新增行"):
        assert "multi_match" not in by_name[nm][0], (
            f"单实例控件「{nm}」被塞了 multi_match —— 只提示、绝不改数据"
        )


# ---------------- ⑥ 措辞：单实例不许说「必须」 ----------------

def test_singleton_wording_is_not_mandatory(capsys) -> None:
    """⑥ 汇总里的单实例控件只能说「需要时请给」，不许说「必须」。"""
    _collapse_row_repeats(_detail_page())
    out = capsys.readouterr().out
    for line in out.splitlines():
        if "单实例控件" in line:
            assert "必须" not in line, (
                f"单实例控件的措辞许是「必须」（探测时确实只有 1 个）：{line.strip()[:110]}"
            )
