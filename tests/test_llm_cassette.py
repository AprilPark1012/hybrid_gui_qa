"""LLM 录像（录制 / 回放）契约测试 —— 秒级，**不需要浏览器、不需要网络、不需要 key**。

为什么这些断言值钱：cassette 是「让连不上外网的机器也能跑 AI 链路」的唯一手段。它一旦
静默降级（未命中时偷偷改走实时调用、或拿 mock 顶），产出的用例就会挂着 AI 的名却没人问过
AI —— 正是本项目反复修掉的那类假绿。所以这里把两条钉死：
  ① 未命中必须报错（绝不悄悄改走 live）；② 回放路径**绝不触碰网络 / LLM 对象**。
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from framework import explorer  # noqa: E402
from framework.llm_cassette import (MODE_RECORD, MODE_REPLAY, Cassette, CassetteError,  # noqa: E402
                                    cassette_key, render_miss_help, struct_key)

ITEMS = [
    {"semantic_name": "搜索按钮", "role": "button", "name": "搜索"},
    {"semantic_name": "搜索框", "role": "textbox", "name": "搜索", "placeholder": "请输入"},
]
URL = "http://localhost:8000/index.html"
SCENARIO = "在搜索框输入 1005 点搜索"


# ---------------------------------------------------------------- 测试替身

def _plan():
    return explorer._PlanModel(steps=[explorer._StepModel(
        order=1, action="click", semantic_name="搜索按钮", description="点搜索")])


class _Resp:
    def __init__(self, completion):
        self.completion = completion


class _FakeLLM:
    """最小可用假 LLM：只走 _ai_explore_async 的结构化那条路径。"""

    model = "fake-model"

    def __init__(self, completion=None):
        self.completion = completion if completion is not None else _plan()
        self.calls = 0

    async def ainvoke(self, msgs, output_format=None):
        self.calls += 1
        return _Resp(self.completion)


def _run_explore(cassette, scenario: str = SCENARIO, items=None):
    return asyncio.run(explorer._ai_explore_async(
        scenario, items or ITEMS, URL, llm_cassette=cassette))


def _no_llm(monkeypatch):
    """把 LLM 工厂换成「一被调用就炸」——用来证明某条路径根本没碰它。"""
    def _boom():
        raise AssertionError("这条路径不该构造 LLM 对象（回放必须完全不联网）")
    monkeypatch.setattr("framework.config.llm_from_env", _boom)


# ---------------------------------------------------------------- 键

def test_key_stable_and_sensitive():
    a = cassette_key("P", "S")
    assert a == cassette_key("P", "S")              # 同 prompt+system ⇒ 同键（可复现的基础）
    assert len(a) == 16 and a.isalnum()
    assert a != cassette_key("P2", "S")             # 场景/清单差一个字 ⇒ 不命中（刻意的严格）
    assert a != cassette_key("P", "S2")             # system 变了（提示词改版）⇒ 不命中


# ---------------------------------------------------------------- 存取

def test_store_lookup_roundtrip(tmp_path):
    c = Cassette(MODE_RECORD, tmp_path)
    p = c.store("PROMPT", "m", "SYS", [{"kind": "structured", "completion": {"steps": []}}])
    assert p is not None
    assert p.is_file()
    rec = json.loads(p.read_text(encoding="utf-8"))
    assert rec["model"] == "m" and rec["system"] == "SYS" and rec["prompt"] == "PROMPT"
    assert rec["framework_version"]                       # 版本是单一来源，能读就读到，读不到写 unknown
    c2 = Cassette(MODE_REPLAY, tmp_path)
    got = c2.lookup("PROMPT", "SYS")
    assert got and got["key"] == rec["key"]
    assert c2.lookup("别的 prompt", "SYS") is None        # 没录过 ⇒ None（由调用方报错）


def test_store_merges_both_kinds(tmp_path):
    """同一次录制里结构化 + 文本两条路径的回答都要留住（回放时按序尝试）。"""
    c = Cassette(MODE_RECORD, tmp_path)
    c.store("P", "m", "S", [{"kind": "structured", "completion": {"steps": []}}])
    c.store("P", "m", "S", [{"kind": "text", "completion": "{\"steps\": []}"}])
    rec = c.lookup("P", "S")
    kinds = sorted(r["kind"] for r in rec["responses"])
    assert kinds == ["structured", "text"]


def test_no_tmp_file_left_behind(tmp_path):
    """原子写：绝不留半截 .tmp（它会被后续回放当成损坏文件）。"""
    c = Cassette(MODE_RECORD, tmp_path)
    c.store("P", "m", "S", [{"kind": "text", "completion": "x"}])
    assert list(tmp_path.glob("*.tmp")) == []
    assert len(list(tmp_path.glob("*.json"))) == 1


def test_corrupt_file_is_error_not_miss(tmp_path):
    """文件坏了要报错 —— 不能伪装成「没录过」（那会把数据损坏藏起来）。"""
    c = Cassette(MODE_RECORD, tmp_path)
    p = c.store("P", "m", "S", [{"kind": "text", "completion": "x"}])
    assert p is not None
    p.write_text("{ 这不是 json", encoding="utf-8")
    with pytest.raises(CassetteError) as ei:
        Cassette(MODE_REPLAY, tmp_path).lookup("P", "S")
    assert "读不动" in str(ei.value)


def test_empty_responses_is_error(tmp_path):
    c = Cassette(MODE_RECORD, tmp_path)
    p = c.store("P", "m", "S", [{"kind": "text", "completion": "x"}])
    assert p is not None
    rec = json.loads(p.read_text(encoding="utf-8"))
    rec["responses"] = []
    p.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(CassetteError) as ei:
        Cassette(MODE_REPLAY, tmp_path).lookup("P", "S")
    assert "没有可用回答" in str(ei.value)


def test_replay_missing_dir_fails_loud(tmp_path):
    with pytest.raises(CassetteError) as ei:
        Cassette(MODE_REPLAY, tmp_path / "nope")
    msg = str(ei.value)
    assert "不存在" in msg and "--llm-record" in msg      # 报错必须带下一步动作


def test_unknown_mode_rejected(tmp_path):
    with pytest.raises(CassetteError):
        Cassette("随便", tmp_path)


# ---------------------------------------------------------------- 回放：不联网

def test_replay_never_touches_llm(tmp_path, monkeypatch):
    """核心红线：回放命中时**不构造 LLM 对象**（离线机器连 key 都没有也得能跑）。"""
    Cassette(MODE_RECORD, tmp_path).store(
        _prompt_for(SCENARIO), "m", explorer._PLANNER_SYSTEM,
        [{"kind": "structured", "completion": _plan().model_dump()}])
    _no_llm(monkeypatch)                                  # 一被调用就炸
    emap = _run_explore(Cassette(MODE_REPLAY, tmp_path))
    assert [s.element.semantic_name for s in emap.steps if s.element] == ["搜索按钮"]


def test_replay_miss_raises_with_diagnosis(tmp_path, monkeypatch):
    """未命中必须报错 + 告诉人「差在哪」，绝不悄悄改走实时调用。"""
    Cassette(MODE_RECORD, tmp_path).store(
        _prompt_for("完全另一个场景"), "m", explorer._PLANNER_SYSTEM,
        [{"kind": "structured", "completion": _plan().model_dump()}])
    _no_llm(monkeypatch)
    with pytest.raises(explorer.AiExploreError) as ei:
        _run_explore(Cassette(MODE_REPLAY, tmp_path))
    msg = str(ei.value)
    assert "没有这一份" in msg
    assert "从第" in msg and "行起不同" in msg            # 给出最接近的一份的差异位置
    assert "--llm-record" in msg                          # 给出下一步动作


def test_replay_bad_recording_fails_loud(tmp_path, monkeypatch):
    """录像在、但解析不出步骤（录制方版本不兼容）⇒ 报错，不能静默产出空用例。"""
    Cassette(MODE_RECORD, tmp_path).store(
        _prompt_for(SCENARIO), "m", explorer._PLANNER_SYSTEM,
        [{"kind": "structured", "completion": {"steps": "这不是列表"}}])
    _no_llm(monkeypatch)
    with pytest.raises(explorer.AiExploreError) as ei:
        _run_explore(Cassette(MODE_REPLAY, tmp_path))
    assert "解析不出步骤" in str(ei.value)


# ---------------------------------------------------------------- 录 → 放 闭环

def test_record_then_replay_same_steps(tmp_path, monkeypatch):
    """录一次 → 用录像回放 ⇒ 结果与录制那次一致（这是「离线可跑」的硬证据）。"""
    fake = _FakeLLM()
    monkeypatch.setattr("framework.config.llm_from_env", lambda: fake)
    rec_cass = Cassette(MODE_RECORD, tmp_path)
    live = _run_explore(rec_cass)
    assert fake.calls == 1 and rec_cass.saves == 1
    assert len(list(tmp_path.glob("*.json"))) == 1

    _no_llm(monkeypatch)                                  # 回放阶段：碰 LLM 就炸
    rep = _run_explore(Cassette(MODE_REPLAY, tmp_path))
    assert [(s.action, s.element.semantic_name if s.element else None) for s in live.steps] == \
           [(s.action, s.element.semantic_name if s.element else None) for s in rep.steps]


def test_record_store_failure_does_not_break_explore(tmp_path, monkeypatch):
    """录制目录不可写时……不该静默成功，也不该把已经拿到的步骤丢掉。

    这里的口径：store 抛错 → 由上层显现（本用例只钉住「store 的异常不会被悄悄吞掉」）。
    """
    fake = _FakeLLM()
    monkeypatch.setattr("framework.config.llm_from_env", lambda: fake)
    cass = Cassette(MODE_RECORD, tmp_path)
    def _boom(*a, **k):
        raise OSError("磁盘满")
    monkeypatch.setattr(Cassette, "store", _boom)
    with pytest.raises(OSError):
        _run_explore(cass)


def test_no_cassette_means_live_only(tmp_path, monkeypatch):
    """不带 cassette → 行为与加本功能之前一致（只调 LLM，不落任何录像）。"""
    fake = _FakeLLM()
    monkeypatch.setattr("framework.config.llm_from_env", lambda: fake)
    emap = asyncio.run(explorer._ai_explore_async(SCENARIO, ITEMS, URL))
    assert [s.element.semantic_name for s in emap.steps if s.element] == ["搜索按钮"]
    assert list(tmp_path.glob("*.json")) == []


# ---------------------------------------------------------------- 报错归因

def test_failure_hint_classification():
    assert "网络" in explorer._llm_failure_hint("结构化输出路径 ModelProviderError: Connection error.")
    assert "网络" in explorer._llm_failure_hint("ConnectTimeout: timed out")
    assert "key" in explorer._llm_failure_hint("Error code: 401 - invalid_api_key")
    assert "限流" in explorer._llm_failure_hint("429 Too Many Requests")
    assert explorer._llm_failure_hint("模型输出里没有 steps 字段") == ""   # 归不了类就不硬猜


def test_error_message_keeps_real_cause(tmp_path, monkeypatch):
    """真因不许被后写的失败冲掉（2026-09-18 修的：无网被报成「解析不出来」）。"""
    class _Boom:
        model = "m"

        async def ainvoke(self, msgs, output_format=None):
            raise RuntimeError("Connection error.")

    monkeypatch.setattr("framework.config.llm_from_env", lambda: _Boom())
    monkeypatch.setenv("HYBRID_LLM_ATTEMPTS", "1")
    with pytest.raises(explorer.AiExploreError) as ei:
        asyncio.run(explorer._ai_explore_async(SCENARIO, ITEMS, URL))
    msg = str(ei.value)
    assert "Connection error" in msg            # 真因在
    assert "网络" in msg                        # 且给出了「最可能是什么问题」
    assert "--llm-record" in msg                # 以及无外网机器的出路


# ---------------------------------------------------------------- CLI 契约

def test_cli_flags_registered_for_explore_only():
    from framework import cli
    for f in ("--llm-cassette", "--llm-record"):
        assert f in cli.FLAG_SPECS
        assert cli.FLAG_SPECS[f] == "opt"            # 值可省（省了用默认目录）
        assert f in cli.CMD_FLAGS["explore"]
        assert f not in cli.CMD_FLAGS["run"]         # 只对 explore 生效


def test_cli_rejects_conflicting_and_wrong_command():
    import subprocess
    from framework.text_io import run_capture

    def _cli(*args):
        return run_capture([sys.executable, "-m", "framework.cli", *args],
                           cwd=str(Path(__file__).resolve().parent.parent))

    r = _cli("explore", "--ai", "--llm-record", "--llm-cassette")
    assert r.returncode == 2 and "互斥" in (r.stdout + r.stderr)

    r = _cli("run", "--llm-cassette", "x")           # 用错子命令 ⇒ 必须报错，不许静默忽略
    assert r.returncode == 2 and "只用于" in (r.stdout + r.stderr)


def test_arg_value_supports_equals_form():
    from framework.cli import _arg_value
    rest = ["--llm-cassette=/tmp/abc", "--scenario", "x"]
    assert _arg_value(rest, "--llm-cassette") == "/tmp/abc"       # 等号写法不许被丢掉
    assert _arg_value(rest, "--scenario") == "x"
    assert _arg_value(["--llm-cassette", "--scenario", "x"], "--llm-cassette") is None   # 省值 = 默认目录
    assert _arg_value(["--llm-cassette"], "--llm-cassette") is None


# ---------------------------------------------------------------- 拼装 ai_explore 全链

def test_ai_explore_accepts_cassette(tmp_path, monkeypatch):
    """ai_explore 把 cassette 透传到异步阶段（同步探测用替身，不启浏览器）。"""
    monkeypatch.setattr(explorer, "_collect_page_context",
                        lambda items, url, pages=None: (ITEMS, [], "", [], []))
    fake = _FakeLLM()
    monkeypatch.setattr("framework.config.llm_from_env", lambda: fake)
    emap = explorer.ai_explore(SCENARIO, [], URL, llm_cassette=Cassette(MODE_RECORD, tmp_path))
    assert emap.steps and fake.calls == 1
    assert len(list(tmp_path.glob("*.json"))) == 1


def test_help_text_mentions_both_flags():
    """--help 取自 docstring：两个参数必须在里面（文档与代码同源）。"""
    from framework import cli
    doc = cli.cmd_explore.__doc__ or ""
    assert "--llm-record" in doc and "--llm-cassette" in doc


def _prompt_for(scenario: str) -> str:
    """拿到与 explorer 内部**逐字相同**的 prompt（录像键就是它的 sha256）。"""
    return explorer._build_planner_prompt(scenario, ITEMS, URL)


# ---------------------------------------------------------------- 结构键（数据值变了也能命中）

def _sk(scenario: str, items=None) -> str:
    return struct_key(scenario, items or ITEMS, None, explorer._PLANNER_SYSTEM)


def _items_with_other_data():
    """同一页面结构、但**业务数据的值**不同 —— 模拟「另一台机器」或「跑过测试的机器」。

    这是实测踩到的真问题：prompt 里的 nearby_text 是列表行整行文本（管理单元/帐套/客户/业务单元），
    而 demo 的预置数据是随机的、/api/reset（pytest 每条用例前都调）会重新随机 ⇒ 严格键跨机器必不命中。
    """
    return [
        {**ITEMS[0], "nearby_text": "合同1 0451 001 预po 北京华信科技有限公司 bu_b"},
        {**ITEMS[1], "nearby_text": "合同2 1031 002 po 上海远东贸易有限公司 bu_c"},
    ]


def test_struct_key_ignores_data_values():
    a = _sk(SCENARIO)
    assert a == _sk(SCENARIO, _items_with_other_data())      # 数据值不同 ⇒ 结构键相同（跨机器可复用）
    changed = [dict(ITEMS[0], semantic_name="搜索按钮2"), ITEMS[1]]
    assert _sk(SCENARIO, changed) != a                       # 控件结构变了 ⇒ 键必须变（不许套旧结论）
    assert _sk(SCENARIO + "换个说法") != a                   # 场景变了 ⇒ 键必须变
    assert a != struct_key(SCENARIO, ITEMS, None, "别的 system")   # system（提示词）变了 ⇒ 键必须变


def test_lookup_struct_fallback_and_strict_switch(tmp_path):
    Cassette(MODE_RECORD, tmp_path).store(
        _prompt_for(SCENARIO), "m", explorer._PLANNER_SYSTEM,
        [{"kind": "structured", "completion": _plan().model_dump()}],
        key_struct=_sk(SCENARIO))
    c = Cassette(MODE_REPLAY, tmp_path)
    rec = c.lookup("prompt 完全变了（数据不同）", explorer._PLANNER_SYSTEM,
                   struct_key_value=_sk(SCENARIO))
    assert rec is not None and rec["_match"] == "struct"
    assert c.lookup("prompt 完全变了（数据不同）", explorer._PLANNER_SYSTEM,
                    struct_key_value=_sk(SCENARIO), strict_only=True) is None
    # 严格键那条路仍然优先、且标记为 strict
    rec2 = c.lookup(_prompt_for(SCENARIO), explorer._PLANNER_SYSTEM, struct_key_value=_sk(SCENARIO))
    assert rec2 is not None and rec2["_match"] == "strict"


def test_struct_key_survives_probe_order_change(tmp_path):
    """控件清单顺序变了（探测顺序不稳）不该让结构键失效 —— 所以键里排序。"""
    assert _sk(SCENARIO) == _sk(SCENARIO, list(reversed(ITEMS)))


def test_replay_uses_struct_key_when_data_changes(tmp_path, monkeypatch):
    """换一批数据（同结构）⇒ 仍能回放成功（这条就是「工作电脑能不能用」的核心断言）。"""
    monkeypatch.setattr("framework.config.llm_from_env", lambda: _FakeLLM())
    _run_explore(Cassette(MODE_RECORD, tmp_path))                       # 录：数据 A
    _no_llm(monkeypatch)                                                # 放：不碰 LLM
    emap = _run_explore(Cassette(MODE_REPLAY, tmp_path), items=_items_with_other_data())
    assert [s.element.semantic_name for s in emap.steps if s.element] == ["搜索按钮"]


def test_strict_replay_fails_when_data_changes(tmp_path, monkeypatch):
    """--llm-cassette-strict：数据变了就不许命中（宁可不跑，也不拿旧数据下的判断充数）。"""
    monkeypatch.setattr("framework.config.llm_from_env", lambda: _FakeLLM())
    _run_explore(Cassette(MODE_RECORD, tmp_path))
    _no_llm(monkeypatch)
    with pytest.raises(explorer.AiExploreError) as ei:
        asyncio.run(explorer._ai_explore_async(
            SCENARIO, _items_with_other_data(), URL,
            llm_cassette=Cassette(MODE_REPLAY, tmp_path), cassette_strict=True))
    assert "禁止结构键兜底" in str(ei.value) or "没有这一份" in str(ei.value)


def test_cli_exposes_strict_switch():
    from framework import cli
    assert cli.FLAG_SPECS.get("--llm-cassette-strict", "?") is None      # 纯开关
    assert "--llm-cassette-strict" in cli.CMD_FLAGS["explore"]
    assert "--llm-cassette-strict" in (cli.cmd_explore.__doc__ or "")
