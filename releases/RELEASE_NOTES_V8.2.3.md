# hybrid_gui_qa V8.2.3 升级说明（2026-09-23）

> 接着 V8.2.2 往下挖：**光有友好报错还不够，得让人「根本没机会漏」**；
> 顺手修掉一个潜伏很久的**退出码空转**缺陷。

## 一、新增：一条命令搞定环境

```bat
python -m framework.cli setup
```

按顺序做完三件事，最后**真启一次 chromium 自检**，就绪了才说 OK：

| 步骤 | 做什么 | 失败时 |
|---|---|---|
| ① | 装依赖（`requirements.txt`，`pip` 优先、没有就用 `uv`）| 打尾部输出 + exit 2 |
| ② | 装浏览器（`playwright install chromium`）| 打尾部输出 + exit 2，并提示离线机器怎么办 |
| ③ | **自检**：真启一次 chromium | 不就绪就明说 |

参数（都很好记）：

| 参数 | 用途 |
|---|---|
| `--check` | **只体检不安装**（只读）：分段报告依赖 / 浏览器，坏在哪一目了然 |
| `--force-browser` | playwright 包换过版本（报错里的 revision 号变了）⇒ 强制重下浏览器 |
| `--with-ai` | 连 AI 依赖（`requirements-ai.txt`）一起装 |

> 为什么不用 `--force`：`run` 那边已有 `--force-workers`（另一件事），叫 `--force-browser` 不会看错。

**预检报错也改了**：现在首推这一条命令，而不是让新人自己拼 `playwright install`：

```
[cli] ❌ 没找到 Playwright 的浏览器（chromium / chromium-headless-shell）…
     一条命令搞定（推荐；会装依赖 + 浏览器，再自检一遍）：
         python -m framework.cli setup
     或只装浏览器：
         python -m playwright install chromium
```

## 二、修复：退出码空转（潜伏缺陷）

**现象**：L15 那道「产物自洽闸」——`generate` 发现产物引用了不存在的数据集时，会打印
「❌ 产物已拒绝落盘（宁可报错，也不产出跑不通的产物）」，**但调用方收到的是 exit 0**。

**真因**：`main()` 的分发是 8 个**裸调用**，**返回值被丢弃** ⇒
`cmd_generate` 里 `DanglingDatasetError` 分支的 `return 2` **空转**。
同族另外三个错误（`_report_unmapped` / `_report_data_sets` / `_report_case_quality`）
都是 `-> NoReturn` 直接 `raise SystemExit`，**只有这一条走 return** ⇒ 典型的不一致。

**修法（根因，不贴膏药）**：修在**分发层** —— 每个子命令的返回值都被采纳：

```python
    if cmd == "probe":
        rc = cmd_probe()
    ...
    if isinstance(rc, int) and rc != 0:
        raise SystemExit(rc)
```

⇒ 以后任何子命令 `return` 非 0，调用方都看得见；老的 `raise SystemExit` 写法继续有效。

**⚠️ 这是本版唯一的"行为变更"**（如实标注）：受影响的是 `generate` 的产物自洽闸
—— 它此前**声称** exit 2、实际 exit 0，现在名副其实。其余子命令不 `return` 非 0 值，退出码不变。

## 三、兼容性与注意事项

- CLI 参数、用例格式、报告形态、判据口径**不变**（除上面那一条退出码修正）。
- `setup` 是**新增**子命令，已有的 `probe / generate / explore / run / all / prune` 行为不变。
- `setup --check` 是**只读**的（有判据守着：它不许往浏览器缓存里写东西）。

## 四、本机实测（真值）

| 项 | 结果 |
|---|---|
| 一类 | **432 passed / 0 red**（新增 5 条 `cli setup` 判据）|
| `setup --check`（环境正常）| → **exit 0**，明确报「环境就绪」|
| `setup --check`（模拟缺浏览器）| → **exit 2** + 可照抄的修复命令（修前是 exit 0 ✗）|
| 新增判据内容 | 正常 0 / 缺浏览器非 0 / `--check` 只读 / `--help` 已注册 / 乱写参数被拦 |
| 文档与代码同步 | `verify_html_sync.py` 逐字节通过 |
| 版本 | `python -m framework.cli --version` → **v8.2.3 (2026-09-23)** |
| 培训页 | **225.5 KB**（9.0 节开头新增「一条命令全搞定」提示块）|

## 五、附带查清的一件事（版本策略的底数）

实测各版本对应的浏览器 revision（**号由 playwright 版本决定**，不是框架写死的）：

| playwright | chromium revision | 有无 headless-shell |
|---|---|---|
| 1.45.0 | 1124 | ❌ 没有（整包 chromium 做无头）|
| 1.62.0 | 1234 | ✅ |
| 1.63.0 | **1243** | ✅ |

框架用到的 API 全部落在 **1.45 之前**（最"新"的是 2022 年的 `get_by_role` / `get_by_test_id`），
且 **1.45.0 / 1.62.0 / 1.63.0 三个版本真跑均通过** ⇒ **框架不挑 playwright 版本**。
是否在 `requirements.txt` 锁定具体版本（可复现性 vs 版本自由度）待定。
