# -*- coding: utf-8 -*-
"""explore 规划提示词的**体积度量**（用真实 LLM 录像，纯函数、不起浏览器、不联网）。

用途：量「提示词里哪一段占了多少篇幅」，以及同一份输入下改了组装逻辑前后的字符数。
做法：录像里存着当时**拼好的完整提示词**与**当时的 DOM 记录**；把语义清单条目从提示词里
解析回来，就能在纯函数级复现同一份输入 -> 数字可比，不需要浏览器、也不需要探测环境。

    ./.venv/bin/python build_tools/measure_explore_prompt.py [cassette.json]
"""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
CASS = ROOT / "output" / "llm_cassettes" / "c5315d9a22d27bd6.json"


def _blocks(prompt: str):
    """按页切出语义清单块 -> [(页名, 条目列表)]，并给出【额外 DOM 上下文】段的字符数。"""
    dec = json.JSONDecoder()
    out = []
    for m in re.finditer(r"\n【([^】]{1,40})】\s*(?=\[)", prompt):
        name = m.group(1)
        j = prompt.index("[", m.end() - 1)
        try:
            arr, _end = dec.raw_decode(prompt[j:])
        except Exception:
            continue
        if isinstance(arr, list) and arr and isinstance(arr[0], dict) and "semantic_name" in arr[0]:
            out.append((name, arr))
    dom = None
    if "额外 DOM 上下文" in prompt:
        i = prompt.index("额外 DOM 上下文")
        j = prompt.index("[", i)
        dom, end = dec.raw_decode(prompt[j:])
        dom_chars = end + j - i
    else:
        dom_chars = 0
    return out, dom, dom_chars


def main(cass_path=CASS):
    d = json.loads(pathlib.Path(cass_path).read_text(encoding="utf-8"))
    prompt = d["prompt"]
    blocks, dom_ctx, dom_chars = _blocks(prompt)
    print(f"真实提示词总字符: {len(prompt)}")
    print(f"语义清单块: {len(blocks)} 页 / {sum(len(b) for _n, b in blocks)} 条")
    for n, b in blocks:
        print(f"  · {n}: {len(b)} 条")
    print(f"DOM 记录: {len(dom_ctx or [])} 条；【额外 DOM 上下文】段 {dom_chars} 字符"
          f"（{round(dom_chars * 100 / len(prompt), 1)}%）")
    items = []
    for n, b in blocks:
        for it in b:
            it = dict(it)
            it.setdefault("page", n)
            it.setdefault("base_name", str(it.get("semantic_name") or "").split("@")[0])
            # [!] 运行时的 `name`/`text` 是**元素自己的可访问名**（不含 `@页名` 后缀，那是
            #   唯一化时才加的）；录像里只有最终语义名 -> 这里用去掉后缀的那段近似。
            it.setdefault("name", it["base_name"])
            it.setdefault("text", it["base_name"])
            # [!] 录像里只有**压缩后**的条目（没有 tag/element_id/name/text 这些原样字段）。
            #   这里按 role 反推一个 tag 只是为了能走一遍「弱键」匹配；真实运行时条目还带
            #   element_id/test_id/name/text（强键）-> 能配上的只会比这里**多**。
            _r = str(it.get("role") or "")
            it.setdefault("tag", {"button": "button", "textbox": "input", "link": "a",
                                  "combobox": "select", "checkbox": "input"}.get(_r, _r))
            items.append(it)
    scen = re.search(r"自然语言测试场景: 「(.*?)」", prompt, re.S)
    pages = [{"name": n, "url": "http://x"} for n, _b in blocks]
    from framework.features.f02_semantic import explorer_explore as EX
    built = EX._build_planner_prompt(scen.group(1) if scen else "场景", items,
                                     "http://127.0.0.1:8000/login.html", dom_ctx,
                                     pages=pages if len(pages) > 1 else None)
    print(f"本脚本重组后的提示词(未加 page_bg/guard/契约尾): {len(built)} 字符")
    out = {"items": items, "dom_ctx": dom_ctx, "scenario": scen.group(1) if scen else "场景",
           "pages": pages, "real_prompt_chars": len(prompt), "real_dump_chars": dom_chars}
    (ROOT / "output" / "c1_measure_input.json").write_text(
        json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return built


if __name__ == "__main__":
    p = _build = main(sys.argv[1] if len(sys.argv) > 1 else CASS)
    print("dump 段是否还在:", "额外 DOM 上下文" in p)
