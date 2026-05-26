"""
路由聚合模块：当前阶段仍依赖 legacy `my_web_service`。
后续可逐步将具体路由拆分成独立模块并在此集中注册。
"""
from fastapi import FastAPI
from my_web_service import app as legacy_app

from app.routers.static import register_static
from app.services.connection_manager import ConnectionManager


def register_routes(app: FastAPI, connection_manager: ConnectionManager) -> None:
    """
    注册静态资源后，再挂载 legacy 应用，并共享 ConnectionManager。
    """
    register_static(app)
    legacy_app.state.connection_manager = connection_manager
    app.mount("/", legacy_app)


