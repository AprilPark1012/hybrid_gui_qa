"""V8.7.8 判据：verify 并发化 + `all --skip-verified`（run 不重跑已验证的用例）。

背景（用户 2026-10-27 提问）：
  「verify 跑通过以后，还需要 run 一遍吗？确认下这个逻辑是否合理？」

  查证结论：`all --ai` = explore(--verify) → generate → run。
    · verify 跑的是 `done`（**本轮**新产出的用例），逻辑是对的；
    · run 跑 `scripts/generated` 全量 —— 多场景时它要跑**其他场景**的用例（正当工作），
      但**本轮那条已经被 verify 真跑过了**，run 又跑一遍 = 纯重复。
      单场景时这一遍就是整个 run 的时间（实测 ~200s）。
    · 另发现：verify 是**逐条串行**跑（一条一个 pytest 子进程、串行等），
      单条 200~400s，10 个场景就是 30 分钟纯等待 —— 而 run 同一批用例 `-n 16` 只要几分钟。

  因此两件事：
    A. verify 串行 -> 并发（每条仍是独立 pytest 进程：日志/超时/归因各自独立）；
    B. 新增 `all --skip-verified`：run 用 `--deselect` 跳过本轮 verify 已通过的用例（默认关闭）。
"""
from __future__ import annotations

from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
CLI_SRC = BASE / "framework/features/f10_cli/cli.py"


def _src() -> str:
    return CLI_SRC.read_text(encoding="utf-8")


# ---------- A. verify 并发化 ----------

def test_verify_runs_cases_concurrently() -> None:
    """verify 必须能并发跑 —— 串行跑 N 条就是 N 倍等待。"""
    src = _src()
    i = src.find("def _verify_cases_detailed")
    assert i > 0
    seg = src[i:i + 12000]
    assert "ThreadPoolExecutor" in seg, "必须用线程池并发跑多条用例"
    assert "as_completed" in seg, "必须按完成顺序收结果（先完成先报，进度可见）"


def test_verify_reuses_run_worker_policy() -> None:
    """并发数必须复用 `safe_workers()`（**与 run 同一套内存预检**），不许另造一份。

    自造一份的下场：两处阈值漂移，run 判定安全、verify 却 OOM，
    或者反过来 verify 只用 1 路、run 用 16 路 —— 同一个项目两套口径。
    """
    src = _src()
    i = src.find("def _verify_cases_detailed")
    seg = src[i:i + 12000]
    assert "from framework.features.f07_concurrency.limits import safe_workers" in seg
    assert "safe_workers(None)" in seg


def test_verify_concurrency_falls_back_to_serial() -> None:
    """预检不可用 / 只有 1 条时，必须干净退回串行（不许因为并发机制挂掉）。"""
    src = _src()
    i = src.find("def _verify_cases_detailed")
    seg = src[i:i + 12000]
    assert "nw = 1" in seg, "默认必须是 1 路（串行）"
    assert "max(1, min(_n, len(todo)))" in seg, "并发数不能超过用例数"
    assert "if nw <= 1:" in seg, "必须有串行分支兜底"


def test_verify_keeps_per_case_process_not_xdist() -> None:
    """每条用例必须是**独立 pytest 进程**，不许改成 `pytest -n`。

    为什么：并发但共用一个 pytest 进程时，
      · 日志混在一起（分不清哪条是哪条）
      · 一条卡住拖累整批
      · 失败归因拆不开 —— 而 AI 重试要的正是「哪条、哪一步炸了」
    """
    src = _src()
    i = src.find("def _verify_cases_detailed")
    seg = src[i:i + 12000]
    # 每条仍是独立子进程调用
    assert '"pytest", node, "-v", "-s"' in seg, "单条仍要单独起 pytest 进程"
    assert '"-n"' not in seg, "verify 里不许出现 xdist 的 -n（会把多条揉进一个 pytest）"


def test_verify_prints_are_lock_protected() -> None:
    """并发下打印必须加锁，否则多行输出会互相插进对方中间。"""
    src = _src()
    i = src.find("def _verify_cases_detailed")
    seg = src[i:i + 12000]
    assert "threading.Lock()" in seg, "必须有打印锁"
    assert "with _out_lock:" in seg, "打印必须走锁"


def test_verify_unrunnable_case_counts_as_failure() -> None:
    """取不到脚本（`index.json` 里没有）必须判**失败**，不许当「跳过」。

    原实现是 `continue`（不影响 all_ok）—— 那等于把「没验过」当「验过了」，
    正是本项目反复吃过的假绿。
    """
    src = _src()
    i = src.find("def _verify_cases_detailed")
    seg = src[i:i + 12000]
    assert "不能把「没验过」当「验过了」" in seg
    assert "elif ok is None:" in seg and "all_ok = False" in seg


def test_verify_timeout_still_per_case() -> None:
    """并发后每条仍要有**独立超时**（一条卡住只判它失败，不拖累其他）。"""
    src = _src()
    i = src.find("def _verify_cases_detailed")
    seg = src[i:i + 12000]
    assert "verify_timeout_s()" in seg, "必须用可配的 verify 超时"
    assert "except subprocess.TimeoutExpired" in seg, "超时必须单独捕获并判该条失败"


# ---------- B. all --skip-verified ----------

