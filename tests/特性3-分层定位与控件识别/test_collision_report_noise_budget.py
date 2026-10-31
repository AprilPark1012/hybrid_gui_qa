"""V8.7.27 判据：跨页同名元素的警告必须**合并汇总**，不许逐个刷屏。

由来（2026-10-30 用户真机日志）：
    某场景刷了 **100+ 行**同构警告：

        [explore] [!] 跨页同名元素 'HT_1001' 出现在 合同列表页、订单列表页、订单详情页、发票列表页
          -> 已唯一化为 HT_1001@合同列表页、HT_1001@订单列表页、HT_1001@订单详情页、HT_1001@发票列表页
        ...（HT_1002 ~ HT_1013 各 2 行，共 26 行；generate 侧再来一遍）

    行为是**对的**（合同号在多个页面的列表里都有，必须跨页唯一化），
    但**提示变成噪音就等于没提示** —— 这 100+ 行把「登录前置 ok」「行容器提示」
    「跨页列警告」等真信息全埋了。与 V8.7.18 的行容器 53 条是同一个道理。

用户 2026-10-30 选 A：**同前缀合并成一行汇总**。

守五件事：
  1. 13 个同前缀元素 -> **行数 <= 4**（噪音预算；旧版是 26 行）；
  2. **单个不合并**（那不是噪音，合并反而让人多绕一层）；
  3. **信息不丢**：合并后仍要说清「多少个」「哪些页」「共多少个唯一化名」；
  4. explore 与 generate **共用同一入口**（`shared/collision_report`，不许各写一份）；
  5. 空名/None 不许炸、也不许产出空行。
"""
from __future__ import annotations

from pathlib import Path

from framework.shared.collision_report import format_collisions, root_of

REPO = Path(__file__).resolve().parents[2]

_PAGES4 = ["合同列表页", "订单列表页", "订单详情页", "发票列表页"]


def _many(n: int = 13) -> list[dict]:
    """真实场景：n 个合同号，每个都出现在 4 个页。"""
    return [{"semantic_name": f"HT_{1000 + i}", "pages": list(_PAGES4)} for i in range(1, n + 1)]


# ---------------- 1. 噪音预算 ----------------

def test_noise_budget_for_many_collisions() -> None:
    """1) 13 个同前缀元素 -> 合并后行数 <= 4（旧版每个名字 2 行 = 26 行）。"""
    lines = format_collisions(_many(13), prefix="      [explore]")
    assert len(lines) <= 4, f"合并没有生效，仍有 {len(lines)} 行：\n" + "\n".join(lines)
    body = "\n".join(lines)
    assert "13 个" in body, f"没说清有几个（信息丢了）：{body}"
    assert "HT_1001" in body and "HT_1013" in body, f"没给出首尾名字（范围信息丢了）：{body}"


# ---------------- 2. 单个不合并 ----------------

def test_single_collision_is_printed_as_is() -> None:
    """2) 单个同名元素 -> 原样打印（合并单个是过度设计，反而增加阅读成本）。"""
    coll = [{"semantic_name": "保存", "pages": ["订单详情页", "开票页"]}]
    lines = format_collisions(coll, prefix="      [explore]")
    assert len(lines) == 1, f"单个不该被合并成多行/零行：{lines}"
    assert "'保存'" in lines[0], lines[0]
    assert "保存@订单详情页" in lines[0], f"单个时要把唯一化结果写出来（可核对）：{lines[0]}"


# ---------------- 3. 信息不丢 ----------------

def test_summary_keeps_counts_and_pages() -> None:
    """3) 合并后的汇总必须给出：数量、涉及页、唯一化总数。"""
    lines = format_collisions(_many(13), prefix="      [explore]")
    body = "\n".join(lines)
    assert "13 个" in body, body
    assert "4 个页" in body, f"没说影响几个页：{body}"
    for p in _PAGES4:
        assert p in body, f"没列出页「{p}」：{body}"
    assert "52" in body, f"没说唯一化后共多少个（13x4=52）：{body}"
    # 要指出去哪看完整清单（否则等于信息被藏了）
    assert "probe_items" in body or "element_map" in body, f"没给完整清单的去处：{body}"


# ---------------- 4. 唯一入口 ----------------

def test_both_sides_use_the_same_entry() -> None:
    """4) explore 与 generate 必须共用 `shared/collision_report`，不许各写一份。"""
    for rel in ("framework/features/f02_semantic/explorer_explore.py",
                "framework/features/f02_semantic/generator_generate.py"):
        src = (REPO / rel).read_text(encoding="utf-8")
        assert "from framework.shared.collision_report import print_collisions" in src, (
            f"{rel} 没走唯一入口 `print_collisions`"
        )
        # 不许再自己拼那句文案（旧实现的指纹）
        assert "跨页同名元素 {c['semantic_name']!r} 出现在" not in src, (
            f"{rel} 里还留着旧的逐个打印实现 —— 两处各写一份必然漂移"
        )


# ---------------- 5. 边界 ----------------

def test_edge_cases_do_not_break() -> None:
    """5) 空列表 / 空名 / 缺页 -> 不炸、不产空行、不编造。"""
    assert format_collisions(None) == []
    assert format_collisions([]) == []
    assert format_collisions([{"semantic_name": "", "pages": []}]) == []
    lines = format_collisions([{"semantic_name": "X1", "pages": []}], prefix="[p]")
    assert len(lines) == 1 and "X1" in lines[0], lines


def test_root_of_strips_trailing_digits_only() -> None:
    """6) `root_of` 只剥**尾部数字**，不动中间、不动纯文本。"""
    assert root_of("HT_1001") == "HT_"
    assert root_of("HT_1013") == "HT_"
    assert root_of("保存") == "保存", "没有尾部数字的不许动"
    assert root_of("发票-12") == "发票-"
    assert root_of("") == ""
    assert root_of("123") == "", "全数字 -> 根为空（调用方会当同组处理，这是可接受退化）"
