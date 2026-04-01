"""노드 핸들러 기본 인터페이스"""
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class ExecutionContext:
    """노드 실행 컨텍스트 — 핸들러가 필요로 하는 외부 의존성을 전달"""
    db: AsyncSession
    execution_id: str
    node_id: str
    # 유틸리티 함수 참조 (workflow_engine에서 주입)
    get_nested_value: Any = None  # (data, path) -> Any
    render_template: Any = None   # (template, data) -> str


class NodeHandler(ABC):
    """모든 노드 핸들러의 기본 인터페이스 (n8n의 INodeType에 해당)"""

    # 서브클래스가 반드시 정의해야 할 메타데이터
    node_type: str = ""                # "sorter", "ai-custom" 등 (NodeDefType 값)
    category: str = ""                 # "trigger", "ai", "logic", "transform", "action", "output"
    display_name: str = ""             # "분류기"
    description: str = ""              # 설명

    @abstractmethod
    async def execute(
        self,
        node: Any,           # WorkflowNode 모델
        input_data: Dict[str, Any],
        ctx: ExecutionContext,
    ) -> Any:
        """노드 실행 로직. 출력 dict를 반환."""
        ...
