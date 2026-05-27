"""인스턴스DB record 단건/다중 삭제 검증.

검증 포인트:
- R1: 단건 DELETE → 200 + 파일 unlink 확인
- R2: 미존재 record DELETE → 404
- R3: bulk recordIds 다중 삭제
- R4: bulk filter (data.boardId=X) → 매치 row 삭제
- R5: 빈 body → 422 (안전 가드)
- R6: recordIds + filter OR 합집합
- R7: bulk 호출은 매치되지 않는 다른 record 보존
- R8: 메타 미존재 시 DELETE → 404
"""

from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.services.instance_db_store import get_instance_db_store


client = TestClient(app, raise_server_exceptions=False)


def _create_idb(name_suffix: str = "") -> dict:
    payload = {
        "name": f"record-delete-test {uuid.uuid4().hex[:6]}{name_suffix}",
        "description": "test_instance_db_record_delete.py 생성",
        "tags": ["test"],
    }
    r = client.post("/api/v1/instance-dbs", json=payload)
    assert r.status_code == 201, f"메타 등록 실패: {r.text}"
    return r.json()


async def _insert(idb_id: str, data: dict) -> str:
    store = get_instance_db_store()
    rec = await store.insert_record(idb_id, data=data, source={})
    return rec["id"]


def _record_file(idb_id: str, rec_id: str) -> Path:
    """테스트 격리 폴더 안에서 record 파일 경로 계산."""
    base = Path(os.environ["INSTANCE_DB_DIR"])
    return base / idb_id / f"{rec_id}.json"


# ── R1 ────────────────────────────────────────────────────────────────────


