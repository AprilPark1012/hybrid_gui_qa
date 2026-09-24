"""scenario 文件（scenarios/**.yml）的解析、校验与发现。

设计（2026-09-11，见内部设计文档「scenario 文件设计」）
---------------------------------------------------
一个文件 = 一个场景；字段按「谁读它」分五组：
    人读   id / title / description / owner / updated / notes
    框架读 tags / priority / target.url
    AI 读  target.page / target.preconditions / business_context / scenario(必填)
    质量闸 assert_guard.must_contain / assert_guard.forbidden
    数据读 data（一期只解析不展开）
**只有 scenario 必填**，其余全可选 ⇒ `explore --ai --scenario "…"`（内联）等价于"只给 scenario 字段"，
两条路共用同一套下游（ElementMap → cases → generate → run），不存在两套实现。
格式 YAML：多行中文块标量免转义 + 可写注释 + pyyaml 已在依赖里。
"""
from __future__ import annotations

import re
import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from framework.tools.common.config import SCENARIOS_DIR

_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_EXTS = (".yml", ".yaml")
_PRIO_ORDER = {"p0": 0, "p1": 1, "p2": 2, "p3": 3}


class ScenarioError(RuntimeError):
    """场景文件不合法（缺字段 / 类型错 / YAML 语法错）—— 消息带文件路径，便于定位。"""


@dataclass
class ScenarioPage:
    """场景里的一个页面（P3 跨页流程）：name 是人/AI 都看的页名，url 是该页直连地址。"""
    name: str
    url: str
    page: str = ""            # 该页的页面说明（给 AI 的领域知识）

    def to_dict(self) -> dict:
        return {"name": self.name, "url": self.url, "page": self.page}


@dataclass
class Scenario:
    path: Path
    id: str
    scenario: str
    title: str = ""
    description: str = ""
    tags: list = field(default_factory=list)
    priority: str = ""
    owner: str = ""
    updated: str = ""
    url: str = ""
    page: str = ""
    preconditions: list = field(default_factory=list)
    business_context: str = ""
    must_contain: list = field(default_factory=list)
    forbidden: list = field(default_factory=list)
    data: list = field(default_factory=list)
    notes: str = ""
    warnings: list = field(default_factory=list)
    pages: list = field(default_factory=list)      # list[ScenarioPage]（跨页；空 = 单页老写法）

    @property
    def name(self) -> str:
        return self.title or self.id

    @property
    def is_multi_page(self) -> bool:
        return len(self.pages) > 1

    def all_pages(self) -> list["ScenarioPage"]:
        """统一视图：单页写法也返回一个元素的列表（下游只认这一个入口，避免两套实现）。"""
        if self.pages:
            return list(self.pages)
        if self.url:
            return [ScenarioPage(name="页面1", url=self.url, page=self.page)]
        return []

    def page_bg(self) -> str:
        """给 AI 的【页面背景】块（页面说明 + 前置条件 + 领域上下文）。"""
        lines: list[str] = []
        if self.page:
            lines.append(f"页面说明：{self.page}")
        if self.preconditions:
            lines.append("前置条件：" + "；".join(str(x) for x in self.preconditions))
        if self.business_context:
            lines.append("领域上下文：\n" + self.business_context.strip())
        return "\n".join(lines)

    def guard_text(self) -> str:
        """给 AI 的【本场景护栏】块（断言必须围绕的稳定文本 / 不得出现的内容）。"""
        lines: list[str] = []
        if self.must_contain:
            lines.append("断言必须围绕这些【稳定文本】（操作前即可确定）："
                         + "、".join(str(x) for x in self.must_contain))
        if self.forbidden:
            lines.append("断言中不得出现：" + "、".join(str(x) for x in self.forbidden))
        return "\n".join(lines)

    def guard_spec(self) -> dict:
        """给质量闸（case_warnings）的结构化护栏。"""
        return {"must_contain": list(self.must_contain), "forbidden": list(self.forbidden)}

    def case_extra(self) -> dict:
        """回写进 case 的溯源字段（generator 只读 case_id/steps/asserts，多余字段安全）。"""
        try:
            rel = str(self.path.resolve().relative_to(SCENARIOS_DIR.resolve().parent))
        except Exception:
            rel = str(self.path)
        extra = {"scenario_id": self.id, "source_scenario": rel}
        # D3（2026-09-24 他定）：记下**当时场景文件的内容指纹**。
        # 场景一改（指纹变）⇒ 判据当场红 ⇒ 必须重新生成，保证用例与场景同步。
        try:
            _raw = self.path.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
            extra["scenario_fingerprint"] = hashlib.sha256(_raw.encode("utf-8")).hexdigest()[:16]
        except Exception as _e:  # 绝不静默：指纹写不进去 = D3 的同步判据会失效
            import sys as _sys
            print(f"  ⚠️ [scenario] 场景指纹计算失败（{type(_e).__name__}: {_e}）"
                  f"⇒ D3 同步判据将失效，必须修", file=_sys.stderr)
        if self.pages:                      # P3 跨页：把页面清单带进用例（质量闸与溯源都用）
            extra["pages"] = [p.to_dict() for p in self.pages]
        return extra


