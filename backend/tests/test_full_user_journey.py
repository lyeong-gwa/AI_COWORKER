"""Phase 5a — 풀 E2E 사용자 여정 검증 (pytest 기반).

CLI 사용자가 빈 시스템에서 다음 순서로 업무를 수행하는 전체 흐름을 검증한다:

1.  GET  /nodes/catalog               — 11종 노드 파악
2.  POST /api-definitions             — 외부 API 명세 등록
3.  POST /knowledge                   — 지식문서 등록
4.  POST /nodes                       — 커스텀 AI 노드 등록
5.  POST /workflows                   — 워크플로우 생성 (form-start → result 최소 구성)
6.  PATCH /workflows/{id}             — status active 변경
7.  POST /workflows/{id}/run          — 백그라운드 실행 (202 + instanceId)
8.  polling                           — 실행 완료 대기 (최대 30초)
9.  GET  /warehouse/instances/{iid}   — status=completed 확인
10. GET  /workflows/{id}/instances    — 인스턴스 목록에 포함 확인
11. POST /knowledge/from-instance     — 지식 프로모션 성공
12. GET  /dashboard/summary           — counts 업데이트 확인

설계 원칙:
- TestClient(raise_server_exceptions=False) 사용 — 백그라운드 실행 예외가 호출자에게 전파 안 됨.
- 실제 DB 사용 (conftest.py 패턴 재활용).
- LLM 호출이 필요한 ai-custom 노드 대신 form-start → result 최소 구성 사용.
- 모든 고유 리소스에 uuid.uuid4().hex[:8] suffix 를 붙여 매 실행마다 idempotent.
- 테스트 완료 후 생성한 리소스를 DB에서 정리.

Note
----
TestClient 와 asyncio.run() 혼합 패턴 사용 (test_api_run.py 참조).
``@pytest.mark.asyncio`` 와 TestClient 동시 사용 금지 — nested event loop 충돌.
"""

from __future__ import annotations

import asyncio
import os
import re
import time
import uuid
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.core.database import async_session_maker
from app.models.workflow import (
    ExecutionStatus,
    Workflow,
    WorkflowExecution,
    WorkflowStatus,
)

# 백그라운드 실행 예외가 테스트에게 전파되지 않도록 False 설정.
client = TestClient(app, raise_server_exceptions=False)

# ── 상수 ────────────────────────────────────────────────────────────────────

EXECUTION_POLL_INTERVAL_S = 1.0   # 폴링 간격 (초)
EXECUTION_TIMEOUT_S = 30           # 최대 대기 시간 (초)
TERMINAL_STATUSES = {"completed", "failed", "cancelled"}


# ── 정리 헬퍼 ────────────────────────────────────────────────────────────────

async def _delete_workflow_by_id(wf_id: str) -> None:
    async with async_session_maker() as db:
        result = await db.execute(select(Workflow).where(Workflow.id == wf_id))
        wf = result.scalar_one_or_none()
        if wf is not None:
            await db.delete(wf)
            await db.commit()


def _delete_knowledge_file_if_exists(title: str) -> None:
    """생성된 지식문서 파일을 정리한다 (test_knowledge_promotion.py 패턴 재활용)."""
    try:
        from app.services.knowledge_file_service import _knowledge_dir
        sanitized = re.sub(r"[^가-힣a-zA-Z0-9\s-]", "", title)
        sanitized = re.sub(r"\s+", "-", sanitized.strip())
        for suffix in ("", "-1", "-2"):
            path = os.path.join(_knowledge_dir(), f"{sanitized}{suffix}.md")
            if os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass
    except Exception:
        pass


# ── 폴링 헬퍼 ────────────────────────────────────────────────────────────────

