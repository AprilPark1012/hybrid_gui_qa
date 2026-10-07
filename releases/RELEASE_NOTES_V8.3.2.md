# 发行说明 V8.3.2（2026-10-07）

> **主题：跨平台修复** —— 修掉「只在 Windows 上暴露」的崩溃：路径分隔符 / 重复定义 / 输出编码
>
> 上一版：V8.3.1（2026-10-07）· 版本号单一来源：`build_tools/build_html.py` 顶部 `VERSION`

---

## 1. 这一版修的是什么（起因）

V8.3.1 在内网 Windows 上跑**日常验证**（`python -m pytest tests/ -q`），出现 **7 条红**：

```
FAILED tests/特性1-混合链路/test_acceptance_entry.py::test_acceptance_skip_ai_marks_scenario1_skipped
FAILED tests/特性8-质量闸门体系/test_env_adaptation.py::test_runner_mem_probe_never_fakes_a_number
FAILED tests/特性8-质量闸门体系/test_generated_layout_contract.py::test_index_and_disk_are_bidirectionally_consistent
FAILED tests/特性8-质量闸门体系/test_test_layout_contract.py::test_class1_tests_live_in_feature_folders
FAILED tests/特性8-质量闸门体系/test_test_layout_contract.py::test_class2_verifies_live_in_feature_folders
FAILED tests/特性8-质量闸门体系/test_test_layout_contract.py::test_negative_find_modules_ignores_noise
FAILED tests/特性8-质量闸门体系/test_utf8_io.py::test_gbk_upstream_utf8_downstream_gbk_must_explode
```

**而这同一份代码在云主机（Linux）上全绿。** 这就是本版最值得记住的一条：

> **一类全绿，只证明「在一个平台上自洽」。**

---

## 2. 根因与修复（逐条）

### 2.1 路径分隔符（4 条红）

`in_feature_dir()` 用 `rel_path.split("/")` 判断「文件是否落在特性夹里」。Windows 的相对路径是
**反斜杠**（`tests\特性1-混合链路\x.py`）⇒ `split("/")` 切不开 ⇒ 判断**恒为 False**。

表现为：「文件明明在特性夹里，判据却说它没归位」——非常反直觉。

| 位置 | 修法 |
|---|---|
| `test_test_layout_contract.in_feature_dir` | `PurePosixPath(str(rel_path).replace("\\", "/")).parts` |
| `find_test_modules` / `find_verify_modules` | `p.relative_to(root).as_posix()` |
| `test_generated_layout_contract` | 磁盘侧集合也改 `.as_posix()`（与 index.json 的 `/` 风格对齐）|

### 2.2 重复定义覆盖（1 条红，**真 bug**）

`tests/_runner/run_verifications.py` 里 `mem_available_mb()` **被定义了两次**：
- 第 145 行：跨平台版（Windows 走 `ctypes` 读内存）
- 第 355 行：旧版（只读 `/proc/meminfo`）

**Python 里后定义者胜** ⇒ 旧版**静默覆盖**了跨平台版 ⇒ Windows 上永远拿不到内存、**返回 0**。
判据「内存探测不许编数字」（`mb is None or mb > 0`）正是抓这个的 —— **判据是对的，实现是错的**。

修：删掉重复的旧定义。

### 2.3 探针前提不成立（1 条红）

GBK 机理判据靠「上游子进程按 UTF-8 输出」这个前提。子脚本用 `print()` ⇒ 走 Python 的
**文本编码层**，Windows 上受 UTF-8 模式 / 控制台代码页影响 ⇒ 未必是 UTF-8 字节
⇒ 下游 gbk 解码**不炸** ⇒ 判据「未复现」。

修：子脚本改成 `sys.stdout.buffer.write("...".encode("utf-8"))`，**绕过编码层**。
测的仍是同一条机理，但「上游 = UTF-8」在任何平台都成立。

### 2.4 输出编码（最后 1 条红，**也是整个框架的通病**）

```
UnicodeEncodeError: 'gbk' codec can't encode character '\u26a0' in position 6
```

`run_acceptance.py` 里 `print("      ⚠️ 跳过场景1 ...")` —— `⚠`（U+26A0）**GBK 编不出来**。

**为什么手工跑没事**：手工跑时 stdout 是**控制台**（走 UTF-8）。
**为什么 pytest 里崩**：stdout 被**捕获成管道** ⇒ Python 退回 **locale 编码**（中文 Windows = cp936）
⇒ `print` 当场抛 `UnicodeEncodeError` ⇒ **整个入口挂掉**（不是少一行日志，是 exit 1）。

