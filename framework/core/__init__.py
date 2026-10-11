# -*- coding: utf-8 -*-
"""framework.core —— 跨特性共享原语（P25 §6.2 目标结构）。

本包只放**与特性无关**的东西（零业务词）：
  · gates.py  闸门统一契约 + 全量注册表 + GateResult（特性9 的契约面）
  · 后续（片 8 搬迁）：config / browser / text_io / textutil / limits /
    retention / target_probe / declared_wait / model（ElementRef/TestStep/ElementMapPage）

[!] 现状：这些模块还在 framework/tools/common/ 下 —— 片 8 按「特性聚合 + 阶段后缀」统一搬迁，
    本包先只落 gates.py（片 1 需要它当契约落点）。
"""
