"""
静态资源路由注册模块。
"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

RESOURCES_DIR = Path(__file__).resolve().parents[2] / "resources"


def register_static(app: FastAPI) -> None:
    """
    在新入口中挂载静态资源，确保 `/static` 仍指向原目录。
    """
    app.mount(
        "/static",
        StaticFiles(directory=str(RESOURCES_DIR)),
        name="static",
    )

