"""InstanceDBStore — 파일시스템 store 의 격리된 단위 검증.

검증 포인트:
1. create_meta — 폴더 + meta.json 생성, 시각 채워짐
2. create_meta — name 중복 거부
3. list_meta — 최신순 + q 부분 일치
4. get_meta / get_record — 미존재 시 None / KeyError
5. update_meta — 필드 갱신 + updatedAt 변경 + name 중복 거부
6. delete_db — 폴더 통째 삭제
7. insert_record — rec-{8hex}.json 생성, _source 채워짐
8. list_records — createdAt 내림차순, source_* AND 필터, limit/offset
9. 원자성 — *.tmp 파일이 남지 않음 (정상 완료 후)
"""
from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

import pytest

from app.services.instance_db_store import InstanceDBStore


# ── 헬퍼 ──────────────────────────────────────────────────────────────────


def _make_store(tmp_path: Path) -> InstanceDBStore:
    return InstanceDBStore(tmp_path / "instance_dbs")


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ── 1. create_meta 기본 ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_meta_creates_folder_and_meta_json(tmp_path):
    store = _make_store(tmp_path)
    meta = await store.create_meta(name="alpha", description="desc", tags=["a", "b"])

    assert meta["id"].startswith("idb-")
    assert meta["name"] == "alpha"
    assert meta["description"] == "desc"
    assert meta["tags"] == ["a", "b"]
    assert meta["createdBy"] == "cli"
    assert meta["createdAt"]
    assert meta["updatedAt"] == meta["createdAt"]

    # 폴더 + meta.json 존재
    db_dir = store.base_dir / meta["id"]
    assert db_dir.is_dir()
    assert (db_dir / "meta.json").is_file()

    # tmp 파일 잔재 없음
    assert not list(db_dir.glob("*.tmp"))


# ── 2. create_meta name 중복 ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_meta_rejects_duplicate_name(tmp_path):
    store = _make_store(tmp_path)
    await store.create_meta(name="dup", description=None, tags=[])
    with pytest.raises(ValueError):
        await store.create_meta(name="dup", description="2nd", tags=[])


# ── 3. list_meta 정렬 + q 검색 ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_meta_orders_newest_first_and_q_search(tmp_path):
    store = _make_store(tmp_path)
    m1 = await store.create_meta(name="alpha-one", description="첫 번째", tags=[])
    # 시간차 보장 — createdAt 가 같으면 사전식 정렬이라 문자열로도 안전.
    await asyncio.sleep(0.01)
    m2 = await store.create_meta(name="beta-two", description="두 번째", tags=[])
    await asyncio.sleep(0.01)
    m3 = await store.create_meta(name="alpha-three", description="세 번째", tags=[])

    listing = await store.list_meta()
    ids = [m["id"] for m in listing]
    # 최신이 앞쪽 — m3, m2, m1 순
    assert ids[0] == m3["id"]
    assert ids[-1] == m1["id"]

    # q 검색 — "alpha" 부분 일치 (2건)
    matched = await store.list_meta(q="alpha")
    matched_ids = {m["id"] for m in matched}
    assert m1["id"] in matched_ids and m3["id"] in matched_ids
    assert m2["id"] not in matched_ids

    # q 검색 — description 도 부분 일치
    matched_desc = await store.list_meta(q="두 번째")
    assert {m["id"] for m in matched_desc} == {m2["id"]}


# ── 4. get_meta / get_record 미존재 ──────────────────────────────────────


@pytest.mark.asyncio
async def test_get_meta_returns_none_for_unknown(tmp_path):
    store = _make_store(tmp_path)
    assert await store.get_meta("idb-no-exist") is None


@pytest.mark.asyncio
async def test_get_record_raises_keyerror_for_unknown_db(tmp_path):
    store = _make_store(tmp_path)
    with pytest.raises(KeyError):
        await store.get_record("idb-no-exist", "rec-xxxxxxxx")


# ── 5. update_meta ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_meta_changes_fields_and_updated_at(tmp_path):
    store = _make_store(tmp_path)
    m = await store.create_meta(name="original", description="old", tags=["t1"])
    original_updated = m["updatedAt"]

    await asyncio.sleep(0.01)
    updated = await store.update_meta(
        m["id"], name="renamed", description="new", tags=["t2", "t3"]
    )

    assert updated["name"] == "renamed"
    assert updated["description"] == "new"
    assert updated["tags"] == ["t2", "t3"]
    assert updated["updatedAt"] > original_updated
    # createdAt 은 그대로
    assert updated["createdAt"] == m["createdAt"]


