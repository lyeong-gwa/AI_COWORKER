"""
Pydantic Schemas for API validation (camelCase 지원)
"""

from .knowledge import (
    KnowledgeCreate, KnowledgeUpdate,
    KnowledgeSearchRequest,
)
from .tool import (
    ApiDocExecuteRequest, ToolTestResponse,
)
from .node import (
    NodeCreate, NodeUpdate, NodeResponse,
    NodeTestRequest, NodeTestResponse,
    OutputEnforcementConfig, LLMConfig,
)
from .workflow import (
    WorkflowCreate, WorkflowUpdate, WorkflowResponse, WorkflowSummaryResponse,
    WorkflowNodeCreate, WorkflowNodeResponse,
    WorkflowConnectionCreate, WorkflowConnectionResponse,
    ExecutionCreate, ExecutionResponse, ExecutionLogEvent,
    TriggerConfig,
)
from .common import PaginatedResponse, ErrorResponse
from .api_definition import (
    ApiParamSchema,
    ResponseFieldSchema,
    ApiDefinitionCreate,
    ApiDefinitionUpdate,
    ApiTestRequest,
    ApiCaptureRequest,
)
from .instance_db import (
    InstanceDBCreate,
    InstanceDBUpdate,
    InstanceDBResponse,
    InstanceDBRecordResponse,
    RecordListResponse,
)

__all__ = [
    # Knowledge
    'KnowledgeCreate', 'KnowledgeUpdate',
    'KnowledgeSearchRequest',
    # Tool (API doc execution)
    'ApiDocExecuteRequest', 'ToolTestResponse',
    # Node
    'NodeCreate', 'NodeUpdate', 'NodeResponse',
    'NodeTestRequest', 'NodeTestResponse',
    'OutputEnforcementConfig', 'LLMConfig',
    # Workflow
    'WorkflowCreate', 'WorkflowUpdate', 'WorkflowResponse', 'WorkflowSummaryResponse',
    'WorkflowNodeCreate', 'WorkflowNodeResponse',
    'WorkflowConnectionCreate', 'WorkflowConnectionResponse',
    'ExecutionCreate', 'ExecutionResponse', 'ExecutionLogEvent',
    'TriggerConfig',
    # Common
    'PaginatedResponse', 'ErrorResponse',
    # ApiDefinition
    'ApiParamSchema', 'ResponseFieldSchema',
    'ApiDefinitionCreate', 'ApiDefinitionUpdate',
    'ApiTestRequest', 'ApiCaptureRequest',
    # InstanceDB
    'InstanceDBCreate', 'InstanceDBUpdate', 'InstanceDBResponse',
    'InstanceDBRecordResponse', 'RecordListResponse',
]
