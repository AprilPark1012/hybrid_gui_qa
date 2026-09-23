"""环境自适应判据（2026-09-22 · AprilPark1012 本地 Windows 验收 19 红驱动）。

三个「换个环境就红」的真 bug 在这里钉住，**每一项都带负向自证**（R7：只跑正向不算验证过）：

① 非 git 目录（交付包解压目录）⇒ 文件清单判据不许红，且降级扫描**必须仍扫到新增文件**；
② 任何「连不上」的形态都必须给出「先起 demo」的动作（Windows 抛 TimeoutError、
   Linux 抛 ConnectionRefusedError；还有 DNS 失败 / 泛 OSError / 库级超时）—— 负向：可达时不许乱报；
③ 生成物不存在 / 0 字节 ⇒ 报错必须是**人话 + 建议命令**，不是「缺接线」天书
   （9 条契约判据的读取口已统一到 `frameworkTest/artifacts.py`）。

秒级、不需要 demo、不需要浏览器。
"""
from __future__ import annotations

import socket
import sys
import urllib.error
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))       # 同目录测试工具

import artifacts                                              # noqa: E402
import repo_files                                            # noqa: E402
from framework.tools.common import target_probe              # noqa: E402


# ==================== ① 文件清单：非 git 环境等效降级 ====================

def _fake_pkg_repo(tmp: Path) -> Path:
    """造一个像「交付包解压目录」的树：无 .git，另带第三方树与运行时目录。"""
    (tmp / "framework").mkdir(parents=True, exist_ok=True)
    (tmp / "framework" / "cli.py").write_text("x = 1\n", encoding="utf-8")
    (tmp / "note.md").write_text("新写的说明（模拟未跟踪的新文件）\n", encoding="utf-8")
    for d in (".venv/lib/site-packages", "log/run1", "output/verify", "__pycache__"):
        (tmp / d).mkdir(parents=True, exist_ok=True)
    (tmp / ".venv/lib/site-packages/third.py").write_text("y = 2\n", encoding="utf-8")
    (tmp / "log/run1/case.log").write_text("旧日志\n", encoding="utf-8")
    (tmp / "output/verify/neg.log").write_text("负向日志\n", encoding="utf-8")
    (tmp / "__pycache__/x.pyc").write_bytes(b"\x00bin")
    return tmp


def test_file_list_falls_back_outside_git_repo(tmp_path):
    """非 git 目录：必须走降级来源，且清单非空（不许再自报「前提不成立」）。"""
    files, source = repo_files.file_list(_fake_pkg_repo(tmp_path))
    assert files, "降级扫描返回空清单 ⇒ 团队用户在交付包现场又会看到红"
    assert "文件树扫描" in source, source
    assert "note.md" in files, "★ 新增（未跟踪）文件必须被扫到 —— 否则又是「提交后才发现」的假绿"
    assert "framework/cli.py" in files


def test_file_list_fallback_skips_third_party_and_runtime(tmp_path):
    """降级扫描必须挡住第三方树 / 运行时目录 / 缓存（否则会误报，甚至扫错人）。"""
    files, _ = repo_files.file_list(_fake_pkg_repo(tmp_path))
    bad = [f for f in files if f.startswith((".venv", "log/", "output/", "__pycache__"))]
    assert not bad, f"降级扫描把不该扫的目录扫进来了：{bad}"


def test_file_list_uses_git_inside_repo():
    """本仓是 git 仓库 ⇒ 必须走 git 口径（含未跟踪但不被忽略那一半）。

    ⚠️ 环境前提：这条只在**仓库内**有效 —— 交付包解压目录本来就不是 git 仓库，
    在那里跑它必然红（那就是被修的那个 bug 本身）。⇒ 显式 SKIP 并说明，绝不假装通过。
    """
    if repo_files._git_file_list(REPO) is None:
        pytest.skip("当前目录不是 git 仓库（例：交付包解压目录）⇒ 本条只在仓库内有效；"
                    "降级路径由 test_file_list_falls_back_outside_git_repo 覆盖")
    files, source = repo_files.file_list(REPO)
    assert "git ls-files" in source, source
    assert "frameworkTest/repo_files.py" in files, "清单里没有本文件 ⇒ 未跟踪文件没被收进来（假绿形态）"


# ==================== ② 「连不上」必须给动作 ====================

