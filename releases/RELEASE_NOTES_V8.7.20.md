# V8.7.20 发布说明（2026-10-29）

> 上一版：V8.7.19 · 版本号单一来源 = `build_tools/build_html.py:VERSION`

## 一句话

**同一能力三份实现，只有一份认 Windows** —— venv 解释器定位收成唯一入口。

---

## 一、你的问题

> 「你要查下为啥你本机跑是 1397 passed / 3 skipped / 0 failed，而我删除 .env 跑的框架自测结果是：
> 1378 passed, 6 skipped, 12 warnings，这个是否合理？」

**结论：3 个合理，1 个是真 bug，2 个合理。**

---

## 二、先对账（数字全对得上）

```
本机 V8.7.19:  1397 + 3 = 1400
你   V8.7.18:  1378 + 6 = 1384
               1400 - 1384 = 16  = V8.7.19 新增的 16 条判据（你没跑那版）

本机 V8.7.18 等价集（--ignore 掉 V8.7.19 新文件）:  1381 + 3 = 1384  ✅ 与你完全一致
```

---

## 三、怎么精确找出那 6 个 skip 的（方法本身值得记）

你的日志是 `pytest -q`，只有点号没有名称。但**点号位置能反推**：

```python
# 1) 进度行 = 以点号序列开头且带 [ NN%] 的行
prog = [m.group(1) for l in log if (m := re.match(r'^([.sFEx]+)\s*\[\s*\d+%\]', l.strip()))]

# 2) 数点号累计位置，记下 's' 出现在第几个
# 3) 用 --collect-only 拿等价测试集（同版本、同 ignore）
# 4) 位置 1:1 对上
```

**校验**：点号总数 **1384** = `--collect-only` 出的 **1384** 条，**严丝合缝** —— 说明映射可信。

### 你机器上的 6 个 skip

| # | 测试 | 原因 | 判定 |
|---|---|---|---|
| 1 | `test_offline_chain_python.py::test_probe_deps_on_repo_venv_if_present` | **硬编码 `.venv/bin/python`** | **❌ 真 bug** |
| 2 | `test_page_identity_contract.py::test_j9_no_item_duplication_across_pages` | 没有探针快照 | ✅ 合理 |
| 3 | `test_row_anchor_selection.py::test_artifacts_row_anchor_is_not_whole_row_text` | 没有 `probe_*.json` | ✅ 合理 |
| 4 | `test_data_driven_placeholders.py::test_ai_cases_with_scenario_data_use_placeholders` | 没有带 `data:` 段的场景 | ✅ 合理 |
| 5 | `test_runner_smoke.py::test_runner_runs_a_real_script` | demo 新鲜度闸门未过（没开 demo）| ✅ 合理 |
| 6 | `test_env_adaptation.py::test_file_list_uses_git_inside_repo` | 非 git 目录（解压包）| ✅ 合理 |

**2/3/4 我这边也 skip**（我也没有对应数据）。**5/6 是判据刻意的设计**：
- 5：demo 没跑 = 环境没准备好，不是 runner 坏了（判据意图是查「runner 起不来 / sys.path 漏目录」）
- 6：解压目录本来就不是 git 仓库，跑它必然红 —— 而那正是 V8.7.19 修的那个 bug 本身

---

## 四、第 1 个是真 bug

```python
venv = REPO / ".venv" / "bin" / "python"       # ← 只认 POSIX
if not venv.exists():
    pytest.skip("本机没有 <repo>/.venv")
```

**Windows 的 venv 布局是 `.venv\Scripts\python.exe`（没有 `bin/` 目录）**
⇒ `bin/python` 永远不存在 ⇒ **这条判据在 Windows 上永远 skip，等于从没被验证过**。

### 更糟的是：全仓共 3 处，只有 1 份是对的

| 位置 | 写法 | Windows 后果 |
|---|---|---|
| `tests/_runner/run_verifications.py:110` | **两个平台都列了** | ✅ 正确 |
| `test_offline_chain_python.py:125` | 只认 POSIX | **永远 skip（假绿）** |
| `verify_slow_target.py:44` | 只认 POSIX | 静默退回 `sys.executable`，依赖可能缺 |
| `verify_offline_chain_deps.py:99` | 只认 POSIX | 拿到不存在的路径，跑就失败 |