def _as_list(value, field_name: str, path) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    raise ScenarioError(f"{path}: 字段 {field_name} 应为列表，实际是 {type(value).__name__}")


def load_scenario_file(path) -> Scenario:
    """读 + 校验一个场景文件；任何不合法都抛 ScenarioError（绝不静默兜底）。"""
    p = Path(path)
    if not p.exists():
        raise ScenarioError(f"场景文件不存在: {p}")
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise ScenarioError(f"{p}: YAML 语法错误 → {e}") from None
    if raw is None:
        raise ScenarioError(f"{p}: 文件为空（没有可解析的字段）")
    if not isinstance(raw, dict):
        raise ScenarioError(f"{p}: 顶层应为映射（key: value），实际是 {type(raw).__name__}")

    warns: list[str] = []
    text = str(raw.get("scenario") or "").strip()
    if not text:
        raise ScenarioError(f"{p}: 缺少必填字段 scenario（自然语言动作流）")

    sid = str(raw.get("id") or p.stem).strip()
    if not _ID_RE.match(sid):
        raise ScenarioError(f"{p}: id {sid!r} 不合法（要求小写蛇形，正则 ^[a-z][a-z0-9_]*$）")
    if sid != p.stem:
        warns.append(f"id({sid}) 与文件名({p.stem}) 不一致 → 以 id 为准（建议改成一致，避免溯源断裂）")

    target = raw.get("target") or {}
    if not isinstance(target, dict):
        raise ScenarioError(f"{p}: target 应为映射（url / page / preconditions）")
    # ---- 跨页流程（P3）：pages 列表 ----
    raw_pages = raw.get("pages")
    pages: list[ScenarioPage] = []
    if raw_pages is not None:
        if not isinstance(raw_pages, list):
            raise ScenarioError(f"{p}: pages 应为列表（每项含 name / url / page）")
        if target.get("url"):
            raise ScenarioError(
                f"{p}: pages 与 target.url 互斥 —— 多页写 pages，单页写 target.url（不猜你的意图）")
        for i, pg in enumerate(raw_pages, 1):
            if not isinstance(pg, dict):
                raise ScenarioError(f"{p}: pages[{i}] 应为映射（name / url / page）")
            pname = str(pg.get("name") or "").strip()
            purl = str(pg.get("url") or "").strip()
            if not pname:
                raise ScenarioError(f"{p}: pages[{i}] 缺少 name（页名，AI 与日志都靠它区分页面）")
            if not purl.startswith("http"):
                raise ScenarioError(f"{p}: pages[{i}].url 必须是完整 http(s) 地址，实际 {purl!r}"
                                    f"（跨页要能直连，否则 AI 只能靠点、不可靠）")
            if any(x.name == pname for x in pages):
                raise ScenarioError(f"{p}: pages 里页名重复：{pname!r}（页名是元素唯一化的依据，必须唯一）")
            pages.append(ScenarioPage(name=pname, url=purl, page=str(pg.get("page") or "")))
        if len(pages) == 1:
            warns.append("pages 只给了一个页面 —— 等价于单页场景（跨页至少 2 页）")
    guard = raw.get("assert_guard") or {}
    if not isinstance(guard, dict):
        raise ScenarioError(f"{p}: assert_guard 应为映射（must_contain / forbidden）")
    data = raw.get("data") or []
    if not isinstance(data, list):
        raise ScenarioError(f"{p}: data 应为列表（每组数据一项）")
    # 2026-09-21 L1「真展开」：data 是真用的了（一组数据 = 一条用例），所以校验必须严格 ——
    # 写错了不能静默忽略，否则会出现「改了 data、报告里还是只有一条」这种没人发现的假象。
    seen_ids: list[str] = []
    for i, item in enumerate(data, 1):
        if not isinstance(item, dict):
            raise ScenarioError(
                f"{p}: data 第 {i} 组应为映射（占位符名: 值），实际是 {type(item).__name__}"
                f"；例：- {{关键词: \"1007\"}}")
        for k in item:
            if not isinstance(k, str) or not k.strip():
                raise ScenarioError(f"{p}: data 第 {i} 组的键必须是占位符名（非空字符串）")
        if "id" in item:
            if not isinstance(item["id"], str) or not item["id"].strip():
                raise ScenarioError(f"{p}: data 第 {i} 组的 id 必须是非空字符串（它进报告里的用例名）")
            seen_ids.append(item["id"].strip())
    dup = sorted({x for x in seen_ids if seen_ids.count(x) > 1})
    if dup:
        raise ScenarioError(
            f"{p}: data 的 id 重复：{dup} —— 参数名会撞车，报告里分不出是哪组数据")

    return Scenario(
        path=p, id=sid, scenario=text,
        title=str(raw.get("title") or ""),
        description=str(raw.get("description") or ""),
        tags=[str(t) for t in _as_list(raw.get("tags"), "tags", p)],
        priority=str(raw.get("priority") or ""),
        owner=str(raw.get("owner") or ""),
        updated=str(raw.get("updated") or ""),
        url=str(target.get("url") or ""),
        page=str(target.get("page") or ""),
        preconditions=_as_list(target.get("preconditions"), "target.preconditions", p),
        business_context=str(raw.get("business_context") or ""),
        must_contain=[str(x) for x in _as_list(guard.get("must_contain"), "assert_guard.must_contain", p)],
        forbidden=[str(x) for x in _as_list(guard.get("forbidden"), "assert_guard.forbidden", p)],
        data=data,
        notes=str(raw.get("notes") or ""),
        warnings=warns,
        pages=pages,
    )


