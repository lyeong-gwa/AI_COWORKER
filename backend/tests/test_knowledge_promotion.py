"""Phase 2b — ``POST /api/v1/knowledge/from-instance`` 지식 프로모션 검증.

검증 포인트:
1. 존재하지 않는 instanceId → 404 NOT_FOUND (envelope)
2. 정상 인스턴스 → 지식문서 생성, source='instance:{id}', 제목·태그·카테고리 반영
3. 동일 title 재호출 → 409 CONFLICT (envelope)
4. 생성된 문서의 ``content`` 에 인스턴스 메타(outputData, nodeResults) 가 포함
5. 생성된 문서가 ``GET /knowledge/{doc_id}`` 로 조회됨
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.core.database import async_session_maker
from app.models.workflow import (
    ExecutionStatus,
    WarehouseEntry,
    Workflow,
    WorkflowExecution,
    WorkflowStatus,
)


client = TestClient(app, raise_server_exceptions=False)


# ── DB 헬퍼 ────────────────────────────────────────────────────────────────


async def _async_setup_instance() -> tuple[str, str]:
    """테스트용 workflow + execution + warehouse entry 를 DB 에 직접 삽입."""
    wf_id = f"wf-promo-{uuid.uuid4().hex[:6]}"
    ex_id = f"exec-promo-{uuid.uuid4().hex[:6]}"
    now = datetime.utcnow()
    async with async_session_maker() as db:
        wf = Workflow(
            id=wf_id,
            name=f"promotion test {wf_id}",
            description="test_knowledge_promotion.py",
            status=WorkflowStatus.ACTIVE,
            tags=[],
            trigger={"type": "manual", "config": {}},
            variables={},
            created_by="test",
        )
        db.add(wf)

        execution = WorkflowExecution(
            id=ex_id,
            workflow_id=wf_id,
            status=ExecutionStatus.COMPLETED,
            input_data={"foo": "bar"},
            output_data={"summary": "테스트 결과 요약"},
            node_results={
                "node-a": {
                    "status": "completed",
                    "outputData": {"answer": 42},
                }
            },
            error_message=None,
            error_node_id=None,
            started_at=now,
            completed_at=now,
        )
        db.add(execution)

        entry = WarehouseEntry(
            id=f"wh-{uuid.uuid4().hex[:6]}",
            node_instance_id="node-a",
            execution_id=ex_id,
            data={"content": "인스턴스 창고 적재 데이터"},
            dedup_key=None,
        )
        db.add(entry)

        await db.commit()
    return wf_id, ex_id


async def _async_cleanup_instance(wf_id: str, ex_id: str) -> None:
    async with async_session_maker() as db:
        # warehouse entries
        entries = (
            (
                await db.execute(
                    select(WarehouseEntry).where(WarehouseEntry.execution_id == ex_id)
                )
            )
            .scalars()
            .all()
        )
        for e in entries:
            await db.delete(e)
        # execution
        ex = (
            await db.execute(
                select(WorkflowExecution).where(WorkflowExecution.id == ex_id)
            )
        ).scalar_one_or_none()
        if ex is not None:
            await db.delete(ex)
        # workflow
        wf = (
            await db.execute(select(Workflow).where(Workflow.id == wf_id))
        ).scalar_one_or_none()
        if wf is not None:
            await db.delete(wf)
        await db.commit()


def _setup_instance() -> tuple[str, str]:
    return asyncio.run(_async_setup_instance())


def _cleanup_instance(wf_id: str, ex_id: str) -> None:
    asyncio.run(_async_cleanup_instance(wf_id, ex_id))


# 테스트 후 도구 문서 정리용
def _delete_knowledge_file_if_exists(title: str) -> None:
    import re
    from app.services.knowledge_file_service import _knowledge_dir

    sanitized = re.sub(r"[^가-힣a-zA-Z0-9\s-]", "", title)
    sanitized = re.sub(r"\s+", "-", sanitized.strip())
    sanitized = sanitized.lower() if sanitized.isascii() else sanitized
    for suffix in ("", "-1", "-2"):
        path = os.path.join(_knowledge_dir(), f"{sanitized}{suffix}.md")
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass


# ── 테스트 케이스 ──────────────────────────────────────────────────────────


def test_promote_missing_instance_returns_404_envelope():
    r = client.post(
        "/api/v1/knowledge/from-instance",
        json={
            "instanceId": "___no_instance___",
            "title": "Promotion-missing-test",
            "category": "test",
            "tags": [],
        },
    )
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["error"]["details"].get("instanceId") == "___no_instance___"


def test_promote_instance_creates_knowledge_document():
    wf_id, ex_id = _setup_instance()
    unique_title = f"Promo-Test-{uuid.uuid4().hex[:8]}"
    created_doc_id: str | None = None
    try:
        r = client.post(
            "/api/v1/knowledge/from-instance",
            json={
                "instanceId": ex_id,
                "title": unique_title,
                "category": "자동화결과",
                "tags": ["promotion", "auto"],
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        created_doc_id = body.get("id")
        assert body["title"] == unique_title
        assert body["category"] == "자동화결과"
        assert set(body["tags"]) == {"promotion", "auto"}
        assert body["source"] == f"instance:{ex_id}"
        # content 안에 인스턴스 메타가 포함되어야 한다
        assert ex_id in body["content"]
        assert "outputData" in body["content"] or "최종 출력" in body["content"]
        assert "nodeResults" in body["content"] or "노드별 결과" in body["content"]

        # 저장된 문서가 조회되어야 한다
        r2 = client.get(f"/api/v1/knowledge/{body['id']}")
        assert r2.status_code == 200
        fetched = r2.json()
        assert fetched["title"] == unique_title
        assert fetched["source"] == f"instance:{ex_id}"
    finally:
        # DELETE API 사용 — 파일 + ChromaDB 동시 정리
        if created_doc_id:
            try:
                client.delete(f"/api/v1/knowledge/{created_doc_id}")
            except Exception:
                pass
        _cleanup_instance(wf_id, ex_id)


def test_promote_duplicate_title_returns_conflict():
    wf_id, ex_id = _setup_instance()
    unique_title = f"Promo-Dup-{uuid.uuid4().hex[:8]}"
    created_doc_id: str | None = None
    try:
        r = client.post(
            "/api/v1/knowledge/from-instance",
            json={
                "instanceId": ex_id,
                "title": unique_title,
                "category": "",
                "tags": [],
            },
        )
        assert r.status_code == 201, r.text
        created_doc_id = r.json().get("id")

        # 동일 title 재호출 → 409
        r2 = client.post(
            "/api/v1/knowledge/from-instance",
            json={
                "instanceId": ex_id,
                "title": unique_title,
                "category": "",
                "tags": [],
            },
        )
        assert r2.status_code == 409, r2.text
        body = r2.json()
        assert body["error"]["code"] == "CONFLICT"
        assert body["error"]["details"].get("title") == unique_title
    finally:
        # DELETE API 사용 — 파일 + ChromaDB 동시 정리
        if created_doc_id:
            try:
                client.delete(f"/api/v1/knowledge/{created_doc_id}")
            except Exception:
                pass
        _cleanup_instance(wf_id, ex_id)


def test_promote_rejects_blank_title():
    wf_id, ex_id = _setup_instance()
    try:
        r = client.post(
            "/api/v1/knowledge/from-instance",
            json={
                "instanceId": ex_id,
                "title": "   ",  # 공백만
                "category": "",
                "tags": [],
            },
        )
        # 먼저 pydantic min_length=1 검증을 통과한 뒤 domain VALIDATION_ERROR
        # 로 진입. pydantic 레벨에서 잘려도 envelope 는 VALIDATION_ERROR
        assert r.status_code in (400, 422)
        body = r.json()
        assert body["error"]["code"] == "VALIDATION_ERROR"
    finally:
        _cleanup_instance(wf_id, ex_id)
