# -*- coding: utf-8 -*-
"""一类判据：**试跑超时必须留下现场**（2026-11-02 · 用户报「900s 卡住查不出原因」后补）。

## 守的是什么（三个真缺陷，都在同一段代码里）

1. **超时把已捕获的输出丢了**：`subprocess.TimeoutExpired` 自带 `stdout/stderr`（`capture_output`
   开着就已经抓在手里），原实现直接 `return False`，用户只看到一句"真卡住"，
   不知道停在哪个 step —— 两边只能靠猜。
2. **只杀直接子进程**：`subprocess.run(timeout=)` 杀 pytest，但 pytest 拉起的 **Chromium / 驱动
   可能继续活着**，还占着被测服务与端口 -> 紧接着的重试轮在更脏的环境里跑，于是"两轮都超时"，
   现象看着像"这条用例根本跑不完"。
3. **`watchdog.txt` 有无被混为一谈**：用例看门狗（`HYBRID_CASE_TIMEOUT` 默认 600s）会写栈。
   它**有内容** => 600s 时用例确实在跑（栈直接指向卡住的行）；
   它**是空文件 / 不存在** => 看门狗没装上（卡在夹具之前）。这两条路要分开说。

## 判据

* `_last_step_line`：能从输出里揪出最后一条 step 行；抓不到返回空串（那本身也是结论）；
* `_find_watchdog_tail`：找最近一次 watchdog.txt 并给尾部；**0 字节要如实返回空行列表**，不许报"有栈";
* `run_capture_tree`：超时抛 `TimeoutExpired` 且**带着已捕获输出**；子进程树被杀掉。
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from framework.shared import text_io as TIO                                          # noqa: E402
from framework.features.f10_cli import cli as CLI                                   # noqa: E402


# --------------------------------------------------------------- 抓“停在哪一步”

def test_last_step_line_picks_the_final_step():
    text = (
        "[TEST] [step 1] login_step: fill account  (+0.0s / 累计 0.0s)\n"
        "some noise line\n"
        "[CHECK] [step 164] v assert: first row is it  (+0.0s / 累计 214.7s)\n"
        "===== short test summary =====\n"
    )
    got = CLI._last_step_line(text)
    assert "step 164" in got, "[NG] 没抓到最后一条 step 行: %r" % (got,)
    assert got.startswith("[CHECK]"), "[NG] 抓错行: %r" % (got,)


def test_last_step_line_returns_empty_when_no_steps():
    """抓不到 step 行 = 卡在**用例开始之前**（夹具/浏览器/服务）—— 这个结论必须能表达。"""
    assert CLI._last_step_line("") == ""
    assert CLI._last_step_line("ERROR collecting ...\nTraceback\n") == ""


def test_last_step_line_ignores_plain_noise():
    text = "[TEST] 这行没有 step 标记\n[TEST] [step 7] real step\n"
    assert "step 7" in CLI._last_step_line(text)


# --------------------------------------------------------------- 看门狗栈

def test_find_watchdog_tail_reports_empty_file_honestly(tmp_path, monkeypatch):
    """**0 字节的 watchdog.txt 必须如实返回空行列表** —— 不许把它说成"有栈"。"""
    run = tmp_path / "log" / "run_x"
    run.mkdir(parents=True)
    (run / "watchdog.txt").write_text("", encoding="utf-8")
    monkeypatch.setattr(CLI.config, "LOG_DIR", tmp_path / "log", raising=False)
    got = CLI._find_watchdog_tail()
    assert got is not None, "[NG] 文件明明在，不该报 None"
    path, lines = got
    assert lines == [], "[NG] 空文件不该给出栈行: %r" % (lines,)


def test_find_watchdog_tail_returns_none_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(CLI.config, "LOG_DIR", tmp_path / "nonexistent", raising=False)
    assert CLI._find_watchdog_tail() is None


# --------------------------------------------------------------- 杀进程树 + 带出输出

def test_run_capture_tree_raises_timeout_with_partial_output(tmp_path):
    """超时必须**带着已输出内容**一起抛 —— 这正是原来被丢掉的那份现场。"""
    script = (
        "import sys, time\n"
        "sys.stdout.write('[TEST] [step 3] clicking\\n')\n"
        "sys.stdout.flush()\n"
        "time.sleep(30)\n"
    )
    f = tmp_path / "hang.py"
    f.write_text(script, encoding="utf-8")
    try:
        TIO.run_capture_tree([sys.executable, str(f)], timeout=2)
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout or ""
        if isinstance(out, bytes):
            out = out.decode("utf-8", "replace")
        assert "[step 3]" in out, "[NG] 超时没把已捕获输出带回来: %r" % (out,)
        return
    raise AssertionError("[NG] 没有按超时抛出")


def test_run_capture_tree_normal_path_matches_run_capture(tmp_path):
    """正常结束时行为与 run_capture 一致（exit code + stdout），别把正常路径搞坏。"""
    f = tmp_path / "ok.py"
    f.write_text("print('hello-utf8-中文')\n", encoding="utf-8")
    r = TIO.run_capture_tree([sys.executable, str(f)], timeout=30)
    assert r.returncode == 0
    assert "hello-utf8-中文" in (r.stdout or "")


def test_run_capture_tree_kills_child_tree(tmp_path):
    """子进程树必须被杀掉：这里让子进程再拉一个孙进程，超时后孙进程不该活着写文件。"""
    marker = tmp_path / "survived.txt"
    script = tmp_path / "parent.py"
    script.write_text(
        "import subprocess, sys, time\n"
        "child = subprocess.Popen([sys.executable, '-c',\n"
        "    'import time,sys;time.sleep(8);open(sys.argv[1],\"w\").write(\"alive\")',\n"
        f"    {str(marker)!r}])\n"
        "time.sleep(30)\n",
        encoding="utf-8",
    )
    try:
        TIO.run_capture_tree([sys.executable, str(script)], timeout=2)
    except subprocess.TimeoutExpired:
        pass
    time.sleep(9)                       # 等过孙进程自己那条 sleep(8)
    assert not marker.exists(), "[NG] 孙进程活着写下了文件 -> 进程树没杀干净"


# --------------------------------------------------------------- 回放模式「重试无意义」短路

def test_case_llm_sources_reads_answer_origin(tmp_path, monkeypatch):
    """用例 -> 答案出处（llm_source）。这是「重放会不会有新答案」的唯一真判据。"""
    import json as _json
    d = tmp_path / "cases" / "scenario_x"
    d.mkdir(parents=True)
    (d / "ai_case_a.json").write_text(_json.dumps({"llm_source": "replay:abcd1234"}),
                                      encoding="utf-8")
    monkeypatch.setattr(CLI.config, "CASES_DIR", tmp_path / "cases", raising=False)
    got = CLI._case_llm_sources(["ai_case_a"])
    assert got == {"ai_case_a": "replay:abcd1234"}, "[NG] 没读出答案出处: %r" % (got,)


def test_case_llm_sources_empty_when_unknown(tmp_path, monkeypatch):
    """读不到出处就返回空 dict —— **不短路**（宁可多试一轮，也别误杀）。"""
    monkeypatch.setattr(CLI.config, "CASES_DIR", tmp_path / "nothing", raising=False)
    assert CLI._case_llm_sources(["ai_case_a"]) == {}
    assert CLI._case_llm_sources([]) == {}


def test_replay_short_circuit_sits_before_verify_and_names_llm_record():
    """回放短路必须在**试跑之前**，且必须告诉用户"要新答案得加 --llm-record"。

    反例（2026-11-02 用户实测）：同一条录像重放出的还是同一个用例，两轮各等 900s 才失败。
    """
    src = Path(CLI.__file__).read_text(encoding="utf-8")
    i_short = src.find("回放模式下新一轮用例与上一轮**出自同一条录像**")
    i_verify = src.find("ok, reasons = _verify_cases_detailed(done)")
    assert i_short > 0, "[NG] 找不到回放短路那段"
    assert i_verify > 0
    assert i_short < i_verify, "[NG] 短路必须排在试跑之前，否则照样白等一个 900s 窗口"
    seg = src[i_short:i_verify]
    assert "--llm-record" in seg, "[NG] 必须告诉用户怎么拿到新答案"
    assert "SystemExit(3)" in seg, "[NG] 短路后要按「用例不可用」退出，不能静默当通过"


# --------------------------------------------------------------- 相似度平手取最新录制

def test_fuzzy_tie_breaks_to_newest_recording(tmp_path, monkeypatch):
    """相似度**平手**时必须取**最新录制**（与结构键同一口径）。

    反例（2026-11-02 实测）：同一场景先后录过两份，场景相似度都是 100%；
    原实现 `r > best[0]` 平手不换 -> 保留字典序先扫到的那份 = 更旧的那份 ->
    回放永远拿到那份**已被闸门判不合格**的答案 -> 拦下 -> 重试还是它 -> 死路。
    """
    import json as _json
    from framework.features.f08_replay.llm_cassette_explore import Cassette

    # 场景文案必须落在 fuzzy 真正比对的那一节（_SCEN_RE 的口径），否则不做 fuzzy
    scen = "把下单到开票的全流程规划成步骤"
    prompt = f"请把场景规划成【JSON 步骤】\n自然语言测试场景：「{scen}」\n控件：A、B"
    for name, created, answer in [
        ("aaaa1111", "2026-11-02T14:07:33+08:00", {"steps": ["旧答案"]}),
        ("bbbb2222", "2026-11-02T14:20:19+08:00", {"steps": ["新答案"]}),
    ]:
        (tmp_path / f"{name}.json").write_text(_json.dumps({
            "key": name, "prompt": prompt, "system": "S",
            "created_at": created, "responses": [{"kind": "structured", "completion": answer}],
        }, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("HYBRID_CASSETTE_FUZZY", "1")
    c = Cassette("replay", tmp_path)
    got = c.lookup(prompt.replace("A、B", "A、B、C"), system="S", struct_key_value="不存在的结构键")
    assert got is not None, "[NG] 相似度匹配没命中"
    assert got.get("_match") == "fuzzy", "[NG] 命中的不是相似度这一级: %r" % (got.get("_match"),)
    assert got.get("key") == "bbbb2222", (
        "[NG] 平手时取了旧录像（%r）—— 必须取最新录制" % (got.get("key"),))


# --------------------------------------------------------------- 试跑预算按「声明等待」推导

def test_declared_wait_sums_timeout_ms_from_generated_script(tmp_path):
    """预算推导必须数**生成脚本里真正的 `timeout_ms=`**，而不是猜步数。"""
    f = tmp_path / "case_x.py"
    f.write_text(
        "_assert_first_row(page, 'a', 'x', timeout_ms=160000)\n"
        "_assert_first_row(page, 'b', 'y', timeout_ms=160000)\n"
        "_assert_wait_text(page, 'z', timeout_ms=45000)\n"
        "_assert_url(page, 'u')\n",
        encoding="utf-8")
    assert CLI._declared_wait_s(f) == 365.0, "[NG] 声明等待没数对: %r" % (CLI._declared_wait_s(f),)


def test_verify_budget_covers_declared_waits(tmp_path, monkeypatch):
    """**慢机器误判「卡死」的根治**：4 处 ×160s 的等待 + 正常执行 400~500s ≈ 1040s > 默认 900s，
    用例其实在正常等，却被判卡住（2026-11-02 用户 Windows 实测）。预算必须由声明等待推导。"""
    monkeypatch.delenv("HYBRID_VERIFY_TIMEOUT", raising=False)
    f = tmp_path / "case_y.py"
    f.write_text("_assert_first_row(page, 'a', 'x', timeout_ms=160000)\n" * 4, encoding="utf-8")
    budget, why = CLI._verify_budget_s(f)
    assert budget >= 1000.0, "[NG] 预算 %r 覆盖不了「基线+4×160s」这种最坏情况" % (budget,)
    assert "声明等待" in why, "[NG] 依据要说人话（让人能审）: %r" % (why,)


def test_verify_budget_respects_explicit_env(tmp_path, monkeypatch):
    """**用户显式设了就听用户的** —— 框架不许偷偷改掉他的明确选择。"""
    monkeypatch.setenv("HYBRID_VERIFY_TIMEOUT", "300")
    f = tmp_path / "case_z.py"
    f.write_text("_assert_first_row(page, 'a', 'x', timeout_ms=160000)\n" * 4, encoding="utf-8")
    budget, why = CLI._verify_budget_s(f)
    assert budget == 300.0, "[NG] 显式设置被覆盖了: %r" % (budget,)
    assert "HYBRID_VERIFY_TIMEOUT" in why


def test_verify_budget_falls_back_when_no_declared_wait(tmp_path, monkeypatch):
    """读不到声明等待就退回默认预算 —— 绝不因为读不到就把预算放大。"""
    monkeypatch.delenv("HYBRID_VERIFY_TIMEOUT", raising=False)
    f = tmp_path / "case_w.py"
    f.write_text("print('no waits here')\n", encoding="utf-8")
    budget, why = CLI._verify_budget_s(f)
    assert budget == 900.0, "[NG] 没读到等待却把预算放大了: %r" % (budget,)