@pytest.mark.asyncio
async def test_update_meta_rejects_duplicate_name(tmp_path):
    store = _make_store(tmp_path)
    m1 = await store.create_meta(name="a", tags=[])
    m2 = await store.create_meta(name="b", tags=[])
    with pytest.raises(ValueError):
        await store.update_meta(m2["id"], name="a")
    # 자기 자신 이름으로 update 는 허용
    refreshed = await store.update_meta(m1["id"], name="a")
    assert refreshed["name"] == "a"


@pytest.mark.asyncio
async def test_update_meta_unknown_id_raises_keyerror(tmp_path):
    store = _make_store(tmp_path)
    with pytest.raises(KeyError):
        await store.update_meta("idb-no-exist", description="x")


# ── 6. delete_db ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_db_removes_folder_and_records(tmp_path):
    store = _make_store(tmp_path)
    m = await store.create_meta(name="del-test", tags=[])
    await store.insert_record(
        m["id"],
        data={"a": 1},
        source={"workflowId": None, "executionId": None, "warehouseId": None},
    )
    db_dir = store.base_dir / m["id"]
    assert db_dir.is_dir()

    await store.delete_db(m["id"])
    assert not db_dir.exists()

    # 재조회 None
    assert await store.get_meta(m["id"]) is None


@pytest.mark.asyncio
async def test_delete_db_unknown_id_raises_keyerror(tmp_path):
    store = _make_store(tmp_path)
    with pytest.raises(KeyError):
        await store.delete_db("idb-no-exist")


# ── 7. insert_record ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_insert_record_writes_rec_file_with_source(tmp_path):
    store = _make_store(tmp_path)
    m = await store.create_meta(name="rec-test", tags=[])

    rec = await store.insert_record(
        m["id"],
        data={"boardId": 42, "title": "hello"},
        source={
            "workflowId": "wf-1",
            "executionId": "exec-9",
            "warehouseId": "wh-3",
        },
    )
    assert rec["id"].startswith("rec-")
    assert rec["data"]["boardId"] == 42
    assert rec["_source"]["workflowId"] == "wf-1"
    assert rec["_source"]["executionId"] == "exec-9"
    assert rec["_source"]["warehouseId"] == "wh-3"
    assert rec["createdAt"]

    # 파일 존재
    rec_path = store.base_dir / m["id"] / f"{rec['id']}.json"
    assert rec_path.is_file()

    # tmp 파일 잔재 없음
    assert not list((store.base_dir / m["id"]).glob("*.tmp"))


@pytest.mark.asyncio
async def test_insert_record_unknown_db_raises_keyerror(tmp_path):
    store = _make_store(tmp_path)
    with pytest.raises(KeyError):
        await store.insert_record(
            "idb-no-exist",
            data={"x": 1},
            source={"workflowId": None, "executionId": None, "warehouseId": None},
        )


# ── 8. list_records 정렬 + 필터 + 페이지네이션 ──────────────────────────


@pytest.mark.asyncio
async def test_list_records_orders_newest_first(tmp_path):
    store = _make_store(tmp_path)
    m = await store.create_meta(name="order-test", tags=[])
    rec_ids = []
    for i in range(5):
        await asyncio.sleep(0.005)
        r = await store.insert_record(
            m["id"],
            data={"i": i},
            source={"workflowId": None, "executionId": None, "warehouseId": None},
        )
        rec_ids.append(r["id"])

    items, total = await store.list_records(m["id"], limit=10, offset=0)
    assert total == 5
    # 가장 최근에 insert 한 것이 맨 앞
    assert items[0]["id"] == rec_ids[-1]
    assert items[-1]["id"] == rec_ids[0]


