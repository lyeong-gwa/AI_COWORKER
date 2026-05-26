"""창고(WarehouseEntry) 및 실행 인스턴스 관련 엔드포인트.

Phase 2b 확장:
- ``GET /warehouse/instances/{instance_id}``          인스턴스 상세
- ``GET /warehouse/instances/{instance_id}/stream``   SSE 실행 진행상황 스트림
- ``GET /warehouse/instances/{instance_id}/entries``  해당 실행의 창고 적재 목록

Phase 4b 재작성:
- SSE 스트림이 1초 polling 대신 ``ExecutionEventBus`` 구독 기반 push 로 동작한다.
- 연결 직후 초기 스냅샷(``stream_open`` + ``nodeResults``) 을 전송한다.
- 15초 heartbeat 로 연결 유지를 보장한다.
- 실행 완료된 인스턴스는 DB 에서 바로 복원해 보내고 스트림을 종료한다.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any, AsyncGenerator, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import async_session_maker, get_db
from ...core.exceptions import NotFoundError
from ...models.workflow import (
    ExecutionStatus,
    WarehouseEntry,
    Workflow,
    WorkflowExecution,
)
from ...services.execution_bus import get_execution_bus

router = APIRouter()


def _hash_key(raw: str) -> str:
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:32]


# ─────────────────────────────────────────────────────────────────────────────
# 기존: dedup_key 기반 warehouse 전역 검색
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/search",
    summary="창고 항목 검색 (dedup key 기반)",
    description=(
        "원본 문자열을 SHA1(해시 32자)로 요약한 ``dedup_key`` 로 창고 항목을 "
        "역조회한다. 동일 입력의 중복 실행 여부 판단에 사용."
    ),
)
async def search_warehouse(
    dedupKey: str = Query(..., description="원문 dedup key (서버에서 SHA1 해시)"),
    nodeId: Optional[str] = Query(None, description="특정 node_instance_id 제한"),
    limit: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """dedup_key로 warehouse_entries 검색."""
    hashed = _hash_key(dedupKey)
    stmt = select(WarehouseEntry).where(WarehouseEntry.dedup_key == hashed)
    if nodeId:
        stmt = stmt.where(WarehouseEntry.node_instance_id == nodeId)
    stmt = stmt.order_by(WarehouseEntry.created_at.desc()).limit(limit)

    rows = (await db.execute(stmt)).scalars().all()
    entries = [
        {
            "id": e.id,
            "nodeInstanceId": e.node_instance_id,
            "executionId": e.execution_id,
            "createdAt": e.created_at.isoformat() if e.created_at else None,
            "dedupKey": e.dedup_key,
            "data": e.data,
        }
        for e in rows
    ]
    return {"count": len(entries), "entries": entries, "hashedKey": hashed}


# ─────────────────────────────────────────────────────────────────────────────
# Phase 2b 신설: 인스턴스(= WorkflowExecution) 조회 API
# ─────────────────────────────────────────────────────────────────────────────

def _execution_to_camel(ex: WorkflowExecution) -> dict:
    return {
        "id": ex.id,
        "instanceId": ex.id,  # CLI 계약 용어
        "workflowId": ex.workflow_id,
        "status": ex.status.value if ex.status else None,
        "inputData": ex.input_data,
        "outputData": ex.output_data,
        "nodeResults": ex.node_results,
        "errorMessage": ex.error_message,
        "errorNodeId": ex.error_node_id,
        "startedAt": ex.started_at.isoformat() if ex.started_at else None,
        "completedAt": ex.completed_at.isoformat() if ex.completed_at else None,
        "createdAt": ex.created_at.isoformat() if ex.created_at else None,
    }


@router.get(
    "/instances/{instance_id}",
    summary="인스턴스(실행) 상세 조회",
    description=(
        "워크플로우 1회 실행의 스냅샷을 반환한다. "
        "노드별 결과(``nodeResults``), 최종 출력(``outputData``), 오류 정보까지 포함."
    ),
)
async def get_instance(instance_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(WorkflowExecution).where(WorkflowExecution.id == instance_id)
    )
    execution = result.scalar_one_or_none()
    if not execution:
        raise NotFoundError(
            "실행 인스턴스를 찾을 수 없습니다",
            details={"instanceId": instance_id},
        )
    return _execution_to_camel(execution)


@router.get(
    "/instances/{instance_id}/entries",
    summary="인스턴스 창고 적재 목록",
    description="해당 실행 ID 로 결과 노드에 적재된 WarehouseEntry 리스트.",
)
async def list_instance_entries(
    instance_id: str,
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(WarehouseEntry)
        .where(WarehouseEntry.execution_id == instance_id)
        .order_by(WarehouseEntry.created_at.desc())
        .limit(limit)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [
        {
            "id": e.id,
            "nodeInstanceId": e.node_instance_id,
            "executionId": e.execution_id,
            "createdAt": e.created_at.isoformat() if e.created_at else None,
            "dedupKey": e.dedup_key,
            "data": e.data,
        }
        for e in rows
    ]


# ─────────────────────────────────────────────────────────────────────────────
# SSE 스트림 — 인스턴스 진행 상황
# ─────────────────────────────────────────────────────────────────────────────

_TERMINAL_STATUSES = {
    ExecutionStatus.COMPLETED,
    ExecutionStatus.FAILED,
    ExecutionStatus.CANCELLED,
}

# Phase 4b 설계 메모
# ------------------
# 이 엔드포인트는 ``ExecutionEventBus`` 를 구독하여 엔진이 push 한 이벤트를
# 그대로 릴레이한다. 더 이상 DB 폴링을 하지 않으므로 SQLite 에 부하가 없고
# 이벤트 지연도 0 에 가깝다.
#
# 구독 순서가 중요하다:
# 1. ``bus.subscribe()`` 를 먼저 열어 이후 도착 이벤트를 큐에 누적
# 2. DB 에서 현재 스냅샷을 읽어 ``stream_open`` 이벤트에 담아 전송
# 3. 이미 종료된 실행이라면 ``execution_complete`` 를 보내고 바로 리턴
# 4. 그 외엔 bus 에서 이벤트를 꺼내 계속 릴레이 (중간에 heartbeat 주기 보장)
# 이 순서는 race condition 을 회피한다: subscribe 이전에 emit 된 이벤트만
# 놓치고, 그 구간은 스냅샷이 커버한다.

# heartbeat 주기. 엔진도 30초 간격으로 heartbeat 이벤트를 publish 하지만,
# 엔진이 heartbeat 을 1초라도 놓치면 프록시 idle cut 이 발생할 수 있으므로
# 엔드포인트 측에서도 방어적으로 15초 마다 주석 라인을 push 한다.
_SSE_IDLE_TIMEOUT_SECONDS = 15.0


def _sse(event: str, data: dict) -> str:
    payload = json.dumps(data, default=str, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


def _sse_comment(note: str) -> str:
    """SSE 프로토콜에서 ``:`` 로 시작하는 라인은 주석. EventSource 는 무시한다.

    keep-alive ping 용도로 사용한다.
    """
    return f": {note}\n\n"


def _snapshot_payload(instance_id: str, execution: WorkflowExecution) -> dict:
    """초기 ``stream_open`` 이벤트에 실어보낼 현재 상태 스냅샷."""
    return {
        "instanceId": instance_id,
        "status": execution.status.value if execution.status else None,
        "startedAt": execution.started_at.isoformat() if execution.started_at else None,
        "completedAt": execution.completed_at.isoformat()
        if execution.completed_at
        else None,
        "nodeResults": execution.node_results or {},
        "errorMessage": execution.error_message,
        "errorNodeId": execution.error_node_id,
        "message": "subscribed",
    }


def _terminal_event_payload(instance_id: str, execution: WorkflowExecution) -> dict:
    """이미 종료된 인스턴스용 ``execution_complete`` 페이로드."""
    return {
        "instanceId": instance_id,
        "status": execution.status.value if execution.status else None,
        "output": execution.output_data,
        "outputData": execution.output_data,
        "error": execution.error_message,
        "errorNodeId": execution.error_node_id,
    }


@router.get(
    "/instances/{instance_id}/stream",
    summary="인스턴스 진행상황 SSE 스트림",
    description=(
        "Server-Sent Events 로 노드별 진행상황을 실시간 전달한다. "
        "이벤트 타입: ``stream_open``, ``node_start``, ``node_complete``, "
        "``node_error``, ``heartbeat``, ``execution_complete``. "
        "프로토콜은 SSE 표준이므로 브라우저 ``EventSource`` 또는 "
        "``curl -N`` 로 바로 소비할 수 있다. "
        "\n\n"
        "**Phase 4b 구현**: ``ExecutionEventBus`` 기반 push. 엔진이 노드 상태를 "
        "바꿀 때 즉시 이벤트가 전달되며, 15초 간격으로 SSE 주석(``: ping``) 이 "
        "흘러 프록시 idle timeout 을 방지한다. 연결 직후 ``stream_open`` 이벤트에 "
        "현재 ``nodeResults`` 스냅샷이 포함된다."
    ),
    response_class=StreamingResponse,
)
async def stream_instance(instance_id: str):
    """SSE: 인스턴스 진행상황 스트림 (event-bus push 기반)."""

    # 1차 존재 확인 — 여기서 404 를 던지면 FastAPI 가 에러 envelope 로 직렬화.
    async with async_session_maker() as probe:
        exists = await probe.execute(
            select(WorkflowExecution.id).where(WorkflowExecution.id == instance_id)
        )
        if exists.scalar_one_or_none() is None:
            raise NotFoundError(
                "실행 인스턴스를 찾을 수 없습니다",
                details={"instanceId": instance_id},
            )

    bus = get_execution_bus()

    async def event_generator() -> AsyncGenerator[str, None]:
        # subscribe() 를 먼저 열어 구독 큐를 확보. subscribe 이후 publish 된
        # 이벤트는 모두 수신 보장.
        subscription = bus.subscribe(instance_id)

        try:
            # 1) 현재 스냅샷 로드 — subscribe 이전에 발생한 이벤트를
            #    대체한다 (이벤트 버스는 replay 를 하지 않는 설계).
            async with async_session_maker() as db:
                result = await db.execute(
                    select(WorkflowExecution).where(
                        WorkflowExecution.id == instance_id
                    )
                )
                execution = result.scalar_one_or_none()

            if execution is None:
                # 조회 시점부터 stream 오픈 시점 사이에 삭제된 레어 케이스.
                yield _sse(
                    "execution_complete",
                    {
                        "instanceId": instance_id,
                        "status": "missing",
                        "reason": "execution deleted",
                    },
                )
                return

            # 2) stream_open 이벤트 (스냅샷 포함)
            yield _sse("stream_open", _snapshot_payload(instance_id, execution))

            # 3) 이미 종료된 실행이면 즉시 완료 이벤트 후 종료.
            if execution.status in _TERMINAL_STATUSES:
                yield _sse(
                    "execution_complete",
                    _terminal_event_payload(instance_id, execution),
                )
                return

            # 4) 이벤트 버스 구독 루프. 일정 시간 이벤트가 없으면 heartbeat
            #    주석을 내보내 연결 유지.
            while True:
                try:
                    event = await asyncio.wait_for(
                        subscription.__anext__(),
                        timeout=_SSE_IDLE_TIMEOUT_SECONDS,
                    )
                except asyncio.TimeoutError:
                    # keep-alive ping (EventSource 는 주석 라인을 무시).
                    yield _sse_comment("ping")
                    continue
                except StopAsyncIteration:
                    # 구독자 큐가 닫힘 (reset 등) — 스트림 종료.
                    return

                # 이벤트 타입별 페이로드 구성. 프론트엔드 호환을 위해
                # 기존 이벤트 구조 (nodeId, status, output, error 등) 유지.
                event_type = event.eventType
                base_data = {
                    "instanceId": instance_id,
                }
                if event.nodeId:
                    base_data["nodeId"] = event.nodeId

                if event_type == "node_start":
                    base_data["status"] = "running"
                    base_data["definitionType"] = event.data.get("definitionType")
                    base_data["startTime"] = event.data.get("startTime")
                elif event_type == "node_complete":
                    base_data["status"] = "completed"
                    base_data["definitionType"] = event.data.get("definitionType")
                    base_data["output"] = event.data.get("output")
                    base_data["endTime"] = event.data.get("endTime")
                elif event_type == "node_error":
                    base_data["status"] = "failed"
                    base_data["definitionType"] = event.data.get("definitionType")
                    base_data["error"] = event.data.get("error")
                    base_data["endTime"] = event.data.get("endTime")
                elif event_type == "heartbeat":
                    base_data["timestamp"] = event.data.get("timestamp")
                elif event_type == "execution_complete":
                    base_data["status"] = event.data.get("status")
                    base_data["output"] = event.data.get("outputData")
                    base_data["outputData"] = event.data.get("outputData")
                    base_data["error"] = event.data.get("error")
                    base_data["errorNodeId"] = event.data.get("errorNodeId")
                else:
                    # 미지의 이벤트 타입은 data 를 그대로 전달 (forward-compatible)
                    base_data.update(event.data or {})

                yield _sse(event_type, base_data)

                if event_type == "execution_complete":
                    return
        finally:
            # 구독 generator close 보장 (내부 finally 에서 구독 해제).
            try:
                await subscription.aclose()
            except Exception:
                pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # nginx 등 프록시 버퍼링 방지
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# 인스턴스 → 통합 Markdown 보고서
# ─────────────────────────────────────────────────────────────────────────────

_SENSITIVE_KEY_SUBSTRINGS = ("token", "password", "secret", "apikey")
_INPUT_VALUE_TRUNCATE_LEN = 32


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(sub in lowered for sub in _SENSITIVE_KEY_SUBSTRINGS)


def _mask_input_data(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: ("***" if _is_sensitive_key(str(k)) else _mask_input_data(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_mask_input_data(v) for v in value]
    if isinstance(value, str) and len(value) >= _INPUT_VALUE_TRUNCATE_LEN:
        return value[: _INPUT_VALUE_TRUNCATE_LEN - 1] + "…"
    return value


def _format_input_line(input_data: Any) -> str:
    masked = _mask_input_data(input_data if input_data is not None else {})
    try:
        return json.dumps(masked, ensure_ascii=False, default=str, separators=(", ", ": "))
    except Exception:
        return str(masked)


def _status_badge(status: Optional[str]) -> str:
    if status == ExecutionStatus.COMPLETED.value:
        return f"{status} (✅ completed)"
    if status == ExecutionStatus.FAILED.value:
        return f"{status} (❌ failed)"
    if status == ExecutionStatus.RUNNING.value:
        return f"{status} (⏳ running)"
    return status or "-"


def _entry_title(entry: WarehouseEntry) -> str:
    data = entry.data if isinstance(entry.data, dict) else {}
    for key in ("title", "prTitle", "prNumber", "dedup_key"):
        val = data.get(key)
        if val not in (None, ""):
            return str(val)
    return entry.id


def _entry_body(entry: WarehouseEntry) -> str:
    data = entry.data if isinstance(entry.data, dict) else {}

    primary = data.get("data")
    if primary is not None:
        if isinstance(primary, str):
            return primary
        if isinstance(primary, (dict, list)):
            return (
                "```json\n"
                + json.dumps(primary, ensure_ascii=False, indent=4, default=str)
                + "\n```"
            )

    for key in ("markdown", "response", "output"):
        val = data.get(key)
        if val is not None:
            if isinstance(val, str):
                return val
            if isinstance(val, (dict, list)):
                return (
                    "```json\n"
                    + json.dumps(val, ensure_ascii=False, indent=4, default=str)
                    + "\n```"
                )

    payload = entry.data if entry.data is not None else {}
    return (
        "```json\n"
        + json.dumps(payload, ensure_ascii=False, indent=4, default=str)
        + "\n```"
    )


def _duration_seconds(started, completed) -> str:
    if not started or not completed:
        return "-"
    delta = completed - started
    return f"{delta.total_seconds():.3f}"


def _reports_directory() -> Path:
    # backend/app/api/routes/warehouse.py → backend/
    backend_dir = Path(__file__).resolve().parent.parent.parent.parent
    return backend_dir / "data" / "reports"


def _build_report_markdown(
    execution: WorkflowExecution,
    workflow: Optional[Workflow],
    entries: list[WarehouseEntry],
) -> str:
    workflow_name = workflow.name if workflow else "(unknown)"
    started_iso = execution.started_at.isoformat() if execution.started_at else "-"
    completed_iso = execution.completed_at.isoformat() if execution.completed_at else "-"
    status_value = execution.status.value if execution.status else None

    lines: list[str] = []
    lines.append(f"# {workflow_name} — 실행 보고서")
    lines.append("")
    lines.append(f"- **Instance**: `{execution.id}`")
    lines.append(f"- **Workflow**: `{execution.workflow_id}` ({workflow_name})")
    lines.append(f"- **Status**: {_status_badge(status_value)}")
    lines.append(f"- **시작**: {started_iso}")
    lines.append(f"- **종료**: {completed_iso}")
    lines.append(
        f"- **경과**: {_duration_seconds(execution.started_at, execution.completed_at)}s"
    )
    lines.append(f"- **입력**: `{_format_input_line(execution.input_data)}`")
    lines.append("")
    lines.append("---")
    lines.append("")

    if not entries:
        lines.append("## 창고 결과 (0건)")
        lines.append("")
        lines.append("(창고에 저장된 결과가 없습니다)")
        lines.append("")
        return "\n".join(lines)

    lines.append(f"## 창고 결과 ({len(entries)}건)")
    lines.append("")

    for idx, entry in enumerate(entries, start=1):
        title = _entry_title(entry)
        if entry.dedup_key:
            header = f"### {idx}. {title} (dedup: {entry.dedup_key})"
        else:
            header = f"### {idx}. {title}"
        lines.append(header)
        lines.append("")
        lines.append(_entry_body(entry))
        lines.append("")
        if idx < len(entries):
            lines.append("---")
            lines.append("")

    return "\n".join(lines)


@router.get(
    "/instances/{instance_id}/report.md",
    summary="인스턴스 통합 Markdown 보고서",
    description=(
        "실행 인스턴스의 메타데이터와 ``WarehouseEntry`` 전체를 하나의 마크다운 "
        "문서로 조립해 반환한다. ``save=true`` 면 ``backend/data/reports/`` 에 "
        "파일로도 저장하고 저장 경로를 ``X-Report-Path`` 헤더로 알려준다. "
        "``download=true`` 면 ``Content-Disposition: attachment`` 로 다운로드 유도."
    ),
    response_description="text/markdown 본문",
)
async def get_instance_report_markdown(
    instance_id: str,
    save: bool = Query(False, description="backend/data/reports/ 에 파일 저장"),
    download: bool = Query(False, description="브라우저 다운로드 유도"),
    db: AsyncSession = Depends(get_db),
):
    execution = (
        await db.execute(
            select(WorkflowExecution).where(WorkflowExecution.id == instance_id)
        )
    ).scalar_one_or_none()
    if not execution:
        raise NotFoundError(
            "실행 인스턴스를 찾을 수 없습니다",
            details={"instanceId": instance_id},
        )

    workflow = (
        await db.execute(
            select(Workflow).where(Workflow.id == execution.workflow_id)
        )
    ).scalar_one_or_none()

    entries = (
        (
            await db.execute(
                select(WarehouseEntry)
                .where(WarehouseEntry.execution_id == instance_id)
                .order_by(WarehouseEntry.created_at.asc())
            )
        )
        .scalars()
        .all()
    )

    markdown = _build_report_markdown(execution, workflow, list(entries))

    headers: dict[str, str] = {}
    if save:
        reports_dir = _reports_directory()
        reports_dir.mkdir(parents=True, exist_ok=True)
        file_path = (reports_dir / f"{instance_id}.md").resolve()
        file_path.write_text(markdown, encoding="utf-8")
        # HTTP 헤더는 latin-1 제약. 한글 경로는 percent-encoding 으로 안전화.
        headers["X-Report-Path"] = quote(str(file_path), safe=":/\\")

    if download:
        headers["Content-Disposition"] = (
            f'attachment; filename="report-{instance_id}.md"'
        )

    return Response(
        content=markdown,
        media_type="text/markdown; charset=utf-8",
        headers=headers,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 단일 Entry → Markdown 보고서
# ─────────────────────────────────────────────────────────────────────────────


def _build_entry_report_markdown(
    entry: WarehouseEntry,
    workflow: Optional[Workflow],
) -> str:
    title = _entry_title(entry)
    created_iso = entry.created_at.isoformat() if entry.created_at else "-"
    execution_line = f"`{entry.execution_id}`"
    if workflow:
        execution_line = f"`{entry.execution_id}` ({workflow.name}, `{workflow.id}`)"

    lines: list[str] = []
    lines.append(f"# {title} — 창고 항목 보고서")
    lines.append("")
    lines.append(f"- **Entry ID**: `{entry.id}`")
    lines.append(f"- **Node Instance**: `{entry.node_instance_id}`")
    lines.append(f"- **Execution**: {execution_line}")
    lines.append(f"- **생성 시각**: {created_iso}")
    lines.append(f"- **Dedup Key**: `{entry.dedup_key or '-'}`")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(_entry_body(entry))
    lines.append("")
    return "\n".join(lines)


@router.get(
    "/entries/{entry_id}/report.md",
    summary="단일 창고 항목 Markdown 보고서",
    description=(
        "하나의 ``WarehouseEntry`` 를 마크다운 문서로 조립해 반환한다. "
        "``save=true`` 면 ``backend/data/reports/{entry_id}.md`` 에 파일로 저장하고 "
        "저장 경로를 ``X-Report-Path`` 헤더로 알려준다. "
        "``download=true`` 면 ``Content-Disposition: attachment`` 로 다운로드 유도."
    ),
    response_description="text/markdown 본문",
)
async def get_entry_report_markdown(
    entry_id: str,
    save: bool = Query(False, description="backend/data/reports/ 에 파일 저장"),
    download: bool = Query(False, description="브라우저 다운로드 유도"),
    db: AsyncSession = Depends(get_db),
):
    entry = (
        await db.execute(
            select(WarehouseEntry).where(WarehouseEntry.id == entry_id)
        )
    ).scalar_one_or_none()
    if not entry:
        raise NotFoundError(
            "창고 항목을 찾을 수 없습니다",
            details={"entryId": entry_id},
        )

    workflow: Optional[Workflow] = None
    if entry.execution_id:
        execution = (
            await db.execute(
                select(WorkflowExecution).where(
                    WorkflowExecution.id == entry.execution_id
                )
            )
        ).scalar_one_or_none()
        if execution and execution.workflow_id:
            workflow = (
                await db.execute(
                    select(Workflow).where(Workflow.id == execution.workflow_id)
                )
            ).scalar_one_or_none()

    markdown = _build_entry_report_markdown(entry, workflow)

    headers: dict[str, str] = {}
    if save:
        reports_dir = _reports_directory()
        reports_dir.mkdir(parents=True, exist_ok=True)
        file_path = (reports_dir / f"{entry_id}.md").resolve()
        file_path.write_text(markdown, encoding="utf-8")
        headers["X-Report-Path"] = quote(str(file_path), safe=":/\\")

    if download:
        headers["Content-Disposition"] = (
            f'attachment; filename="report-{entry_id}.md"'
        )

    return Response(
        content=markdown,
        media_type="text/markdown; charset=utf-8",
        headers=headers,
    )
