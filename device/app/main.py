"""
新的 FastAPI 入口。
当前通过挂载 legacy `my_web_service`，为后续路由拆分创造统一入口。
"""
from fastapi import FastAPI

from app.routers import register_routes
from app.services.connection_manager import ConnectionManager

connection_manager = ConnectionManager()


def create_app() -> FastAPI:
    app = FastAPI()
    app.state.connection_manager = connection_manager
    register_routes(app, connection_manager)
    return app


app = create_app()

