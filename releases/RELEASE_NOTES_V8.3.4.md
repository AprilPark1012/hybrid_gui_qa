# 发行说明 V8.3.4（2026-10-07）

> **主题：交付包缺文件修复** —— 包里少了「登录前置清单」，导致整条用例跑在登录页上，
> 报出来却是「元素语义未找到」（现象把排查方向带偏）
>
> 上一版：V8.3.3（2026-10-07）· 版本号单一来源：`build_tools/build_html.py` 顶部 `VERSION`

---

## 1. 用户报的现象

内网 Windows 上跑 `python -m framework.cli run --debug`，**两条用例全挂**：

```
RuntimeError: 元素语义未找到: 超@合同列表页 —— 确定性主定位没命中，语义兜底也没找到这个语义名。
常见原因：(1) 页面还在异步取数/弹层未渲染；(2) 弹层没打开；(3) 语义名过期（页面改版后要重跑 probe/generate）。
```

**但截图/对象里有个关键线索**（很容易被忽略）：

```
page = <Page url='http://localhost:8000/login.html?next=%2F'>     ← 页面停在登录页！
```

⇒ 页面**根本没进业务页**，所以「找不到元素」是**必然**的；报错文案却把人引向「就绪/弹层/语义名过期」。

---

## 2. 根因：交付包缺 `scripts/generated/_auth.json`

| 环节 | 事实 |
|---|---|
| `_harness.py` 的登录前置 | 从**同目录**读 `_auth.json`（读不到 ⇒ **空表 ⇒ 不做登录前置**）|
| 该文件的来源 | `generate` 按场景 `auth:` 段写入 |
| `.gitignore:56` | **忽略它**，注释理由：「运行期产物，**不入库/不入包**」|
| `pack_release.py` 收集文件 | 走 **`git ls-files`** ⇒ **只收入库文件** ⇒ **必然漏它** |
| 包里的 `scripts/generated/*.py` | **已经是生成好的产物** ⇒ 用户解包后**直接 `run`、不会跑 generate** |

**链条**：包缺 `_auth.json` ⇒ 登录前置无凭据 ⇒ 业务页被重定向到登录页 ⇒ 找不到任何业务元素。

**注意这不是「V8.3 新引入」的问题** —— 任何时候从包里直接跑都会中招，
只是前几轮的验证都在**没清空 `_auth.json` 的工作区**里跑，所以没暴露。

---

## 3. 30 秒复现（本机即可）

```bash
mv scripts/generated/_auth.json /tmp/
python -m framework.cli run --case manual_order_create_smoke     # ⇒ FAILED（复现）
mv /tmp/_auth.json scripts/generated/
python -m framework.cli run --case manual_order_create_smoke     # ⇒ 1 passed（证明）
```

---

## 4. 修法

1. **`pack_release.py` 收集文件时显式补上** `scripts/generated/_auth.json`（存在才加）。
2. **包自检加一条**：**仓库里有该文件而包里没有 ⇒ 报问题**
   —— 只在仓库确实有该文件时才要求，避免对「无登录场景」误报。

**口径修正（写进项目 skill）**：

> **「不入库」≠「不入包」** —— 入库靠 git，交付靠打包脚本，**是两件事**。
> `.gitignore` 的注释不能替打包做决定。

### 通用教训

- `.gitignore` 里每一个「运行期产物」，都要逐个问：**用户拿到包能不能直接跑？**
  「generate 时会重建」这个理由，**只在用户真的会跑 generate 时成立**
  ——交付包里产物是**预生成**的，用户直接跑 ⇒ 一切「重建出来的依赖」都必须在包里。
- **交付包自检要覆盖「跑起来必需、但不在 git 里」的文件**，否则这类缺失**一路绿到用户手上**。
- **排查心法**：用例报「元素找不到」时**先看 `page.url`** ——
  URL 是登录页/空白页，说明问题**根本不在定位**，而在**前置没生效**。

---

## 5. 附：二类脚本临时文件清理（同日发现）

`verify_cross_page.py` 做负向自证时会往 `cases/` 写 `neg_cross_*.json`（5 个），
跑完若未清理会：① 让一类的一致性判据报「无数据集/孤儿」；② **被打包脚本收进交付包**（脏包）。

已在跑完验证后清理；清理规则写进 skill：
**任何会往 `cases/` `scripts/generated/` `scripts/datasets/` 写文件的验证脚本，必须 `try/finally` 清理，
并在跑完后再核一次目录**（别只依赖 `finally` —— 进程被 kill 就没了）。

> 同类前例：`verify_e2e_scenario2_handwritten.py` 的 `manual_negative_probe_tmp` 也留过残渣。

**打包前自检**：`git status --short` 看有没有未跟踪的 `cases/*.json` / `scripts/generated/*`。

---

## 6. 验证

| 项 | 结果 |
|---|---|
| 复现 | 移走 `_auth.json` ⇒ `run --case …` **必现**（FAILED）|
| 修复验证 | 移回来 ⇒ **`1 passed`** |
| 包内容验证 | 新包内含 `scripts/generated/_auth.json` |
| 包自检负向自证 | 仓库有而包无 ⇒ **报问题** |
| 一类 | 679 passed / 0 failed / 1 skipped |
| 残渣清理 | `cases/` 只剩 2 个真用例（manual + ai）|

---

## 7. 交付包

- `hybrid_gui_qa_V8.3.4_20261007.zip`
- `hybrid_gui_qa_llm_cassettes_20261007.zip`（LLM 录像）

**复验**：
```
.venv\Scripts\python -m framework.cli run --debug
```
预期：**Chromium 窗口弹出并逐步执行完，用例 PASSED**（若 demo 未启动，先 `python -m demo.app`）。