def _wait_for_completion(instance_id: str, timeout: float = EXECUTION_TIMEOUT_S) -> dict:
    """인스턴스가 terminal status 에 도달할 때까지 폴링한다.

    Returns
    -------
    dict
        최종 인스턴스 응답 (status 포함).

    Raises
    ------
    TimeoutError
        timeout 초 내에 terminal status 에 도달하지 못한 경우.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        r = client.get(f"/api/v1/warehouse/instances/{instance_id}")
        assert r.status_code == 200, f"인스턴스 조회 실패: {r.status_code} {r.text}"
        data = r.json()
        if data.get("status") in TERMINAL_STATUSES:
            return data
        time.sleep(EXECUTION_POLL_INTERVAL_S)
    raise TimeoutError(
        f"인스턴스 {instance_id} 가 {timeout}초 내에 완료되지 않음."
    )


# ── 메인 여정 테스트 ──────────────────────────────────────────────────────────

def test_full_user_journey():
    """CLI 사용자의 빈 시스템 → 워크플로우 실행 → 지식 프로모션 전체 흐름 검증."""

    run_id = uuid.uuid4().hex[:8]
    created_wf_id: str | None = None
    promo_title = f"풀여정-프로모션-{run_id}"
    created_knowledge_id: str | None = None
    created_promo_id: str | None = None
    created_api_def_id: str | None = None
    created_node_id: str | None = None

    try:
        # ── Step 1: GET /nodes/catalog — 13종 노드 확인 (11종 + 인스턴스DB Phase A 2종) ──
        r = client.get("/api/v1/nodes/catalog")
        assert r.status_code == 200, f"[Step 1] 카탈로그 조회 실패: {r.text}"
        catalog = r.json()
        assert isinstance(catalog, list), "[Step 1] 카탈로그가 리스트가 아님"
        assert len(catalog) == 13, f"[Step 1] 카탈로그 13종 기대, 실제={len(catalog)}"
        def_types = {n["defType"] for n in catalog}
        assert "form-start" in def_types, "[Step 1] form-start 노드 없음"
        assert "result" in def_types, "[Step 1] result 노드 없음"

        # ── Step 2: POST /api-definitions — API 명세 등록 ──────────────────
        r = client.post(
            "/api/v1/api-definitions",
            json={
                "name": f"httpbin-journey-{run_id}",
                "urlTemplate": "https://httpbin.org/get",
                "method": "GET",
                "description": "풀여정 테스트용 httpbin API",
            },
        )
        assert r.status_code == 200, f"[Step 2] API 명세 등록 실패: {r.text}"
        api_def = r.json()
        assert api_def.get("id"), "[Step 2] API 명세 id 없음"
        created_api_def_id = api_def["id"]

        # ── Step 3: POST /knowledge — 지식문서 등록 (Karpathy v2) ──────────
        # P2 부터 page_type / category enum / slug (영문 kebab-case) 필수.
        # category 는 _schema.yaml 의 4 종 중 하나 (faq 사용).
        slug = f"journey-{run_id}"
        r = client.post(
            "/api/v1/knowledge",
            json={
                "title": f"여정 지식문서 {run_id}",
                "service": "codeeyes",
                "category": "faq",
                "slug": slug,
                "page_type": "Summary",
                "tags": ["e2e", "풀여정"],
                "content": "## 풀여정 테스트\n\n이 문서는 E2E 풀 여정 테스트용 지식문서입니다.",
            },
        )
        assert r.status_code in (200, 201), f"[Step 3] 지식문서 등록 실패: {r.text}"
        knowledge_doc = r.json()
        assert knowledge_doc.get("id"), "[Step 3] 지식문서 id 없음"
        created_knowledge_id = knowledge_doc["id"]

        # ── Step 4: POST /nodes — 커스텀 AI 노드 등록 ──────────────────────
        r = client.post(
            "/api/v1/nodes",
            json={
                "name": f"여정분류기-{run_id}",
                "description": "풀여정 테스트용 분류 노드",
                "systemPrompt": "당신은 IT 지원 티켓을 분류하는 전문가입니다.",
                "userPromptTemplate": "다음 문의글을 분류하세요: {{input}}",
                "inputSchema": {"type": "object", "properties": {"input": {"type": "string"}}},
                "outputSchema": {"type": "object", "properties": {"category": {"type": "string"}}},
                "tags": ["분류", "e2e"],
            },
        )
        assert r.status_code in (200, 201), f"[Step 4] 커스텀 노드 등록 실패: {r.text}"
        custom_node = r.json()
        assert custom_node.get("id"), "[Step 4] 커스텀 노드 id 없음"
        created_node_id = custom_node["id"]

        # ── Step 5: POST /workflows — 워크플로우 생성 (form-start → result) ─
        n1 = f"wn-{uuid.uuid4().hex[:8]}"
        n2 = f"wn-{uuid.uuid4().hex[:8]}"
        c1 = f"wc-{uuid.uuid4().hex[:8]}"
        r = client.post(
            "/api/v1/workflows",
            json={
                "name": f"풀여정 워크플로우 {run_id}",
                "description": "Phase 5a E2E 풀 사용자 여정 검증",
                "status": "draft",
                "nodes": [
                    {
                        "id": n1,
                        "nodeId": n1,
                        "definitionType": "form-start",
                        "name": "여정 시작",
                        "config": {
                            "fields": [
                                {
                                    "name": "message",
                                    "label": "메시지",
                                    "type": "string",
                                    "required": True,
                                }
                            ]
                        },
                        "orderIndex": 0,
                    },
                    {
                        "id": n2,
                        "nodeId": n2,
                        "definitionType": "result",
                        "name": "여정 결과",
                        "config": {},
                        "orderIndex": 1,
                    },
                ],
                "connections": [
                    {
                        "id": c1,
                        "sourceNodeId": n1,
                        "targetNodeId": n2,
                        "sourceHandle": "output",
                        "targetHandle": "input",
                    }
                ],
            },
        )
        assert r.status_code in (200, 201), f"[Step 5] 워크플로우 생성 실패: {r.text}"
        workflow = r.json()
        created_wf_id = workflow.get("id")
        assert created_wf_id, "[Step 5] 워크플로우 id 없음"
        assert len(workflow.get("nodes", [])) == 2, "[Step 5] 노드 수 불일치"
        assert len(workflow.get("connections", [])) == 1, "[Step 5] 연결선 수 불일치"

        # ── Step 6: PATCH /workflows/{id} — status active 로 변경 ────────────
        r = client.patch(
            f"/api/v1/workflows/{created_wf_id}",
            json={"status": "active"},
        )
        assert r.status_code == 200, f"[Step 6] 워크플로우 활성화 실패: {r.text}"
        updated = r.json()
        assert updated.get("status") == "active", f"[Step 6] status가 active가 아님: {updated.get('status')}"

        # ── Step 7: POST /workflows/{id}/run — 백그라운드 실행 시작 ────────
        r = client.post(
            f"/api/v1/workflows/{created_wf_id}/run",
            json={"inputData": {"message": "E2E 풀여정 테스트 입력"}},
        )
        assert r.status_code == 202, f"[Step 7] 실행 시작 실패: {r.text}"
        run_resp = r.json()
        instance_id = run_resp.get("instanceId")
        assert instance_id, "[Step 7] instanceId 없음"
        assert run_resp.get("workflowId") == created_wf_id, "[Step 7] workflowId 불일치"
        assert run_resp.get("status") == "queued", f"[Step 7] status가 queued가 아님: {run_resp.get('status')}"
        assert instance_id.startswith("exec-"), f"[Step 7] instanceId 형식 불일치: {instance_id}"

        # ── Step 8: 실행 완료 대기 (polling, max 30초) ───────────────────────
        # TimeoutError 는 assert 실패로 처리
        try:
            final_instance = _wait_for_completion(instance_id, timeout=EXECUTION_TIMEOUT_S)
        except TimeoutError as e:
            pytest.fail(f"[Step 8] {e}")

        # ── Step 9: GET /warehouse/instances/{iid} — status 확인 ─────────────
        r = client.get(f"/api/v1/warehouse/instances/{instance_id}")
        assert r.status_code == 200, f"[Step 9] 인스턴스 조회 실패: {r.text}"
        instance_detail = r.json()
        assert instance_detail.get("instanceId") == instance_id, "[Step 9] instanceId 불일치"
        assert instance_detail.get("workflowId") == created_wf_id, "[Step 9] workflowId 불일치"
        # completed 또는 failed 모두 terminal — 실행은 됐지만 엔진이 실패해도 여정은 계속
        assert instance_detail.get("status") in TERMINAL_STATUSES, (
            f"[Step 9] 예상 terminal status, 실제={instance_detail.get('status')}"
        )

        # ── Step 10: GET /workflows/{id}/instances — 목록에 포함 확인 ───────
        r = client.get(f"/api/v1/workflows/{created_wf_id}/instances")
        assert r.status_code == 200, f"[Step 10] 인스턴스 목록 조회 실패: {r.text}"
        instances = r.json()
        assert isinstance(instances, list), "[Step 10] 인스턴스 목록이 리스트가 아님"
        instance_ids_in_list = {inst.get("id") or inst.get("instanceId") for inst in instances}
        assert instance_id in instance_ids_in_list, (
            f"[Step 10] 인스턴스 {instance_id} 가 목록에 없음. 목록={instance_ids_in_list}"
        )

        # ── Step 11: POST /knowledge/from-instance — 지식 프로모션 ──────────
        r = client.post(
            "/api/v1/knowledge/from-instance",
            json={
                "instanceId": instance_id,
                "title": promo_title,
                "category": "자동화결과",
                "tags": ["e2e", "풀여정", "프로모션"],
            },
        )
        assert r.status_code in (200, 201), f"[Step 11] 지식 프로모션 실패: {r.text}"
        promo_doc = r.json()
        assert promo_doc.get("id"), "[Step 11] 프로모션 문서 id 없음"
        assert promo_doc.get("title") == promo_title, (
            f"[Step 11] 프로모션 title 불일치: {promo_doc.get('title')}"
        )
        assert promo_doc.get("source") == f"instance:{instance_id}", (
            f"[Step 11] source 불일치: {promo_doc.get('source')}"
        )
        created_promo_id = promo_doc.get("id")

        # ── Step 12: GET /dashboard/summary — counts 업데이트 확인 ──────────
        r = client.get("/api/v1/dashboard/summary")
        assert r.status_code == 200, f"[Step 12] 대시보드 요약 조회 실패: {r.text}"
        summary = r.json()
        assert "counts" in summary, "[Step 12] counts 키 없음"
        assert "workflows" in summary, "[Step 12] workflows 키 없음"
        counts = summary["counts"]
        for key in ("todayRuns", "inProgress", "failed", "completed"):
            assert key in counts, f"[Step 12] counts.{key} 키 없음"
            assert isinstance(counts[key], int), f"[Step 12] counts.{key} 가 int가 아님"
        # 대시보드 workflows 목록에 생성한 워크플로우가 포함돼야 함
        wf_ids_in_summary = {w["id"] for w in summary["workflows"]}
        assert created_wf_id in wf_ids_in_summary, (
            f"[Step 12] 생성한 워크플로우 {created_wf_id} 가 대시보드에 없음"
        )
        # 해당 워크플로우의 latestInstance 가 방금 실행한 인스턴스여야 함
        wf_summary = next(w for w in summary["workflows"] if w["id"] == created_wf_id)
        assert wf_summary.get("latestInstance") is not None, (
            "[Step 12] latestInstance 없음 — 실행 인스턴스가 요약에 반영되지 않음"
        )
        assert wf_summary["latestInstance"]["id"] == instance_id, (
            f"[Step 12] latestInstance.id 불일치: "
            f"기대={instance_id}, 실제={wf_summary['latestInstance']['id']}"
        )

    finally:
        # ── 정리 — 실패 무관하게 생성한 리소스를 모두 삭제 ──────────────────
        # 지식문서: DELETE API 사용 (파일 + ChromaDB 동시 정리)
        if created_promo_id:
            try:
                client.delete(f"/api/v1/knowledge/{created_promo_id}")
            except Exception:
                pass
        if created_knowledge_id:
            try:
                client.delete(f"/api/v1/knowledge/{created_knowledge_id}")
            except Exception:
                pass
        # 커스텀 노드 삭제
        if created_node_id:
            try:
                client.delete(f"/api/v1/nodes/{created_node_id}")
            except Exception:
                pass
        # API 명세 삭제
        if created_api_def_id:
            try:
                client.delete(f"/api/v1/api-definitions/{created_api_def_id}")
            except Exception:
                pass
        # 워크플로우 삭제 (executions cascade)
        if created_wf_id:
            asyncio.run(_delete_workflow_by_id(created_wf_id))


# ── 개별 단계 스모크 테스트 ────────────────────────────────────────────────────
# 풀 여정과 독립적으로 각 핵심 API를 간단히 검증하는 단위 테스트.


def test_catalog_returns_expected_node_types():
    """카탈로그가 기대하는 13종 defType 을 모두 포함하는지 확인 (11종 + 인스턴스DB Phase A 2종)."""
    r = client.get("/api/v1/nodes/catalog")
    assert r.status_code == 200
    catalog = r.json()
    expected_types = {
        "form-start", "api-start", "ai-custom", "ai-api-router",
        "sorter", "unpacker", "mapper", "api-call",
        "knowledge", "result", "markdown-viewer",
        "instance-db-insert", "instance-db-lookup",
    }
    actual_types = {n["defType"] for n in catalog}
    assert expected_types == actual_types, (
        f"카탈로그 defType 불일치.\n기대: {expected_types}\n실제: {actual_types}"
    )


def test_workflow_create_and_run_returns_queued():
    """form-start → result 워크플로우 생성 + 활성화 + 실행이 202 + queued 를 반환하는지 확인.

    Note: WorkflowCreate 스키마에 status 필드가 없으므로 생성 후 PATCH 로 활성화한다.
    """
    run_id = uuid.uuid4().hex[:8]
    n1 = f"wn-{uuid.uuid4().hex[:8]}"
    n2 = f"wn-{uuid.uuid4().hex[:8]}"
    c1 = f"wc-{uuid.uuid4().hex[:8]}"
    wf_id = None

    try:
        # 1) 워크플로우 생성 (draft 상태)
        r = client.post(
            "/api/v1/workflows",
            json={
                "name": f"스모크 WF {run_id}",
                "description": "스모크 테스트용",
                "nodes": [
                    {
                        "id": n1, "nodeId": n1,
                        "definitionType": "form-start",
                        "name": "시작", "config": {"fields": []},
                        "orderIndex": 0,
                    },
                    {
                        "id": n2, "nodeId": n2,
                        "definitionType": "result",
                        "name": "결과", "config": {},
                        "orderIndex": 1,
                    },
                ],
                "connections": [
                    {
                        "id": c1, "sourceNodeId": n1, "targetNodeId": n2,
                        "sourceHandle": "output", "targetHandle": "input",
                    }
                ],
            },
        )
        assert r.status_code in (200, 201), r.text
        wf_id = r.json()["id"]

        # 2) active 로 활성화
        r_patch = client.patch(
            f"/api/v1/workflows/{wf_id}",
            json={"status": "active"},
        )
        assert r_patch.status_code == 200, r_patch.text

        # 3) 실행
        r2 = client.post(
            f"/api/v1/workflows/{wf_id}/run",
            json={"inputData": {"msg": "smoke"}},
        )
        assert r2.status_code == 202, r2.text
        body = r2.json()
        assert body["status"] == "queued"
        assert body["workflowId"] == wf_id
        assert body["instanceId"].startswith("exec-")

    finally:
        if wf_id:
            asyncio.run(_delete_workflow_by_id(wf_id))


def test_knowledge_promotion_requires_valid_instance():
    """존재하지 않는 instanceId 로 프로모션 시 404 를 반환하는지 확인."""
    r = client.post(
        "/api/v1/knowledge/from-instance",
        json={
            "instanceId": f"exec-nonexistent-{uuid.uuid4().hex[:8]}",
            "title": f"없는인스턴스 프로모션 {uuid.uuid4().hex[:8]}",
            "category": "test",
            "tags": [],
        },
    )
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == "NOT_FOUND"


def test_dashboard_summary_schema():
    """대시보드 요약 응답이 올바른 스키마를 갖는지 확인."""
    r = client.get("/api/v1/dashboard/summary")
    assert r.status_code == 200
    data = r.json()
    assert "counts" in data
    assert "workflows" in data
    for key in ("todayRuns", "inProgress", "failed", "completed"):
        assert key in data["counts"], f"counts.{key} 없음"
        assert isinstance(data["counts"][key], int)
    assert isinstance(data["workflows"], list)
