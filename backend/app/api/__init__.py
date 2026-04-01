"""
API Module
"""

from fastapi import APIRouter
from .routes import knowledge, nodes, factory, chat, api_definitions, workflows, export_import

api_router = APIRouter()

api_router.include_router(knowledge.router, prefix="/knowledge", tags=["Knowledge"])
api_router.include_router(nodes.router, prefix="/nodes", tags=["Nodes"])
api_router.include_router(workflows.router, prefix="/workflows", tags=["Workflows"])
api_router.include_router(factory.router, prefix="/factory", tags=["Factory"])
api_router.include_router(chat.router, prefix="/chat", tags=["Chat"])
api_router.include_router(api_definitions.router, prefix="/api-definitions", tags=["API Definitions"])
api_router.include_router(export_import.router, tags=["Export/Import"])
