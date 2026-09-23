# hybrid_gui_qa V8.2.2 升级说明（2026-09-23）

> **真机踩坑驱动的一版**：把「装浏览器」这件事从**靠经验**变成**框架自己会说话**。

## 一句话

新增**浏览器预检** —— `probe / generate / explore / run` 开跑前先探一次 chromium，缺了就**当场**给
「缺什么 + 期望路径 + 当前 playwright 版本 + **一行修复命令**」并 exit 2；
培训页同步补上「**装环境三件事**」与「报错 → 怎么办」对照表。

## 一、为什么（真实事故）

在新机器（Windows 首次部署）上跑这三条命令，**三条各炸一次**：

```bat
python -m framework.cli explore --ai --scenario-dir scenarios/
python -m framework.cli generate
python -m framework.cli run
```

报错都是 Playwright 的原始异常栈，只有这一句有用：

```
BrowserType.launch: Executable doesn't exist at
  C:\Users\<user>\AppData\Local\ms-playwright\chromium_headless_shell-1243\chrome-headless-shell-win64\chrome-headless-shell.exe
```

问题不在真因（**没装浏览器**，一句话就能修），问题在**报错完全不提「该跑哪条命令」** ——
新人看不懂、也搜不到。这违反本项目「开箱即用、提示说人话」的口径。

## 二、怎么修（两条）

### ① 框架：开跑前先探一次（`ensure_browser_installed`）

```bat
:: 缺浏览器时现在长这样（而不是 Playwright 原始栈）
[cli] ❌ 没找到 Playwright 的浏览器（chromium / chromium-headless-shell），框架需要它才能探测页面、跑用例。
     期望位置：C:\Users\...\ms-playwright\chromium_headless_shell-1243\chrome-headless-shell-win64\chrome-headless-shell.exe
     当前 playwright 版本：1.63.0
     一行修好（装完即可跑）：
         python -m playwright install chromium
```

- 覆盖命令：`probe / generate / explore / run / all`（`prune` 不需要浏览器，`--version`/`--help` 也不受影响）
- 退出码 **2**（脚本调用方能察觉，不静默）
- 已确认环境可用时可跳过：`HYBRID_SKIP_BROWSER_CHECK=1`

### ② 培训页：9.0「装环境三件事」+ 报错对照表

| # | 做什么 | 命令 |
|---|---|---|
| ① | 建虚拟环境 | `python -m venv .venv` → `.venv\Scripts\activate`（Windows）/ `source .venv/bin/activate` |
| ② | 装 Python 依赖 | `pip install -r requirements.txt` |
| ③ | **装浏览器**（最容易漏，漏了必报错）| `python -m playwright install chromium` |

自检：`python -m playwright install --list`（能看到 `chromium-<rev>` + `chromium_headless_shell-<rev>` 就对了）→
`python -m framework.cli probe`（能吐出元素清单 = 通了）

**「报错 → 怎么办」对照表**覆盖：`Executable doesn't exist` / revision 号变了 / `ModuleNotFoundError: playwright` /
`Target crashed`（内存不足）/ Windows 控制台乱码。

## 三、一条关键知识（省下以后的时间）

**报错里的 revision 号由 `playwright` 版本决定，不是框架写死的**：

| playwright 版本 | 期望的浏览器 revision（实测）|
|---|---|
| 1.62.0 | `1234` |
| 1.63.0 | `1243` |

⇒ 所以**升级过 `playwright` 包之后**，要重跑一次：

```bat
python -m playwright install --force chromium
```

否则就会看到「版本对不上」的那类 `Executable doesn't exist`。

## 四、兼容性与注意事项

- **CLI 参数、用例格式、报告形态、判据口径全部不变**；已有用例/场景/录像照旧可用。
- 预检的代价：每次开跑前多一次「起一个 headless chromium 再关掉」的探测（约 1 秒）。
- 本版为**真机问题修复**，不改行为语义。

## 五、本机实测（真值）

| 项 | 结果 |
|---|---|
| 一类（`pytest tests/ -q`） | **426 passed / 0 red**（新增 5 条预检判据：含负向 + 子进程端到端）|
| 预检实测（模拟缺浏览器） | 打印人话 + 一行修复命令 + **exit 2** ✓ |
| 文档与代码同步（`verify_html_sync.py`） | ✅ 可复现 + 与代码同步 + 无畸形嵌套（逐字节）|
| 培训页规模 | **220.6 KB**（含 9.0 节与对照表）|
| 版本号 | `python -m framework.cli --version` → **v8.2.2 (2026-09-23)** |
