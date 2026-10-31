# V8.7.17 发布说明（2026-10-29）

> 上一版：V8.7.16 · 版本号单一来源 = `build_tools/build_html.py:VERSION`

## 一句话

**只修半边等于没修** —— 路径分隔符问题，写入侧也要 `as_posix()`。

---

## 一、你报的那 1 failed 是什么

```
FAILED tests\特性9-质量闸门体系\test_generated_layout_contract.py::
       test_index_and_disk_are_bidirectionally_consistent
       AssertionError: X 磁盘上有 index 不认识的孤儿脚本：
       ['scripts/generated/orders_invoice_full_lifecycle/ai_orders_invoice_full_lifecycle_161243.py']
```

## 二、这是**假红**，不是真孤儿

看断言里两个集合的实际内容：

```python
on_disk  = {'scripts/generated/.../ai_..._161243.py'}      ← 正斜杠
in_index = {'scripts\generated\...\ai_..._161243.py'}     ← 反斜杠
```

**同一个文件**，只是**格式不同**，集合相减自然非空 → 被判成「孤儿」。

## 三、根因：写入侧用了 `str(Path)`

`framework/features/f02_semantic/generator_generate.py`：

```python
_mod_path = str(mod.relative_to(BASE))     # Windows 上 Path 的字符串形式 = 反斜杠
```

存进 `index.json` 后就是 `scripts\generated\...`，而判据侧：

```python
on_disk = {p.relative_to(REPO).as_posix() for p in GEN.glob("*/*.py")}   # 正斜杠
```

**两侧口径不同，永远对不上。**

## 四、最扎心的地方：注释说「已经修过」

该判据里有一行注释：

```python
# [!] 跨平台（2026-10-07 修）：Windows 上 str(relative_to) 给 `scripts\generated\…`，
# 而 index.json 里存的是 `/` 风格 -> 集合永远对不上（假红）。统一用 as_posix()。
```

**但它只给 `on_disk` 那一侧加了 `as_posix()`，写入侧没动。** 所以：

- 2026-10-07 之后生成的**新数据**仍是反斜杠
- 判据依然红

**「只修半边」是本项目反复踩的坑**，这次记进判据里。

## 五、修法：三处一起动

| # | 改什么 | 为什么 |
|---|---|---|
| ① | **写入侧** `script_path` / `source_scenario` 全部 `as_posix()` | 防止**新数据**再写成反斜杠 |
| ② | **判据读取侧**比较前归一化 `in_index` | 兼容**你机器上的存量反斜杠**（不要求你手工改 index.json）|
| ③ | **拼路径前**归一化 `sp = REPO / str(...).replace("\\", "/")` | Linux 上 `Path / "a\\b"` 不认反斜杠，拼出不存在的路径 |

**只做 ① 是不够的** —— 你已有的 `index.json` 还是反斜杠，判据照样红。

## 六、验证（我用你机器的真实状态验的）

把本机 `index.json` **临时改成反斜杠**（模拟你的机器），再跑那条判据：

```
[已改成反斜杠] 样例: scripts\generated\orders_invoice_full_lifecycle\ai_..._161243.py
  退出码: 0
  1 passed in 0.03s
[已恢复 index.json]
```

**归一化真的生效** —— 反斜杠数据下判据通过。验证完自动恢复原文件。

## 七、新增判据 `test_repo_relative_paths_use_forward_slash.py`（5 条）

| 测试 | 守什么 |
|---|---|
| `test_index_script_paths_use_forward_slash` | 现有 `index.json` 里不许有反斜杠 |
| `test_case_source_scenario_uses_forward_slash` | 用例里 `source_scenario` 不许有反斜杠 |
| `test_generator_writes_script_path_as_posix` | **静态钉住**写入侧必须 `as_posix()` |
| `test_scenario_source_written_as_posix` | `source_scenario` 写入侧同理 |
| `test_layout_contract_compares_same_notation` | 判据**两侧**口径一致（防再只修半边）|

## 八、顺带说清 6 skipped / 1361 passed 的差异

我这边是 `1365 passed / 3 skipped`，你那边 `1361 passed / 1 failed / 6 skipped` —— **总数都是 1368**，同一套测试。

差异来自 **GBK 相关判据的平台差异**（`test_utf8_io.py` 里有两条 `skipif(_gbk_default_encoding() is None)`）：

- **Linux**：需要 `locale -a` 里有 `zh_CN.gbk`，没有就 skip
- **中文 Windows**：ANSI 代码页就是 936（cp936），`getpreferredencoding()` 天然是 GBK 家族 → **能跑**

所以你那 3 个多出来的 skip 不是问题，是**平台本该如此**。

## 九、验证

```
全量：pytest tests/ -q
新判据：pytest tests/特性9-质量闸门体系/test_repo_relative_paths_use_forward_slash.py -v   -> 5 passed
```

## 十、怎么验

```powershell
.venv\Scripts\python -m pytest tests\ -q
```

**预期：0 failed**（那 1 个假红消失）。skip 数仍是 6（平台决定，不是问题）。

## 十一、提交状态

V8.7.14 / 15 / 16 / 17 都还没提交，等你验完点头。

—— AprilPark1012
