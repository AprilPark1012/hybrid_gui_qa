"""数据驱动核心：dataset 加载 + 模板占位符替换 + 用例上下文(case_ctx)隔离。

设计要点（对应需求 5/6/8）：
  - 每个用例的输入数据来自 datasets/*.json，通过 scenarios/index.json 映射表关联。
  - 脚本里用 {contractName} 这类占位符，运行时用 dataset 的实际值替换（format_template）。
  - case_ctx 是一个 【function-scope】 的 dict：每个用例独享一个实例（fixture 注入），
    新建返回的合同编号等"缓存变量"写在这里，并发执行时【互不污染】。

v 本文件不含任何 LLM/浏览器调用 —— 纯数据层。
"""
from __future__ import annotations
import json
import re
from pathlib import Path

from framework.shared.config import BASE   # 仓库根：单一来源，不自己推层级

# ---------------- dataset / scenarios 加载 ----------------
def load_dataset(path: str | Path) -> dict:
    """加载一份 dataset 文件（json），校验含 type 字段。"""
    p = Path(path)
    if not p.is_absolute():
        p = BASE / p
    data = json.loads(p.read_text(encoding="utf-8"))
    if "type" not in data:
        raise ValueError(f"dataset {p} 缺少 type 字段（search/create）")
    return data


def load_index(index_path: str | Path | None = None) -> dict:
    """加载用例编排表。默认 scenarios/index.json。"""
    p = Path(index_path) if index_path else BASE / "scenarios" / "index.json"
    if not p.is_absolute():
        p = BASE / p
    return json.loads(p.read_text(encoding="utf-8"))


def iter_cases(index: dict):
    """按编排表逐个产出 (case, dataset_data)。dataset 相对 BASE 解析。"""
    base_url = index.get("defaults", {}).get("base_url", "http://localhost:8000")
    for t in index.get("tests", []):
        data = load_dataset(t["dataset"])
        yield {
            "case_id": t["case_id"],
            "type": t["type"],
            "dataset": t["dataset"],
            "label": t.get("label", t["case_id"]),
            "data": data,
            "base_url": base_url,
        }, data


# ---------------- 模板占位符替换 ----------------
from datetime import datetime
import time as _time
import uuid as _uuid
import random as _random

_PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")


def _builtin_value(name: str) -> str | None:
    """内置动态占位符：每次解析时生成【当时的实际值】。

    返回 None 表示不是内置变量（交给 ctx 查）。用于解决"合同名称不能重复"——
    如 {date}/{datetime}/{timestamp}/{uuid}/{random}，合同名带它们就永不重名。
    """
    now = datetime.now()
    if name == "date":
        return now.strftime("%Y%m%d")
    if name == "datetime":
        return now.strftime("%Y%m%d%H%M%S")
    if name == "timestamp":
        return str(int(_time.time()))
    if name == "uuid":
        return str(_uuid.uuid4())[:8]
    if name == "random":
        return str(_random.randint(1000, 9999))
    if name == "randomHex":
        return format(_random.randint(0, 65535), "04x")
    return None


def format_template(value, ctx: dict) -> str:
    """把字段里的 {contractName} / {date} / {datetime} 等占位符替换成实际值。

    解析顺序（关键）：
      1. 内置动态变量（{date}/{datetime}/{timestamp}/{uuid}/{random}/...）→ 当时生成
      2. 静态变量（{contractName}/{managementUnit}/...）→ 从 ctx 取
    未命中的原样保留（可能留给后续或报错由调用方决定）。
    """
    if isinstance(value, (dict, list)):
        return value  # 容器类型不在此层处理
    if value is None:
        return ""
    s = str(value)
    if "{" not in s:
        return s

    def _sub(m):
        name = m.group(1)
        b = _builtin_value(name)
        if b is not None:
            return b
        return str(ctx.get(name, m.group(0)))   # 静态变量从 ctx 取；未命中保留原样

    return _PLACEHOLDER_RE.sub(_sub, s)


def resolve_expected(expected: dict, ctx: dict) -> dict:
    """递归解析 expect 部分：把里面的 {var} 用 ctx 替换，供断言用。"""
    out = {}
    for k, v in expected.items():
        if isinstance(v, dict):
            out[k] = resolve_expected(v, ctx)
        elif isinstance(v, list):
            out[k] = [format_template(x, ctx) for x in v]
        else:
            out[k] = format_template(v, ctx)
    return out


# ---------------- 用例级变量池 ----------------
def resolve_dynamic_inputs(ctx: dict, keys=("contractName", "created_name")) -> dict:
    """对 ctx 里的【输入字段】做一次动态占位符解析，并把结果固化回 ctx。

    关键：动态占位符（{date}/{datetime}）必须【在用例运行时一次性解析并固化】，
    不能每次引用都重新 format_template（否则填表值==断言值会因跨秒而不同）。
    这里的解析产物 = 填表用的值 = 断言引用的值，全链路一致。
    """
    for k in keys:
        v = ctx.get(k)
        if isinstance(v, str) and "{" in v:
            resolved = format_template(v, ctx)
            ctx[k] = resolved
            # 可再解析一次纯净字符（避免嵌套如 {datetime} 里再无占位符）
            if "{" in str(resolved):
                ctx[k] = format_template(str(resolved), ctx)
    # created_name 跟随 contractName（若无独立值）
    if ctx.get("contractName") and not ctx.get("created_name"):
        ctx["created_name"] = ctx["contractName"]
    return ctx


