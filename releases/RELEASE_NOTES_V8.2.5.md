# hybrid_gui_qa V8.2.5 升级说明（2026-09-24）

> 把「生成物」这一层**按 id 收口**：不再有「一个 test_cases.py 装全部用例」，
> 改成 **一个场景一个目录、一个用例一个脚本**，并用 `index.json` 把
> `scenario_id → case_id → 脚本 → 数据集` 串起来 —— 于是 **generate 只重做"变了"的那些**。

## 一、为什么要改（来自实际交付场景）

| 问题 | 之前 | 现在 |
|---|---|---|
| 用例越来越多怎么办？ | 全部塞进一个 `scripts/test_cases.py` ✗ 生产上会有几百条专属用例/场景，管理起来很乱 | `scripts/generated/<scenario_id>/<case_id>.py` 一个用例一个文件，按 id 就能定位 ✓ |
| 改一条用例要等多久？ | generate **全量重生成**（所有用例 + 现场探测）⇒ 慢脚本里有近一半时间花在这 | **增量重生成**：只重写指纹变了的模块；无变化 ⇒ **零重写** ✓ |
| 改了东西，产物到底刷没刷？ | 靠"重跑一遍看看" | `index.json` 记录**四种指纹**（用例 / 场景 / 探测结果 / 渲染模板）⇒ 谁变了重做谁 ✓ |

## 二、本版改动

### ① 产物形态：按 id 分文件

```
cases/<scenario_id>/<case_id>.json          用例（AI 用例按场景分目录）
cases/manual/<case_id>.json                 手搓用例（无场景的）
scripts/generated/<scenario_id>/<case_id>.py     ★ 一个用例一个脚本
scripts/generated/manual/<case_id>.py
scripts/generated/_harness.py               共享运行时（原 conftest 的辅助函数原样搬）
scripts/generated/conftest.py               只做转发（暴露夹具给 pytest）
scripts/generated/index.json                case_id → {script_path, 四种指纹}
```

- **`scripts/test_cases.py` 与 `scripts/conftest.py` 不再产出**（旧单文件形态已废弃，不留兼容薄壳）。
  升级动作：**重跑一次 `python -m framework.cli generate`** 即可，无需手工删文件（生成期会清掉旧的）。
- `_harness.py` 里 `BASE` 与 `datasets` 的路径按产物实际位置推导（`scripts/generated/` 下一层）。

### ② 增量重生成（本版核心收益）

- `generate` 默认 **`--changed`**：三指纹（用例 / 场景 / 探测结果）+ 模板指纹任一不同 ⇒ 才重写这个模块。
- 新增 `--force`（全量重写，发版/核对用）与 `--only <case_id[,case_id...]>`（只重做指定用例，其余一动不动）。
- 生成结束会打印：`用例模块 N 个：重写 X · 跳过（无变化）Y`，另打印共享运行时重写与孤儿清理清单（**可核对、不静默**）。

### ③ 一致性与新陈代谢（R7-f）

- `index.json` ↔ 磁盘**双向对账**：孤儿脚本、幽灵条目都会在判据里直接红。
- 生成期清掉「index 不认识的脚本」与「对应用例已不存在的 dataset/sets」，清理动作**出声**。
- 产物自洽闸扩到分模块产物：任一模块引用的 dataset 不存在 ⇒ **拒绝落盘并报错**（不是等到运行期 FileNotFoundError）。

### ④ 跟随新布局改动的部件

| 部件 | 改动 |
|---|---|
| `cli run` | 直接跑 `scripts/generated/`（不再是单个文件）；缺失时提示 `index.json` 而非旧文件名 |
| `cli explore --verify` | 用 `index.json` 的 `case_id → script_path` 取 node id（不再拼 `test_cases.py::test_x`） |
| `build_tools/pack_release.py` | 必需项改指 `scripts/generated/**`；产物检查改为**拼读全部生成模块**（存根/就绪契约/裸 goto 三条语义不变） |
| 二类验证脚本 | 新增共享助手 `tests/featureTest/_gen_layout.py`（case_id → 新脚本路径）；8 个脚本按新布局取 node id / 读产物 |
| `tests/frameworkTest/**` 判据 | 全部按新布局读产物（语义未变，另加严数处：逐模块判就绪契约、数据集也不许落盘、模板↔产物逐字节互锁） |
| README / `docs/training.html` | 当前结构、目录树、命令示例同步；**历史变更记录一律未动** |

### ⑤ 用例落盘与清理的安全边界（照旧，未放松）

- "同场景只留一条"仍只由**严格形态**的 AI 用例（`ai_<scenario_id>_<6位数字>`）触发；
- 手搓/临时用例保留 `-2` 递增，绝不覆盖用户手工产物；
- 清理按 `case_id` 精确比对（不是按路径）—— 避免今天早些时候那类"静默删用例"的事故复发。

## 三、升级动作（对使用者的影响）

1. **拉代码后重跑一次**：`python -m framework.cli generate`
2. 若你的脚本/CI 引用了 `scripts/test_cases.py` ⇒ 改成 `scripts/generated/`（目录，pytest 直接收集）
3. 想按用例调试：`python -m framework.cli run --debug --case <case_id>`（不变）
4. 只想重做某几条：`python -m framework.cli generate --only <case_id>`

## 四、验证（本版交付证据）

- **一类（判据）**：**537 passed / 0 failed**（27 秒级）
- **二类（特性验证）**：**17 通过 · 0 跳过 · 0 失败 · 35.2 分钟**（预算 40 分钟 · D6）
  · 连续两轮独立复跑均全绿（第 3 轮 34.9 分钟 / 第 4 轮 35.2 分钟）
- **generate 自检**：退出码 0 · 空 element 0 · 映射存根 0 · 数据组校验拦截 0
- **分模块产物对账**：pytest 真收集 = 模块数 + 数据驱动展开数 ⇒ 与 `index.json` 一致
- **增量实证**（实测）：无变更重跑 ⇒ **重写 0 · 跳过 19**；改用例 ⇒ **只有那条脚本变化**（其余逐字节不变）；改渲染模板 ⇒ 全部重写（第四指纹生效）
- **产物自洽**：index 19 = 生成脚本 19 = 用例 19 · 平铺残留 0 · 孤儿脚本 0 · 幽灵条目 0 · 悬空引用 0
- **pytest 真收集**：25 条（19 模块 + 数据驱动 3 组展开）⇒ 与 `index.json` 对账一致

> ⚠️ 本版为**结构性变更**：产物位置变了，任何"绕过 generate 直接改产物"的做法都会在下次生成被覆盖
> （这是设计意图 —— 产物永远由用例驱动）。
