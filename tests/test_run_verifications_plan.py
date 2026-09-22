"""二类统一入口的**调度判据**（P16 批 6 新增：预算 1200s + 并发 + 内存闸）。

为什么值得单测：并行跑验证是**有副作用**的事（多个 Chromium 抢内存，抢输的那套会被 SKIP，
且 SKIP **不等于通过**）。所以"什么时候允许起下一个"必须是**纯函数**、必须被钉住，
绝不能靠"看着差不多就并"。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_verifications as rv      # noqa: E402


def test_单脚本预算已按拍板提到_1200():
    # AprilPark1012 2026-09-22：用例变多，600s 下 verify_assert_kinds 永远跑不完（exit 124 被记成失败）
    assert rv.PER_SCRIPT_TIMEOUT_S == 1200


def test_内存红线与框架其它地方同源():
    assert rv.MEM_PER_BROWSER_MB == 550


def test_串行模式永远只起一个():
    ok, why = rv.may_start(is_browser=False, running=0, running_browsers=0, jobs=1, mem_mb=99999)
    assert ok and "串行" in why
    ok2, _ = rv.may_start(is_browser=False, running=1, running_browsers=0, jobs=1, mem_mb=99999)
    assert not ok2, "串行模式下不允许第二个并发"


def test_并发数到上限就不再起():
    ok, why = rv.may_start(is_browser=True, running=2, running_browsers=2, jobs=2, mem_mb=99999)
    assert not ok and "并发已满" in why


def test_浏览器脚本必须过内存闸_差一点也硬闯():
    # 550MB 一个浏览器实例：可用 500MB 时**不许起**（硬闯的下场是浏览器起不来 ⇒ 整套被 SKIP）
    ok, why = rv.may_start(is_browser=True, running=0, running_browsers=0, jobs=2, mem_mb=500)
    assert not ok and "内存闸未过" in why
    ok2, _ = rv.may_start(is_browser=True, running=0, running_browsers=0, jobs=2, mem_mb=550)
    assert ok2, "刚好 550MB 应当放行"


def test_非浏览器脚本不吃内存闸():
    # 纯逻辑/离线验证（不起 Chromium）可以放心并
    ok, _ = rv.may_start(is_browser=False, running=1, running_browsers=1, jobs=2, mem_mb=10)
    assert ok


def test_浏览器脚本数越多_内存要求越高():
    # 已有 1 个浏览器在跑 ⇒ 起第二个需要 550×2=1100MB
    ok, why = rv.may_start(is_browser=True, running=1, running_browsers=1, jobs=3, mem_mb=1000)
    assert not ok and "1100MB" in why


def test_按脚本源码判定是否起浏览器(tmp_path):
    heavy = tmp_path / "verify_x.py"
    heavy.write_text("from playwright.sync_api import sync_playwright\n", encoding="utf-8")
    light = tmp_path / "verify_y.py"
    light.write_text("print('纯离线校验')\n", encoding="utf-8")
    assert rv.is_browser_script(heavy) is True
    assert rv.is_browser_script(light) is False


def test_读不到文件按会起浏览器处理():
    assert rv.is_browser_script(Path("/nonexistent/verify_z.py")) is True


def test_命令行支持_timeout_s_与_jobs():
    a = rv._parse([])
    assert a.timeout_s == rv.PER_SCRIPT_TIMEOUT_S and a.jobs == 1, "默认必须是串行 + 1200s（行为与改造前一致）"
    b = rv._parse(["--jobs", "3", "--timeout-s", "900"])
    assert b.jobs == 3 and b.timeout_s == 900


# ——— 独占屏障（2026-09-22 实测补：并发自己引入的假红，必须自己判掉）———
def test_会写共享产物的脚本判为独占(tmp_path):
    x = tmp_path / "verify_x.py"
    x.write_text("subprocess.run([PY, '-m', 'framework.cli', 'generate'])\n", encoding="utf-8")
    y = tmp_path / "verify_y.py"
    y.write_text("print('只读校验')\n", encoding="utf-8")
    assert rv.is_exclusive_script(x) is True
    assert rv.is_exclusive_script(y) is False


def test_读不到文件按独占处理():
    assert rv.is_exclusive_script(Path("/nonexistent/verify_z.py")) is True


def test_独占是屏障_两个方向都拦住():
    base = dict(is_browser=False, running_browsers=0, jobs=2, mem_mb=99999)
    # 方向①：已有独占在跑 ⇒ 谁也别起
    ok, why = rv.may_start(running=0, exclusive=False, running_exclusive=True, **base)
    assert ok is False and "独占" in why
    # 方向②：自己要独占、别人在跑 ⇒ 自己等
    ok, why = rv.may_start(running=1, exclusive=True, running_exclusive=False, **base)
    assert ok is False and "独占" in why
    # 不能死锁：独占脚本在**没人跑**时一定能起
    ok, _ = rv.may_start(running=0, exclusive=True, running_exclusive=False, **base)
    assert ok is True, "独占脚本空场时必须能起，否则整套验证卡死"


def test_串行模式下独占不破坏原行为():
    ok, why = rv.may_start(is_browser=False, running=0, running_browsers=0, jobs=1,
                           mem_mb=99999, exclusive=True)
    assert ok is True and "串行" in why

# ---------- 脚本间产物质检（悬空引用必须被抓到）----------
def test_artifacts_check_catches_dangling_case_id(tmp_path, monkeypatch):
    """★负向：产物嵌了一个没有数据集的 case_id ⇒ 必须报出来（这是 L15 事故的核心判据）。"""
    import run_verifications as rv
    (tmp_path / "scripts" / "datasets").mkdir(parents=True)
    (tmp_path / "scripts" / "test_cases.py").write_text(
        "def test_ghost_case_999999(page):\n    pass\n", encoding="utf-8")
    (tmp_path / "scripts" / "conftest.py").write_text("# empty\n", encoding="utf-8")
    monkeypatch.setattr(rv, "REPO", tmp_path)
    assert rv.artifacts_are_consistent() == ["ghost_case_999999"]


def test_artifacts_check_passes_when_dataset_exists(tmp_path, monkeypatch):
    """正向：case_id 有对应数据集 ⇒ 干净（不许误报）。"""
    import run_verifications as rv
    d = tmp_path / "scripts" / "datasets"
    d.mkdir(parents=True)
    (tmp_path / "scripts" / "test_cases.py").write_text(
        "def test_ok_case_000001(page):\n    pass\n", encoding="utf-8")
    (tmp_path / "scripts" / "conftest.py").write_text("# empty\n", encoding="utf-8")
    (d / "ok_case_000001.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(rv, "REPO", tmp_path)
    assert rv.artifacts_are_consistent() == []


def test_artifacts_check_tolerates_missing_files(tmp_path, monkeypatch):
    """健壮性：产物还没生成（文件不在）⇒ 不崩、不误报。"""
    import run_verifications as rv
    monkeypatch.setattr(rv, "REPO", tmp_path)
    assert rv.artifacts_are_consistent() == []