def test_verified_ok_is_process_local_not_persisted() -> None:
    """「本轮已验证」必须**只存进程内**，绝不落盘。

    落盘的下场：下次跑读到上一次的记录 -> 把**新用例**当成「已验证」跳过 = 假绿。
    进程内生命周期天然只覆盖本轮；跨进程（用户单独跑 run）读到空集 -> 不跳过，安全。
    """
    src = _src()
    assert "_VERIFIED_OK: set[str] = set()" in src, "必须有进程内的已验证集合"
    assert "_VERIFIED_OK.json" not in src and 'write_text' not in src.split("_VERIFIED_OK")[0][-400:]
    # 更硬的判据：整份源码里不许出现把 _VERIFIED_OK 写文件的调用
    for line in src.splitlines():
        if "_VERIFIED_OK" in line:
            assert "write_text" not in line and "json.dump" not in line, \
                f"不许持久化 _VERIFIED_OK：{line.strip()}"


def test_cmd_run_accepts_skip_verified() -> None:
    """`cmd_run` 必须接受 `skip_verified` 开关，并默认关闭。"""
    src = _src()
    i = src.find("def cmd_run(")
    assert i > 0
    head = src[i:i + 400]
    assert "skip_verified: bool = False" in head, "必须默认 False（不改变默认行为）"


def test_skip_verified_uses_deselect() -> None:
    """跳过的实现方式必须是 pytest 的 `--deselect`（精确排除 node id）。"""
    src = _src()
    i = src.find("def cmd_run(")
    assert i > 0
    j = src.find('mode = "调试模式', i)
    assert j > i
    seg = src[i:j]                       # cmd_run 从签名到 pytest 命令构建完为止
    assert '"--deselect", _node' in seg, "必须按 node id deselect"
    assert "index.json" in seg, "node id 要从 index.json 的 script_path 拼出来"


def test_skip_verified_uses_relative_node_id() -> None:
    """`--deselect` 必须用**相对 rootdir 的路径**，不许拼绝对路径。

    实测事故（2026-10-27）：用 `config.BASE / script_path` 拼绝对路径时，
    打印说「1 条不再重复跑」、命令行也确实带了 `--deselect`，
    但 pytest 静默不匹配 node id —— **用例照跑满 204 秒**，等于开关完全没生效。
    改成相对路径后同场景 **1.09 秒**（no tests ran）。

    这是「看着生效、实际没生效」型 bug：只有真跑一次才发现，静态读代码看不出来。
    """
    src = _src()
    i = src.find("if skip_verified:")
    j = src.find('mode = "调试模式', i)
    assert j > i
    seg = src[i:j]
    assert '_rel = _idx2[_cid]["script_path"]' in seg, "必须取 index.json 里的相对路径"
    assert 'config.BASE / _idx2' not in seg, "不许拼绝对路径（--deselect 会静默失效）"
    assert 'f"{_rel}::test_{_cid}"' in seg, "node id 必须是相对路径 + ::test_<case_id>"


def test_skip_verified_skips_all_is_not_failure() -> None:
    """全部用例都跳过时 pytest 返回 5（no tests ran）——**必须**与「--case 写错」区分开。

    否则用户一开开关就被判红，开关等于不能用。
    """
    src = _src()
    assert "_skip_all = bool(skip_verified and _deselected and r.returncode == 5)" in src
    assert "if r.returncode != 0 and not _skip_all:" in src, "全部跳过时不许 raise"
    assert "_write_run_summary(run_dir, run_id, 0 if _skip_all else r.returncode)" in src, \
        "summary 要记 0，否则归档策略会把这次当失败 run"


def test_skip_verified_warns_without_records() -> None:
    """单独跑 `run --skip-verified`（没有本轮 verify 记录）时必须**明确告知无效果**，
    不许静默什么都不做（用户会以为省了时间，其实没省）。"""
    src = _src()
    i = src.find("if skip_verified:")
    assert i > 0
    seg = src[i:i + 900]
    assert "无效果" in seg, "必须提示「本进程内没有 verify 记录」"


def test_skip_verified_flags_registered() -> None:
    """`--skip-verified` 必须同时登记在 FLAG_SPECS（权威规格）与 CMD_FLAGS（`all` 可用列表）。

    [!] 只登记 CMD_FLAGS 没用：真正把关的是 FLAG_SPECS，漏了就会报「不认识的参数」
        并给一个「是不是想写 --no-verify」的误导性建议（本次实测踩过）。
    """
    src = _src()
    i = src.find("FLAG_SPECS: dict[str, str | None] = {")
    j = src.find("}", src.find('"--skip-verified"', i))
    assert '"--skip-verified": None' in src[i:j + 1], "必须登记在 FLAG_SPECS"
    k = src.find('"all": set(_COMMON_FLAGS)')
    seg2 = src[k:k + 800]
    assert '"--skip-verified"' in seg2, "必须出现在 all 的可用参数列表里"


def test_skip_verified_threads_through_all() -> None:
    """`all` → `cmd_run` 必须把开关接上（否则参数收了但没生效）。"""
    src = _src()
    i = src.find("def cmd_all(")
    head = src[i:i + 500]
    assert "skip_verified: bool = False" in head, "cmd_all 也要接这个参数"
    call = src[src.find("cmd_run(workers, debug, force_workers, cases=cases", i):][:400]
    assert "skip_verified=skip_verified" in call, "必须透传给 cmd_run"
    dispatch = src[src.find('elif cmd == "all":'):][:500]
    assert 'skip_verified=("--skip-verified" in rest)' in dispatch, "分发层要从 rest 读开关"
