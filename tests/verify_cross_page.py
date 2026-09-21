"""跨页面流程 · 正/负向端到端验证（2026-09-13 P3 配套）。

跑法（需要 demo 在 8000 上：python -m demo.app）：
    cd ~/hybrid_gui_qa && source .venv/bin/activate
    python tests/verify_cross_page.py        # 末行：全部符合预期 ✅

为什么单独一个脚本（不叫 test_*.py）：
  它会**临时**往 cases/ 写一批故意做错的跨页用例（prefix=neg_cross_）、跑完清理并重新 generate，
  不适合跟主用例套件混跑。

判据（防假绿铁律）：跨页的每条**错误**都必须**失败**——
  ① 详情页断言值写错；② 换页证据放在换页之前（页面根本没变）；
  ③ 跨页用例用了跨页重名的原始名（会静默落到另一页）；④ 跨页用例没有 url 断言（质量闸必须告警）；
  ⑤ **新建 → 详情页**：详情页必须读到同一条真实记录（客户 = 弹层里选的那个），
     且对**不存在的编号**如实报「未找到」而不是编一份出来（2026-09-14 数据搬到服务端后新增的判据）。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
# 统一 UTF-8（同 cli.py 口径）：本脚本跨进程收 generate / pytest 输出，父进程绝不能按
# 系统默认编码（Windows cp936/gbk）解码子进程的 UTF-8 中文输出。
sys.path.insert(0, str(BASE))
from framework.tools.common.text_io import UTF8_ENV, force_stdio  # noqa: E402

force_stdio()
_U8 = {**os.environ, **UTF8_ENV}
CASES = BASE / "cases"
DATASETS = BASE / "scripts" / "datasets"
DEMO = "http://localhost:8000"
PREFIX = "neg_cross_"
LIST = "http://localhost:8000/"
DETAIL = "http://localhost:8000/contract_detail.html?no=HT-1005"
PAGES = [{"name": "列表页", "url": LIST}, {"name": "详情页", "url": DETAIL}]

GOTO_LIST = {"op": "goto", "desc": "打开列表页", "url": LIST}
FILL = {"op": "fill", "desc": "关键字 1005",
        "element": "合同编号_名称_管理单元_合同类型_帐套", "value": "1005"}
SEARCH = {"op": "click", "desc": "点搜索", "element": "搜索@列表页"}
CLICK_NO = {"op": "click", "desc": "点编号进详情页", "element": "HT_1005"}
BACK = {"op": "click", "desc": "返回列表", "element": "返回列表"}


def _demo_up() -> bool:
    try:
        with urllib.request.urlopen(DEMO, timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


# ---- 负向：每条都必须 FAILED（结构性问题在生成阶段就 pytest.fail）----
NEGATIVE = {
    # ① 详情页断言值写错（真换页了，但期望值与实际不符）
    "wrong_detail_value": dict(
        steps=[GOTO_LIST, FILL, SEARCH, CLICK_NO],
        asserts=[{"kind": "url", "expect": "contract_detail", "after_step": 4},
                 {"kind": "text", "expect": "合同9999", "desc": "详情页名称写错", "after_step": 4}],
    ),
    # ② 换页证据放在换页之前：此时还在列表页，url 不含 contract_detail
    "url_assert_before_nav": dict(
        steps=[GOTO_LIST, FILL, SEARCH, CLICK_NO],
        asserts=[{"kind": "url", "expect": "contract_detail",
                  "desc": "换页前就断言已在详情页（实际还在列表页）", "after_step": 3}],
    ),
    # ③ 跨页用例用了跨页重名的原始名「搜索」→ 会静默落到另一页 → 必须显式失败
    "raw_duplicate_name": dict(
        steps=[GOTO_LIST, FILL,
               {"op": "click", "desc": "用原始名点搜索（跨页重名）", "element": "搜索"}],
        asserts=[{"kind": "text", "expect": "HT-1005"}],
    ),
    # ④ 详情页元素名写错
    "detail_element_typo": dict(
        steps=[GOTO_LIST, FILL, SEARCH,
               {"op": "click", "desc": "点一个不存在的元素", "element": "根本不存在的按钮"}],
        asserts=[{"kind": "text", "expect": "HT-1005"}],
    ),
    # ⑤ 「回到列表页」的独有文案证据，在**没回到列表页**（还在详情页）时必须 FAILED
    #    —— 2026-09-17：原来那条证据是 expect_url=localhost（换页前后都通过 = 没有牙），
    #    换成「列表页独有文案」后，这条负向证明它真的有牙。
    "weak_evidence_no_teeth": dict(
        steps=[{"op": "goto", "desc": "直接打开详情页（不回到列表页）", "url": DETAIL}],
        asserts=[{"kind": "text", "expect": "新建合同",
                  "desc": "列表页独有文案（详情页没有该文案）—— 没回到列表页时必须失败",
                  "after_step": 1}],
    ),
}


def _write_neg_cases():
    written = []
    for name, spec in NEGATIVE.items():
        cid = f"{PREFIX}{name}"
        p = CASES / f"{cid}.json"
        payload = {"case_id": cid, "name": f"负向验证（跨页）：{name}",
                   "base_url": LIST, "pages": PAGES,
                   "steps": spec["steps"], "asserts": spec["asserts"]}
        p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        written.append(p)
    return written


def _cleanup(written):
    for p in written:
        p.unlink(missing_ok=True)
        (DATASETS / p.name).unlink(missing_ok=True)
    subprocess.run([sys.executable, "-m", "framework.cli", "generate"],
                   cwd=BASE, capture_output=True, text=True, encoding="utf-8", errors="replace",
                   env=_U8)


def _gen():
    """生成（含负向用例）。

    ⚠️ 必须带 `--allow-unmapped`：负向用例 ④ 故意用一个**不存在的元素名**（就是为了证明
    「元素名写错 ⇒ 该用例 FAILED，不许静默跳过」）。而 V7.5.1 的映射质量闸会因此把**整个** generate
    拦成 exit 2（闸门本身是对的：有未映射就不许出产物）—— 实测该负向段**从 V7.5.1 起就再没跑起来过**
    （2026-09-17 复跑时当场暴露）。
    这里显式走调试逃生口：④ 会生成成 `pytest.fail` 存根 → 运行时 FAILED（正是负向段要验的结果）。
    这些产物只服务于负向验证；跑完 `_cleanup()` 会**不带逃生口**重新生成干净产物。
    """
    r = subprocess.run([sys.executable, "-m", "framework.cli", "generate", "--allow-unmapped"],
                       cwd=BASE, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env=_U8)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def _run_node(cid: str):
    e = dict(os.environ, HYBRID_RUN_ID="verify_cross_page")
    r = subprocess.run([sys.executable, "-m", "pytest", f"scripts/test_cases.py::test_{cid}",
                        "-q", "--no-header"],
                       cwd=BASE, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env={**e, **UTF8_ENV})
    text = ((r.stdout or "") + (r.stderr or "")).strip().splitlines()
    return r.returncode, (text[-1][:110] if text else "")


def _reset_demo():
    """POST /api/reset：把 demo 数据复位成预置 20 条（别把新建数据留给后面的用例）。"""
    try:
        req = urllib.request.Request(DEMO + "/api/reset", data=b"", method="POST")
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read().decode("utf-8")).get("count")
    except Exception as e:
        print(f"  ⚠️ 数据复位失败：{type(e).__name__}: {e}")
        return None


def _check_new_then_detail():
    """② 的直接效果：UI 新建（客户选 c1）→ 详情页读到的必须是**同一条真实记录**。

    两个判据：
      ① 正向：详情页的客户 = 弹层里选的那个（改造前详情页是「按编号序号推导」，
         新建的合同在详情页会显示成别的客户 —— 那种"看着像对的"假数据最坑）；
      ② 负向：**不存在的编号**必须如实报「未找到」、单元格保持「—」，绝不编一份出来。
    """
    import time as _t
    from playwright.sync_api import sync_playwright
    from framework.tools.common.browser import launch_opts

    out = []
    print("      （先复位数据）count =", _reset_demo())
    name = f"跨页新建_{_t.strftime('%H%M%S')}"
    with sync_playwright() as p:
        b = p.chromium.launch(**launch_opts(headless=True))
        pg = b.new_context().new_page()
        pg.goto(LIST)
        pg.wait_for_load_state("networkidle")
        pg.get_by_test_id("btn-new").click()
        pg.fill("[data-testid='inp-name']", name)
        pg.select_option("[data-testid='sel-mu']", "0021")
        pg.select_option("[data-testid='sel-fs']", "001")
        pg.select_option("[data-testid='sel-type']", "合同")
        pg.get_by_test_id("btn-pick-c").click()          # 打开客户弹层
        pg.get_by_test_id("pick-c1").click()             # 选「北京华信科技有限公司」
        pg.select_option("[data-testid='sel-b']", "bu_a")
        pg.get_by_test_id("btn-submit").click()
        pg.wait_for_selector("#status:has-text('已新增合同')", timeout=8000)
        with urllib.request.urlopen(DEMO + "/api/contracts", timeout=5) as r:
            rows = json.loads(r.read().decode("utf-8"))
        rec = next((x for x in rows if x["name"] == name), None)
        out.append((rec is not None, "新建的合同进了服务端数据（编号由服务端分配）",
                    f"name={name} no={(rec or {}).get('no')}"))
        if rec:
            pg.goto(f"{DEMO}/contract_detail.html?no={rec['no']}")
            pg.wait_for_load_state("networkidle")
            got = pg.evaluate(
                "() => ({text: document.getElementById('d-cust').textContent.trim(), "
                "cust: document.getElementById('d-cust').dataset.cust || '', "
                "no: document.getElementById('d-no').textContent.trim(), "
                "st: document.getElementById('status').textContent.trim()})")
            out.append((got["cust"] == "c1" and got["text"] == "北京华信科技有限公司",
                        "详情页读到的客户 = 弹层里选的那个（c1 北京华信）",
                        f"详情页: {got['text']} / data-cust={got['cust']}"))
            out.append((got["no"] == rec["no"] and rec["no"] in got["st"],
                        "详情页编号/状态行与新建记录一致", got["st"]))
        # 负向：不存在的编号
        pg.goto(f"{DEMO}/contract_detail.html?no=HT-9999")
        pg.wait_for_load_state("networkidle")
        nf = pg.evaluate(
            "() => ({cust: document.getElementById('d-cust').textContent.trim(), "
            "st: document.getElementById('status').textContent.trim()})")
        out.append(("未找到" in nf["st"] and nf["cust"] == "—",
                    "不存在的编号：如实报「未找到」，不编数据",
                    f"{nf['st']} / 客户单元格={nf['cust']}"))
        b.close()
    print("      （复位收尾）count =", _reset_demo())
    return out


def main() -> int:
    if not _demo_up():
        print(f"❌ 被测 demo 不可达（{DEMO}）——先跑：python -m demo.app")
        return 2

    print("===== 一、正向：跨页手写用例必须 PASSED（含换页 url 断言）=====")
    e = dict(os.environ, HYBRID_RUN_ID="verify_cross_page")
    r = subprocess.run([sys.executable, "-m", "pytest",
                        "scripts/test_cases.py::test_cross_page_detail", "-q", "--no-header"],
                       cwd=BASE, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env={**e, **UTF8_ENV})
    pos_ok = r.returncode == 0
    print(f"  {('✅' if pos_ok else '❌')} test_cross_page_detail  "
          f"{((r.stdout or '').strip().splitlines() or [''])[-1][:90]}")

    print("\n===== 二、质量闸：跨页用例缺 url 断言必须告警；弱换页证据必须红线 =====\n")
    sys.path.insert(0, str(BASE))
    from framework.tools.generate.case_builder import case_errors, case_warnings   # noqa: E402
    warn = case_warnings({
        "pages": PAGES,
        "steps": [GOTO_LIST, FILL, SEARCH, CLICK_NO],
        "asserts": [{"kind": "text", "expect": "HT-1005"}],
    })
    gate_ok = any("URL 断言" in w for w in warn)
    print(f"  {('✅' if gate_ok else '❌')} 告警命中: {[w for w in warn if 'URL 断言' in w] or warn}")
    # 弱换页证据（expect=localhost：换页前后都通过）⇒ 红线必须拦
    red = case_errors({"pages": PAGES, "steps": [GOTO_LIST, FILL, SEARCH, CLICK_NO],
                       "asserts": [{"kind": "url", "expect": "localhost", "after_step": 4}]})
    redline_ok = bool(red) and "假绿" in red[0]
    print(f"  {('✅' if redline_ok else '❌')} 弱换页证据被红线拦下: {red[:1] or '（没拦住 —— 假绿会进产物！）'}")
    # 反向：真证据（只出现在详情页的片段）不许被拦 —— 假拦会把人逼向绕过闸门
    no_false_block = case_errors({"pages": PAGES, "steps": [GOTO_LIST, FILL, SEARCH, CLICK_NO],
                                  "asserts": [{"kind": "url", "expect": "contract_detail",
                                               "after_step": 4}]}) == []
    print(f"  {('✅' if no_false_block else '❌')} 真换页证据（contract_detail）未被误拦")

    print("\n===== 三、负向：每条都必须 FAILED（防假绿）=====")
    written = _write_neg_cases()
    bad = []
    try:
        rc, out = _gen()
        if rc != 0:
            print("  ❌ generate 失败：", out[-400:])
            return 2
        for name in NEGATIVE:
            code, line = _run_node(f"{PREFIX}{name}")
            ok = code != 0
            if not ok:
                bad.append(name)
            print(f"  {('✅' if ok else '❌ 假绿！')} {name:<22} pytest exit={code}  {line}")
    finally:
        _cleanup(written)

    print("\n===== 四、新建 → 详情页：详情页必须读同一条真实记录（客户 = 弹层里选的那个）=====")
    cross = _check_new_then_detail()
    cross_ok = all(ok for ok, _, _ in cross)
    for ok, desc, detail in cross:
        print(f"  {('✅' if ok else '❌')} {desc}  {detail}")

    print("\n===== 结论 =====")
    all_ok = pos_ok and gate_ok and redline_ok and no_false_block and cross_ok and not bad
    if all_ok:
        print("全部符合预期 ✅（正向跨页 PASSED；质量闸：缺 url 断言告警 / 弱证据被红线拦 / 真证据未误拦；"
              "新建→详情页客户一致；负向全部 FAILED，无假绿）")
        return 0
    print(f"不符合预期 ❌  正向={'OK' if pos_ok else 'FAIL'}，质量闸={'OK' if gate_ok else 'FAIL'}，"
          f"弱证据红线={'OK' if redline_ok else 'FAIL'}，真证据未误拦={'OK' if no_false_block else 'FAIL'}，"
          f"新建→详情页={'OK' if cross_ok else 'FAIL'}，假绿项={bad or '无'}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
