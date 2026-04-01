"""
Export / Import Routes

Per-entity export and import endpoints for:
- AI Nodes
- API Definitions
- Knowledge (file-based)
- Workflows (with bundled dependencies)
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
import uuid
import logging

from ...core.database import get_db
from ...models.node import AINode
from ...models.api_definition import ApiDefinition
from ...models.workflow import Workflow, WorkflowNode, WorkflowConnection
from ...services.knowledge_file_service import (
    list_md_files,
    read_md_file,
    write_md_file,
    generate_doc_id,
    KnowledgeFileDoc,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Serialization helpers ────────────────────────────────────────────────────

def _ai_node_to_export(node: AINode) -> dict:
    """AINode ORM -> export camelCase dict (no timestamps)"""
    return {
        "id": node.id,
        "name": node.name,
        "description": node.description,
        "category": node.category,
        "icon": node.icon,
        "color": node.color,
        "tags": node.tags,
        "systemPrompt": node.system_prompt,
        "userPromptTemplate": node.user_prompt_template,
        "inputSchema": node.input_schema,
        "outputSchema": node.output_schema,
        "outputEnforcement": node.output_enforcement,
        "llmConfig": node.llm_config,
        "isActive": node.is_active,
    }


def _api_def_to_export(api_def: ApiDefinition) -> dict:
    """ApiDefinition ORM -> export camelCase dict (no timestamps)"""
    return {
        "id": api_def.id,
        "name": api_def.name,
        "description": api_def.description,
        "icon": api_def.icon,
        "color": api_def.color,
        "category": api_def.category,
        "tags": api_def.tags or [],
        "method": api_def.method,
        "urlTemplate": api_def.url_template,
        "headers": api_def.headers or {},
        "bodyTemplate": api_def.body_template,
        "authType": api_def.auth_type,
        "authConfig": api_def.auth_config or {},
        "parameters": api_def.parameters or [],
        "responseSchema": api_def.response_schema or {},
        "isActive": api_def.is_active,
    }


def _knowledge_doc_to_export(doc: KnowledgeFileDoc) -> dict:
    """KnowledgeFileDoc -> export dict"""
    return {
        "id": doc.id,
        "title": doc.title,
        "content": doc.content,
        "category": doc.category,
        "tags": doc.tags,
        "source": doc.source,
    }


def _workflow_node_to_export(node: WorkflowNode) -> dict:
    """WorkflowNode ORM -> export camelCase dict"""
    return {
        "id": node.id,
        "nodeId": node.node_id,
        "definitionType": node.definition_type,
        "aiNodeId": node.ai_node_id,
        "config": node.config,
        "name": node.name,
        "position": node.position,
        "configOverrides": node.config_overrides,
        "inputMapping": node.input_mapping,
    }


def _workflow_conn_to_export(conn: WorkflowConnection) -> dict:
    """WorkflowConnection ORM -> export camelCase dict"""
    return {
        "id": conn.id,
        "sourceNodeId": conn.source_node_id,
        "targetNodeId": conn.target_node_id,
        "sourceHandle": conn.source_handle,
        "targetHandle": conn.target_handle,
        "condition": conn.condition,
    }


def _workflow_to_export(wf: Workflow) -> dict:
    """Workflow ORM -> export camelCase dict (no timestamps)"""
    return {
        "id": wf.id,
        "name": wf.name,
        "description": wf.description,
        "status": wf.status.value if wf.status else None,
        "tags": wf.tags,
        "viewport": wf.viewport,
        "trigger": wf.trigger,
        "variables": wf.variables,
        "nodes": [_workflow_node_to_export(n) for n in wf.nodes],
        "connections": [_workflow_conn_to_export(c) for c in wf.connections],
    }


# ── Dependency extraction helpers ────────────────────────────────────────────

def _collect_dependency_ids(wf: Workflow) -> dict:
    """
    Scan workflow nodes and extract referenced entity IDs.

    Returns:
        {
            "ai_node_ids": set[str],
            "api_def_ids": set[str],
            "knowledge_doc_ids": set[str],
        }
    """
    ai_node_ids: set[str] = set()
    api_def_ids: set[str] = set()
    knowledge_doc_ids: set[str] = set()

    for node in wf.nodes:
        # AI 노드 참조
        if node.definition_type == "ai-custom" and node.ai_node_id:
            ai_node_ids.add(node.ai_node_id)

        # config 기반 참조
        config = node.config or {}

        # API 정의 참조 (api-call 노드)
        api_def_id = config.get("apiDefinitionId")
        if api_def_id:
            api_def_ids.add(str(api_def_id))

        # 지식 문서 참조 (knowledge 노드)
        knowledge_ids = config.get("knowledgeDocIds") or config.get("knowledgeIds") or []
        if isinstance(knowledge_ids, list):
            for kid in knowledge_ids:
                if kid:
                    knowledge_doc_ids.add(str(kid))

    return {
        "ai_node_ids": ai_node_ids,
        "api_def_ids": api_def_ids,
        "knowledge_doc_ids": knowledge_doc_ids,
    }


async def _build_workflow_bundle(wf: Workflow, db: AsyncSession) -> dict:
    """Workflow + dependencies -> bundle dict"""
    dep_ids = _collect_dependency_ids(wf)

    # AI 노드 조회
    ai_nodes: List[dict] = []
    if dep_ids["ai_node_ids"]:
        result = await db.execute(
            select(AINode).where(AINode.id.in_(dep_ids["ai_node_ids"]))
        )
        ai_nodes = [_ai_node_to_export(n) for n in result.scalars().all()]

    # API 정의 조회
    api_defs: List[dict] = []
    if dep_ids["api_def_ids"]:
        result = await db.execute(
            select(ApiDefinition).where(ApiDefinition.id.in_(dep_ids["api_def_ids"]))
        )
        api_defs = [_api_def_to_export(d) for d in result.scalars().all()]

    # 지식 문서 조회 (파일 기반)
    knowledge_docs: List[dict] = []
    for doc_id in dep_ids["knowledge_doc_ids"]:
        doc = read_md_file(doc_id)
        if doc:
            knowledge_docs.append(_knowledge_doc_to_export(doc))

    return {
        "workflow": _workflow_to_export(wf),
        "dependencies": {
            "aiNodes": ai_nodes,
            "apiDefinitions": api_defs,
            "knowledgeDocs": knowledge_docs,
        },
    }


# ── Export: AI Nodes ─────────────────────────────────────────────────────────

@router.get("/export/nodes")
async def export_nodes(db: AsyncSession = Depends(get_db)):
    """모든 AI 노드 JSON 배열로 내보내기"""
    result = await db.execute(select(AINode))
    nodes = result.scalars().all()
    return [_ai_node_to_export(n) for n in nodes]


# ── Import: AI Nodes ─────────────────────────────────────────────────────────

@router.post("/import/nodes")
async def import_nodes(
    items: List[Dict[str, Any]] = Body(...),
    db: AsyncSession = Depends(get_db),
):
    """AI 노드 가져오기 (upsert by id)"""
    created = updated = skipped = 0

    for item in items:
        node_id = item.get("id")
        if not node_id:
            skipped += 1
            continue

        existing = await db.get(AINode, node_id)
        try:
            if existing:
                # Update
                existing.name = item.get("name", existing.name)
                existing.description = item.get("description", existing.description)
                existing.category = item.get("category", existing.category)
                existing.icon = item.get("icon", existing.icon)
                existing.color = item.get("color", existing.color)
                existing.tags = item.get("tags", existing.tags)
                existing.system_prompt = item.get("systemPrompt", existing.system_prompt)
                existing.user_prompt_template = item.get("userPromptTemplate", existing.user_prompt_template)
                existing.input_schema = item.get("inputSchema", existing.input_schema)
                existing.output_schema = item.get("outputSchema", existing.output_schema)
                existing.output_enforcement = item.get("outputEnforcement", existing.output_enforcement)
                existing.llm_config = item.get("llmConfig", existing.llm_config)
                existing.is_active = item.get("isActive", existing.is_active)
                updated += 1
            else:
                new_node = AINode(
                    id=node_id,
                    name=item.get("name", ""),
                    description=item.get("description", ""),
                    category=item.get("category", "general"),
                    icon=item.get("icon", "🤖"),
                    color=item.get("color", "text-blue-400"),
                    tags=item.get("tags", []),
                    system_prompt=item.get("systemPrompt", ""),
                    user_prompt_template=item.get("userPromptTemplate", ""),
                    input_schema=item.get("inputSchema", {"type": "object", "properties": {}, "required": []}),
                    output_schema=item.get("outputSchema", {"type": "object", "properties": {}, "required": []}),
                    output_enforcement=item.get("outputEnforcement", {}),
                    llm_config=item.get("llmConfig", {}),
                    is_active=item.get("isActive", True),
                )
                db.add(new_node)
                created += 1
        except Exception as e:
            logger.warning(f"AI 노드 가져오기 실패 id={node_id}: {e}")
            skipped += 1

    await db.commit()
    return {"created": created, "updated": updated, "skipped": skipped}


# ── Export: API Definitions ──────────────────────────────────────────────────

@router.get("/export/api-definitions")
async def export_api_definitions(db: AsyncSession = Depends(get_db)):
    """모든 API 정의 JSON 배열로 내보내기"""
    result = await db.execute(select(ApiDefinition))
    defs = result.scalars().all()
    return [_api_def_to_export(d) for d in defs]


# ── Import: API Definitions ──────────────────────────────────────────────────

@router.post("/import/api-definitions")
async def import_api_definitions(
    items: List[Dict[str, Any]] = Body(...),
    db: AsyncSession = Depends(get_db),
):
    """API 정의 가져오기 (upsert by id)"""
    created = updated = skipped = 0

    for item in items:
        def_id = item.get("id")
        if not def_id:
            skipped += 1
            continue

        existing = await db.get(ApiDefinition, def_id)
        try:
            if existing:
                existing.name = item.get("name", existing.name)
                existing.description = item.get("description", existing.description)
                existing.icon = item.get("icon", existing.icon)
                existing.color = item.get("color", existing.color)
                existing.category = item.get("category", existing.category)
                existing.tags = item.get("tags", existing.tags)
                existing.method = item.get("method", existing.method)
                existing.url_template = item.get("urlTemplate", existing.url_template)
                existing.headers = item.get("headers", existing.headers)
                existing.body_template = item.get("bodyTemplate", existing.body_template)
                existing.auth_type = item.get("authType", existing.auth_type)
                existing.auth_config = item.get("authConfig", existing.auth_config)
                existing.parameters = item.get("parameters", existing.parameters)
                existing.response_schema = item.get("responseSchema", existing.response_schema)
                existing.is_active = item.get("isActive", existing.is_active)
                updated += 1
            else:
                new_def = ApiDefinition(
                    id=def_id,
                    name=item.get("name", ""),
                    description=item.get("description", ""),
                    icon=item.get("icon", "🌐"),
                    color=item.get("color", "text-cyan-400"),
                    category=item.get("category", ""),
                    tags=item.get("tags", []),
                    method=item.get("method", "GET"),
                    url_template=item.get("urlTemplate", ""),
                    headers=item.get("headers", {}),
                    body_template=item.get("bodyTemplate"),
                    auth_type=item.get("authType", "none"),
                    auth_config=item.get("authConfig", {}),
                    parameters=item.get("parameters", []),
                    response_schema=item.get("responseSchema", {}),
                    is_active=item.get("isActive", True),
                )
                db.add(new_def)
                created += 1
        except Exception as e:
            logger.warning(f"API 정의 가져오기 실패 id={def_id}: {e}")
            skipped += 1

    await db.commit()
    return {"created": created, "updated": updated, "skipped": skipped}


# ── Export: Knowledge ────────────────────────────────────────────────────────

@router.get("/export/knowledge")
async def export_knowledge():
    """모든 지식 문서 JSON 배열로 내보내기"""
    docs = list_md_files()
    return [_knowledge_doc_to_export(d) for d in docs]


# ── Import: Knowledge ────────────────────────────────────────────────────────

@router.post("/import/knowledge")
async def import_knowledge(items: List[Dict[str, Any]] = Body(...)):
    """지식 문서 가져오기 (write_md_file upsert)"""
    created = updated = skipped = 0

    for item in items:
        doc_id = item.get("id")
        title = item.get("title", "")
        content = item.get("content", "")

        if not doc_id or not title:
            skipped += 1
            continue

        try:
            existing = read_md_file(doc_id)
            is_update = existing is not None

            write_md_file(
                doc_id=doc_id,
                title=title,
                content=content,
                category=item.get("category", ""),
                tags=item.get("tags", []),
                source=item.get("source", ""),
                created=existing.created if is_update else None,
            )

            if is_update:
                updated += 1
            else:
                created += 1
        except Exception as e:
            logger.warning(f"지식 문서 가져오기 실패 id={doc_id}: {e}")
            skipped += 1

    return {"created": created, "updated": updated, "skipped": skipped}


# ── Export: Single Workflow ──────────────────────────────────────────────────

@router.get("/export/workflows/{workflow_id}")
async def export_workflow(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
):
    """단일 워크플로우 내보내기 (의존성 포함)"""
    result = await db.execute(
        select(Workflow)
        .where(Workflow.id == workflow_id)
        .options(
            selectinload(Workflow.nodes),
            selectinload(Workflow.connections),
        )
    )
    wf = result.scalar_one_or_none()
    if not wf:
        raise HTTPException(status_code=404, detail="워크플로우를 찾을 수 없습니다")

    return await _build_workflow_bundle(wf, db)


# ── Export: All Workflows ────────────────────────────────────────────────────

@router.get("/export/workflows")
async def export_all_workflows(db: AsyncSession = Depends(get_db)):
    """모든 워크플로우 내보내기 (각각 의존성 포함)"""
    result = await db.execute(
        select(Workflow).options(
            selectinload(Workflow.nodes),
            selectinload(Workflow.connections),
        )
    )
    workflows = result.scalars().all()

    bundles = []
    for wf in workflows:
        bundle = await _build_workflow_bundle(wf, db)
        bundles.append(bundle)

    return bundles


# ── Import: Workflows ────────────────────────────────────────────────────────

@router.post("/import/workflows")
async def import_workflows(
    bundles: List[Dict[str, Any]] = Body(...),
    db: AsyncSession = Depends(get_db),
):
    """
    워크플로우 번들 가져오기.

    각 번들 형식:
    {
      "workflow": { ...workflow data },
      "dependencies": {
        "aiNodes": [...],
        "apiDefinitions": [...],
        "knowledgeDocs": [...]
      }
    }

    순서: 의존성 먼저 upsert -> 워크플로우 upsert
    """
    total_created = total_updated = total_skipped = 0

    for bundle in bundles:
        deps = bundle.get("dependencies", {})
        wf_data = bundle.get("workflow")
        if not wf_data:
            total_skipped += 1
            continue

        # 1. AI 노드 upsert
        for node_item in deps.get("aiNodes", []):
            node_id = node_item.get("id")
            if not node_id:
                continue
            existing = await db.get(AINode, node_id)
            try:
                if existing:
                    existing.name = node_item.get("name", existing.name)
                    existing.description = node_item.get("description", existing.description)
                    existing.category = node_item.get("category", existing.category)
                    existing.icon = node_item.get("icon", existing.icon)
                    existing.color = node_item.get("color", existing.color)
                    existing.tags = node_item.get("tags", existing.tags)
                    existing.system_prompt = node_item.get("systemPrompt", existing.system_prompt)
                    existing.user_prompt_template = node_item.get("userPromptTemplate", existing.user_prompt_template)
                    existing.input_schema = node_item.get("inputSchema", existing.input_schema)
                    existing.output_schema = node_item.get("outputSchema", existing.output_schema)
                    existing.output_enforcement = node_item.get("outputEnforcement", existing.output_enforcement)
                    existing.llm_config = node_item.get("llmConfig", existing.llm_config)
                    existing.is_active = node_item.get("isActive", existing.is_active)
                else:
                    db.add(AINode(
                        id=node_id,
                        name=node_item.get("name", ""),
                        description=node_item.get("description", ""),
                        category=node_item.get("category", "general"),
                        icon=node_item.get("icon", "🤖"),
                        color=node_item.get("color", "text-blue-400"),
                        tags=node_item.get("tags", []),
                        system_prompt=node_item.get("systemPrompt", ""),
                        user_prompt_template=node_item.get("userPromptTemplate", ""),
                        input_schema=node_item.get("inputSchema", {"type": "object", "properties": {}, "required": []}),
                        output_schema=node_item.get("outputSchema", {"type": "object", "properties": {}, "required": []}),
                        output_enforcement=node_item.get("outputEnforcement", {}),
                        llm_config=node_item.get("llmConfig", {}),
                        is_active=node_item.get("isActive", True),
                    ))
            except Exception as e:
                logger.warning(f"워크플로우 번들 - AI 노드 upsert 실패 id={node_id}: {e}")

        # 2. API 정의 upsert
        for def_item in deps.get("apiDefinitions", []):
            def_id = def_item.get("id")
            if not def_id:
                continue
            existing = await db.get(ApiDefinition, def_id)
            try:
                if existing:
                    existing.name = def_item.get("name", existing.name)
                    existing.description = def_item.get("description", existing.description)
                    existing.icon = def_item.get("icon", existing.icon)
                    existing.color = def_item.get("color", existing.color)
                    existing.category = def_item.get("category", existing.category)
                    existing.tags = def_item.get("tags", existing.tags)
                    existing.method = def_item.get("method", existing.method)
                    existing.url_template = def_item.get("urlTemplate", existing.url_template)
                    existing.headers = def_item.get("headers", existing.headers)
                    existing.body_template = def_item.get("bodyTemplate", existing.body_template)
                    existing.auth_type = def_item.get("authType", existing.auth_type)
                    existing.auth_config = def_item.get("authConfig", existing.auth_config)
                    existing.parameters = def_item.get("parameters", existing.parameters)
                    existing.response_schema = def_item.get("responseSchema", existing.response_schema)
                    existing.is_active = def_item.get("isActive", existing.is_active)
                else:
                    db.add(ApiDefinition(
                        id=def_id,
                        name=def_item.get("name", ""),
                        description=def_item.get("description", ""),
                        icon=def_item.get("icon", "🌐"),
                        color=def_item.get("color", "text-cyan-400"),
                        category=def_item.get("category", ""),
                        tags=def_item.get("tags", []),
                        method=def_item.get("method", "GET"),
                        url_template=def_item.get("urlTemplate", ""),
                        headers=def_item.get("headers", {}),
                        body_template=def_item.get("bodyTemplate"),
                        auth_type=def_item.get("authType", "none"),
                        auth_config=def_item.get("authConfig", {}),
                        parameters=def_item.get("parameters", []),
                        response_schema=def_item.get("responseSchema", {}),
                        is_active=def_item.get("isActive", True),
                    ))
            except Exception as e:
                logger.warning(f"워크플로우 번들 - API 정의 upsert 실패 id={def_id}: {e}")

        # 3. 지식 문서 upsert (파일 기반)
        for doc_item in deps.get("knowledgeDocs", []):
            doc_id = doc_item.get("id")
            doc_title = doc_item.get("title", "")
            if not doc_id or not doc_title:
                continue
            try:
                existing_doc = read_md_file(doc_id)
                write_md_file(
                    doc_id=doc_id,
                    title=doc_title,
                    content=doc_item.get("content", ""),
                    category=doc_item.get("category", ""),
                    tags=doc_item.get("tags", []),
                    source=doc_item.get("source", ""),
                    created=existing_doc.created if existing_doc else None,
                )
            except Exception as e:
                logger.warning(f"워크플로우 번들 - 지식 문서 upsert 실패 id={doc_id}: {e}")

        # 4. 워크플로우 upsert
        wf_id = wf_data.get("id")
        if not wf_id:
            total_skipped += 1
            continue

        try:
            # Flush dependencies first so FK constraints are satisfied
            await db.flush()

            existing_wf = await db.get(Workflow, wf_id)
            if existing_wf:
                # Update workflow metadata
                existing_wf.name = wf_data.get("name", existing_wf.name)
                existing_wf.description = wf_data.get("description", existing_wf.description)
                existing_wf.tags = wf_data.get("tags", existing_wf.tags)
                existing_wf.viewport = wf_data.get("viewport", existing_wf.viewport)
                existing_wf.trigger = wf_data.get("trigger", existing_wf.trigger)
                existing_wf.variables = wf_data.get("variables", existing_wf.variables)

                # Remove old nodes and connections (cascade handles it via delete-orphan)
                for node in list(existing_wf.nodes):
                    await db.delete(node)
                for conn in list(existing_wf.connections):
                    await db.delete(conn)
                await db.flush()

                total_updated += 1
            else:
                from ...models.workflow import WorkflowStatus
                status_val = wf_data.get("status", "draft")
                try:
                    status = WorkflowStatus(status_val)
                except ValueError:
                    status = WorkflowStatus.DRAFT

                existing_wf = Workflow(
                    id=wf_id,
                    name=wf_data.get("name", ""),
                    description=wf_data.get("description"),
                    status=status,
                    tags=wf_data.get("tags", []),
                    viewport=wf_data.get("viewport", {"x": 0, "y": 0, "zoom": 1}),
                    trigger=wf_data.get("trigger", {"type": "manual", "config": {}}),
                    variables=wf_data.get("variables", {}),
                )
                db.add(existing_wf)
                await db.flush()
                total_created += 1

            # Re-create nodes
            for node_data in wf_data.get("nodes", []):
                node_instance_id = node_data.get("id") or str(uuid.uuid4())
                wf_node = WorkflowNode(
                    id=node_instance_id,
                    workflow_id=wf_id,
                    node_id=node_data.get("nodeId", ""),
                    definition_type=node_data.get("definitionType", "ai-custom"),
                    ai_node_id=node_data.get("aiNodeId"),
                    config=node_data.get("config", {}),
                    name=node_data.get("name", ""),
                    position=node_data.get("position", {"x": 0, "y": 0}),
                    config_overrides=node_data.get("configOverrides", {}),
                    input_mapping=node_data.get("inputMapping", {}),
                )
                db.add(wf_node)

            # Re-create connections
            for conn_data in wf_data.get("connections", []):
                conn_id = conn_data.get("id") or str(uuid.uuid4())
                wf_conn = WorkflowConnection(
                    id=conn_id,
                    workflow_id=wf_id,
                    source_node_id=conn_data.get("sourceNodeId", ""),
                    target_node_id=conn_data.get("targetNodeId", ""),
                    source_handle=conn_data.get("sourceHandle"),
                    target_handle=conn_data.get("targetHandle"),
                    condition=conn_data.get("condition"),
                )
                db.add(wf_conn)

        except Exception as e:
            logger.error(f"워크플로우 upsert 실패 id={wf_id}: {e}")
            total_skipped += 1
            continue

    await db.commit()
    return {
        "created": total_created,
        "updated": total_updated,
        "skipped": total_skipped,
    }
