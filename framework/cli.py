"""顶层入口**薄壳**（P25 片 8 目录重组后）。

真正实现在 `framework.features.f10_cli.cli`。

为什么保留这个文件：`python -m framework.cli <cmd>` 与 `from framework.cli import X`
都是**对外契约** —— 文档、脚本、判据（如 `CMD_FLAGS` / `FLAG_SPECS` / `_validate_args`）、
发布说明、用户肌肉记忆都认它。搬目录属于内部重构，不该把成本转嫁给所有调用方。

为什么用模块级 `__getattr__` 转发而不是逐个 `from ... import`：
  逐个列举 = 以后框架新增一个公开符号，调用方拿到的是 AttributeError，而薄壳"看不出来"。
  `__getattr__` 让**所有**名字（含 `_` 私有名，判据要用）自动透传，语义与搬迁前完全一致。
"""
from framework.features.f10_cli import cli as _cli


def __getattr__(name):
    """把任意属性转发给真正的实现模块（含私有名，判据依赖它们）。"""
    return getattr(_cli, name)


def __dir__():
    return sorted(set(globals()) | set(dir(_cli)))


def main():
    return _cli.main()


if __name__ == "__main__":
    main()