def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def test_unreachable_message_has_action_on_real_dead_port():
    """真实形态：本机一个没人听的端口（Linux 拒连 / Windows 超时，两边都要有动作）。"""
    ok, why = target_probe.reachability(f"http://127.0.0.1:{_free_port()}", timeout=2)
    assert ok is False
    assert "demo.app" in why, f"不可达时必须给动作：{why}"


@pytest.mark.parametrize("reason", [
    ConnectionRefusedError(61, "Connection refused"),          # Linux 形态
    TimeoutError("timed out"),                                 # ★ Windows 形态（老写法漏的就是它）
    socket.gaierror(-2, "Name or service not known"),          # DNS 失败
    OSError(101, "Network is unreachable"),                    # 泛 OSError
    socket.timeout("timed out"),                               # 旧式超时异常
], ids=["refused", "timeout", "dns", "oserror", "socket-timeout"])
def test_unreachable_hint_covers_every_reason_shape(reason):
    """★ 核心：**任何**连不上形态都必须带「先起 demo」的动作，且保留真实原因。"""
    msg = target_probe.unreachable_hint("http://localhost:8000", reason)
    assert "demo.app" in msg, msg
    assert type(reason).__name__ in msg, f"真实原因要保留（排查用）：{msg}"


def test_reachability_wrapped_timeout_still_has_action(monkeypatch):
    """Windows 上 urllib 会把超时包成 `URLError(TimeoutError)` ⇒ 文案仍须带动作。"""
    def _boom(*a, **k):
        raise urllib.error.URLError(TimeoutError("timed out"))

    monkeypatch.setattr(target_probe.urllib.request, "urlopen", _boom)
    ok, why = target_probe.reachability("http://127.0.0.1:9", timeout=0.1)
    assert ok is False and "demo.app" in why, why


def test_reachability_wrapped_oserror_still_has_action(monkeypatch):
    """中文 Windows 上「积极拒绝」是 OSError(10061) ⇒ 文案也要给动作。"""
    def _boom(*a, **k):
        raise OSError(10061, "由于目标计算机积极拒绝，无法连接。")

    monkeypatch.setattr(target_probe.urllib.request, "urlopen", _boom)
    ok, why = target_probe.reachability("http://127.0.0.1:9", timeout=0.1)
    assert ok is False and "demo.app" in why, why


def test_reachable_target_message_does_not_cry_wolf(monkeypatch):
    """负向：可达时**不许**出现「先起 demo」这类误导动作。"""
    class _Resp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(target_probe.urllib.request, "urlopen", lambda *a, **k: _Resp())
    ok, why = target_probe.reachability("http://127.0.0.1:8000")
    assert ok is True and "demo.app" not in why, why


# ==================== ③ 生成物空 / 缺 ⇒ 人话 + 动作 ====================

def test_artifact_missing_says_what_to_do(tmp_path):
    """产物不存在：一句话说清「没产出」+ 两条下一步（起 demo + generate / 重新解压）。"""
    with pytest.raises(AssertionError) as ei:
        artifacts.read_artifact(tmp_path / "conftest.py", role="生成物 scripts/conftest.py")
    msg = str(ei.value)
    assert "不存在" in msg and "generate" in msg and "demo.app" in msg, msg


def test_artifact_empty_says_what_to_do(tmp_path):
    """★ 现场形态：产物 0 字节 ⇒ 必须点明「产物是空的」而不是报「缺接线」。"""
    p = tmp_path / "conftest.py"
    p.write_text("", encoding="utf-8")
    with pytest.raises(AssertionError) as ei:
        artifacts.read_artifact(p, role="生成物 scripts/conftest.py")
    msg = str(ei.value)
    assert "字节" in msg and "generate" in msg and "解压" in msg, msg


def test_artifact_healthy_is_returned_as_is(tmp_path):
    """负向：正常产物不许被这道闸拦住（防修成「永远报错」）。"""
    p = tmp_path / "conftest.py"
    body = "def _act():\n    pass\n" + "# 填充到正常产物的量级\n" * 20
    p.write_text(body, encoding="utf-8")
    assert artifacts.read_artifact(p, role="生成物 scripts/conftest.py").startswith("def _act")


def test_contract_gates_now_report_actionable_message(tmp_path, monkeypatch):
    """接线判据：产物缺失/为空时，原来那 9 条契约判据报的必须是**带动作的人话**。"""
    import test_artifacts_health as health

    monkeypatch.setattr(health, "SCRIPTS", tmp_path)          # 指向一个没有产物的目录
    for fn in (health.test_generated_test_cases_uses_ready_contract,
               health.test_generated_conftest_has_contract_helpers,
               health.test_generated_test_cases_has_no_unmapped_stubs):
        with pytest.raises(AssertionError) as ei:
            fn()
        assert "generate" in str(ei.value), f"{fn.__name__} 的报错没给出下一步：{ei.value}"


