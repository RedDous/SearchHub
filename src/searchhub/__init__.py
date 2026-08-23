__version__ = "0.1.0"

import os


def build_info() -> dict:
    """版本与构建信息（commit 由 Dockerfile/CI 经 SEARCHHUB_COMMIT 注入）。"""
    return {
        "version": __version__,
        "commit": os.environ.get("SEARCHHUB_COMMIT") or "dev",
    }
