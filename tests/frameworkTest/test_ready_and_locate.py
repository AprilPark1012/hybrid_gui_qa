"""F1/F2/F3/F6 的契约锁（秒级、不需要浏览器、不需要 demo）。

为什么要有这一层：这些改动的"生效点"分布在**生成物**（scripts/conftest.py、scripts/test_cases.py、
demo 页面、CLI）里，而生成物是 generate 从模板产出的 —— 只改生成物、忘了改模板（或反过来），
下次 generate 就会把修复抹掉。所以这里做**源码级互锁**：模板与生成物必须同时具备这些接线。

口径（与项目一致）：任何"少做一步还报绿"都要显式失败；这里的"步骤"= 修复的接线点。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

# 同目录测试工具：生成物读取入口（缺失/为空时给「先跑 generate」这类可行动诊断）
sys.path.insert(0, str(Path(__file__).resolve().parent))
import artifacts  # noqa: E402

GEN = ROOT / "framework" / "tools" / "generate" / "generator.py"
CONFTEST = ROOT / "scripts" / "conftest.py"
TESTS_PY = ROOT / "scripts" / "test_cases.py"
CLI = ROOT / "framework" / "cli.py"
APP = ROOT / "demo" / "app.py"
CONTRACTS_HTML = ROOT / "demo" / "contracts.html"
DETAIL_HTML = ROOT / "demo" / "contract_detail.html"


def _read(p: Path) -> str:
    """读来源文件：**生成物**走带动作诊断的入口，框架源码照常读。

    ⚠️ 2026-09-22（AprilPark1012 本地 Windows 验收 19 红驱动）：生成物为 0 字节时，6 条契约判据各自
    报「生成物 缺少 _wait_ready / 缺 _goto」这类细节 —— 读的人看不出真因是「产物是空的」。
    产物缺失/为空属**环境问题**，第一句就要说清 + 给出下一步命令（见 tests/frameworkTest/artifacts.py）。
    """
    if p.parent == ROOT / "scripts":
        return artifacts.read_artifact(p, role=f"生成物 scripts/{p.name}")
    return p.read_text(encoding="utf-8")


# ---------------- F1：就绪契约 + 统一导航入口 ----------------

def test_generator_emits_goto_helper():
    """生成脚本必须通过 _goto 导航（它内部才做 HYBRID_BASE_URL 覆盖 + 等就绪）。"""
    src = _read(TESTS_PY)
    assert "_goto(page," in src, "生成脚本里没有 _goto( —— 是不是又回退成裸 page.goto 了？"
    assert "page.goto('http" not in src, "生成脚本里还有裸 page.goto( —— 导航没有走统一入口"


def test_generator_source_uses_goto_helper():
    """模板侧（唯一真源）也必须 emit _goto —— 只改生成物会被下次 generate 抹掉。"""
    src = _read(GEN)
    assert "    _goto(page, {case.get(" in src
    assert "    _goto(page, {st.get('url'" in src
    assert "    page.goto({case.get(" not in src and "page.goto({st.get(" not in src


def test_conftest_has_ready_wait_and_base_override():
    for src, tag in ((_read(CONFTEST), "生成物"), (_read(GEN), "模板")):
        assert "def _wait_ready(page" in src, f"{tag} 缺少 _wait_ready"
        assert "data-hybrid-ready='1'" in src, f"{tag} 没有等就绪标志"
        assert "HYBRID_READY_SELECTOR" in src, f"{tag} 缺少无契约页面的退化方案"
        assert "HYBRID_BASE_URL" in src, f"{tag} 缺少目标地址覆盖（闸门/多环境要用）"
        assert "HYBRID_WAIT_READY" in src, f"{tag} 缺少就绪等待开关（回滚用）"


def test_pages_declare_ready_contract():
    for p in (CONTRACTS_HTML, DETAIL_HTML):
        src = _read(p)
        assert 'data-hybrid-ready="0"' in src, f"{p.name} 没有静态声明就绪契约"
        assert "markReady" in src, f"{p.name} 没有在数据就绪后置位"
        assert "apiUrl(" in src, f"{p.name} 的 /api 调用没走 apiUrl（分区带不上）"
        assert "window.__HYBRID_W" in src, f"{p.name} 没读分区号"


# ---------------- F2：有界等待（且不能把复数断言也拖慢） ----------------

def test_bounded_wait_helper_present_and_used():
    for src, tag in ((_read(CONFTEST), "生成物"), (_read(GEN), "模板")):
        assert "def _count_attached(cand" in src, f"{tag} 缺少有界等待工具"
        assert "n = _count_attached(cand)" in src, f"{tag} 的动作定位没有用有界等待"


def test_plural_assertions_keep_instant_judgement():
    """count 这类复数断言必须**瞬时**判定：『期望 0 个』是合法用例，等 attached 只会白等超时。"""
    for src, tag in ((_read(CONFTEST), "生成物"), (_read(GEN), "模板")):
        assert "cand.count() if not unique else _count_attached(cand)" in src, \
            f"{tag} 的断言定位把 unique=False 也改成等待了（会让『期望 0』白等超时）"


# ---------------- F3：报错信息必须指向真因 ----------------

def test_misleading_errors_are_gone():
    bad1 = "断言 locator 失效且无语义兜底（该断言既没 selector 也没 element）"
    for src, tag in ((_read(CONFTEST), "生成物"), (_read(GEN), "模板")):
        assert bad1 not in src, f"{tag} 里还留着那条自相矛盾的旧文案"
        assert "元素语义未找到" in src and "排查：加 --debug 看逐步截图" in src, \
            f"{tag} 的『语义未找到』没有给出真因+下一步"


# ---------------- F6：分区隔离（demo / 页面 / conftest / CLI 四处必须一致） ----------------

def test_demo_partition_and_health():
    src = _read(APP)
    assert "/api/health" in src and '"partitioned"' in src, "demo 没有能力探针"
    assert "def _part_of(" in src and "def _store(" in src, "demo 没有分区数据层"
    assert "def reset_data(part" in src and "reset_data(part)" in src, "复位没带分区（会不会又全局复位了？）"
    assert "threading.RLock()" in src, "锁必须是可重入的（_store 与调用方都会加锁，普通 Lock 会自死锁）"


def test_conftest_partition_wiring():
    for src, tag in ((_read(CONFTEST), "生成物"), (_read(GEN), "模板")):
        assert "PYTEST_XDIST_WORKER" in src and "_PARTITION" in src, f"{tag} 没有 worker 分区概念"
        assert "add_init_script" in src and "__HYBRID_W" in src, f"{tag} 没把分区注入页面"
        assert "_with_partition(url)" in src, f"{tag} 的复位没带分区"


def test_cli_has_isolated_target_flag():
    src = _read(CLI)
    assert '"--isolated-target": None' in src, "FLAG_SPECS 没登记 --isolated-target"
    assert '"--isolated-target"' in src.split("_COMMON_FLAGS =")[1].split("\n")[0] or \
           "--isolated-target" in src.split("_COMMON_FLAGS =")[1][:200], "CMD_FLAGS 没给 run/all 放行"
    assert "probe_partitioned" in src, "cmd_run 没有接并发能力探针（F6b）"


# ---------------- F6b：真的跑一遍 CLI，锁住"未声明就降级"的行为 ----------------

def _run_cli(args: list[str], env_extra: dict) -> str:
    env = dict(os.environ)
    env.update({"HYBRID_RESET_URL": "off", "HYBRID_BASE_URL": "http://127.0.0.1:9",  # 探针必然失败
                "HYBRID_MB_PER_WORKER": "100", "HYBRID_RESERVE_MB": "50"})
    env.update(env_extra)
    r = subprocess.run([sys.executable, "-m", "framework.cli", "run", *args],
                       cwd=ROOT, capture_output=True, text=True, timeout=180, env=env,
                       encoding="utf-8", errors="replace")
    return (r.stdout or "") + (r.stderr or "")


@pytest.mark.parametrize("extra,expect", [
    ([], ["目标未声明可并发隔离", "保守降级为 1"]),
    (["--isolated-target"], ["已显式声明", "保持 2 worker"]),
])
def test_cli_downgrade_or_explicit_declaration(extra, expect):
    """并发能力探针：未声明 → 降级到 1 并说明原因；显式声明 → 放行。

    用 --case 选一个不存在的用例名 ⇒ pytest 只收集、**不起浏览器**（秒级、低内存）。
    用 --force-workers 固定「请求 2 并发」这个前提，**不依赖本机当时的内存**
    （否则 MemAvailable 一波动，期望就从"保持 2"变成"降为 1"，测试会莫名其妙红）。
    """
    out = _run_cli(["--workers", "2", "--force-workers", "--case", "__no_such_case__", *extra], {})
    for token in expect:
        assert token in out, f"期望输出里出现 {token!r}，实际：\n{out}"

    assert "未声明可并发隔离" in out if not extra else True
    if not extra:
        assert "保守降级为 1" in out and "已显式声明" not in out
    else:
        assert "保守降级为 1" not in out


def test_target_probe_returns_none_for_unknown_target():
    from framework.tools.common.target_probe import probe_partitioned, _base_url
    ok, why = probe_partitioned("http://127.0.0.1:9")
    assert ok is None and "未声明" in why
    assert _base_url("http://x:1/") == "http://x:1"
