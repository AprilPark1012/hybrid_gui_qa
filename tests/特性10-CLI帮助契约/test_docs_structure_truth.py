# -*- coding: utf-8 -*-
"""特性10 · 文档结构真值契约：培训页/README 里画的目录结构，必须与磁盘**真实一致**。

为什么单独立这条（V8.6 加的）：
  审计发现文档里的目录树长期停留在旧版本 —— 例如
  · 培训页第 2 章曾整整一版是 V8.0 的 `framework/tools/{common,probe,explore,generate,run}`，
    而磁盘上早已是 `framework/features/f02..f11 + shared/`；
  · 文档写 `features/f01..f11`、且「每特性 `api.py` 是唯一入口」，
    而磁盘上**没有 f01、也没有任何 api.py**。
  这类错**不会自己暴露**：目录树是静态文本，没有命令会失败，读者照着找文件才撞墙。

判据形状（**守真值，不守格式**）：
  1. 文档里出现的 `framework/features/fNN_xxx/` 目录名，必须在磁盘上存在；
  2. 磁盘上的每个特性夹，必须能在培训页目录树里找到（防漏登记新特性）；
  3. 文档不许再把 `api.py` 说成「每特性唯一入口」（磁盘上没有这个文件）。
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HTML = REPO / "docs" / "training.html"
HTML_GEN = REPO / "build_tools" / "build_html.py"
README = REPO / "README.md"
FEATURES = REPO / "framework" / "features"

# 冻结历史区（changelog）里的旧结构描述不算错 —— 那是历史事实，按 R9 口径不改。
# 这几条是历史上真实存在过的目录名，允许出现在版本史里。
LEGACY_OK = {"f01_core"}


def feature_dirs_on_disk() -> set[str]:
    return {p.name for p in FEATURES.iterdir()
            if p.is_dir() and re.fullmatch(r"f\d\d_\w+", p.name)}


def test_documented_feature_dirs_exist_on_disk():
    """文档里写的每个 `fNN_xxx/` 特性夹，磁盘上必须真的有。"""
    html = HTML.read_text(encoding="utf-8")
    # 只取目录树形态（行首带树线）里的特性夹名，避免把正文闲聊也算进来
    documented = set(re.findall(r"[│├└─\s]*(f\d\d_[a-z_]+)/", html))
    missing = sorted(d for d in documented - feature_dirs_on_disk() if d not in LEGACY_OK)
    assert not missing, (
        "文档里登记了磁盘上不存在的特性夹（目录树是静态文本，写错不会自己报错，"
        "读者照着找文件才撞墙）：\n  - " + "\n  - ".join(missing)
        + f"\n磁盘实际: {sorted(feature_dirs_on_disk())}"
    )


def test_every_feature_dir_is_documented():
    """磁盘上的每个特性夹，都必须在培训页目录树里出现（防漏登记新特性）。"""
    html = HTML.read_text(encoding="utf-8")
    missing = sorted(d for d in feature_dirs_on_disk() if d not in html)
    assert not missing, (
        "这些特性夹在磁盘上存在、但培训页目录树里没登记（新增特性要同步文档）：\n  - "
        + "\n  - ".join(missing)
    )


# 冻结历史区的锚（与 tests/特性9-质量闸门体系/test_docs_sync.py::live_body 同一口径）：
# 「版本与更新记录」之后是历史事实，按 R9 口径原样保留 —— 那里出现旧结构名**不算错**。
_CHANGELOG_ANCHOR = re.compile(r'<span class="n">A</span>版本与更新记录')


def _live(src: str) -> str:
    """只取**正文区**（切掉版本史附录）。"""
    m = _CHANGELOG_ANCHOR.search(src)
    return src[:m.start()] if m else src


def test_no_f01_nor_api_py_claims_in_live_docs():
    """**正文区**不许再声称 `f01` 存在、或「每特性 `api.py` 是唯一入口」（磁盘上都没有）。

    [!] 查的是**产物** `docs/training.html` 与 `README.md`，不是生成器 `build_html.py` ——
    生成器里 changelog 是**数据**（`changed=[...]`），HTML 锚切不进去，切了也不准；
    产物里「版本与更新记录」之后才是冻结历史，切得准。口径与 `test_docs_sync.live_body` 一致。
    """
    for path in (README, HTML):
        src = _live(path.read_text(encoding="utf-8"))
        assert "features/f01..f11" not in src, (
            f"{path.name} 正文区仍写 `features/f01..f11` —— 磁盘上特性夹是 f02..f11（没有 f01）"
        )
        # 「api.py 是唯一入口」这句在 V8.6 前就不成立了：全仓根本没有 api.py。
        # [!] 必须匹配**完整断言句**，不能只匹配「每特性 api.py」——
        #     10.7 的目标文案里就有「不许声称有 f01 或每特性 api.py」这种**否定式说明**，
        #     只匹配短语会把判据自己绊倒（实测踩到）。
        for bad in ("每特性 api.py 是唯一入口", "同一特性只有 `api.py` 一个入口",
                    "同一特性只有 `api.py` 一个入口。"):
            assert bad not in src, (
                f"{path.name} 正文区仍声称「{bad}」—— 全仓不存在 api.py"
            )


def test_api_py_really_absent():
    """反向自证：全仓确实没有 api.py。哪天真的加了，这条会红，提醒删掉上面那条判据。"""
    found = [str(p.relative_to(REPO)) for p in REPO.rglob("api.py")
             if ".venv" not in str(p) and "__pycache__" not in str(p)]
    assert not found, (
        "现在存在 api.py 了（判据假设它不存在）：" + str(found)
        + " —— 若这是刻意新增的「唯一入口」，请更新 test_no_f01_nor_api_py_claims_in_live_docs"
    )
