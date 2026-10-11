# -*- coding: utf-8 -*-
"""场景「业务等待时长」的**唯一解析入口**（L27 · 2026-10-09）。

## 为什么需要（实测事故）

V8.4.4 干净环境 E2E 卡在场景第 7 步：

```
AssertionError: 等待超时：30000ms 内页面始终没有出现 '已关闭'
```

而 demo 的业务事实是 **150 秒**才自动关闭（`demo/app.py` 需求29），**场景 yml 自己也写明了**
（两处：「提交后 **150 秒**自动关闭」）。唯独框架的等待默认值是**写死的 30000ms**。

-> **框架的默认值把场景的明确声明盖掉了**，而失败现象是「页面始终没出现『已关闭』」——
**看着像业务没流转，其实是框架等太短**。这是最贵的一类错：现象指向业务，根因在框架。

## 口径（三条，缺一不可）

1. **只认「与等待/流转语义同句」的时长** —— 避免把「履行频率 10 秒一档」这类无关数字
   当成业务等待时长。（同句里两者都有时按第 2 条取最大。）
2. 同一场景声明了多个时取**最大** —— 框架按**最长**的那个准备预算：宁可等够，不可等短。
3. **认不出来就返回 `None`** —— 框架退回**有界默认**（`HYBRID_WAIT_DEFAULT_MS`），
   绝不拍脑袋给一个「大概够」的值。

## 支持写法

`150 秒` / `150秒` / `150 s` / `150s` / `2 分钟` / `2分钟` / `2 min` / `1 小时` / `30 seconds`

毫秒级写法**不认**：业务等待不会是毫秒级，认了反而容易误伤。

## 安全上界

超过 `_MAX_DECLARED_MS`（1 小时）的值**不采信**（视为误解析）并**出声**——
这是**安全界**，不是业务默认值：宁可退回有界默认，也不因为一个手误把整条链路挂住。
"""
from __future__ import annotations

import re

#: 视为「与等待相关」的语义提示词。**没有它就不认那句里的时长**（口径 1）。
#: 放宽会误伤（把「履行频率 10 秒一档」当业务等待），收紧会漏（场景换了说法就认不出）——
#: 故取「等待/异步/流转」这一族**明确表示『等一会儿』**的词。
_WAIT_HINT_RE = re.compile(
    r"等待|自动|流转|轮询|超时|异步|生效|同步|刷新|定时|延迟"
    # 英文族：场景文案可能是英文（`wait 30 seconds for auto refresh`）——口径不该绑中文
    r"|wait\w*|auto\w*|poll\w*|timeout|async|refresh\w*|delay\w*|retry|until",
    re.I,
)

#: 时长写法。[!] alternation 顺序敏感：长词必须排在短词前（`分钟` 在 `分` 前、`minutes?` 在 `min` 前），
#: 否则 "2 分钟" 会被 `分` 抢走、"2 mins" 会被 `min` 抢走（结果数值对但单位口径不同，暂时等价，
#: 但只要将来加单位就会错——现在就排对，别埋雷）。
_DUR_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*"
    r"(小时|分钟|分|时|hours?|hrs?|h\b|minutes?|mins?|min\b|seconds?|secs?|sec\b|s\b|秒)",
    re.I,
)

_UNIT_MS: dict[str, int] = {
    "秒": 1000, "s": 1000, "sec": 1000, "secs": 1000, "second": 1000, "seconds": 1000,
    "分": 60_000, "分钟": 60_000, "min": 60_000, "mins": 60_000,
    "minute": 60_000, "minutes": 60_000,
    "时": 3_600_000, "小时": 3_600_000, "h": 3_600_000, "hr": 3_600_000, "hrs": 3_600_000,
    "hour": 3_600_000, "hours": 3_600_000,
}

#: 安全上界：超过它的「声明」不采信（视为误解析），并出声。**不是业务默认值**。
_MAX_DECLARED_MS = 60 * 60 * 1000

_warned: list[str] = []


def _durations_in(line: str) -> list[int]:
    out: list[int] = []
    for m in _DUR_RE.finditer(line or ""):
        unit = m.group(2).lower()
        mult = _UNIT_MS.get(unit)
        if mult is None:                      # 理论上不可达（正则与表同源），保守跳过
            continue
        try:
            out.append(int(round(float(m.group(1)) * mult)))
        except Exception:                     # noqa: BLE001
            continue
    return out


def declared_wait_ms(scenario_text: str | None) -> int | None:
    """从场景原文里抽出**声明的业务等待时长**（毫秒）；认不出返回 `None`。

    只扫**含等待语义提示词的那些行**（口径 1），多行命中时取最大（口径 2）。
    """
    best: int | None = None
    for line in (scenario_text or "").splitlines():
        if not _WAIT_HINT_RE.search(line):
            continue
        for ms in _durations_in(line):
            if ms > _MAX_DECLARED_MS:
                note = f"[wait] [!] 场景声明的等待时长 {ms}ms 超过安全上界 {_MAX_DECLARED_MS}ms，不采信"
                if note not in _warned:
                    _warned.append(note)
                    print(note, flush=True)
                continue
            if best is None or ms > best:
                best = ms
    return best


def effective_wait_ms(scenario_text: str | None, ai_timeout_ms, default_ms: int) -> int:
    """AI **没给**（或给了非法值）时该用的等待时长：**场景声明优先**，其次有界默认。

    为什么是这个优先级：场景声明的是**业务事实**（多久才会变），默认值只是框架的兜底猜测。
    「AI 没给」时用声明值不是覆盖模型的决定，而是**补上它没表达的那部分**。
    （AI **给了**合法值时一律尊重 —— 那属于模型明确决定，见 `wait_shortfall`。）
    """
    declared = declared_wait_ms(scenario_text)
    if isinstance(ai_timeout_ms, int) and ai_timeout_ms > 0:
        # AI/手写用例给了值：**声明是事实，偏小视为缺陷 -> 抬到声明值**（并留痕，见 wait_shortfall）。
        # 为什么不静默保留：一个短于业务事实的等待 = 一条**注定失败**的用例；
        # 为什么不算"覆盖模型决定"：`infer_kind_for_assert` 那条讲的是**别覆盖模型的偏好**
        #（它选了哪种 kind），而这里是**与客观事实矛盾**（业务就是 150 秒才变），不是偏好问题。
        return max(ai_timeout_ms, declared) if declared else ai_timeout_ms
    if declared:
        return max(declared, int(default_ms))
    return int(default_ms)


def wait_shortfall(scenario_text: str | None, ai_timeout_ms) -> list[str]:
    """AI 给的等待时长**小于场景声明的业务时长** -> 返回可读原因（空列表 = 没问题）。

    为什么不静默改写：这是**模型明确给了值**的情形，按项目口径「不许覆盖模型的明确决定」
    -> 一律**拦下 + 说清**（把场景声明值一并给出，让下一轮改得对）。
    """
    if not isinstance(ai_timeout_ms, int) or ai_timeout_ms <= 0:
        return []                              # 没给：走 effective_wait_ms 补默认，不算冲突
    declared = declared_wait_ms(scenario_text)
    if not declared or ai_timeout_ms >= declared:
        return []
    return [
        f"等待时长不足：场景声明了 {declared}ms（约 {round(declared / 1000)} 秒），"
        f"而这一步只给了 {ai_timeout_ms}ms -> 必然等不到。请把 timeout_ms 提高到 >= {declared}"
    ]
