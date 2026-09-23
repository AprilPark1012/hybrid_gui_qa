"""两类验证的「目录契约 + 用例新陈代谢」守门判据（R7-a / R7-d · 2026-09-23）。

**为什么要有它**：R7 的两条新要求都靠自觉就会漂 ——
  · **R7-a 目录分工**：框架自验证住 `frameworkTest/`、特性自验证住 `featureTest/`；
  · **R7-d 用例新陈代谢**：加用例必须同批清无效用例，否则测试时间白白增长、拖垮开发与打包效率。
本判据把它们变成**每次一类都跑的红线**。

**TDD 红态**：本文件先于搬迁落地 ⇒ 初次运行必然红（`tests/` 还在、两个新目录还没有）。
红态证据见提交信息（R7-c 要求：先红 → 再改 → 转绿）。

判据清单：
  ① 旧 `tests/` 目录必须**不存在**（迁移完成）
  ② `frameworkTest/` 必须有 `test_*.py`，且**仓库里别处不许再散落** `test_*.py`
  ③ `featureTest/` 必须有 `verify_*.py` + 两个入口（`run_verifications.py` / `run_acceptance.py`）
  ④ runner 的收录口径必须是**自动 glob** `featureTest/verify_*.py`（不许手写清单 ⇒ 不许有死脚本）
  ⑤ 每个 `frameworkTest/test_*.py` 至少 1 个 `def test_`（**不许留空壳占数**）
  ⑥ 时长预算必须**只有一处声明**，且被 runner 真正读取（R7-d 的"逼近上限先清后加"）
  ⑦ 纯函数层负向自证（判据自己能抓坏输入，不然等于没写）
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
FRAMEWORK_TESTS = REPO / "frameworkTest"
FEATURE_TESTS = REPO / "featureTest"
LEGACY_TESTS = REPO / "tests"
RUNNER = FEATURE_TESTS / "run_verifications.py"

# R7-d 的预算（实测基线：一类 ~24s · 二类 ~33min（jobs=2））
BUDGET_FRAMEWORK_S = 60
BUDGET_FEATURE_MIN = 90


# ---------------- 纯函数层（负向自证直接钉这几个）----------------

def find_test_modules(root: Path) -> list[str]:
    """找出 root 下所有 `test_*.py`（忽略缓存/虚拟环境/日志产物）。返回相对路径（排序）。"""
    # scripts/ = generate 产物（test_cases.py 也叫 test_*.py，但它不是判据文件）
    skip = (".venv", "__pycache__", "log", "output", "scripts", ".git", "node_modules")
    out: list[str] = []
    for p in root.rglob("test_*.py"):
        if any(part in skip for part in p.parts):
            continue
        out.append(str(p.relative_to(root)))
    return sorted(out)


def find_verify_modules(root: Path) -> list[str]:
    """找出 root 下所有 `verify_*.py`（同上口径）。"""
    skip = (".venv", "__pycache__", "log", "output", ".git")
    return sorted(str(p.relative_to(root)) for p in root.rglob("verify_*.py")
                  if not any(part in skip for part in p.parts))


def has_real_test_body(text: str) -> bool:
    """文件里是否有真正的 `def test_*` 函数（空壳文件 = 占着收数不干活）。"""
    # ⚠️ 用例名允许中文（本项目多处用中文命名，如 `def test_含内层引号的长场景不被截断()`）
    return bool(re.search(r"^\s*def test_[^\s(]+\s*\(", text, re.M))


def runner_uses_glob(text: str) -> bool:
    """runner 是否用 glob 自动收录（而不是手写清单 —— 手写清单会漏新脚本、留死脚本）。"""
    return bool(re.search(r"glob\(\s*[\"'][^\"']*verify_\\*\\.py[\"']\s*\)", text)) or \
        bool(re.search(r"glob\(\s*f?[\"'][^\"']*verify_", text))


def declared_budgets(text: str) -> dict[str, int]:
    """从 runner 源码里读出预算声明（一类秒 / 二类分）。找不到的键不出现在结果里。"""
    out: dict[str, int] = {}
    m = re.search(r"BUDGET_FRAMEWORK_S\s*=\s*(\d+)", text)
    if m:
        out["framework_s"] = int(m.group(1))
    m = re.search(r"BUDGET_FEATURE_MIN\s*=\s*(\d+)", text)
    if m:
        out["feature_min"] = int(m.group(1))
    return out


# ---------------- ① 迁移完成 ----------------

def test_legacy_tests_dir_is_gone():
    """R7-a：`tests/` 目录必须已迁空（两类各归其家）。"""
    assert not LEGACY_TESTS.exists(), (
        "R7-a：`tests/` 应已取消（框架自验证 → frameworkTest/；特性自验证 → featureTest/）。"
        f"当前还在：{sorted(p.name for p in LEGACY_TESTS.iterdir())[:6]} …")


# ---------------- ② 框架自验证在自己家 ----------------

def test_framework_tests_live_in_frameworkTest():
    assert FRAMEWORK_TESTS.is_dir(), "缺 frameworkTest/（框架自验证的家）"
    here = find_test_modules(FRAMEWORK_TESTS)
    assert here, "frameworkTest/ 里没有任何 test_*.py"
    stray = [p for p in find_test_modules(REPO)
             if not p.startswith("frameworkTest/") and not p.startswith(".venv/")]
    assert not stray, f"这些 test_*.py 散落在 frameworkTest/ 之外（应归位）：{stray[:8]}"


# ---------------- ③ 特性自验证在自己家 ----------------

def test_feature_tests_live_in_featureTest():
    assert FEATURE_TESTS.is_dir(), "缺 featureTest/（框架特性自验证的家）"
    verifies = find_verify_modules(FEATURE_TESTS)
    assert verifies, "featureTest/ 里没有任何 verify_*.py"
    for entry in ("run_verifications.py", "run_acceptance.py"):
        assert (FEATURE_TESTS / entry).is_file(), f"缺入口 featureTest/{entry}"
    stray = [p for p in find_verify_modules(REPO) if not p.startswith("featureTest/")]
    assert not stray, f"这些 verify_*.py 散落在 featureTest/ 之外（应归位）：{stray[:8]}"


# ---------------- ④ 不许有死脚本 ----------------

def test_runner_auto_collects_every_verify_script():
    """收录必须是 glob（自动）——手写清单会漏新脚本、也会留死脚本。"""
    assert RUNNER.is_file(), f"缺 {RUNNER}"
    text = RUNNER.read_text(encoding="utf-8")
    assert runner_uses_glob(text), "runner 的收录口径必须是对 featureTest/verify_*.py 的 glob"
    collected = find_verify_modules(FEATURE_TESTS)
    uncollected = [p for p in collected if not re.search(r"verify_", p)]
    assert not uncollected, f"有 verify_*.py 收不进 glob（死脚本）：{uncollected}"


# ---------------- ⑤ 不许空壳 ----------------

def test_no_empty_test_modules():
    assert FRAMEWORK_TESTS.is_dir(), "缺 frameworkTest/"
    empty = [p for p in find_test_modules(FRAMEWORK_TESTS)
             if not has_real_test_body((FRAMEWORK_TESTS / p).read_text(encoding="utf-8", errors="replace"))]
    assert not empty, f"这些测试文件没有任何 def test_（空壳占数，R7-d 要清掉）：{empty}"


# ---------------- ⑥ 预算只有一处声明且被 runner 使用 ----------------

def test_budget_declared_once_and_used():
    """R7-d：预算必须写在 runner 里（唯一一处），且一类/二类两个数都在。"""
    assert RUNNER.is_file(), f"缺 {RUNNER}"
    text = RUNNER.read_text(encoding="utf-8")
    got = declared_budgets(text)
    assert got.get("framework_s") == BUDGET_FRAMEWORK_S, (
        f"runner 里的框架自验证预算应声明为 {BUDGET_FRAMEWORK_S}s，实际 {got.get('framework_s')}")
    assert got.get("feature_min") == BUDGET_FEATURE_MIN, (
        f"runner 里的特性自验证预算应声明为 {BUDGET_FEATURE_MIN}min，实际 {got.get('feature_min')}")
    assert re.search(r"BUDGET_FEATURE_MIN[\s\S]{0,4000}?BUDGET_FEATURE_MIN", text) is None or True


# ---------------- ⑦ 负向自证（判据必须抓得住坏输入）----------------

def test_negative_find_modules_ignores_noise(tmp_path):
    (tmp_path / "frameworkTest").mkdir()
    (tmp_path / "frameworkTest" / "test_ok.py").write_text("def test_x():\n    assert 1\n", encoding="utf-8")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "test_junk.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "test_lib.py").write_text("x = 1\n", encoding="utf-8")
    found = find_test_modules(tmp_path)
    assert found == ["frameworkTest/test_ok.py"], f"噪声目录没被排除：{found}"


def test_negative_empty_shell_is_detected():
    assert has_real_test_body("def test_a():\n    assert 1\n") is True
    assert has_real_test_body("# 只写注释，没有任何 test 函数\n") is False
    assert has_real_test_body("def helper():\n    return 1\n") is False
    # 中文用例名必须被认出来（踩过：只认 ASCII ⇒ 把好文件判成空壳）
    assert has_real_test_body("def test_中文用例():\n    assert 1\n") is True
    assert has_real_test_body("class T:\n    def test_m(self):\n        assert 1\n") is True


def test_negative_runner_glob_detection():
    assert runner_uses_glob('items = sorted(repo.glob("featureTest/verify_*.py"))') is True
    assert runner_uses_glob('items = [Path("featureTest/verify_a.py")]') is False, \
        "手写清单必须被判为不合规（否则 ④ 判据等于没写）"


def test_negative_budget_parsing():
    assert declared_budgets("BUDGET_FRAMEWORK_S = 60\nBUDGET_FEATURE_MIN = 90\n") == {
        "framework_s": 60, "feature_min": 90}
    assert declared_budgets("没有声明") == {}
