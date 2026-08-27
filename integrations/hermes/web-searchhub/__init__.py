"""SearchHub hermes web backend plugin entry point.

Hermes 的目录插件要求插件目录下必须有 ``__init__.py`` 且包含
``register(ctx)``（加载器在 ``hermes_cli/plugins.py`` 中直接
``getattr(module, "register")`` 调用；缺失或为空文件会加载失败）。
"""

from .provider import SearchHubProvider, register  # noqa: F401