"""路径拼接的「容器层」契约判据（2026-09-24 补 —— 二类才抓住的漏网，提前到一类）。

**为什么要有它**（真实事故）：`tests/` 结构迁移时，`verify_element_ambiguity.py` 的夹具路径写成
`BASE / "featureTest" / "fixtures" / …` —— 这是**第三种写法**（既不是 `REPO / "x"`，也不是
`parents[N] / "x"`），我的两条批量替换规则都没覆盖 ⇒ 路径少了 `tests/` 容器层 ⇒
`Page.goto: ERR_FILE_NOT_FOUND` ⇒ **只有跑完二类才暴露（45 分钟）**。
同类错误会以任何「某变量 / 目录名字面量」的形式出现 ⇒ 按写法枚举替换必漏。

本判据改成按**结构**审计：源码里任何 `… / "frameworkTest"` / `… / "featureTest"` 的拼接，
其左侧必须已经包含 `tests` 这一层（或本身就是权威常量 `TESTS_DIR`）。

判据：
  ① 全仓源码扫描：没有「拼接目录名却漏了 tests 容器层」的写法
  ② 负向自证：给一个漏层的样例，检查函数必须报出来（否则判据等于没写）
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TESTS_DIR_NAME = "tests"
NAMES = ("frameworkTest", "featureTest")
SKIP_DIRS = {".git", ".venv", "__pycache__", "output", "node_modules", "log"}
# 本文件自己的负向样例里就写着"漏层"的串 ⇒ 扫描时必须跳过它（否则判据自指、永远红）
SELF = Path(__file__).name

# 形如：<左侧表达式> / "frameworkTest"
_JOIN = re.compile(r'([A-Za-z_][\w\.\[\]\(\)]*|"[^"]*"|\'[^\']*\')\s*/\s*"(%s)"' % "|".join(NAMES))
# 这些标识符本身已经指向 tests/ 容器（权威常量）
_OK_LEFT_HINTS = ("TESTS_DIR",)


def scan_source(text: str) -> list[str]:
    """返回「拼接了目录名但左侧看不出 tests 容器层」的片段（纯函数，便于负向自证）。"""
    bad: list[str] = []
    for m in _JOIN.finditer(text):
        left = m.group(1)
        if TESTS_DIR_NAME in left or any(h in left for h in _OK_LEFT_HINTS):
            continue
        bad.append(m.group(0))
    return bad


def test_no_join_misses_tests_container():
    """★核心：目录名拼接必须带上 tests 容器层（漏了就是 ERR_FILE_NOT_FOUND 那一类）。"""
    offenders: list[str] = []
    for p in REPO.rglob("*.py"):
        if any(s in p.parts for s in SKIP_DIRS) or p.name == SELF:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for frag in scan_source(text):
            offenders.append(f"{p.relative_to(REPO)}: {frag}")
    assert not offenders, (
        "这些路径拼接漏了 tests 容器层（2026-09-24 实测踩过：夹具指向 <仓库>/featureTest/… ⇒ 二类红）：\n  - "
        + "\n  - ".join(offenders))


def test_negative_missing_container_is_detected():
    """负向自证：漏层样例必须被检查函数报出来，且正确样例不许误报。"""
    bad_sample = 'FIX = BASE / "featureTest" / "fixtures" / "x.html"\n'
    ok_sample = 'FIX = REPO / "tests" / "featureTest" / "fixtures" / "x.html"\n'
    ok_sample2 = 'FIX = TESTS_DIR / "frameworkTest" / "t.py"\n'
    assert scan_source(bad_sample) == ['BASE / "featureTest"'], scan_source(bad_sample)
    assert scan_source(ok_sample) == [], scan_source(ok_sample)
    assert scan_source(ok_sample2) == [], scan_source(ok_sample2)