而**正确的那份早就在**——`test_env_adaptation` 还专门测过 `_venv_python` 认得 `Scripts/python.exe`。
**典型「同一能力多份实现、只有一份对」**，与项目「同一能力收敛成唯一入口」的原则正面冲突。

---

## 五、修法（你选的 A）

新建 `framework/shared/paths.py` 作**唯一入口**：

```python
_VENV_CANDIDATES = (
    (".venv", "Scripts", "python.exe"),   # Windows
    (".venv", "bin", "python3"),          # POSIX（优先）
    (".venv", "bin", "python"),
)

def venv_python_or_none(repo) -> Path | None:
    """没有 venv 就如实 None（不退回 sys.executable）。"""
    ...

def venv_python(repo) -> str:
    """找不到就退回当前解释器（不让脚本直接崩）。"""
    ...
```

**两个入口的语义差异是刻意的**：
- 判据要「如实 SKIP」→ 用 `venv_python_or_none()`，`None` 就是真没有
- 脚本要「尽力跑起来」→ 用 `venv_python()`，退回 `sys.executable`

**四处全部改用**，`run_verifications._venv_python` **退化成一行转发**（防再次漂移）。

细节：用 `is_file()` 而不是 `exists()` —— 否则「同名目录」会被当成解释器，拿去执行直接炸。

---

## 六、判据（10 条）

| 守什么 | 手段 |
|---|---|
| ① Windows 布局认得 | `tmp_path` 建 `.venv/Scripts/python.exe` |
| ② POSIX 认得，且 `python3` 优先于 `python` | 造两种布局比对 |
| ③ 没有 venv **如实 None** | 不许假装找到了 |
| ④ **同名目录不算** | `is_file()` 的边界 |
| ⑤ **全仓扫描防漂移** | 正则扫 `framework/tests/build_tools/demo` 下所有 `.py` |
| ⑥ `_venv_python` 只转发 | 静态钉住「不许自己留候选路径表」 |

### 判据自己踩的两个坑（值得记）

**坑 1：第一版扫出 4 处误报**
- 3 处是测试自己用 `tmp_path` 造假 venv（造的就是 POSIX 布局，属于被测数据）
- 1 处是 `build_tools/offline_explore_chain.py:108`，**它是对的**（两个平台都列了当候选）
- ⇒ 加了两条放行规则

**坑 2：反向验证当场没变红，判据其实失效了**
- 我加的放行规则是「**整个文件**里出现过 `Scripts` 和 `python.exe` 就放行」
- 而 `test_offline_chain_python.py:9` 的 **docstring** 里就写着 `.venv/{bin,Scripts}` → 整个文件被放行
- ⇒ **教训：白名单按「文件」给，别按「文件里出现过某词」给 —— 注释谁都能写。**
- 改成显式文件白名单后，回退硬编码 → **判据变红** ✅

---

## 七、验证

| 手段 | 结果 |
|---|---|
| `test_venv_python_single_entry.py` | **10 passed** |
| 反向验证：把 `test_offline_chain_python` 改回硬编码 | **`test_no_hardcoded_posix_venv_python_in_logic` 变红** ✅ |
| 恢复后 | **10 passed** |
| 相关旧判据（特性1 + 环境适配 + utf8） | **52 passed** |

---

## 八、你那边 skip 数会怎么变

**测 V8.7.20 时预期**：由 **6 skip** 变成 **5 skip**（第 1 条会真跑起来）。

不过有个前提：`test_probe_deps_on_repo_venv_if_present` 真跑起来后，它会断言「仓库 venv 依赖齐全」。
**如果你那 `.venv` 里没装 `dotenv` / `playwright` / `pytest`**，它会**红**（而不是 skip）——
那才是它本来要查的东西。红了告诉我，我看是缺依赖还是别的。

**其余 5 个 skip 仍会 skip**（探针快照 / 数据驱动场景 / demo 没开 / 非 git 目录），都是设计如此。

---

## 九、提交状态

V8.7.14 ~ 20 全部等你验完点头再提交，push 一律等你点头。

—— AprilPark1012
