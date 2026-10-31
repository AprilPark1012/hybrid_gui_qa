"""V8.7.19 判据：含凭据的 `.env` 绝不许进交付包 —— **非 git 目录下也必须成立**。

由来（2026-10-29 用户 Windows 实测 1 failed）：
  `test_collect_files_keeps_sources_and_drops_runtime_cruft` 报
      「包里有不该发的内容：['.env']」
  而他机器上正是**交付包解压目录（非 git）**，本地那份含 API key 的 `.env` 被 `collect_files()` 收进包。

根因（两层）：
  ① `Path(".env").suffix == ""` —— 隐藏文件**没有后缀**，所以它**落不进 `EXCLUDE_SUFFIX`**
     （`""` 不在 `{".zip",".tar.gz",".pyc",".pyo}` 里）；
  ② `collect_files()` 有两条分支：git 仓库走 `git ls-files --exclude-standard`（`.gitignore`
     帮它排除了 `.env`），**非 git 目录走 `rglob`**（什么都收）——
     于是「开发机绿、交付包解压后红」，正好撞在本项目「一类自测必须与 git / 非 git 无关」那条铁律上。

[!] 为什么原有判据没抓到：它在**本仓库（git）**里跑，走的是 `git ls-files` 分支，
    `.env` 被 `.gitignore` 排除 -> 永远看不见这个 bug。**必须在非 git 分支上测。**

守五件事：
  ① `.env` / `.env.*` / `*.env` 一律被判为凭据文件；
  ② `.env.example` / `.env.sample` / `.env.template` / `.env.dist` **必须放行**（模板要随包交付）；
  ③ 非 git 分支（`rglob`）下，仓库里真有一个 `.env` 时，`collect_files()` **不许**把它收进包；
  ④ git 分支下同样不许 —— 两条分支口径必须一致（防「只修半边」）；
  ⑤ 真实的打包产物里不许出现 `.env`（端到端）。
"""
from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("name", [".env", ".env.local", ".env.production", "a.env", ".ENV"])
def test_env_secret_names_are_rejected(name: str) -> None:
    """① 各种写法的凭据 env 都要被判为 secret（大小写不敏感）。"""
    from build_tools.pack_release import _is_env_secret

    assert _is_env_secret(name), f"{name!r} 没被判成凭据文件 —— 会被打进交付包"


@pytest.mark.parametrize("name", [".env.example", ".env.sample", ".env.template", ".env.dist",
                                  "README.md", "env.py", "environment.yml", ".gitignore"])
def test_template_and_normal_files_are_allowed(name: str) -> None:
    """② 示例文件必须放行（否则交付包没有模板可用）；普通文件不许误伤。"""
    from build_tools.pack_release import _is_env_secret

    assert not _is_env_secret(name), f"{name!r} 被误判成凭据文件 —— 模板/普通文件会被漏掉"


def test_collect_files_drops_env_in_non_git_branch(tmp_path, monkeypatch) -> None:
    """③ 非 git 目录（rglob 分支）下，`.env` 不许进包 —— 这就是用户机器上的真实场景。

    手法：把 REPO 指到一个临时目录（没有任何 `.git`，`git ls-files` 必然失败），
    在里面放一个 `.env` 和几个正常文件，然后调 `collect_files()`。

    [!] 必须同时 patch `CASSETTE_SRC` —— 它是**模块级常量**，指向真仓库的
        `output/llm_cassettes/`；只 patch `REPO` 的话，函数末尾那段
        `out.extend(CASSETTE_SRC.rglob(...))` 会把真路径塞进来，
        随后的 `p.relative_to(tmp_path)` 就抛 ValueError（第一版判据就栽在这里）。
    """
    from build_tools import pack_release as pr

    (tmp_path / ".env").write_text("LLM_API_KEY=sk-should-never-ship\n", encoding="utf-8")
    (tmp_path / ".env.example").write_text("LLM_API_KEY=\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# x\n", encoding="utf-8")

    monkeypatch.setattr(pr, "REPO", tmp_path, raising=False)
    monkeypatch.setattr(pr, "CASSETTE_SRC", tmp_path / "output" / "llm_cassettes", raising=False)
    got = {p.relative_to(tmp_path).as_posix() for p in pr.collect_files()}

    assert ".env" not in got, (
        "非 git 目录下 `.env` 被收进了交付包 —— 用户本地那份含 API key 的凭据会被原样发出去"
    )
    assert ".env.example" in got, "示例文件也被排除了 —— 交付包会缺模板"
    assert "README.md" in got, "正常文件被误排"


def test_env_name_filter_is_shared_by_both_branches() -> None:
    """④ 两条分支（git ls-files / rglob）必须共用同一道 env 过滤（防只修半边）。

    静态钉住：`_is_env_secret` 的调用点必须在**两个分支汇合后的公共过滤循环**里，
    而不是只在某一分支里 —— 否则换个环境又漏。
    """
    src = (REPO / "build_tools/pack_release.py").read_text(encoding="utf-8")
    i_loop = src.find("    out = []")
    assert i_loop > 0, "找不到两个分支汇合后的过滤循环"
    tail = src[i_loop : i_loop + 1200]
    assert "_is_env_secret(p.name)" in tail, (
        "公共过滤循环里没有 `_is_env_secret` —— 只可能在某个分支里加了，另一条分支仍会漏"
    )
    # 不许出现「在 git 分支里单独排 env」这种只修半边的写法
    i_git = src.find("git\", \"ls-files\"")
    if i_git > 0:
        seg = src[i_git : i_git + 400]
        assert "_is_env_secret" not in seg, (
            "env 过滤被塞进了 git 分支 —— 应放在两分支汇合后的公共循环里"
        )


def test_built_package_contains_no_env_secret() -> None:
    """⑤ 端到端：最近一次打出的包（若有）里不许有凭据 env 文件。"""
    import zipfile

    releases = REPO / "releases"
    if not releases.exists():
        pytest.skip("没有 releases/ 目录")
    zips = sorted(releases.glob("hybrid_gui_qa_V*.zip"))
    if not zips:
        pytest.skip("还没有打过包")
    with zipfile.ZipFile(zips[-1]) as zf:
        bad = []
        for n in zf.namelist():
            base = n.rsplit("/", 1)[-1]
            if base.lower() in (".env",) or base.lower().startswith(".env.local"):
                bad.append(n)
        assert not bad, f"{zips[-1].name} 里混进了凭据 env 文件：{bad}"