def discover_scenarios(root=None, tags=None, limit: int | None = None) -> list[Scenario]:
    """递归扫 scenarios/ 下的 *.yml/*.yaml（跳过 README*），按 tags 过滤、priority 排序。

    - 任一文件不合法 → 直接抛 ScenarioError（批量模式更要早失败，别跑一半才发现）
    - tags：OR 语义（命中任一 tag 即入选）
    """
    r = Path(root or SCENARIOS_DIR)
    if not r.exists():
        raise ScenarioError(f"场景目录不存在: {r}")
    files = [f for f in sorted(r.rglob("*"))
             if f.is_file() and f.suffix.lower() in _EXTS and not f.name.upper().startswith("README")]
    if not files:
        raise ScenarioError(f"{r} 下没有找到 *.yml / *.yaml 场景文件")

    scenarios: list[Scenario] = []
    errors: list[str] = []
    for f in files:
        try:
            scenarios.append(load_scenario_file(f))
        except ScenarioError as e:
            errors.append(str(e))
    if errors:
        raise ScenarioError("以下场景文件不合法，已中止：\n  - " + "\n  - ".join(errors))

    if tags:
        want = {str(t).lower() for t in tags}
        hit = [s for s in scenarios if want & {str(t).lower() for t in s.tags}]
        if not hit:
            raise ScenarioError(f"{r} 下没有 tag 命中 {sorted(want)} 的场景")
        scenarios = hit

    scenarios.sort(key=lambda s: (_PRIO_ORDER.get(s.priority.lower(), 9), str(s.path)))
    if limit:
        scenarios = scenarios[: int(limit)]
    return scenarios