# ==================== ④ 二类统一入口：跨平台 Python 实现 ====================
# 背景（2026-09-22 使用者现场反馈）：Windows PowerShell 里**没有 bash** ⇒
# `bash featureTest/run_verifications.sh` 直接报「无法将"bash"项识别为 cmdlet」⇒
# 二类验证对团队里的 Windows 用户等于不存在，而本框架的现场恰恰是 Windows。
# 口径：**唯一实现 = featureTest/run_verifications.py**；`.sh` 退化成转发包装（防漂移判据见 ⑤ 节）。

def _run_runner(args):
    import subprocess
    return subprocess.run([sys.executable, "featureTest/run_verifications.py", *args],
                          cwd=str(REPO), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=180)


def test_runner_lists_exactly_the_repo_verify_scripts():
    """★ `--list` 必须与仓库里的 verify_*.py 完全一致（**自动收录、不许手写清单** ⇒ 新增脚本不会漏跑）。"""
    r = _run_runner(["--list"])
    assert r.returncode == 0, r.stderr
    listed = sorted(ln.strip() for ln in r.stdout.splitlines() if ln.strip().endswith(".py"))
    expected = sorted(p.name for p in (REPO / "featureTest").glob("verify_*.py"))
    assert listed == expected, f"\n--list 给的: {listed}\n仓库实际有: {expected}"


def test_runner_only_filter_and_unknown_flag():
    r = _run_runner(["--only", "html_sync", "--list"])
    assert r.returncode == 0 and "verify_html_sync.py" in r.stdout, r.stdout
    assert "verify_assert_kinds.py" not in r.stdout, "过滤没生效"
    bad = _run_runner(["--onlyy", "x"])
    assert bad.returncode == 2, f"未知参数必须 exit 2（脚本调用方不能把「没跑」当成功），实际 {bad.returncode}"


def test_runner_finds_windows_venv_layout(tmp_path):
    """跨平台解释器定位：Windows 的 `.venv/Scripts/python.exe` 必须认得出来。"""
    import run_verifications as rv
    d = tmp_path / ".venv" / "Scripts"
    d.mkdir(parents=True)
    (d / "python.exe").write_text("", encoding="utf-8")
    assert rv._venv_python(tmp_path).endswith("python.exe")


def test_runner_mem_probe_never_fakes_a_number():
    """内存探测：要么给出正整数，要么如实 None（Windows 走 ctypes；两条都拿不到就 None）。"""
    import run_verifications as rv
    mb = rv.mem_available_mb()
    assert mb is None or (isinstance(mb, int) and mb > 0), mb


def test_runner_classify_maps_exit_codes():
    """退出码语义：0 通过 / 3 跳过（**不是通过**）/ 其它（含超时 124）一律算失败。"""
    import run_verifications as rv
    assert (rv.classify(0), rv.classify(3), rv.classify(1), rv.classify(124)) == \
        ("ok", "skip", "fail", "fail")


# ==================== ⑤ .sh 只许转发（防两处逻辑漂移）====================

def test_sh_entry_is_thin_wrapper_over_python():
    """★ 防漂移：`.sh` 只做转发 —— **唯一实现是 `.py`**（Windows 上 bash 根本不存在）。

    历史：这份 .sh 原先自带全套逻辑（参数解析 / 内存检查 / demo 启停 / 逐个跑 / 汇总），
    2026-09-22 因为 Windows 跑不起来而把实现搬到 Python ⇒ 若 .sh 里还留着旧逻辑，
    两边就会各改各的（这类「改了一处忘了另一处」在本项目已踩过多次）。
    """
    sh = (REPO / "featureTest" / "run_verifications.sh").read_text(encoding="utf-8")
    assert "run_verifications.py" in sh, ".sh 没有转发到 Python 版 ⇒ 两处逻辑会漂移"
    body = [ln for ln in sh.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    assert len(body) <= 12, f".sh 里还有 {len(body)} 行实体逻辑 ⇒ 应只剩转发：{body}"
    for stale in ("mapfile", "MemAvailable", "declare -a NAMES", "demo_up()"):
        assert stale not in sh, f".sh 里还留着旧实现片段（应已搬到 .py）：{stale}"
