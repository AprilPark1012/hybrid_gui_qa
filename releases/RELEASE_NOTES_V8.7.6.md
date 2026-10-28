# V8.7.6 发布说明（2026-10-27）

> 上一版：V8.7.5（2026-10-27）· 版本号单一来源 = `build_tools/build_html.py:VERSION`

## 一句话

**跑得好好的，看起来像卡死。** 父进程全程静默 + 子进程超时默认「无限等」。

---

## 现象

Windows 上跑 `all --ai`，日志停在：

```
[explore] --verify：先 generate 一次，再逐条试跑 1 条新用例…
```

之后**一行输出都没有**。用户报「好像卡住了」。

**实际情况：任务正常跑完了。**

```
[OK] 【orders_invoice_full_lifecycle】校验通过：该用例实测 PASSED
locator 来源: element_map(element_map_20261027_170352.json) 命中 34/34
1 passed in 202.74s (0:03:22)
[run] pytest 退出码 0
```

所以这是**可观测性缺陷**，不是故障。

---

## 根因 1：父进程全程静默

`--verify` 阶段两次阻塞调用都走 `run_capture(...)`：

```python
# cli.py 改动前
gen = run_capture([sys.executable, "-m", "framework.cli", "generate"], cwd=...)
...
r = run_capture([sys.executable, "-m", "pytest", node, "-v", "-s"], cwd=...)
```

`run_capture` 是**同步阻塞 + 捕获全部输出**（`subprocess.run(capture_output=True)`）——
子进程跑完才返回，**期间父进程一行都不打印**。

而一条真实全链路用例有 **62 步**，其中第 43 步是：

```
43. expect_text → 已关闭 | 有界等待订单状态按时间自动流转到已关闭：提交后最长约160秒
```

整体 3~10 分钟。用户看到的就是「打完这行彻底没声了」。

## 根因 2：`run_capture` 的 timeout 默认 None = 永久等

```python
def run_capture(cmd, *, cwd=None, env=None, timeout: float | None = None, **kw):
```

默认 `None` 意味着**子进程卡住，父进程就永久等**。一旦 demo 没响应、或「已关闭」这个状态
永不流转，就是**真卡死** —— 用户只能 Ctrl+C，而且看不出停在哪一步。

> 根因 1 让人**误判**卡死；根因 2 让**真卡死**没有出口。两个都得修。

---

## 修复

### 1. 每次阻塞前交代清楚

```
[explore] --verify：先 generate 一次，再逐条试跑 1 条新用例…
  [1/2] 正在 generate 生成脚本（确定性转换，不调 AI）…
  [1/2] generate 结束（耗时 12.3s）
  [2/2] 正在试跑 【orders_invoice_full_lifecycle】ai_xxx（pytest 子进程，输出先被捕获、结束才显示）…
        提示：这类全链路用例常含「等订单状态流转」的有界等待（最长约 160s），整体 3~10 分钟属正常；
        想看实时进度去 log/ 下最新的 run 目录
        试跑结束（耗时 202.7s）
  [OK] 【orders_invoice_full_lifecycle】校验通过：该用例实测 PASSED
```

**全部带 `flush=True`** —— 不带 flush 在 PowerShell 管道里会被缓冲，等于没打（这是「看不到输出」
的另一个独立来源，必须一并解决）。

### 2. 试跑加真超时

```python
_vto = config.verify_timeout_s()      # 默认 900 秒
try:
    r = run_capture([...], cwd=..., timeout=_vto)
except subprocess.TimeoutExpired:
    print(f"        [!] 试跑超过 {_vto:.0f}s 仍未结束 -> 判失败（这是真卡住，不是刷屏）")
    print("            可能原因：demo 服务没响应 / 订单状态一直没流转到已关闭 / 某一步的元素永远等不到")
    print("            处置：① 调大 HYBRID_VERIFY_TIMEOUT；② 或先手工跑一次该 pytest 看停在哪一步：")
    print(f"                 python -m pytest {node} -v -s")
    continue
```

