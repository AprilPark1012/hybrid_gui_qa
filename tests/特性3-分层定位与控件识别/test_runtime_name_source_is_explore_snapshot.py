# -*- coding: utf-8 -*-
"""特性3 · 运行时的「语义名 -> 控件」必须以 **explore 快照**为唯一权威（V8.4.3+）。

事故（Windows 实测，干净环境跑 explore --ai）：
    AI 照它**看到的**清单写了 `保存@订单详情页`；运行时却报
    「语义名歧义：'保存@订单详情页' 逐字不存在，而清单里有多个名字含它」。

根因：运行时用 `probe_page(page)` **单页重探**建索引，而 explore 是**跨页合并** ——
      两条链路命名规则不同，同一个控件因此有两个名字：

| 链路 | 命名规则 | 实测结果 |
|---|---|---|
| explore（AI 看到的就是这份） | 跨页重名 -> `原名@页名` | `保存@订单详情页` |
| 运行时单页重探 | 同页容器唯一化 -> `原名@容器` | `保存` / `保存@订单详情` |

**凡跨页重名控件（保存 / 取消 / 返回 / 编辑…）都会踩** —— 不是某场景的特例。

口径：快照是**唯一权威**；现场重探只补快照里没有的（弹窗打开后才出现的控件），且必须出声。
"""
import json
import pathlib
import re
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from framework.tools.generate import probe_snapshot as PS          # noqa: E402
from framework.tools.generate.generator import generate_scripts    # noqa: E402
from framework.tools.common.config import CASES_DIR as _CASES       # noqa: E402

#: 事故现场的那两个名字（一个来自 explore，一个来自单页重探）
_EXPLORE_NAME = "保存@订单详情页"
_PROBE_ONLY_NAMES = ["保存", "保存@订单详情", "取消@订单详情", "取消@详细信息"]


def _element_map(names) -> dict:
    return {"steps": [{"element": {"semantic_name": n, "role": "button", "name": n}}
                      for n in names]}


# ---------- ① 快照：读 / 写 / 往返 ----------

def test_element_map_items_keep_explore_names_verbatim():
    """从 element_map 取条目时，名字必须**逐字保留**（含 `@页名` 后缀）——不许再加工。"""
    items = PS.items_from_element_map(_element_map([_EXPLORE_NAME, "编辑@订单详情页"]))
    assert [i["semantic_name"] for i in items] == [_EXPLORE_NAME, "编辑@订单详情页"]


def test_snapshot_roundtrip(tmp_path):
    """写出去再读回来：名字与定位所需字段都要在。"""
    items = [{"semantic_name": _EXPLORE_NAME, "role": "button", "name": "保存",
              "test_id": "btn-save", "anchor": {"row_text": "SO-1"},
              "label": "", "name_source": "x"}]
    p = PS.write_snapshot(tmp_path, items)
    assert p and p.name == PS.SNAPSHOT_FILENAME
    idx = PS.load_snapshot(tmp_path)
    assert _EXPLORE_NAME in idx
    got = idx[_EXPLORE_NAME]
    assert got["role"] == "button" and got["test_id"] == "btn-save" and got["anchor"]
    assert "name_source" not in got, "快照只留定位要用的字段（体积可控、形状稳定）"


def test_duplicate_names_keep_first():
    """同名条目只留首个（快照里不许有重复键把真值挤掉）。"""
    items = [{"semantic_name": "保存@页A", "role": "button", "test_id": "t1"},
             {"semantic_name": "保存@页A", "role": "button", "test_id": "t2"}]
    assert PS.index_from_items(items)["保存@页A"]["test_id"] == "t1"


def test_empty_items_write_nothing(tmp_path):
    """没有条目就不落快照（留个空文件只会误导运行时）。"""
    assert PS.write_snapshot(tmp_path, []) is None
    assert not (tmp_path / PS.SNAPSHOT_FILENAME).exists()


def test_missing_or_broken_snapshot_returns_empty(tmp_path):
    """快照缺失/损坏 -> 返回空 dict（运行时退回现场探测，不许炸）。"""
    assert PS.load_snapshot(tmp_path) == {}
    (tmp_path / PS.SNAPSHOT_FILENAME).write_text("{ 不是合法 json", encoding="utf-8")
    assert PS.load_snapshot(tmp_path) == {}


# ---------- ② 核心：事故里那个名字必须能逐字命中 ----------

