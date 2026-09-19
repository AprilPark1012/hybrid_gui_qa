"""LLM 录制 / 回放（cassette）—— 让 AI 语义链路在**没有外网**的机器上也能跑。

问题
----
`explore --ai` 必须连 LLM（DeepSeek）。受管网络里的机器（典型：工作电脑）连不出去 ⇒
AI 语义链路在那台机器上根本跑不了，只能人工把产物拷来拷去；换个场景就得回到有网的机器。

做法
----
把「发给 LLM 的 prompt → LLM 的回答」录成一个 json（一次调用一个文件）：
有外网的机器录一次（`--llm-record`），把整个目录拷到离线机器 ⇒ 后者能跑**完整** explore
（含默认的 `--verify` 试跑），连 key 都不用配。
附带收益：回放是**逐字节可复现**的 ⇒ 顺带消掉 DeepSeek function calling 的间歇性 JSON 抖动
（同一 prompt 连调两次结果不同，是上游的老毛病）。

三种模式（**只由 CLI 参数决定，运行中绝不自动切换**）
--------------------------------------------------
* 不带参数                → live    真调 LLM（与本功能之前逐字一致）
* `--llm-record [DIR]`    → record  真调 LLM，成功后落盘
* `--llm-cassette [DIR]`  → replay  **只**读 DIR：命中即用（不联网 / 不需要 key）；
                                    未命中 → 明确报错，绝不悄悄改走 live 或 mock

红线（沿用本项目既有口径）
------------------------
1. **未命中必须 fail loud** —— 静默降级 = 造假。
2. **回放产物必须标注来源** —— 「这是回放、不是当场问的 AI」要让人看得见
   （CLI 输出 + 写进用例 json 的 `llm_source` 字段）。
3. **键是严格匹配**（sha256(prompt)）—— 场景文案、控件清单、DOM 上下文、提示词模板
   任意一处变了就不命中。宁可报「录的那份和现在对不上」，也不拿旧结论套新页面。
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from . import config

__all__ = ["Cassette", "CassetteError", "MODE_LIVE", "MODE_RECORD", "MODE_REPLAY",
           "cassette_key", "struct_key", "default_dir", "render_miss_help"]

MODE_LIVE = "live"
MODE_RECORD = "record"
MODE_REPLAY = "replay"

DEFAULT_DIRNAME = "llm_cassettes"


class CassetteError(RuntimeError):
    """cassette 用法/内容有问题（目录不存在、文件损坏、键不命中……）。一律 fail loud。"""


def default_dir() -> Path:
    """默认录像目录 `output/llm_cassettes/`。

    为什么放 output/：① 它已在 `.gitignore` 里 ⇒ 录像**不会**被提交、更不会进公开仓
    （录像含 prompt 全文 = 场景文案 + 控件语义名 + 页面背景，属内部信息）；
    ② 语义上它就是「运行时证据」，与 element_maps / traces 同类。
    """
    return config.OUTPUT_DIR / DEFAULT_DIRNAME


def cassette_key(prompt: str, system: str = "") -> str:
    """录像键 = sha256(system + \\x00 + prompt) 的前 16 个 hex。

    刻意**不含模型名**：离线机器通常连 `.env` 都没有、更不会配 `DEEPSEEK_MODEL`，
    把模型名拌进键会导致「在 A 机录、B 机放」永远不命中，把可用性毁掉。
    模型名作为元信息写进录像，命中时打印出来供人核对。
    """
    h = hashlib.sha256()
    h.update((system or "").encode("utf-8"))
    h.update(b"\x00")
    h.update((prompt or "").encode("utf-8"))
    return h.hexdigest()[:16]


def struct_key(scenario: str, items: list[dict] | None, pages: list[dict] | None = None,
               system: str = "") -> str:
    """**结构键**：只看「场景 + 页面结构 + 控件语义骨架」，**不看业务数据的值**。

    为什么要有第二个键（2026-09-18 实测逼出来的）：
    prompt 里含 `nearby_text` 这类**业务数据值**（列表行的整行文本 = 管理单元/帐套/类型/客户/业务单元），
    而 demo 的预置数据是**随机生成**的、且 `/api/reset`（pytest 每条用例前都会调）会重新随机
    ⇒ 同一个场景在「另一台机器」或「跑过测试的机器」上，prompt 逐字必然不同
    （实测：同场景两次录制，40 行差异全是 nearby_text 的数据值）。
    只用严格键 ⇒ 跨机器回放永远不命中 ⇒ 这个功能等于没做。

    结构键把这些值换成稳定的骨架（控件语义名 + role + name/label/placeholder/test_id + 所在页），
    于是「同一场景、同一页面结构、不同数据」可以复用同一份录像 —— **代价是命中时必须在日志里
    大声说明**（步骤是录制当时针对那批数据做的判断，换了数据要人核对）。

    刻意排除的字段：nearby_text / text / help_text / container_heading（都可能含业务数据值）。
    """
    import hashlib as _h
    parts = [system or "", (scenario or "").strip()]
    for pg in (pages or []):
        parts.append(f"PAGE|{pg.get('name', '')}|{pg.get('url', '')}")
    for it in sorted(items or [], key=lambda x: (str(x.get("page") or ""),
                                                 str(x.get("semantic_name") or ""))):
        parts.append("EL|" + "|".join(
            str(it.get(k) or "") for k in ("page", "semantic_name", "role", "name", "label",
                                           "placeholder", "test_id", "opens_new_tab")))
    return _h.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:16]


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _framework_version() -> str:
    """读 `tools/build_html.py` 的 VERSION（版本单一来源）；读不到就如实说 unknown，不编。"""
    try:
        import re
        src = config.VERSION_SOURCE.read_text(encoding="utf-8")
        m = re.search(r'^VERSION\s*=\s*"([^"]+)"', src, re.M)
        return m.group(1) if m else "unknown"
    except Exception:
        return "unknown"


def _first_diff_line(old: str, new: str) -> tuple[int, str, str, int]:
    """比较两份 prompt → (首个差异行号, 录像那行, 现在那行, 差异行总数)。

    为什么要"差异行总数"：选"最接近的一份"必须按**相似度**（差异行数）排序。
    2026-09-18 踩到：只按"首个差异行号"排，会挑中一份「第一行就不同、其余全同」的跨页录像
    （它的首行与单页模板天然不同），而真正同一场景的那份因首行相同、第 134 行才不同被排到后面。
    """
    a, b = old.splitlines(), new.splitlines()
    first, x0, y0, n = 0, "", "", 0
    for i in range(max(len(a), len(b))):
        x = a[i] if i < len(a) else "<无此行>"
        y = b[i] if i < len(b) else "<无此行>"
        if x != y:
            n += 1
            if first == 0:
                first, x0, y0 = i + 1, x, y
    return first, x0, y0, n


def render_miss_help(prompt: str, system: str, root: Path) -> str:
    """未命中时的诊断说明（人话）：目录里有多少份、最接近的那份第几行开始不同。

    为什么要做这件事：cassette 是**严格键**，控件清单/DOM 上下文变一点就不命中；
    不给出「差在哪」的话，用户只会看到「没有这一份」而完全不知道下一步该干嘛。
    """
    lines: list[str] = []
    files = sorted(root.glob("*.json")) if root.is_dir() else []
    if not files:
        lines.append(f"  · 目录 {root} 里**一份录像都没有** ⇒ 需要先在**有外网**的机器上录：")
        lines.append("      python -m framework.cli explore --ai --scenario-file <场景.yml> --llm-record")
        lines.append("    然后把整个目录拷到这台机器，再带 --llm-cassette 跑。")
        return "\n".join(lines)

    lines.append(f"  · 目录 {root} 里有 {len(files)} 份录像，但没有一份对应现在的 prompt（键不匹配）")
    best: tuple[int, int, str, str, str] | None = None   # (差异行数, 首个差异行, 文件名, 录像行, 现在行)
    for f in files:
        try:
            rec = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        old = rec.get("prompt") or ""
        n, x, y, nd = _first_diff_line(old, prompt)
        if n == 0:                                     # prompt 相同却没命中 ⇒ 文件坏了，另行提示
            lines.append(f"  · ⚠️ {f.name} 的 prompt 与现在**完全一致**却没命中 ⇒ 该文件可能损坏，删掉重录")
            continue
        if best is None or nd < best[0]:               # 按**差异行数**选最像的（不是首个差异行号）
            best = (nd, n, f.name, x, y)
    if best:
        nd, n, name, x, y = best
        lines.append(f"  · 最接近的是 {name}（{nd} 行不同），从第 {n} 行起不同：")
        lines.append(f"      录像：{x[:140]}")
        lines.append(f"      现在：{y[:140]}")
    lines.append("  · 说明：控件清单 / DOM 上下文 / 场景文案变一点就不会命中 —— 这是**刻意的**"
                 "（宁可报错，也不拿旧结论套新页面）。")
    lines.append("  · 下一步二选一：① 在用**同一个场景**的机器上加 `--llm-record` 重录一份"
                 "（命令形如 `explore --ai --scenario-file <场景.yml> --llm-record`）；"
                 "② 核对两台机器的 demo 页面与框架版本是否一致。")
    return "\n".join(lines)


class Cassette:
    """一份录像带目录。模式在构造时定死，运行中不改。"""

    def __init__(self, mode: str, root: str | Path | None = None):
        if mode not in (MODE_LIVE, MODE_RECORD, MODE_REPLAY):
            raise CassetteError(f"未知 cassette 模式 {mode!r}（只支持 {MODE_LIVE}/{MODE_RECORD}/{MODE_REPLAY}）")
        self.mode = mode
        self.root = Path(root).expanduser() if root else default_dir()
        self.hits = 0
        self.saves = 0
        self.last_key = ""          # 最近一次 lookup/store 的键（供 source_tag 写溯源）
        self.last_match = ""        # "strict" | "struct"：最近一次命中用的是哪种键
        if mode == MODE_REPLAY and not self.root.is_dir():
            raise CassetteError(
                f"离线回放目录不存在：{self.root}\n"
                f"  ⇒ 先在**有外网**的机器上跑 `explore --ai --llm-record` 录一份，再把整个目录拷过来；\n"
                f"     或者用 `--llm-cassette <目录>` 指定你拷贝到的位置。"
            )
        if mode == MODE_RECORD:
            self.root.mkdir(parents=True, exist_ok=True)

    # ---------------- 对外说明 ----------------

    @property
    def is_replay(self) -> bool:
        return self.mode == MODE_REPLAY

    @property
    def is_record(self) -> bool:
        return self.mode == MODE_RECORD

    def banner(self) -> str:
        """一行模式说明（CLI 打在最前面，让人一眼知道这次是不是真问 AI）。"""
        if self.mode == MODE_REPLAY:
            return (f"LLM 模式：**离线回放（非实时 AI）** ← 录像目录 {self.root}"
                    f"（命中即用；不联网、不需要 key）")
        if self.mode == MODE_RECORD:
            return f"LLM 模式：实时调用 + 录制 → {self.root}（录好后可分发到无外网的机器回放）"
        return "LLM 模式：实时调用（未使用录像）"

    def source_tag(self, key: str = "") -> str:
        """写进产物溯源字段的来源标记（不带 key 时用最近一次调用记下的键）。"""
        k = key or self.last_key
        if self.mode == MODE_REPLAY:
            return f"cassette:{k}" if k else "cassette"
        if self.mode == MODE_RECORD:
            return f"live+record:{k}" if k else "live+record"
        return "live"

    # ---------------- 存取 ----------------

    def file_for(self, key: str) -> Path:
        return self.root / f"{key}.json"

    def lookup(self, prompt: str, system: str = "", struct_key_value: str = "",
               strict_only: bool = False) -> dict | None:
        """回放：返回录好的记录（命中方式写在返回值的 `_match` 里）；没有返回 None。

        查找顺序：① **严格键**（prompt 逐字相同）→ 命中即用；② 给了 struct_key_value 且未禁用
        → 扫目录找**结构键**相同的录像（数据值不同但页面结构相同）。
        文件存在但读不动 / 里面没有可用回答 ⇒ 抛 CassetteError（**不能**把坏文件当成「未命中」：
        那会把一次数据损坏伪装成「只是没录过」）。
        """
        key = cassette_key(prompt, system)
        p = self.file_for(key)
        if p.is_file():
            try:
                rec = json.loads(p.read_text(encoding="utf-8"))
            except Exception as e:
                raise CassetteError(f"cassette 文件读不动（{p}）：{type(e).__name__}: {e}") from e
            resps = rec.get("responses")
            if not isinstance(resps, list) or not resps:
                raise CassetteError(f"cassette 文件里没有可用回答（{p}）—— 删掉它后重新录制")
            self.hits += 1
            self.last_key = key
            self.last_match = "strict"
            return dict(rec, _match="strict")

        if strict_only or not struct_key_value:
            return None
        for f in sorted(self.root.glob("*.json")):      # 扫描时跳过坏文件：一个坏文件不该毁掉整次回放
            try:
                rec = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            if rec.get("key_struct") == struct_key_value and rec.get("responses"):
                self.hits += 1
                self.last_key = rec.get("key") or key
                self.last_match = "struct"
                return dict(rec, _match="struct")
        return None

    def store(self, prompt: str, model: str, system: str, responses: list[dict],
              key_struct: str = "") -> Path | None:
        """录制：把这次拿到的回答落盘（同键按 kind 合并，重录覆盖旧的同类回答）。

        responses: [{"kind": "structured"|"text", "completion": <dict|str>}, ...]
        原子写（先写 .tmp 再 replace）—— 半截文件绝不能被后续回放当成命中。
        """
        responses = [r for r in (responses or []) if isinstance(r, dict) and r.get("kind") and r.get("completion") is not None]
        if not responses:
            return None
        key = cassette_key(prompt, system)
        p = self.file_for(key)
        merged: dict[str, dict] = {}
        if p.is_file():                                    # 保留上次录到的另一条路径的回答
            try:
                old = json.loads(p.read_text(encoding="utf-8"))
                for r in (old.get("responses") or []):
                    if isinstance(r, dict) and r.get("kind"):
                        merged[r["kind"]] = r
            except Exception:
                merged = {}
        for r in responses:
            merged[r["kind"]] = r
        rec: dict[str, Any] = {
            "key": key,
            "key_struct": key_struct or "",       # 结构键：数据值变了也能命中的兜底（见 struct_key）
            "framework_version": _framework_version(),
            "created_at": _now_iso(),
            "model": model,
            "system": system,
            "prompt_sha256": hashlib.sha256((prompt or "").encode("utf-8")).hexdigest(),
            "prompt": prompt,
            "responses": list(merged.values()),
        }
        self.root.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, p)
        self.saves += 1
        self.last_key = key
        return p
