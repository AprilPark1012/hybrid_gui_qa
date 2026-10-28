"""V8.7.9 判据：`all --ai --no-run`（开发期不跑 run）。

由来（用户 2026-10-28 原话）：
  「对，现在要解决的是开发期效率低的问题，还没有进入交付期可以不跑 run」

在此之前，开发期调 AI 产出只能用 `all --ai`，**每次都把交付期的 run 也跑一遍**
（那条已 verify 过的用例被重跑一次，实测 ~200s），而 run 的产出（report.html）
在开发期根本没人看。

【为什么是 `all --no-run` 而不是教用户敲 `explore --ai`】
  助手一开始的建议是「开发期用 `explore --ai`」，被
  `test_j2_no_explore_ai_as_runnable_command` 当场否掉 —— 那条判据钉的是
  用户 2026-10-11 定的口径：「两条链路统一成 `python -m framework.cli all`，
  真 AI 链路用 `--ai` 区分，**不另开命令**」。
  所以能力开在 `all` 上（与已有的 `--no-verify` / `--no-cases` 同族），入口仍只有一个。

【`--no-run` 到底省了什么、留下了什么】
  留下的：用例已生成、脚本已生成（verify 内部会 generate 一次）、**已实跑验证过**
          （`explore --ai` 默认带 verify，`do_verify = "--no-verify" not in rest`）
  省掉的：run 阶段的正式执行（并发 + report.html + traces）—— 开发期不看它
"""
from __future__ import annotations

from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
CLI_SRC = BASE / "framework/features/f10_cli/cli.py"


def _src() -> str:
    return CLI_SRC.read_text(encoding="utf-8")


def test_cmd_all_accepts_no_run_default_false() -> None:
    """`cmd_all` 必须接受 `no_run` 且**默认 False**（不改变默认行为）。"""
    src = _src()
    i = src.find("def cmd_all(")
    assert i > 0
    head = src[i:i + 600]
    assert "no_run: bool = False" in head, "必须默认 False —— 不加开关就是原来的三段全跑"


def _no_run_block() -> str:
    """取 `if no_run:` 分支的**完整范围** —— 到调用 cmd_run 之前为止。

    [!] 不要用固定字符数（如 src[i:i+900]）当窗口：V8.7.10 往这个分支里加了
        `--case` 组合校验后，`report.html` 那句就被挤出了 900 字符窗口，
        两条判据跟着变红 —— **那是窗口不够，不是断言不成立**。
        按函数体结构取范围，以后再加校验也不会误伤。
    """
    src = _src()
    i = src.find("if no_run:")
    assert i > 0, "cmd_all 里必须有 if no_run: 分支"
    j = src.find("cmd_run(", i)
    assert j > i, "找不到 cmd_run 调用（no_run 分支之后必须有它，否则开关没有意义）"
    return src[i:j]


def test_no_run_skips_cmd_run() -> None:
    """`no_run=True` 时必须**在调 cmd_run 之前 return**。"""
    seg = _no_run_block()
    assert "return" in seg, "必须 return（不继续走到 cmd_run）"


def test_no_run_rejects_case_combination() -> None:
    """`--case` + `--no-run` 一起给必须**报错**，不许静默忽略。

    [!] 这是 V8.7.9 引入 `--no-run` 时我自己埋的坑：`cmd_all` 里 `cases` **只传给
        `cmd_run`**，所以 `no_run` 时它完全不生效 —— 但也不报错。
        用户会以为「只重跑了那一条」，实际 explore 仍按场景文件走全流程。
        项目口径是「无效参数绝不静默忽略」，所以必须 `exit 2` 并指出正确做法。
    """
    seg = _no_run_block()
    j = seg.find("if cases:")
    k = seg.find("raise SystemExit(2)")
    assert j != -1, "no_run 分支里必须检查 cases"
    assert k != -1 and k > j, "必须 exit 2（不许只打印）"
    assert "run --case <case_id>" in seg, "必须指出正确做法（run --case）"


def test_no_run_says_report_is_missing() -> None:
    """必须**明说本次没有 report.html** —— 否则用户以为报告在某个目录里找半天。"""
    seg = _no_run_block()
    assert "report.html" in seg, "必须点明没有 report.html"
    assert "output/verify" in seg, "必须指出实测记录在哪（output/verify/）"


def test_no_run_registered_in_flag_specs_and_cmd_flags() -> None:
    """必须同时登记 `FLAG_SPECS`（权威规格）与 `CMD_FLAGS["all"]`（`all` 可用列表）。

    只登记 CMD_FLAGS 没用 —— 真正把关的是 FLAG_SPECS，
    漏了会报「不认识的参数」并给误导性建议（V8.7.8 加 `--skip-verified` 时实测踩过）。
    """
    src = _src()
    i = src.find("FLAG_SPECS: dict[str, str | None] = {")
    j = src.find("}", src.find('"--no-run"', i))
    assert '"--no-run": None' in src[i:j + 1], "必须登记在 FLAG_SPECS"
    k = src.find('"all": set(_COMMON_FLAGS)')
    seg2 = src[k:k + 900]
    assert '"--no-run"' in seg2, "必须出现在 all 的可用参数列表里"


def test_no_run_threads_through_dispatch() -> None:
    """分发层必须从 rest 读开关并传给 cmd_all。"""
    src = _src()
    dispatch = src[src.find('elif cmd == "all":'):][:600]
    assert 'no_run=("--no-run" in rest)' in dispatch, "分发层要从 rest 读 --no-run"


def test_dev_phase_does_not_teach_explore_ai() -> None:
    """开发期命令不许教成 `explore --ai` —— 统一入口是 `all`（用户 2026-10-11 口径）。

    这条与 `test_docs_truth_contract.py::test_j2_no_explore_ai_as_runnable_command`
    同向，但这里钉的是**README 的引导行**：它必须是 `all --ai --no-run`。
    """
    readme = (BASE / "README.md").read_text(encoding="utf-8")
    assert "all --ai --no-run" in readme, "README 要给出开发期命令"
    # 不许出现可照敲的 `framework.cli explore --ai`
    import re
    bad = re.search(r"framework\.cli\s+explore\s+--ai", readme)
    assert not bad, f"README 里不许出现可照敲的 explore --ai：{bad.group(0) if bad else ''}"
