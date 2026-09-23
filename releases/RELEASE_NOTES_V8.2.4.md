# hybrid_gui_qa V8.2.4 升级说明（2026-09-23）

> 把「不管团队装哪个 playwright 版本都能跑」这件事**收口**：
> 框架**不挑版本**（已实测），但团队**用同一版本**（锁定）—— 锁的是**可复现**，不是能力。

## 一、先回答一个被反复问到的问题

| 问题 | 结论（全部实测） |
|---|---|
| 框架挑 playwright 版本吗？ | **不挑**。1.45.0 / 1.62.0 / 1.63.0 三个版本**真跑均通过**（含真启浏览器）；用到的 API 全部落在 **1.45 之前**（最"新"的是 2022 年的 `get_by_role` / `get_by_test_id`）|
| 会不会写死了浏览器路径？ | **没有**。全仓库搜到的 revision 号**只出现在注释与文档里**；真逻辑是 `p.chromium.launch()`，路径由**你装的那个 playwright 自己解析** |
| 那锁定会不会「用不了新特性」？ | **不会**。框架压根没用新特性；锁定只是让「升级」变成一次**有意识的动作**（三步规程见下），而不是各人机器上悄悄漂移 |
| 不锁有什么代价？ | 团队各装一个版本 ⇒ 期望的浏览器 revision 各不相同（实测 **1.45⇒1124 · 1.62⇒1234 · 1.63⇒1243**）⇒ 反复踩「包升级了、浏览器没重下」 |

## 二、本版改动

### ① 锁定版本：`requirements.txt`

```diff
- playwright>=1.45
+ playwright==1.63.0
```

**为什么是 1.63.0**：这是团队（AprilPark1012本机）在用的版本，且我已**两类验证都跑过**。
pin 上方写了锁定理由与升级规程（就在文件里，不用翻文档）。

> 已装 1.63.0 的环境**无需任何动作** —— 这只是把「大家一致」写下来。

### ② `cli setup` 显示版本漂移

```
[setup] playwright 版本：锁定 1.63.0 · 环境 1.63.0   ✅ 一致
```

不一致时：

```
[setup] playwright 版本：锁定 1.63.0 · 环境 1.64.0   ⚠️ 不一致
[setup]   不是错，但浏览器可能对不上（期望的 revision 号会变）；要对齐就：
[setup]       python -m framework.cli setup --force-browser
```

**只告警不拦** —— 新版 playwright 未必不能用（框架不挑版本），目的是让漂移**看得见**，不是卡住你。

### ③ 培训页新增两块

**【浏览器到底装在哪儿】**（离线/内网机器要用）

| 系统 | 默认缓存目录 |
|---|---|
| Windows | `%USERPROFILE%\AppData\Local\ms-playwright` |
| Linux | `~/.cache/ms-playwright` |
| macOS | `~/Library/Caches/ms-playwright` |

不确定就**让工具自己说**（最准）：`python -m playwright install --list`

**【离线 / 内网机器四步】**

1. 找一台**能联网、系统与架构相同**的机器：`python -m playwright install chromium`
2. 把整个 `ms-playwright` 目录拷到目标机同位置（或放到共享目录）
3. 若用共享目录，设 `PLAYWRIGHT_BROWSERS_PATH` 指过去
4. 自检：`python -m framework.cli setup --check` → 报「✅ 可用（真启一次成功）」就成了

**三个坑**：Windows 与 Linux 的浏览器**不能混用**（不同构建）；拷贝要**连 revision 号目录一起**拷；
换了 playwright 版本后，联网机器重跑 `setup --force-browser`、离线机器要**重新拷**对应 revision。

> `pip install` 本身也要联网 ⇒ 离线机器可用 `pip download -r requirements.txt -d wheels/` 预先下好 wheel，或走内网 PyPI 镜像。

**【升级规程（三步走完再交付）】**

```bash
# ① 改 requirements.txt 里的 pin，例如 playwright==1.63.0 → 1.64.0
python -m framework.cli setup --force-browser      # ② 按新版本重下浏览器
python -m pytest tests/ -q                          # ③ 一类判据
python tests/run_verifications.py                   #    二类特性验证
```

## 三、兼容性与注意事项

- CLI 参数、用例格式、报告形态、判据口径**不变**；已装 1.63.0 的环境无需任何动作。
- 版本漂移**不会**阻断运行（只告警）—— 万一你装了别的版本，框架照跑，只是浏览器 revision 可能对不上。
- 离线部署必须**同系统同架构**（Windows 的浏览器拷到 Linux 上起不来）。

## 四、本机实测（真值）

| 项 | 结果 |
|---|---|
| 一类 | **466 passed / 0 red**（新增 5 条版本判据）|
| 新增判据 | pin 读得出 / **范围约束与注释不算锁定** / **repo 必须锁定**的回归 / 不一致必须告警且给对齐命令 / 边界不炸 |
| `setup --check` 真跑 | 显示「锁定 1.63.0 · 环境 1.63.0 ✅ 一致」|
| 三版本真跑 | 1.45.0 ✅ · 1.62.0 ✅ · 1.63.0 ✅（含真启浏览器）|
| 文档与代码同步 | `verify_html_sync.py` 逐字节通过 |
| 版本 | `python -m framework.cli --version` → **v8.2.4 (2026-09-23)** |
| 培训页 | **243.3 KB**（新增「浏览器装在哪儿 / 离线四步 / 升级规程」）|
