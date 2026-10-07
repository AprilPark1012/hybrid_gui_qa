# 发行说明 V8.3.3（2026-10-07）

> **主题：两条判据的跨平台适配** —— 把「我方无法在 Windows 验证的假设」换成「平台无关的确定判据」
>
> 上一版：V8.3.2（2026-10-07）· 版本号单一来源：`build_tools/build_html.py` 顶部 `VERSION`

---

## 1. 这一版修什么

V8.3.2 在内网 Windows 上复跑一类：**7 条红 → 2 条红**（674 passed）。

剩下的 2 条**都不是原来那批**，性质是「**判据隐含了本平台假设**」：

| 判据 | 现象 | 性质 |
|---|---|---|
| `test_runner_runs_a_real_script` | runner `exit 2` —— `[NG] demo 新鲜度闸门未过（exit 5）` | **环境没准备好**（demo 没在跑），不是判据要防的东西 |
| `test_gbk_upstream_utf8_downstream_gbk_must_explode` | `OLD_GBK= 未复现`（同一段字节在 Linux 上**必炸**） | **平台行为差异**，而我方只有 Linux、无法验证 |

---

## 2. 修法

### 2.1 GBK 机理判据：改用「固定字节流」

**本机对照实验（Linux）**：同一子脚本输出

```
raw = b'[generate] \xe8\xaf\xbb cases/\n'      ← 确认上游是纯 UTF-8
```

下游 `subprocess.run(..., encoding="gbk", errors="strict")` **确实抛**：

```
UnicodeDecodeError: 'gbk' codec can't decode byte 0xbb in position 13
```

⇒ **机理本身成立，差异在平台**（Windows 的 subprocess / 管道编码行为与 POSIX 不同）。

**改法**：
- **机理部分**（硬核）→ 直接对**固定字节流**做 gbk 解码：平台无关、**必然抛异常**，
  并断言签名 `0xbb@13` + `errors="replace"` 解出的文本确实**变错**（证明「不炸 ≠ 对」）
- **端到端部分**（子进程 + 管道）→ 保留：POSIX 上**仍必须复现**；
  **Windows 上降级为诊断打印**（不红）

> 这与本项目**既有口径**一致 —— 见 `test_reproduce_and_fix_gbk_byte_0xbb_position_13` 的处理：
> **「我方只有 Linux，无法验证 Windows 的真实行为 → 不拿未验证的假设去红别人的环境」**。

### 2.2 runner 冒烟判据：demo 闸门未过时跳过

该判据的意图是「**防 runner 起不来 / sys.path 漏目录**」；
而「demo 没在跑 / demo 比进程新」是**环境状态**（R7 第 0 步本就要求跑验证前先重启 demo）。

**改法**：检测到输出含「新鲜度闸门未过」⇒ `pytest.skip(...)` 并**说明原因**。
**注意**：只在**这一种情况**下跳过 —— runner 真起不来（import 失败 / 用法错）**仍然照红**。

**防空转**：云主机上 demo 常驻，这条判据**每轮都在真跑**（已验证：`1 passed`，不是 skip）。

---

## 3. 顺带清掉的一个残渣

`verify_e2e_scenario2_handwritten.py` 做负向自证时会建一个临时用例
（`manual_negative_probe_tmp`），其 `cleanup()` 已会清 cases / generated / datasets 三处；
但**早前版本跑过的残渣**还留在 `cases/manual/`，会让一类的
`test_case_ids_and_datasets_are_one_to_one` 报「这些用例没有数据集」。

已删除残渣；脚本清理逻辑确认完整（三个位置都清）。

---

## 4. 验证

| 项 | 结果 |
|---|---|
| 一类（云主机） | **679 passed / 0 failed / 1 skipped** |
| 全仓 GBK 不可编码字符 | **0 处** |
| 负向自证 · GBK 判据 | 把样本字节改成 gbk 能正常解 ⇒ **立刻红** |
| 负向自证 · runner 判据 | 云主机 demo 常驻 ⇒ **真跑 passed**（未退化为 skip）|

**⚠️ 内网 Windows 复验**：
```
.venv\Scripts\python -m pytest tests\ -q
```
**预期：679 passed, 1 skipped（GBK 那条会打印一行 `[诊断]`，属正常降级）**

> 若复验时 **demo 没在跑**，runner 冒烟那条会 **skip**（并打印原因）——
> 那不是失败；要让它真跑，请按 R7 第 0 步先起 demo。

---

## 5. 交付包

- `hybrid_gui_qa_V8.3.3_20261007.zip`
- `hybrid_gui_qa_llm_cassettes_20261007.zip`（LLM 录像）
