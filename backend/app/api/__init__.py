"""
API Module
"""

from fastapi import APIRouter
from .routes import tasks, knowledge, tools, nodes, workflows, chat

api_router = APIRouter()

api_router.include_router(tasks.router, prefix="/tasks", tags=["Tasks"])
api_router.include_router(knowledge.router, prefix="/knowledge", tags=["Knowledge"])
api_router.include_router(tools.router, prefix="/tools", tags=["Tools"])
api_router.include_router(nodes.router, prefix="/nodes", tags=["Nodes"])
api_router.include_router(workflows.router, prefix="/workflows", tags=["Workflows"])
api_router.include_router(chat.router, prefix="/chat", tags=["Chat"])
