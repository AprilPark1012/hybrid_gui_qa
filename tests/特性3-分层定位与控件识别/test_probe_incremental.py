# -*- coding: utf-8 -*-
"""特性3 · D3 方案：`expand` 重扫时**只探新增元素**（V8.3.7 性能治理 D3）。

背景（2026-10-08 实测，七页现场探测 260.9s）：
    `expand` 118.2s 是最大单项。原因：`expand_and_collect` 的等待循环里，只要「信号变了」
    就调一次 `probe_page` —— 而 `probe_page` 会对**整页每个元素**打 ~13 次 CDP 往返
    （212 元素 ≈ 2756 次往返 ≈ 60s）。于是「点开一个菜单」的代价 = 把整页重新探一遍，
    哪怕新增的只有 4 个控件。

D3 的做法（**语义等价，只去掉重复劳动**）：
    循环里先用一次**廉价的** `evaluate` 拿回「当前可见交互元素的 key→索引」映射；与上一轮
    对比得到**新出现的索引**；`probe_page(..., only_indexes={...})` **只探这些**。
    `only_indexes=None`（默认）= 全探，**行为与改造前逐字段一致**。

判据口径：全部用假页/假函数，**不写死任何业务页面名、控件名**（能力与场景解耦）。
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PROBE = REPO / "framework" / "tools" / "probe" / "probe.py"
EXPANDABLE = REPO / "framework" / "tools" / "probe" / "expandable.py"


def _src(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _fn_src(p: Path, name: str) -> str:
    src = _src(p)
    lines = src.splitlines()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return "\n".join(lines[node.lineno - 1: node.end_lineno])
    raise AssertionError(f"{p.name} 里找不到 {name}()")


# ---------------------------------------------------------------- 接口存在性

def test_probe_page_accepts_only_indexes():
    """`probe_page` 必须支持「只探指定索引」（默认 None = 全探，保持兼容）。"""
    src = _src(PROBE)
    assert "only_indexes" in src, (
        "probe.py 的 probe_page 缺少 `only_indexes` 参数 —— D3 的「只探新增」没有落点"
    )
    tree = ast.parse(src)
    fn = next((n for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef) and n.name == "probe_page"), None)
    assert fn is not None, "找不到 probe_page()"
    names = [a.arg for a in fn.args.args] + [a.arg for a in fn.args.kwonlyargs]
    assert "only_indexes" in names, f"probe_page 形参里没有 only_indexes：{names}"
    # 默认必须是 None（否则所有既有调用方行为被改）
    kw_defaults = dict(zip(fn.args.kwonlyargs, fn.args.kw_defaults))
    if "only_indexes" in kw_defaults:
        d = kw_defaults["only_indexes"]
        assert isinstance(d, ast.Constant) and d.value is None, (
            "`only_indexes` 的默认值必须是 None（不改既有调用方行为）"
        )


def test_visible_key_map_exists():
    """必须有一个「一次 evaluate 拿回 key→索引」的廉价函数，供循环做增量判断。"""
    src = _src(PROBE) + _src(EXPANDABLE)
    assert "visible_key_map" in src, (
        "缺少 `visible_key_map(...)` —— 增量判断需要「一次往返拿回索引对齐的 key 表」"
    )


# ---------------------------------------------------------------- 行为判据（假页驱动）

class _FakeLoc:
    def __init__(self, tag="button"):
        self._tag = tag
        self.clicked = 0

    def evaluate(self, script, *a, **kw):
        return self._tag

    def get_attribute(self, *_a, **_kw):
        return None

    @property
    def first(self):
        return self


class _FakeLocs:
    def __init__(self, n):
        self._n = n

    def count(self):
        return self._n

    def nth(self, i):
        return _FakeLoc()


class _FakePage:
    """最小假页：只提供 probe_page 真正会用到的那几样。"""

    def __init__(self, n=3):
        self._n = n

    def locator(self, *_a, **_kw):
        return _FakeLocs(self._n)


def _scan_count(monkeypatch, monkeypatch_n, total, only_indexes):
    """观测点 = `_visible(page, loc)` 被调用几次 —— 它每个元素恰好过一次。

    为什么选它：probe_page 的循环体是一整段（没有可 patch 的单元素构造函数），
    而 `_visible` 是循环里**第一个**每元素必过的调用，且被 patch 掉后不会碰真实 DOM。
    """
    import framework.tools.probe.probe as P

    calls: list[int] = []
    monkeypatch.setattr(P, "_visible", lambda page, loc: (calls.append(1), False)[1])
    try:
        P.probe_page(_FakePage(total), only_indexes=only_indexes)
    except Exception:                                          # noqa: BLE001
        pass                                                   # 只需知道「看了几个元素」
    return len(calls)


def test_only_indexes_none_scans_all(monkeypatch):
    """等价性：`only_indexes=None` 时，逐个元素都要被看到（与改造前一致）。"""
    assert _scan_count(monkeypatch, None, 4, None) == 4


def test_only_indexes_restricts_scan(monkeypatch):
    """D3 核心：`only_indexes={0,2}` 时**只**看这两个索引。"""
    n = _scan_count(monkeypatch, None, 5, {0, 2})
    assert n == 2, f"应只看 2 个元素，实际 {n}（= 又全探了一遍，D3 没生效）"


def test_empty_only_indexes_scans_nothing(monkeypatch):
    """没有新元素（空集合）-> 一个都不看（别退化成"空集合=全探"，那就白做了）。"""
    n = _scan_count(monkeypatch, None, 5, set())
    assert n == 0, f"空集合必须表示「一个都不探」，实际看了 {n} 个"


# ---------------------------------------------------------------- 接线判据

def test_expand_loop_uses_incremental_scan():
    """接线：`expand_and_collect` 的等待循环必须用「增量 key 判断 + only_indexes」。"""
    body = _fn_src(EXPANDABLE, "expand_and_collect")
    assert "visible_key_map(" in body, (
        "expand_and_collect 的等待循环没有用 visible_key_map 做增量判断 —— D3 没接上"
    )
    assert "only_indexes" in body, (
        "expand_and_collect 调 probe_page 时没有传 only_indexes —— 还是全页重扫"
    )


def test_expand_loop_no_longer_full_rescans():
    """回退即红：循环里不许再出现「信号一变就全页 probe_page(page)」的裸调用。

    口径：**循环体**内必须带 `only_indexes`。循环外的「兜底补扫」允许裸调用 ——
    它是安全网（整段等待一次都没扫过时补一次），不是循环里的重复劳动。
    """
    body = _fn_src(EXPANDABLE, "expand_and_collect")
    loop = body[body.index("while time.time() < deadline"):]
    # 只允许「拿不到索引表」那条保守分支里的全探（它在 `if not kmap:` 里，且整段最多一次）；
    # 其余位置出现裸调用即视为 D3 回退。
    guarded = loop.split("if not kmap:")[1].split("continue")[0]
    rest = loop.replace(guarded, "")
    assert "probe_page(page)" not in rest.split("# 兜底")[0], (
        "expand_and_collect 循环里仍有 `probe_page(page)` 全页重扫 —— D3 被回退了"
    )
