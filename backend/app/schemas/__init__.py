"""
Pydantic Schemas for API validation (camelCase 지원)
"""

from .task import (
    TaskCreate, TaskUpdate, TaskResponse,
    TodoItem, Comment, ActivityLog,
)
from .knowledge import (
    KnowledgeCreate, KnowledgeUpdate,
    KnowledgeSearchRequest,
)
from .tool import (
    ToolCreate, ToolUpdate, ToolResponse,
    ToolTestRequest, ToolTestResponse,
)
from .node import (
    NodeCreate, NodeUpdate, NodeResponse,
    NodeTestRequest, NodeTestResponse,
    OutputEnforcementConfig, LLMConfig, KnowledgeConfig,
)
from .workflow import (
    WorkflowCreate, WorkflowUpdate, WorkflowResponse, WorkflowSummaryResponse,
    WorkflowNodeCreate, WorkflowNodeResponse,
    WorkflowConnectionCreate, WorkflowConnectionResponse,
    ExecutionCreate, ExecutionResponse, ExecutionLogEvent,
    TriggerConfig, ViewportConfig, Position,
)
from .common import PaginatedResponse, ErrorResponse

__all__ = [
    # Task
    'TaskCreate', 'TaskUpdate', 'TaskResponse',
    'TodoItem', 'Comment', 'ActivityLog',
    # Knowledge
    'KnowledgeCreate', 'KnowledgeUpdate',
    'KnowledgeSearchRequest',
    # Tool
    'ToolCreate', 'ToolUpdate', 'ToolResponse',
    'ToolTestRequest', 'ToolTestResponse',
    # Node
    'NodeCreate', 'NodeUpdate', 'NodeResponse',
    'NodeTestRequest', 'NodeTestResponse',
    'OutputEnforcementConfig', 'LLMConfig', 'KnowledgeConfig',
    # Workflow
    'WorkflowCreate', 'WorkflowUpdate', 'WorkflowResponse', 'WorkflowSummaryResponse',
    'WorkflowNodeCreate', 'WorkflowNodeResponse',
    'WorkflowConnectionCreate', 'WorkflowConnectionResponse',
    'ExecutionCreate', 'ExecutionResponse', 'ExecutionLogEvent',
    'TriggerConfig', 'ViewportConfig', 'Position',
    # Common
    'PaginatedResponse', 'ErrorResponse',
]
