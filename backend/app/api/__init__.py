"""
API Module
"""

from fastapi import APIRouter
from .routes import tasks, knowledge, tools, nodes, factory, chat, api_definitions, workflows

api_router = APIRouter()

api_router.include_router(tasks.router, prefix="/tasks", tags=["Tasks"])
api_router.include_router(knowledge.router, prefix="/knowledge", tags=["Knowledge"])
# tools 라우터는 하위 호환성을 위해 유지 (기능은 /api-definitions로 이전됨)
api_router.include_router(tools.router, prefix="/tools", tags=["Tools"])
api_router.include_router(nodes.router, prefix="/nodes", tags=["Nodes"])
api_router.include_router(workflows.router, prefix="/workflows", tags=["Workflows"])
api_router.include_router(factory.router, prefix="/factory", tags=["Factory"])
api_router.include_router(chat.router, prefix="/chat", tags=["Chat"])
api_router.include_router(api_definitions.router, prefix="/api-definitions", tags=["API Definitions"])
