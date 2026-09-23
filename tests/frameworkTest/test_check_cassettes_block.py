"""录像体检的「场景段抠取 + 覆盖判定」判据（P16 批 6 实测回归）。

背景（真事故）：录制明明成功、prompt 里场景文案完整存在，体检却报「缺 4」。
两个真 bug：
  ① 抠取用非贪婪 `([\s\S]*?)[」』”"]` ⇒ 场景里**自带内层引号**时（「返回列表」「查看订单」）
     在第一个内层闭引号处截断 ⇒ 长场景永远匹配不上；
  ② 判定用严格相等 ⇒ 抠取一旦偏一点就判「没有录像」，而这恰恰是最该报绿的情形。
修法：抠取取到**段落边界**（下一小节标题/空行）；判定改「相等 **或**完整包含」。
⚠️ 包含是**精确子串**判定，不是模糊相似度 —— 下面第三条负向就是钉死这点。
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _cc():
    spec = importlib.util.spec_from_file_location("cc_test", REPO / "build_tools" / "check_cassettes.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _prompt(scen: str, tail: str = "\n\n页面已探测出以下可交互控件（只有这些可用）:\n[\n {\"name\": \"搜索\"}\n]") -> str:
    return f"你是测试专家。\n\n自然语言测试场景: 「{scen}」{tail}"


def test_含内层引号的长场景不被截断():
    """★回归：内层引号必须不再当终止符。"""
    cc = _cc()
    scen = "打开合同列表页；\n点击「返回列表」回到列表页，再输入 1005 确认仍有 HT-1005。"
    got = cc.scenario_block_in_prompt(_prompt(scen))
    assert "HT-1005" in got, f"尾段被截断了: {got!r}"
    assert got == scen, f"抠取结果应与场景逐字一致: {got!r}"


def test_遇到下一个小节标题就停():
    cc = _cc()
    got = cc.scenario_block_in_prompt(_prompt("第一步。第二步。", tail="\n\n跨页规则（**必须遵守**）：\n  · 只能操作当前页"))
    assert got == "第一步。第二步。", f"不该把下一节吃进来: {got!r}"


def test_覆盖判定_相等命中():
    cc = _cc()
    text = "搜索 1005 并确认结果。"
    cass = [{"normalized": cc._flatten(cc.normalize_values(text)), "file": "a.json",
     "framework_version": "v-test", "created_at": "2026-09-22T00:00:00+08:00"}]
    with _fake_yml("搜索 1005 并确认结果。") as files:
        covered, missing = cc.check(files, cass)
    assert covered and not missing


def test_覆盖判定_包含命中():
    """录像带的说明比场景多 ⇒ 仍算覆盖（精确包含）。"""
    cc = _cc()
    got = cc._flatten("（补充说明）搜索 1005 并确认结果。\n（附加约束）必须唯一命中。")
    with _fake_yml("搜索 1005 并确认结果。") as files:
        covered, missing = cc.check(files, [{"normalized": got, "file": "b.json",
      "framework_version": "v-test", "created_at": "2026-09-22T00:00:00+08:00"}])
    assert covered and not missing


def test_覆盖判定_不包含必须报缺():
    """★负向：场景没被任何录像覆盖时**必须**报缺（别把「包含」口径用成假绿）。"""
    cc = _cc()
    other = cc._flatten("完全不同的另一个场景。")
    with _fake_yml("搜索 1005 并确认结果。") as files:
        covered, missing = cc.check(files, [{"normalized": other, "file": "c.json",
      "framework_version": "v-test", "created_at": "2026-09-22T00:00:00+08:00"}])
    assert not covered and missing


class _TmpScen:
    """临时场景文件 —— 必须建在**仓库内**（check 会做 relative_to(REPO)），用完必删（仓库零残留）。

    注意：文件名以 `_pytest_tmp_` 开头且不在 scenarios/ 下，不会被录像体检/录制扫到；
    但仍放在 try/finally 里删，任何断言失败都不会留残渣。
    """

    def __init__(self, scen: str):
        import yaml
        self.path = REPO / "tests" / "featureTest" / "_pytest_tmp_scen.yml"
        self.path.write_text(yaml.safe_dump({"scenario": scen}, allow_unicode=True), encoding="utf-8")

    def __enter__(self):
        return [self.path]

    def __exit__(self, *exc):
        self.path.unlink(missing_ok=True)
        return False


def _fake_yml(scen: str):
    return _TmpScen(scen)


def test_仓库外的场景路径不许把体检崩掉():
    """★回归：调用方传 /tmp 下的临时场景（verify_e2e_scenario3_cassette 就是这么用的）。"""
    import tempfile
    import yaml
    d = Path(tempfile.mkdtemp())
    yml = d / "tampered.yml"
    yml.write_text(yaml.safe_dump({"scenario": "随便一个场景"}, allow_unicode=True), encoding="utf-8")
    cc = _cc()
    covered, missing = cc.check([yml], [])           # 不许抛异常
    assert missing and str(yml) in missing[0]["scenario"]