| 项 | 值 | 依据 |
|---|---|---|
| `HYBRID_VERIFY_TIMEOUT` 默认 | **900 秒** | 实测单次试跑 202.7s + 62 步执行，整体约 360s，留 2.5 倍余量 |
| 可调 | `.env` 里写，已登记 `cli config` | 可调项必须可发现 |
| 非法值 | 空/非数/0/负数/**inf/nan** 一律回落 900 | 见下 |

---

## 连带修掉一个真 bug（V8.7.3 起就存在）

`float("1e400")` 在 Python 里是 **`inf`**，而 `inf > 0` 成立 —— 原来的判断：

```python
return val if val > 0 else 180.0     # inf 会被当成合法超时！
```

于是 `HYBRID_LLM_TIMEOUT=1e400` 会让超时变成无限大，**效果等于又禁用了一次超时** ——
同一个坑（V8.7.3 修的「`timeout=None` = 禁用超时」）换了个门又进来了。

现在两个函数都加 `math.isfinite()`：

```python
if not math.isfinite(val) or val <= 0:
    return 180.0        # llm_timeout_s
```

实测：

```
HYBRID_LLM_TIMEOUT=1e400  -> 180.0   （修复前：inf）
HYBRID_LLM_TIMEOUT=inf    -> 180.0
HYBRID_LLM_TIMEOUT=nan    -> 180.0
HYBRID_LLM_TIMEOUT=400    -> 400.0
```

---

## 判据（新增 9 条）

`tests/特性11-交付即验证/test_verify_observability.py`

| 组 | 钉住什么 |
|---|---|
| 超时取值 | 默认 900；空/非数/0/负数/**`1e400`/`inf`/`nan`** 全部回落 900；正数照收 |
| **inf 回归** | `llm_timeout_s()` 也不许接受 inf/nan —— V8.7.3 起的老洞，单独一条守着 |
| 试跑带超时 | `--verify` 的 pytest 调用**必须**显式传 `timeout=`，且必须走 `verify_timeout_s()`（唯一入口） |
| 超时处理 | 必须捕获 `subprocess.TimeoutExpired`，报错里要给「调哪个值」+「手工复跑命令」 |
| 进度交代 | generate / 试跑前后都要打；试跑提示里必须含预期耗时 + `log/` 路径 |
| flush | 进度打印必须 `flush=True`（否则 PowerShell 里被缓冲 = 等于没打） |
| 可发现性 | `HYBRID_VERIFY_TIMEOUT` 必须登记进 `cli config` 清单，且写出默认值 + 治什么问题 |

**反向验证**：回退「试跑不带超时 + 去掉进度交代 + 放开 inf」→ **2 条变红**；恢复后 9 条全绿
（恢复后逐字节比对一致）。

---

## 配置结论（本次实测背书）

用户这次跑通的配置就是正确配置，**不用再改**：

```ini
LLM_REASONING_EFFORT=high
HYBRID_LLM_TIMEOUT=400
```

完整链路实测：

```
explore --ai  → 62 步 ElementMap（element_map_20261027_170352.json）
verify        → PASSED
generate      → locator 命中 34/34
run           → 1 passed in 202.74s / pytest 退出码 0
```

`HYBRID_VERIFY_TIMEOUT` **不用设**（默认 900 够用）；只有试跑超过 15 分钟才需要调大。

---

## 升级检查清单

```bash
# 1) 不需要动 .env（除非试跑超 15 分钟，才需要 HYBRID_VERIFY_TIMEOUT）
# 2) 自检：大 prompt 实探应为绿色
python -m framework.cli llm-doctor
# 3) 真跑
python -m framework.cli all --ai --scenario-file scenarios/orders/orders_invoice_full_lifecycle.yml
```

跑起来后你会看到 `[1/2]` / `[2/2]` 两行进度，以及一行「整体 3~10 分钟属正常」的预期说明 ——
**如果真卡住，900 秒后它会明确报错并告诉你手工复跑的命令。**

---

## 兼容性

- 无破坏性变更。`HYBRID_VERIFY_TIMEOUT` 不设就是 900，之前的行为（能跑通）不变。
- 有行为变化的地方：**试跑现在最长 900 秒必返回**（以前是无限等）。如果你的用例真的需要
  超过 15 分钟，把 `HYBRID_VERIFY_TIMEOUT` 调大。
- 输出多了几行（`[1/2]` / `[2/2]` / 耗时）。若有脚本解析 CLI 输出，按前缀匹配而非行号。

---

## 过程记录（诚实留档）

1. 用户第一次报「卡住」时，我以为要查「第 2 次重试后卡死」的代码路径。实际根因是
   **`--verify` 阶段的静默阻塞** —— 当时没先确认「卡在哪一行」，绕了一圈。
   教训：**用户报卡住，第一件事是定位日志最后一行属于哪个阶段**，不要先假定是重试逻辑。
2. 我第一版判据把窗口写成 `src[i:i+420]`，但超时值是在 `try` 之前取的，判据找不到 →
   已改成向前后各看 400/420 字符。
3. 判据一跑就抓到「`1e400` → inf」这个洞，而这个洞是 V8.7.3 我自己写的。
   **判据的价值就在这里** —— 不是证明「我写的对」，是抓「我以为对」的地方。
