"""tests/ 目录契约 + 用例新陈代谢 守门判据（R7-a / R7-d）。

**为什么要有它**：目录结构靠自觉就会漂 ——
  · **R7-a 目录分工**：`tests/` 是容器，下面按**框架 9 个特性**分文件夹（一类 `test_*.py`
    与二类 `verify_*.py` 同住一个特性夹，靠**文件名前缀**区分）；
    公共模块住 `tests/_helpers/`，runner 工具住 `tests/_runner/`。
  · **R7-d 用例新陈代谢**：加用例必须同批清无效用例，否则测试时间白白增长、拖垮开发效率。
  · **R7 新增（2026-10-07）**：**特性已实现但无判据的，必须显式标记**（`UNVERIFIED.md`），
    不许默默漏 —— 否则「能力丢了没人知道」。

本判据把上面几条变成**每次一类都跑的红线**。

判据清单：
  ① `tests/` 是容器，且**9 个特性夹 + `_helpers` + `_runner`** 齐备、无第三类目录
  ② 所有一类 `test_*.py` 必须住在**特性夹**里（不许散落 `_helpers`/`_runner`/仓库别处）
  ③ 所有二类 `verify_*.py` 必须住在**特性夹**里
  ④ runner 收录口径必须是**自动 glob** `tests/**/verify_*.py`（不许手写清单 ⇒ 不许死脚本）
  ⑤ 不许空壳判据文件（`test_*.py` 里至少 1 个 `def test_`）
  ⑥ 时长预算只有一处声明，且被 runner 真正读取
  ⑦ **零判据的特性必须显式标 `UNVERIFIED.md`**（有实现、没验证 = 必须被看见）
  ⑧ 纯函数层负向自证（判据自己能抓坏输入，否则等于没写）
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]          # tests/<特性>/ ⇒ 上两级才是仓库根
TESTS_DIR = REPO / "tests"                          # 容器目录（2026-09-24 定：容器保留）
HELPERS = TESTS_DIR / "_helpers"                    # 公共模块（artifacts / repo_files / …）
RUNNER_DIR = TESTS_DIR / "_runner"                  # runner 工具（入口 / 重录 / fixtures）
RUNNER = RUNNER_DIR / "run_verifications.py"

# 框架 9 个特性（名称取自 docs/training.html 第 7 章《框架特性设计实现说明》）
FEATURE_DIRS = [
    "特性1-混合链路",
    "特性2-语义识别与分层定位",
    "特性3-选错控件兜底",
    "特性4-用例脚本数据三层分离",
    "特性5-自愈闭环Healer",
    "特性6-并发与资源安全",
    "特性7-离线回放",
    "特性8-质量闸门体系",
    "特性9-CLI帮助契约",
]

# R7-d / D6 预算（实测基线：一类 ~30s · 二类日常 ~12.4min）
BUDGET_FRAMEWORK_S = 60
BUDGET_FEATURE_MIN = 40     # D6（2026-09-24）：二类控制在 40 分钟以内


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
    # ⚠️ 用例名允许中文（本项目多处用中文命名）
    return bool(re.search(r"^\s*def test_[^\s(]+\s*\(", text, re.M))


def runner_uses_glob(text: str) -> bool:
    """runner 是否用 glob 自动收录（而不是手写清单 —— 手写清单会漏新脚本、留死脚本）。"""
    return bool(re.search(r"glob\(\s*f?[\"'][^\"']*verify_\*\.py[\"']", text))


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


def in_feature_dir(rel_path: str) -> bool:
    """相对路径是否落在某个「特性N-…」夹里。"""
    parts = rel_path.split("/")
    return len(parts) >= 2 and parts[0] == "tests" and any(
        parts[1].startswith(f"特性{i}-") for i in range(1, 10))


# ---------------- ① 容器 + 9 特性夹齐备 ----------------


def test_tests_dir_holds_nine_feature_folders():
    """`tests/` 是容器：下面必须是 **9 个特性夹 + _helpers + _runner**，不许漂成别的结构。"""
    assert TESTS_DIR.is_dir(), f"缺容器目录 {TESTS_DIR}"
    names = {p.name for p in TESTS_DIR.iterdir() if p.is_dir() and p.name != "__pycache__"}
    missing = [d for d in FEATURE_DIRS if d not in names]
    assert not missing, f"缺这些特性夹：{missing}"
    assert HELPERS.is_dir(), "缺 tests/_helpers/（公共模块的家）"
    assert RUNNER_DIR.is_dir(), "缺 tests/_runner/（runner 工具的家）"
    stray = sorted(n for n in names if n not in FEATURE_DIRS and n not in ("_helpers", "_runner"))
    assert not stray, f"tests/ 下出现了预期外的目录（结构漂了）：{stray}"


# ---------------- ② 一类必须住特性夹 ----------------


def test_class1_tests_live_in_feature_folders():
    here = [p for p in find_test_modules(TESTS_DIR) if in_feature_dir("tests/" + p)]
    assert here, "9 个特性夹里没有任何一类 test_*.py"
    stray = [p for p in find_test_modules(REPO)
             if not in_feature_dir(p) and not p.startswith(".venv/")]
    assert not stray, f"这些 test_*.py 没归到特性夹（应归位，别散落 _helpers/_runner/仓库别处）：{stray[:8]}"


# ---------------- ③ 二类必须住特性夹 ----------------


def test_class2_verifies_live_in_feature_folders():
    here = [p for p in find_verify_modules(TESTS_DIR) if in_feature_dir("tests/" + p)]
    assert here, "9 个特性夹里没有任何二类 verify_*.py"
    stray = [p for p in find_verify_modules(REPO) if not in_feature_dir(p)]
    assert not stray, f"这些 verify_*.py 没归到特性夹（应归位）：{stray[:8]}"
    for entry in ("run_verifications.py", "run_acceptance.py"):
        assert (RUNNER_DIR / entry).is_file(), f"缺入口 tests/_runner/{entry}"


# ---------------- ④ 不许死脚本 ----------------


def test_runner_auto_collects_every_verify_script():
    """收录必须是 glob（自动）——手写清单会漏新脚本、也会留死脚本。"""
    assert RUNNER.is_file(), f"缺 {RUNNER}"
    text = RUNNER.read_text(encoding="utf-8")
    assert runner_uses_glob(text), "runner 的收录口径必须是 glob tests/**/verify_*.py（不许手写清单）"
    collected = find_verify_modules(TESTS_DIR)
    assert collected, "runner 一条 verify_*.py 都收不到（glob 口径错了）"


# ---------------- ⑤ 不许空壳 ----------------


def test_no_empty_test_modules():
    empty = [p for p in find_test_modules(TESTS_DIR)
             if in_feature_dir("tests/" + p)
             and not has_real_test_body((TESTS_DIR / p).read_text(encoding="utf-8", errors="replace"))]
    assert not empty, f"这些判据文件没有任何 def test_（空壳占数，R7-d 要清掉）：{empty}"


# ---------------- ⑥ 预算只有一处声明且被 runner 使用 ----------------


def test_budget_declared_once_and_used():
    """R7-d：预算必须写在 runner 里（唯一一处），且一类/二类两个数都在。"""
    assert RUNNER.is_file(), f"缺 {RUNNER}"
    got = declared_budgets(RUNNER.read_text(encoding="utf-8"))
    assert got.get("framework_s") == BUDGET_FRAMEWORK_S, (
        f"runner 里的框架自验证预算应声明为 {BUDGET_FRAMEWORK_S}s，实际 {got.get('framework_s')}")
    assert got.get("feature_min") == BUDGET_FEATURE_MIN, (
        f"runner 里的特性自验证预算应声明为 {BUDGET_FEATURE_MIN}min，实际 {got.get('feature_min')}")


# ---------------- ⑦ 零判据的特性必须显式标记（2026-10-07 新要求）----------------


def test_unverified_features_are_marked():
    """特性已实现但无判据 ⇒ **必须**在该特性夹里有 `UNVERIFIED.md`（不许默默漏）。

    口径：一个特性夹里既没有 `test_*.py` 也没有 `verify_*.py` ⇒ 视为「零判据」，
    此时必须有 UNVERIFIED.md 说明「实现住哪 / 风险 / 待补哪几条判据」。
    """
    problems = []
    for d in FEATURE_DIRS:
        folder = TESTS_DIR / d
        if not folder.is_dir():
            continue
        has_judgement = bool(list(folder.glob("test_*.py"))) or bool(list(folder.glob("verify_*.py")))
        marker = folder / "UNVERIFIED.md"
        if not has_judgement and not marker.is_file():
            problems.append(f"{d}（零判据但没写 UNVERIFIED.md）")
    assert not problems, f"这些特性零判据却没显式标记：{problems}"


# ---------------- ⑧ 负向自证（判据必须抓得住坏输入）----------------


def test_negative_find_modules_ignores_noise(tmp_path):
    (tmp_path / "tests" / "特性1-混合链路").mkdir(parents=True)
    (tmp_path / "tests" / "特性1-混合链路" / "test_ok.py").write_text("def test_x():\n    assert 1\n", encoding="utf-8")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "test_junk.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "test_lib.py").write_text("x = 1\n", encoding="utf-8")
    found = find_test_modules(tmp_path)
    assert found == ["tests/特性1-混合链路/test_ok.py"], f"噪声目录没被排除：{found}"


def test_negative_empty_shell_is_detected():
    assert has_real_test_body("def test_a():\n    assert 1\n") is True
    assert has_real_test_body("# 只写注释，没有任何 test 函数\n") is False
    assert has_real_test_body("def helper():\n    return 1\n") is False
    # 中文用例名必须被认出来（踩过：只认 ASCII ⇒ 把好文件判成空壳）
    assert has_real_test_body("def test_中文用例():\n    assert 1\n") is True
    assert has_real_test_body("class T:\n    def test_m(self):\n        assert 1\n") is True


def test_negative_runner_glob_detection():
    assert runner_uses_glob('items = sorted(repo.glob("tests/**/verify_*.py"))') is True
    assert runner_uses_glob('items = [Path("tests/_runner/verify_a.py")]') is False, \
        "手写清单必须被判为不合规（否则 ④ 判据等于没写）"


def test_negative_budget_parsing():
    assert declared_budgets("BUDGET_FRAMEWORK_S = 60\nBUDGET_FEATURE_MIN = 40\n") == {
        "framework_s": 60, "feature_min": 40}
    assert declared_budgets("没有声明") == {}


def test_negative_in_feature_dir():
    assert in_feature_dir("tests/特性1-混合链路/test_a.py") is True
    assert in_feature_dir("tests/_helpers/artifacts.py") is False
    assert in_feature_dir("tests/特性10-没有这个/test_a.py") is False
