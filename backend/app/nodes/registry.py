"""노드 핸들러 레지스트리"""
from typing import Dict, List, Optional, Type
from .base import NodeHandler


class NodeHandlerRegistry:
    """노드 타입별 핸들러를 관리하는 레지스트리"""
    _handlers: Dict[str, NodeHandler] = {}

    @classmethod
    def register(cls, handler_class: Type[NodeHandler]) -> Type[NodeHandler]:
        """데코레이터로 사용 가능: @NodeHandlerRegistry.register"""
        instance = handler_class()
        if not instance.node_type:
            raise ValueError(f"{handler_class.__name__}에 node_type이 정의되지 않았습니다")
        cls._handlers[instance.node_type] = instance
        return handler_class

    @classmethod
    def get(cls, node_type: str) -> NodeHandler:
        handler = cls._handlers.get(node_type)
        if not handler:
            raise ValueError(f"알 수 없는 노드 타입: {node_type}")
        return handler

    @classmethod
    def has(cls, node_type: str) -> bool:
        return node_type in cls._handlers

    @classmethod
    def all_handlers(cls) -> Dict[str, NodeHandler]:
        return dict(cls._handlers)

    @classmethod
    def by_category(cls, category: str) -> List[NodeHandler]:
        return [h for h in cls._handlers.values() if h.category == category]