def test_the_exact_failing_name_resolves_from_snapshot():
    """事故复现：`保存@订单详情页` 在快照索引里**逐字命中**（修前它在运行时索引里不存在）。"""
    idx = PS.index_from_items(PS.items_from_element_map(_element_map([_EXPLORE_NAME])))
    assert _EXPLORE_NAME in idx, "快照里都没有它 -> 事故必然复发"


def test_single_page_probe_names_would_not_match_reverse_check():
    """【反向自证】单页重探那套名字里**没有** `保存@订单详情页`
    -> 证明「快照优先」不是装饰，是这条查找能成立的**必要条件**。

    同时钉住「为什么它会报歧义」：两个重探名字都是它的子串/超串
    -> 模糊兜底看到多候选 -> 按设计直接失败（宁可失败，不许猜着点）。
    """
    idx = PS.index_from_items([{"semantic_name": n} for n in _PROBE_ONLY_NAMES])
    assert _EXPLORE_NAME not in idx
    fuzzy = [k for k in idx if k and (k in _EXPLORE_NAME or _EXPLORE_NAME in k)]
    assert len(fuzzy) >= 2, f"应至少两个候选才会触发歧义，实际 {fuzzy}"


# ---------- ③ generate 必须真的落快照 ----------

def test_generate_writes_snapshot_next_to_generated_scripts(tmp_path):
    """generate 后，`<scripts_dir>/generated/_probe_snapshot.json` 必须存在且覆盖用例所需名字。"""
    needed = set()
    for f in sorted(_CASES.rglob("*.json")):
        c = json.loads(f.read_text(encoding="utf-8"))
        needed |= {st.get("element") for st in c.get("steps", [])}
        needed |= {a.get("element") for a in c.get("asserts", [])}
    needed.discard(None)
    needed.discard("")
    assert needed, "前置：用例里应引用语义名"

    snap_src = tmp_path / "element_map_full.json"
    snap_src.write_text(json.dumps(_element_map(sorted(needed)), ensure_ascii=False),
                        encoding="utf-8")
    out = tmp_path / "scripts"
    generate_scripts(cases_dir=_CASES, scripts_dir=out, element_map_path=snap_src)

    written = out / "generated" / PS.SNAPSHOT_FILENAME
    assert written.exists(), "generate 没落 explore 快照 -> 运行时又要靠单页重探（事故根因）"
    idx = PS.load_snapshot(out / "generated")
    miss = sorted(n for n in needed if n not in idx)
    assert not miss, f"用例引用的名字没进快照（运行时必然找不到）：{miss[:5]}"


# ---------- ④ 渲染出来的 harness：先灌快照、再探测 ----------

def _harness_code() -> str:
    """渲染后的 harness 文本，**剔掉注释**再断言（注释骗过判据本项目已犯 4 次）。"""
    from framework.tools.generate.generator import _render_harness
    src = _render_harness()
    return "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))


def test_harness_seeds_index_from_snapshot():
    code = _harness_code()
    assert "_seed_index_from_snapshot()" in code, "harness 没有装载 explore 快照的入口"
    assert "load_snapshot" in code, "harness 没调用快照模块"


def test_snapshot_seeding_happens_before_live_probe():
    """顺序必须正确：装载快照**在**现场重探之前 —— 否则重探先占坑，快照名永远进不去。"""
    code = _harness_code()
    i_seed = code.index("_seed_index_from_snapshot()", code.index("def _item_for("))
    i_probe = code.index("probe_page(page)", i_seed)
    assert i_seed < i_probe, "先重探后灌快照 -> 快照等于没用"


def test_harness_snapshot_path_is_relative_to_harness_file():
    """快照要按 `__file__` 同目录找 —— 不许写死绝对路径/依赖环境变量（跨平台 + 可搬运）。"""
    code = _harness_code()
    i = code.index("def _seed_index_from_snapshot")
    seg = code[i:i + 1400]
    assert "__file__" in seg, "快照路径没按 harness 自身位置推导 -> 换个目录就找不到"
    assert "/home/" not in seg and "C:\\\\" not in seg, "出现了绝对路径"


def test_missing_name_falls_back_to_probe_with_notice():
    """快照里没有的名字（弹层后新出现的控件）仍要能重探，且**必须出声**留痕。"""
    code = _harness_code()
    i = code.index("def _item_for(")
    seg = code[i:i + 1200]
    assert "probe_page(page)" in seg, "丢了现场重探的兜底能力"
    assert "不在 explore 快照里" in seg, "重探时必须打印留痕（静默重探 = 同样的坑再踩一次）"