def test_delete_single_record_removes_file():
    """단건 삭제 → 200 + 파일 unlink + 후속 GET 404."""
    created = _create_idb()
    idb_id = created["id"]

    rec_id = asyncio.run(_insert(idb_id, {"boardId": 1001, "title": "단건"}))
    file_path = _record_file(idb_id, rec_id)
    assert file_path.exists(), "사전 시드 파일 미존재"

    r = client.delete(f"/api/v1/instance-dbs/{idb_id}/records/{rec_id}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["deleted"] is True
    assert body["recordId"] == rec_id

    assert not file_path.exists(), "파일이 삭제되지 않음"

    # 후속 GET 404
    r = client.get(f"/api/v1/instance-dbs/{idb_id}/records/{rec_id}")
    assert r.status_code == 404


# ── R2 ────────────────────────────────────────────────────────────────────


def test_delete_missing_record_returns_404():
    """미존재 record DELETE → 404 envelope."""
    created = _create_idb()
    idb_id = created["id"]

    ghost_rec = f"rec-{uuid.uuid4().hex[:8]}"
    r = client.delete(f"/api/v1/instance-dbs/{idb_id}/records/{ghost_rec}")
    assert r.status_code == 404, r.text
    err = r.json()["error"]
    assert err["code"] == "NOT_FOUND"
    assert err["details"]["recordId"] == ghost_rec


def test_delete_record_in_missing_idb_returns_404():
    """미존재 InstanceDB → 404."""
    ghost_idb = f"idb-{uuid.uuid4().hex[:8]}"
    ghost_rec = f"rec-{uuid.uuid4().hex[:8]}"
    r = client.delete(f"/api/v1/instance-dbs/{ghost_idb}/records/{ghost_rec}")
    assert r.status_code == 404, r.text


# ── R3 ────────────────────────────────────────────────────────────────────


def test_bulk_delete_by_record_ids():
    """recordIds 리스트로 다중 삭제."""
    created = _create_idb()
    idb_id = created["id"]

    rec_a = asyncio.run(_insert(idb_id, {"boardId": 100, "tag": "a"}))
    rec_b = asyncio.run(_insert(idb_id, {"boardId": 101, "tag": "b"}))
    rec_c = asyncio.run(_insert(idb_id, {"boardId": 102, "tag": "c"}))

    r = client.post(
        f"/api/v1/instance-dbs/{idb_id}/records/delete",
        json={"recordIds": [rec_a, rec_b]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["deletedCount"] == 2
    assert set(body["deletedIds"]) == {rec_a, rec_b}

    # rec_c 는 보존
    r = client.get(f"/api/v1/instance-dbs/{idb_id}/records/{rec_c}")
    assert r.status_code == 200


# ── R4 ────────────────────────────────────────────────────────────────────


def test_bulk_delete_by_filter():
    """filter 로 다중 삭제 — data.boardId 매치 row 만."""
    created = _create_idb()
    idb_id = created["id"]

    rec_match_1 = asyncio.run(_insert(idb_id, {"boardId": 2778, "title": "x"}))
    rec_match_2 = asyncio.run(_insert(idb_id, {"boardId": 2778, "title": "y"}))
    rec_other = asyncio.run(_insert(idb_id, {"boardId": 9999, "title": "z"}))

    r = client.post(
        f"/api/v1/instance-dbs/{idb_id}/records/delete",
        json={"filter": {"boardId": 2778}},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["deletedCount"] == 2
    assert set(body["deletedIds"]) == {rec_match_1, rec_match_2}

    # rec_other 보존
    r = client.get(f"/api/v1/instance-dbs/{idb_id}/records/{rec_other}")
    assert r.status_code == 200


# ── R5 ────────────────────────────────────────────────────────────────────


def test_bulk_delete_empty_body_returns_422():
    """recordIds + filter 둘 다 비면 422 (안전 가드)."""
    created = _create_idb()
    idb_id = created["id"]

    # 1) 완전 빈 body
    r = client.post(
        f"/api/v1/instance-dbs/{idb_id}/records/delete",
        json={},
    )
    assert r.status_code == 422, r.text
    err = r.json()["error"]
    assert err["code"] == "VALIDATION_ERROR"

    # 2) recordIds=[] + filter={} 도 차단
    r = client.post(
        f"/api/v1/instance-dbs/{idb_id}/records/delete",
        json={"recordIds": [], "filter": {}},
    )
    assert r.status_code == 422, r.text

    # 3) recordIds=None + filter=None 도 차단
    r = client.post(
        f"/api/v1/instance-dbs/{idb_id}/records/delete",
        json={"recordIds": None, "filter": None},
    )
    assert r.status_code == 422, r.text


# ── R6 ────────────────────────────────────────────────────────────────────


def test_bulk_delete_or_union_of_ids_and_filter():
    """recordIds 와 filter 둘 다 있으면 OR 합집합."""
    created = _create_idb()
    idb_id = created["id"]

    rec_by_id = asyncio.run(_insert(idb_id, {"boardId": 50, "tag": "a"}))
    rec_by_filter = asyncio.run(_insert(idb_id, {"boardId": 100, "tag": "match"}))
    rec_safe = asyncio.run(_insert(idb_id, {"boardId": 200, "tag": "keep"}))

    r = client.post(
        f"/api/v1/instance-dbs/{idb_id}/records/delete",
        json={
            "recordIds": [rec_by_id],
            "filter": {"tag": "match"},
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["deletedCount"] == 2
    assert set(body["deletedIds"]) == {rec_by_id, rec_by_filter}

    # rec_safe 보존
    r = client.get(f"/api/v1/instance-dbs/{idb_id}/records/{rec_safe}")
    assert r.status_code == 200


# ── R7 ────────────────────────────────────────────────────────────────────


def test_bulk_delete_nonexistent_record_ids_silently_ignored():
    """존재하지 않는 recordIds 는 무시되고 존재하는 것만 삭제 (실패 없음)."""
    created = _create_idb()
    idb_id = created["id"]

    rec_real = asyncio.run(_insert(idb_id, {"boardId": 1, "tag": "x"}))
    ghost = f"rec-{uuid.uuid4().hex[:8]}"

    r = client.post(
        f"/api/v1/instance-dbs/{idb_id}/records/delete",
        json={"recordIds": [rec_real, ghost]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["deletedCount"] == 1
    assert body["deletedIds"] == [rec_real]


# ── R8 ────────────────────────────────────────────────────────────────────


def test_bulk_delete_missing_idb_returns_404():
    """미존재 InstanceDB 에 대한 bulk DELETE → 404."""
    ghost_idb = f"idb-{uuid.uuid4().hex[:8]}"
    r = client.post(
        f"/api/v1/instance-dbs/{ghost_idb}/records/delete",
        json={"filter": {"boardId": 1}},
    )
    assert r.status_code == 404, r.text


def test_bulk_delete_filter_multi_key_requires_all_match():
    """filter 의 모든 key 가 일치해야 매치 (AND)."""
    created = _create_idb()
    idb_id = created["id"]

    rec_full_match = asyncio.run(
        _insert(idb_id, {"boardId": 7, "status": "open"})
    )
    rec_partial = asyncio.run(_insert(idb_id, {"boardId": 7, "status": "closed"}))
    rec_other = asyncio.run(_insert(idb_id, {"boardId": 8, "status": "open"}))

    r = client.post(
        f"/api/v1/instance-dbs/{idb_id}/records/delete",
        json={"filter": {"boardId": 7, "status": "open"}},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["deletedCount"] == 1
    assert body["deletedIds"] == [rec_full_match]

    # 나머지 보존
    for rid in (rec_partial, rec_other):
        r = client.get(f"/api/v1/instance-dbs/{idb_id}/records/{rid}")
        assert r.status_code == 200


# ── C1~C5: records/clear 엔드포인트 ────────────────────────────────────────


def test_clear_all_records_removes_records_but_keeps_meta():
    """C1: clear 호출 → 모든 records 삭제 + IDB 메타 보존."""
    created = _create_idb()
    idb_id = created["id"]

    # 3건 시드
    asyncio.run(_insert(idb_id, {"key": "a"}))
    asyncio.run(_insert(idb_id, {"key": "b"}))
    asyncio.run(_insert(idb_id, {"key": "c"}))

    # 시드 확인
    r = client.get(f"/api/v1/instance-dbs/{idb_id}/records")
    assert r.json()["total"] == 3

    # clear 호출
    r = client.post(
        f"/api/v1/instance-dbs/{idb_id}/records/clear",
        json={"confirmDbId": idb_id},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["cleared"] is True
    assert body["instanceDbId"] == idb_id
    assert body["deletedCount"] == 3

    # records 0건 확인
    r = client.get(f"/api/v1/instance-dbs/{idb_id}/records")
    assert r.json()["total"] == 0

    # 메타 보존 확인
    r = client.get(f"/api/v1/instance-dbs/{idb_id}")
    assert r.status_code == 200
    assert r.json()["id"] == idb_id


def test_clear_records_confirmdbid_mismatch_returns_422():
    """C2: confirmDbId 불일치 → 422."""
    created = _create_idb()
    idb_id = created["id"]

    r = client.post(
        f"/api/v1/instance-dbs/{idb_id}/records/clear",
        json={"confirmDbId": "idb-wrongid"},
    )
    assert r.status_code == 422, r.text
    err = r.json()["error"]
    assert err["code"] == "VALIDATION_ERROR"
    assert "mismatch" in err["message"].lower()


def test_clear_records_missing_confirmdbid_returns_422():
    """C3: confirmDbId 누락 → 422 (Pydantic validation)."""
    created = _create_idb()
    idb_id = created["id"]

    r = client.post(
        f"/api/v1/instance-dbs/{idb_id}/records/clear",
        json={},
    )
    assert r.status_code == 422, r.text


def test_clear_records_idempotent_on_empty_idb():
    """C4: 멱등성 — 비어있는 IDB 에 clear 재호출 → 200 + deletedCount=0."""
    created = _create_idb()
    idb_id = created["id"]

    # 첫 호출 (이미 비어있음)
    r = client.post(
        f"/api/v1/instance-dbs/{idb_id}/records/clear",
        json={"confirmDbId": idb_id},
    )
    assert r.status_code == 200, r.text
    assert r.json()["deletedCount"] == 0

    # 두 번째 호출도 동일
    r = client.post(
        f"/api/v1/instance-dbs/{idb_id}/records/clear",
        json={"confirmDbId": idb_id},
    )
    assert r.status_code == 200, r.text
    assert r.json()["deletedCount"] == 0


def test_clear_records_then_new_insert_works():
    """C5: clear 후 신규 POST 가능 — record 재등록 후 정상 조회."""
    created = _create_idb()
    idb_id = created["id"]

    # 시드
    asyncio.run(_insert(idb_id, {"val": 1}))
    asyncio.run(_insert(idb_id, {"val": 2}))

    # clear
    r = client.post(
        f"/api/v1/instance-dbs/{idb_id}/records/clear",
        json={"confirmDbId": idb_id},
    )
    assert r.status_code == 200, r.text
    assert r.json()["deletedCount"] == 2

    # 신규 insert 후 조회
    new_rec_id = asyncio.run(_insert(idb_id, {"val": 99, "tag": "post-clear"}))
    r = client.get(f"/api/v1/instance-dbs/{idb_id}/records/{new_rec_id}")
    assert r.status_code == 200, r.text
    assert r.json()["data"]["val"] == 99

    r = client.get(f"/api/v1/instance-dbs/{idb_id}/records")
    assert r.json()["total"] == 1
