# ⚠️ 特性 5 · 自愈闭环 Healer —— 零判据（有实现、无验证）

**状态**：🔴 **未验证**（2026-10-07 登记 · 对应遗留项 L11）

## 现状
- **实现**：`framework/tools/run/healer.py` —— A 级放宽阈值（阈值×0.75 / MINGAP×0.6，确定性无 LLM）·
  B 级 LLM 重猜（需 key，可选）· 三态裁决 `recovered` / `real_bug` / `failed`
- **判据**：**本目录为空** —— `tests/` 全文搜 `healer` / `try_heal` / `heals/` **没有任何行为判据**
  （只有 `test_docs_sync.py` / `test_no_stale_paths.py` 里的非行为引用）

## 风险
自愈一动，**没有任何判据会拦** ⇒ 可能静默退化（看着正常、其实没在干活）。
历史上多起"机制静默退化"都是靠负向判据才发现的。

## 待补判据（4 条 · 估 ~40 分钟 · TDD 判据先行）
1. **A 级能重定位**：放宽阈值后命中唯一元素 ⇒ 成功，且留下 recovered 记录
2. **B 级只在 A 级失败后触发**：不许越过 A 级直接问 LLM（负向自证）
3. **三态裁决正确**：recovered / real_bug / failed 各自判对
4. **兜不住必须如实失败**：不许把 real_bug 记成 recovered（负向自证 · 防假绿）

> 补完后删掉本文件，换成 `test_healer_*.py`（一类，秒级）。
