"""`goto` 步骤 url 里 `{占位符}` 的**参数化**判据（2026-09-24 能力缺口修复）。

背景：多套数据场景常需要"同一场景、不同详情页地址"（`contracts_detail_multi` 就是）
     data:
       - {id: …, 详情地址: "…?no=HT-1005", 期望编号: "HT-1005", 期望客户: "…"}
用例的 goto 写成 `url: "{详情地址}"`。

修复前的三处缺口（缺一处都不成立）：
  ① `_extract_data` 不抽 `goto.url` ⇒ 数据组校验判「组值没被用到」⇒ **generate exit 2**（拦得对 ✓）
  ② `_add_payload_refs` 不给它打 `_payload_ref` ⇒ 无从参数化
  ③ 渲染器 `_goto(page, {url!r})` **原样塞** ⇒ 浏览器收到字面 `{详情地址}`（看着在跑、其实全错）

本判据同时守**向后兼容**：url 里没有 `{占位符}` 的 goto 一步都不许变（老产物逐字节一致）。
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from framework.tools.generate.generator import _add_payload_refs, _extract_data  # noqa: E402

PLACEHOLDER_URL = "http://localhost:8000/contract_detail.html?no={期望编号}"
LITERAL_URL = "http://localhost:8000/contract_detail.html?no=HT-1005"


def _case(url: str) -> dict:
    return {"case_id": "c", "base_url": "http://localhost:8000",
            "steps": [{"op": "goto", "desc": "打开合同详情页", "url": url}], "asserts": []}


def test_goto_url_with_placeholder_is_extracted_as_data():
    """① 抽离：url 含 {占位符} ⇒ 必须进数据字典（否则数据组校验会判"没用到的组值"）。"""
    data = _extract_data(_case(PLACEHOLDER_URL))
    assert any(PLACEHOLDER_URL == str(v) for v in data.values()), \
        f"goto.url 的占位符没被抽离 ⇒ 数据组校验必然拦下：{data}"


def test_goto_url_with_placeholder_gets_payload_ref():
    """② 打标记：有了 _payload_ref 才可能被参数化。"""
    step = _add_payload_refs(_case(PLACEHOLDER_URL))["steps"][0]
    assert step.get("_payload_ref"), "goto.url 没拿到 _payload_ref ⇒ 渲染时只能原样塞字面值"


def test_literal_goto_url_is_untouched():
    """③ 向后兼容：url 没有占位符 ⇒ 既不抽离也不打标记（老产物零变化）。"""
    assert "goto_0" not in _extract_data(_case(LITERAL_URL))
    assert "_payload_ref" not in _add_payload_refs(_case(LITERAL_URL))["steps"][0]
