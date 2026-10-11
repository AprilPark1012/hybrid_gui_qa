# -*- coding: utf-8 -*-
"""V8.5.1 · P23 登录步骤化 —— **判据先行**（R7-c：先落判据跑红，再实现，最后转绿）。

## 范围（他 2026-10-11 定，比 P23 原案更明确）

> 删 `auth` 段与整套平行机制，登录变成 `probe_pre` 里的动作序列（填账号 -> 填密码 -> 点登录）

即**两期共用一份动作序列声明**：
  · 探测期：`probe_pre` 直接就是那三步（框架不认识"账号/密码"，只认"声明了动作"）；
  · 执行期：生成期把同一份动作展开成用例的**前导步骤**（goto 登录页 -> fill -> fill -> click -> wait）。

## 为什么必须做（现状的三个真问题）

1. **隐藏运行期依赖**：`generate` 写 `scripts/generated/_auth.json`，但该文件被 `.gitignore` 忽略
   -> `pack_release`（`git ls-files --exclude-standard`）**不打进包** -> 收包方 `run` 时登录前置
   **静默失效**，报「元素语义未找到」而真因是"整条用例跑在登录页上"。
   -> 从此**包里有什么、跑的就是什么**，不存在"运行期必需的隐藏文件"。
2. **两条路必然漂移**：探测期走 POST 接口 + token 注入（`login.py`），执行期走 harness 里的
   `_install_login` 读 `_auth.json` —— 同一件事两套实现（框架自己反复吃过的亏）。
3. **登录不可见**：登录动作不在用例里，跑挂了看不出"卡在登录"这一步，报错还把方向带向
   "异步取数 / 弹层未渲染 / 语义名过期"。

## 判据清单（本文件 = 一类，秒级、不需 demo）

  J1  场景声明了登录动作 -> 生成脚本里出现前导登录步骤，顺序 goto->fill->fill->click->wait
  J2  负向：场景**没有**登录动作 -> **零**前导步骤（向后兼容）
  J3  负向：登录动作声明不全（缺值 / 定位表达式非法）-> **生成期大声报错**，不许静默跳过
  J4  出厂闸门：**运行期读到的文件集合 是……子集 打包清单**（防"不入包却运行必需"复发）
  J5  机制移除守门：全仓无 `_auth.json` 读写、`.gitignore` 无该条
  J6  报错文案：跑到登录页上 -> 明确报「当前在登录页 —— 登录步骤未执行/失败」

[!] 本文件先落**红态**。实现后逐条转绿；不许为了让判据过而放宽断言。
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FRAMEWORK = REPO / "framework"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""


# ==================== J5 机制移除守门（先测这条：它定义"做完"的边界）====================

def test_j5_no_auth_json_anywhere_in_source():
    """`_auth.json` 的读写必须从框架里彻底消失（隐藏运行期依赖的根源）。

    [!] 判定要**排除假阳性**：`test_scenario_auth_spec.py` 这类**测试文件名**里含 "auth"，
    但它跟 `_auth.json` 无关 —— 只认真正的**路径/文件名字面量**写法。
    """
    offenders = []
    for p in FRAMEWORK.rglob("*.py"):
        if "__pycache__" in str(p):
            continue
        for i, l in enumerate(_read(p).split("\n"), 1):
            code = l.split("#", 1)[0]
            # [!] 精确判定，避免两类误报：
            #   ① `test_scenario_auth_spec.py`（测试**文件名**）含 `_auth_spec` 子串；
            #   ② `sc.auth_spec()` 是**方法调用**，与 `_auth.json` 毫无关系。
            #   => 只认 `_auth.json` 的**字面量**写法。
            if '"_auth.json"' in code or "'_auth.json'" in code:
                offenders.append(f"{p.relative_to(REPO)}:{i}  {l.strip()[:110]}")
    assert not offenders, (
        "框架里仍有 `_auth.json` 的**代码引用**（这文件不进包 -> 收包方静默失效）：\n"
        + "\n".join(offenders[:20]))


def test_j5_gitignore_has_no_auth_json_entry():
    """`.gitignore` 里不许再有 `_auth.json` 那条（它正是"被忽略却运行必需"的成因）。"""
    gi = _read(REPO / ".gitignore")
    assert "_auth.json" not in gi, (
        ".gitignore 仍忽略 _auth.json -> 它不会进交付包，但运行期又要读（隐藏依赖）")


def test_j5_harness_template_has_no_install_login():
    """生成物 harness 模板里不许再有 `_install_login`（执行期登录要走可见步骤）。"""
    gen = _read(FRAMEWORK / "features" / "f02_semantic" / "generator_generate.py")
    offenders = [f"{i}: {l.strip()[:110]}" for i, l in enumerate(gen.split("\n"), 1)
                 if "_install_login" in l.split("#", 1)[0]]
    assert not offenders, (
        "generator 里仍有 `_install_login` 相关代码（那套机制要整体下线）：\n" + "\n".join(offenders[:12]))


# ==================== J1/J2/J3 生成期登录步骤（先锁"有 / 无 / 报错"三种行为）====================

def test_j1_login_steps_are_expanded_into_generated_case():
    """声明了登录动作 -> 生成期把它展开成**前导步骤**（goto->fill->fill->click->wait）。"""
    gen = _read(FRAMEWORK / "features" / "f02_semantic" / "generator_generate.py")
    assert ("expand_login_steps" in gen) or ("login_steps_of" in gen) or \
           ("登录步骤" in gen and "前导" in gen), (
        "generator 里没有把登录动作展开成前导步骤的实现（登录仍不在用例里，跑挂了看不出来）")


def test_j2_no_login_declaration_means_no_leading_steps():
    """负向：没有登录声明的场景，生成结果必须与今天**完全一致**（零前导步骤）。

    [!] 用**行为**验证，不查字面正则 —— 原来那种 `if not \\w*login\\w*:` 的写法只在
    某种代码形态下成立，实现一变就"看着还在守、其实早不守了"。
    """
    import sys
    from pathlib import Path as _P
    sys.path.insert(0, str(REPO))
    from framework.features.f02_semantic import generator_generate as G
    # ① 完全没有场景信息的用例 -> 零前导步骤
    assert G._login_lines_for({}, "http://localhost:8000") == [], \
        "无场景信息的用例被插入了登录步骤 -> 会把所有用例都改掉（破坏向后兼容）"
    # ② 有场景名、但该场景没声明 login: -> 同样零前导步骤
    assert G._login_lines_for(
        {"scenario_id": "__not_exist_scenario__"}, "http://localhost:8000") == [], \
        "拿不到场景时也必须是零步骤（不许猜、不许降级）"
    # ③ 真实场景（已声明 login:）-> 必须有前导步骤（正例，防止"守卫写太死把正例也挡了"）
    lines = G._login_lines_for(
        {"scenario_id": "orders_invoice_full_lifecycle"}, "http://localhost:8000")
    assert lines, "场景声明了 login: 却一步都没展开 -> 登录又不在用例里了"
    joined = "\n".join(lines)
    assert "_login_do" in joined and "_login_wait" in joined
    assert "goto" in joined, "前导步骤缺 goto（要先到登录页）"


def test_j3_malformed_login_declaration_fails_loudly():
    """负向：登录声明不全（缺值/非法定位表达式）必须**生成期大声报错**，不许静默跳过。"""
    sce = _read(FRAMEWORK / "features" / "f02_semantic" / "scenario_generate.py")
    assert ("LoginSpecError" in sce) or ("登录" in sce and "raise" in sce), (
        "scenario 侧没有登录声明的必填校验（缺了静默跳过 = 又会变成'跑在登录页上'的假红）")


# ==================== J4 出厂闸门：运行期必需 是……子集 打包清单 ====================

def test_j4_runtime_required_files_are_subset_of_package_manifest():
    """运行期要读的文件必须都在打包清单里（防同类'不入包却运行必需'复发）。

    做法：收集"框架源码里出现的、仓库内相对路径形态的运行期文件名"
    （如 `scripts/generated/xxx.json`），断言它们在 `pack_release` 的收集规则下**不被忽略**。
    """
    import subprocess
    # 用 git 判定：被 .gitignore 忽略的文件 = 不会进包
    from framework.shared.text_io import run_capture
    r = run_capture(["git", "ls-files", "--others", "--ignored", "--exclude-standard",
                     "scripts/"], cwd=REPO)
    # [!] run_capture 返回的是 `CompletedProcess`（第一版我按 dict 取了 `.get("stdout")`
    #   => AttributeError。返回值形态要现查、不能想当然。）
    ignored = [x for x in (getattr(r, "stdout", "") or "").split("\n") if x.strip()]
    gen = _read(FRAMEWORK / "features" / "f02_semantic" / "generator_generate.py")
    # 生成期写出的、且**运行期要读**的文件（以 `_xxx.json` 形态出现在 scripts/generated 下）
    written = set(re.findall(r'["\'](_[a-z_]+\.json)["\']', gen))
    clash = [f for f in written
             if any(x.endswith(f) for x in ignored)]
    assert not clash, (
        "生成期写出、运行期要读的文件被 .gitignore 忽略 -> 不进包 -> 收包方静默失效：\n"
        + "\n".join(clash))


# ==================== J6 报错文案：卡在登录页要直说 ====================

def test_j6_error_message_names_login_page_when_stuck():
    """跑到登录页上时，报错必须直指登录（不许把方向带向"异步取数/弹层未渲染"）。"""
    hits = []
    for p in (FRAMEWORK / "features").rglob("*.py"):
        if "__pycache__" in str(p):
            continue
        s = _read(p)
        if "登录页" in s and ("登录步骤" in s or "未执行" in s or "登录失败" in s):
            hits.append(str(p.relative_to(REPO)))
    assert hits, (
        "全框架没有「当前在登录页 -> 直说登录步骤未执行/失败」的报错文案："
        "实测真因是登录没生效，报错却指向「元素语义未找到」，排查方向被带偏")