@pytest.mark.asyncio
async def test_list_records_filter_by_source_workflow_id_and(tmp_path):
    store = _make_store(tmp_path)
    m = await store.create_meta(name="filter-test", tags=[])

    for i in range(2):
        await store.insert_record(
            m["id"],
            data={"i": i},
            source={"workflowId": "wf-A", "executionId": "exec-1", "warehouseId": None},
        )
    await store.insert_record(
        m["id"],
        data={"i": 99},
        source={"workflowId": "wf-B", "executionId": "exec-1", "warehouseId": None},
    )

    items_a, total_a = await store.list_records(
        m["id"], limit=10, offset=0, source_workflow_id="wf-A"
    )
    assert total_a == 2
    assert all((r["_source"]["workflowId"] == "wf-A") for r in items_a)

    # AND 필터
    items_both, total_both = await store.list_records(
        m["id"], limit=10, offset=0, source_workflow_id="wf-B", source_execution_id="exec-1"
    )
    assert total_both == 1
    assert items_both[0]["data"]["i"] == 99


@pytest.mark.asyncio
async def test_list_records_limit_offset(tmp_path):
    store = _make_store(tmp_path)
    m = await store.create_meta(name="paging-test", tags=[])
    for i in range(5):
        await asyncio.sleep(0.005)
        await store.insert_record(
            m["id"],
            data={"i": i},
            source={"workflowId": None, "executionId": None, "warehouseId": None},
        )

    items, total = await store.list_records(m["id"], limit=2, offset=0)
    assert total == 5
    assert len(items) == 2

    items2, total2 = await store.list_records(m["id"], limit=2, offset=2)
    assert total2 == 5
    assert len(items2) == 2

    items3, total3 = await store.list_records(m["id"], limit=2, offset=4)
    assert total3 == 5
    assert len(items3) == 1


@pytest.mark.asyncio
async def test_list_records_unknown_db_raises_keyerror(tmp_path):
    store = _make_store(tmp_path)
    with pytest.raises(KeyError):
        await store.list_records("idb-no-exist", limit=10, offset=0)


# ── 9. 한국어 보존 ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_korean_name_and_description_preserved(tmp_path):
    store = _make_store(tmp_path)
    m = await store.create_meta(
        name="한글 InstanceDB 이름", description="설명입니다", tags=["테스트"]
    )
    re_read = await store.get_meta(m["id"])
    assert re_read["name"] == "한글 InstanceDB 이름"
    assert re_read["description"] == "설명입니다"
    assert re_read["tags"] == ["테스트"]


# ── 10. base_dir 자동 생성 ────────────────────────────────────────────────


def test_store_creates_base_dir_if_missing(tmp_path):
    base = tmp_path / "deeply" / "nested" / "dir"
    assert not base.exists()
    store = InstanceDBStore(base)
    assert base.is_dir()
    assert store.base_dir == base


# ── 11. viewerHints — create → get 매칭 ──────────────────────────────────


@pytest.mark.asyncio
async def test_viewer_hints_create_and_get(tmp_path):
    store = _make_store(tmp_path)
    hints = {"answer_md": "markdown", "category": "tag", "title": "text"}
    meta = await store.create_meta(
        name="hints-test",
        description="viewerHints 포함 생성",
        tags=[],
        viewer_hints=hints,
    )

    assert meta["viewerHints"] == hints

    # get_meta 로 재조회해도 동일
    re_read = await store.get_meta(meta["id"])
    assert re_read is not None
    assert re_read["viewerHints"] == hints


# ── 12. viewerHints 미포함 create → 빈 dict ───────────────────────────────


@pytest.mark.asyncio
async def test_viewer_hints_default_empty_dict(tmp_path):
    store = _make_store(tmp_path)
    meta = await store.create_meta(name="no-hints", tags=[])

    # 생성 시 hints 미지정 → 빈 dict
    assert meta["viewerHints"] == {}

    re_read = await store.get_meta(meta["id"])
    assert re_read is not None
    assert re_read["viewerHints"] == {}


# ── 13. viewerHints update → 반영 ────────────────────────────────────────


@pytest.mark.asyncio
async def test_viewer_hints_update(tmp_path):
    store = _make_store(tmp_path)
    meta = await store.create_meta(name="hints-update", tags=[])
    assert meta["viewerHints"] == {}

    new_hints = {"body": "markdown", "status": "tag"}
    updated = await store.update_meta(meta["id"], viewerHints=new_hints)
    assert updated["viewerHints"] == new_hints

    # 재조회 확인
    re_read = await store.get_meta(meta["id"])
    assert re_read["viewerHints"] == new_hints
