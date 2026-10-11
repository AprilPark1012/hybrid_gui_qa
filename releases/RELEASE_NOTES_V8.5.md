# V8.5 发布说明（2026-10-12）

> 一句话：**真 AI 链路端到端跑通**，`framework/` 按**特性**重组。

## 1. 真 AI 链路端到端跑通

```
python -m framework.cli all --ai      # 探测 -> 生成 -> 真跑，一条命令
=> 2 passed / pytest 退出码 0
```

手搓链路（`all`，不带 `--ai`）同样全绿。两条链路共用同一套判据与生成器。

## 2. framework 按特性重组（破坏性变更：import 路径）

| 旧路径 | 新路径 |
|---|---|
| `framework/tools/probe/probe.py` | `framework/features/f03_locate/probe.py` |
| `framework/tools/probe/element_map.py` | `framework/features/f03_locate/element_map.py` |
| `framework/tools/explore/explorer.py` | `framework/features/f02_semantic/explorer_explore.py` |
| `framework/tools/generate/generator.py` | `framework/features/f02_semantic/generator_generate.py` |
| `framework/tools/explore/llm_cassette.py` | `framework/features/f08_replay/llm_cassette_explore.py` |
| `framework/tools/generate/kit_check.py` | `framework/features/f11_verify/kit_check_generate.py` |
| `framework/tools/common/*` | `framework/shared/*` |
| `framework/tools/run/login.py` · `pre_actions.py` | `framework/shared/login.py` · `pre_actions_run.py` |
| `framework/core/gates.py` | `framework/features/f09_gate/gates.py` |

**不受影响**：`python -m framework.cli ...` 与 `from framework.cli import ...`（顶层薄壳转发，
含 `CMD_FLAGS` / `FLAG_SPECS` 等符号，语义与搬迁前一致）。CLI 参数、断言体系、报告形态、用例格式**零变化**。

阶段归属看文件名后缀：`*_explore / _probe / _generate / _run / _verify`；无后缀 = 阶段无关。

## 3. 能力收敛与补齐

- **逐页探测唯一入口** `f03_locate/scan_pages_probe.py`：explore 与 generate 不再各写一遍骨架
  （两处实现必漏一处 —— V8.3.7 事故即由此而来）。
- **probe 支持单页 / 多页**（`probe --scenario-file <yml>`），产物统一 elementMap 形态
  （一页一个对象）。实测一场景 7 页 / 470 条控件。
- **元素 `id` 采集**：定位链 `test_id > element_id > 锚点下钻 > role+name`。
  无语义容器里的按钮（如右下角「保存」）由此获得稳定定位信号。
- **框架确定性兜底**（有边界、可审计）：起手页导航纠正、行定位兜底（判得死才补）。

## 4. 删除

- `--mock-fallback`（决策 D5：兜底必须有边界，模拟降级会掩盖真问题）
- `framework/tools/probe/semantic_locate.py`（零代码引用的孤儿模块）

## 5. 升级须知

1. 若你有**自己写的**脚本 import 框架模块，请按上表改路径（不留兼容 shim）。
2. 只跑 `python -m framework.cli ...` 的用法**无需任何改动**。
3. 场景文件（`scenarios/*.yml`）格式向后兼容；本轮新增的字段都是可选的。

## 6. 闸门统一契约（特性9 · B′）已落地

8 个闸门全部按 B′ 实现 `Gate` 协议并登记进全量注册表（`features/f09_gate/gates.py`）：

| 闸门 | 住址 | 守卫 |
|---|---|---|
| `ai_output` | `f02_semantic/ai_output_gate_explore.py` | AI 产出（写死行数据 / 语义误选 / 必填覆盖 / 行定位缺失） |
| `case_quality` | `f02_semantic/case_quality_gate_generate.py` | 用例质量（假绿红线） |
| `probe_pre` | `f02_semantic/probe_pre_gate_generate.py` | 用例与场景前置一致性（D9） |
| `mapping` | `f03_locate/mapping_gate_generate.py` | elementMap 映射完整性 |
| `is_valid_rescan` | `f03_locate/is_valid_rescan_gate_probe.py` | `isValid=false` 排除计数（D3） |
| `ambiguity` | `f04_ambiguity/ambiguity_gate_generate.py` | 歧义 / 行定位 |
| `data_sets` | `f05_layers/data_gate_generate.py` | 数据组 / 悬空数据集 |
| `consistency` | `f09_gate/consistency_gate.py` | 齐套（elementMap / 录像 / cases / scripts） |

**关键改进**：`cli.py` 不再用 `getattr` **直读 explorer 的私有全局**传闸门结果
（上游没填 / 改名 / 搬家都会静默失效）—— 现在统一走 `GateResult`（显式返回、单一形状）。

**全量回归**：`1107 passed / 1 skipped / 0 failed`。

## 7. 已知未完成（如实标注）

- **登录步骤化**：按决策 D6 排到 **V8.5.1**。
- 闸门 `check()` 本轮做的是「搬家 + 统一契约」（委托既有实现），
  **判定逻辑本身未改**；各闸门的判定口径后续可按特性继续收口到唯一入口。