**全仓扫描：135 个文件 / 4550 处 / 98 种字符** —— 这不是一处 bug，是整个框架的输出风格问题。

---

## 3. 本版改动面

### 3.1 输出装饰 emoji → ASCII（135 文件 / 4550 处）

| 原 | 现 |
|---|---|
| `✅` / `❌` / `⚠️` | `[OK]` / `[NG]` / `[!]` |
| `⇒` / `⇄` | `->` / `<->` |
| `⏭` `ℹ` `⏱` `▶` `◀` `↻` `↩` `⛔` | `[skip]` `[info]` `[time]` `[run]` `[here]` `[redo]` `[back]` `[stop]` |
| `✓` / `✗` / `✘` | `v` / `X` / `X` |
| 圈号 `⑮` `⑰` `㉑` … | `(15)` `(17)` `(21)` … |
| 被编码搞坏的编号（`㛃` 等） | `(9-29批)` —— **原编号已不可考，只标批次，不猜** |

### 3.2 入口补 `force_stdio()`

框架**早就有** `framework/tools/common/text_io.py::force_stdio()`（统一 UTF-8 + Windows 控制台代码页 65001），
**20 个脚本都调了** —— 偏偏两个**入口**漏了：`run_acceptance.py` / `run_verifications.py`。已补。

### 3.3 模板层坑（生成物的来源）

`_CONFTEST_TEMPLATE` 是**普通三引号字符串**（不是 raw）⇒ 里面的 `\u4e00` 在**模块定义期**
就被 Python 解析成「一」⇒ 生成物 `_harness.py` 里那个 CJK 区间变成了实际汉字。

修：模板里写成**双反斜杠**让字面透传，生成物恢复成 `\u4e00` 形式的转义
（Python `re` 会解析它，**功能不变** —— 已重跑 `generate --force` 验证）。

### 3.4 用例数据

`cases/*.json` 的 steps 文本会**原样写进生成的脚本 docstring** ⇒ 同步换 ASCII。

⚠️ **刻意不动 `scenarios/*.yml`**：场景指纹 = `sha256(yml 原文)`，改它会让**已有 41 份录像失效**；
而 yml 里的符号只在「给 AI 看的场景文案」里，**不会落进 `.py`**。

---

## 4. 新增的两条守门判据（本版重点）

这类问题的可怕之处是「**在 Linux 上永远绿**」，所以必须**在 Linux 上就能把它拦住**：

| 判据 | 守什么 | 怎么证明它有效 |
|---|---|---|
| `test_in_feature_dir_accepts_windows_style_paths` | 拿**反斜杠路径**喂纯函数，钉住「分隔符假设」 | 把归一化改回 `split("/")` ⇒ **立刻红** |
| `test_source_has_no_gbk_unencodable_chars` | 源码（含注释）禁出现 GBK 编不了的字符 | 塞一个 emoji ⇒ **立刻红** |

> 为什么不用「扫源码文本」判路径问题：`str(x.relative_to())` 有两种用法 ——
> 当 subprocess 参数是**安全**的（Windows 的 Python 认 `\`），只有用于**集合/比较**才危险；
> 纯文本扫描分不出来（会误报）⇒ **直接测行为更可靠**。

---

## 5. 验证结果

| 项 | 结果 |
|---|---|
| 一类（`python -m pytest tests/ -q`） | **679 passed / 0 failed / 1 skipped**（30.2s）|
| 全仓 GBK 不可编码字符 | **0 处** |
| 生成物 | 重跑 `generate --force`，正则行为不变 |
| 负向自证 | 两条新判据都做过了（改回旧写法 / 塞 emoji ⇒ 立刻红）|

---

## 6. 遗留

- **`--verify` 的中文主题 bug**：`send_email.py --verify` 用中文主题搜 IMAP 会
  `UnicodeEncodeError`（已修：先抽 ASCII 关键词再搜）。
- 内网 Windows 的 **二类验证**（`run_verifications.py`）本版未在 Windows 上实测 ——
  但二类脚本 20 个里 19 个早就调了 `force_stdio()`，且输出符号已全 ASCII。

---

## 7. 交付包

- `hybrid_gui_qa_V8.3.2_20261007.zip`
- `hybrid_gui_qa_llm_cassettes_20261007.zip`（LLM 录像）
