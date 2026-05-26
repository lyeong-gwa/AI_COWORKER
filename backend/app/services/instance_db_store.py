"""InstanceDB 파일시스템 스토어 — 1 InstanceDB = 1 폴더, 1 record = 1 JSON.

설계서: ``docs/instance-db-fs-redesign.md`` (SSoT).

폴더 구조::

    backend/data/instance_dbs/
      {db_id}/                     # db_id = idb-{8hex}
        meta.json                  # 메타 (name, description, tags, 시각)
        rec-{8hex}.json            # record 본체
        ...

원자성:
- 쓰기는 모두 ``write-then-rename`` 패턴 (``.tmp`` → ``os.replace``).
- Windows 에서도 ``os.replace`` 는 atomic rename 을 보장한다.

동시성:
- FastAPI 단일 워커 가정. 프로세스 내 ``asyncio.Lock`` 1개로 모든 쓰기 직렬화.
- 토이 부하 가정이므로 단일 lock 으로 충분 (테이블 락 수준).

검증 없음:
- record.data 는 자유 JSON. JSON Schema 검증 없음 (구 설계 폐기).
- dedup_key 없음. 중복 차단은 노드/사용자 책임.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import uuid
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ── ID 생성 ────────────────────────────────────────────────────────────────


def _new_db_id() -> str:
    return f"idb-{uuid.uuid4().hex[:8]}"


def _new_record_id() -> str:
    return f"rec-{uuid.uuid4().hex[:8]}"


# ── 시각 ──────────────────────────────────────────────────────────────────


def _utcnow_iso() -> str:
    return datetime.utcnow().isoformat()


# ── 파일명 ─────────────────────────────────────────────────────────────────

_META_FILE = "meta.json"
_REC_PREFIX = "rec-"
_REC_SUFFIX = ".json"
_REC_NAME_RE = re.compile(r"^rec-[a-f0-9]{8}\.json$", re.IGNORECASE)


# ── Store ─────────────────────────────────────────────────────────────────


class InstanceDBStore:
    """파일시스템 기반 InstanceDB store.

    경로 결정:
    - ``__init__(base_dir=Path)`` 로 명시 지정.
    - 의존성 주입용 ``get_instance_db_store()`` 가 ``settings.INSTANCE_DB_DIR``
      env 값으로 인스턴스를 생성한다.
    """

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()

    # ── 내부 경로 헬퍼 ───────────────────────────────────────────────────

    def _db_dir(self, db_id: str) -> Path:
        return self.base_dir / db_id

    def _meta_path(self, db_id: str) -> Path:
        return self._db_dir(db_id) / _META_FILE

    def _record_path(self, db_id: str, rec_id: str) -> Path:
        return self._db_dir(db_id) / f"{rec_id}{_REC_SUFFIX}"

    # ── 원자적 쓰기 ──────────────────────────────────────────────────────

    @staticmethod
    def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
        """``payload`` 를 ``path`` 에 원자적으로 기록한다 (tmp + os.replace)."""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        # ensure_ascii=False — 한국어 보존
        data = json.dumps(payload, ensure_ascii=False, indent=2)
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(data)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass  # fsync 실패는 무시 (Windows tmp 일부)
        os.replace(tmp, path)

    @staticmethod
    def _read_json(path: Path) -> Optional[Dict[str, Any]]:
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return None

    # ── 메타 CRUD ────────────────────────────────────────────────────────

    async def create_meta(
        self,
        *,
        name: str,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        viewer_hints: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """메타 1건 생성. name 중복 시 ``ValueError``.

        반환: ``meta.json`` 의 내용 dict.
        """
        name = (name or "").strip()
        if not name:
            raise ValueError("name must not be empty")

        async with self._lock:
            # name 중복 검사 (전수 스캔)
            for existing in self._iter_meta_sync():
                if existing.get("name") == name:
                    raise ValueError(f"duplicate name: {name}")

            db_id = _new_db_id()
            # uuid 충돌 가드 (사실상 무시 가능하지만 명시)
            while self._db_dir(db_id).exists():
                db_id = _new_db_id()

            now = _utcnow_iso()
            meta = {
                "id": db_id,
                "name": name,
                "description": description,
                "tags": list(tags or []),
                "viewerHints": dict(viewer_hints) if viewer_hints else {},
                "createdBy": "cli",
                "createdAt": now,
                "updatedAt": now,
            }
            self._atomic_write_json(self._meta_path(db_id), meta)
            return meta

    async def list_meta(self, q: Optional[str] = None) -> List[Dict[str, Any]]:
        """전체 메타 목록을 createdAt 내림차순으로 반환.

        ``q`` 가 주어지면 name/description 부분 일치 (대소문자 무시).
        """
        items = list(self._iter_meta_sync())
        if q:
            needle = q.lower()
            filtered: List[Dict[str, Any]] = []
            for m in items:
                name = (m.get("name") or "").lower()
                desc = (m.get("description") or "").lower()
                if needle in name or needle in desc:
                    filtered.append(m)
            items = filtered
        # 최신순 — createdAt ISO 문자열 사전식 내림차순
        items.sort(key=lambda m: m.get("createdAt") or "", reverse=True)
        return items

    async def get_meta(self, db_id: str) -> Optional[Dict[str, Any]]:
        meta = self._read_json(self._meta_path(db_id))
        if meta is not None and "viewerHints" not in meta:
            meta["viewerHints"] = {}
        return meta

    async def update_meta(self, db_id: str, **fields: Any) -> Dict[str, Any]:
        """메타 부분 갱신. 지원 필드: ``name``, ``description``, ``tags``, ``viewerHints``.

        존재하지 않으면 ``KeyError``. name 중복 시 ``ValueError``.
        기존 meta.json 에 ``viewerHints`` 가 없으면 빈 dict 로 forward compat.
        """
        async with self._lock:
            meta = self._read_json(self._meta_path(db_id))
            if meta is None:
                raise KeyError(db_id)

            # forward compat — 구 meta.json 에 viewerHints 없으면 빈 dict 보충
            if "viewerHints" not in meta:
                meta["viewerHints"] = {}

            new_name = fields.get("name")
            if new_name is not None:
                new_name = str(new_name).strip()
                if not new_name:
                    raise ValueError("name must not be empty")
                if new_name != meta.get("name"):
                    for existing in self._iter_meta_sync():
                        if existing.get("id") == db_id:
                            continue
                        if existing.get("name") == new_name:
                            raise ValueError(f"duplicate name: {new_name}")
                meta["name"] = new_name

            if "description" in fields:
                meta["description"] = fields["description"]
            if "tags" in fields:
                tags = fields["tags"]
                meta["tags"] = list(tags) if tags is not None else []
            if "viewerHints" in fields:
                hints = fields["viewerHints"]
                meta["viewerHints"] = dict(hints) if hints is not None else {}

            meta["updatedAt"] = _utcnow_iso()
            self._atomic_write_json(self._meta_path(db_id), meta)
            return meta

    async def delete_db(self, db_id: str) -> None:
        """폴더 통째 삭제. 존재하지 않으면 ``KeyError``."""
        async with self._lock:
            db_dir = self._db_dir(db_id)
            if not db_dir.exists() or not self._meta_path(db_id).exists():
                raise KeyError(db_id)
            shutil.rmtree(db_dir)

    # ── records ──────────────────────────────────────────────────────────

    async def insert_record(
        self,
        db_id: str,
        *,
        data: Dict[str, Any],
        source: Dict[str, Any],
    ) -> Dict[str, Any]:
        """record 1건 추가. 폴더 부재 시 ``KeyError``.

        ``source`` 는 ``{workflowId, executionId, warehouseId}`` 의 부분/전체.
        없거나 None 인 키는 그대로 유지된다.

        반환: 저장된 record dict (id, data, _source, createdAt 포함).
        """
        async with self._lock:
            # 메타 존재 검증
            if not self._meta_path(db_id).exists():
                raise KeyError(db_id)

            rec_id = _new_record_id()
            while self._record_path(db_id, rec_id).exists():
                rec_id = _new_record_id()

            now = _utcnow_iso()
            payload = {
                "id": rec_id,
                "data": data if isinstance(data, dict) else {"value": data},
                "_source": {
                    "workflowId": source.get("workflowId"),
                    "executionId": source.get("executionId"),
                    "warehouseId": source.get("warehouseId"),
                },
                "createdAt": now,
            }
            self._atomic_write_json(self._record_path(db_id, rec_id), payload)
            return payload

    async def list_records(
        self,
        db_id: str,
        *,
        limit: int,
        offset: int,
        source_workflow_id: Optional[str] = None,
        source_execution_id: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """createdAt 내림차순. ``source_*`` 필터는 in-memory AND.

        반환: ``(items, total)``. ``items`` 는 limit/offset 적용.
        폴더 부재 시 ``KeyError``.
        """
        if not self._meta_path(db_id).exists():
            raise KeyError(db_id)

        all_records = self._load_all_records(db_id)

        if source_workflow_id is not None:
            all_records = [
                r
                for r in all_records
                if (r.get("_source") or {}).get("workflowId") == source_workflow_id
            ]
        if source_execution_id is not None:
            all_records = [
                r
                for r in all_records
                if (r.get("_source") or {}).get("executionId") == source_execution_id
            ]

        all_records.sort(key=lambda r: r.get("createdAt") or "", reverse=True)
        total = len(all_records)
        sliced = all_records[offset : offset + limit]
        return sliced, total

    async def get_record(
        self, db_id: str, rec_id: str
    ) -> Optional[Dict[str, Any]]:
        if not self._meta_path(db_id).exists():
            raise KeyError(db_id)
        return self._read_json(self._record_path(db_id, rec_id))

    # ── 내부 스캐너 ──────────────────────────────────────────────────────

    def _iter_meta_sync(self) -> List[Dict[str, Any]]:
        """``base_dir`` 의 모든 ``{db_id}/meta.json`` 을 로드."""
        out: List[Dict[str, Any]] = []
        if not self.base_dir.exists():
            return out
        for child in self.base_dir.iterdir():
            if not child.is_dir():
                continue
            meta = self._read_json(child / _META_FILE)
            if meta is None:
                continue
            # forward compat — 구 meta.json 에 viewerHints 없으면 빈 dict 보충
            if "viewerHints" not in meta:
                meta["viewerHints"] = {}
            out.append(meta)
        return out

    def _load_all_records(self, db_id: str) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        db_dir = self._db_dir(db_id)
        if not db_dir.exists():
            return out
        for child in db_dir.iterdir():
            if not child.is_file():
                continue
            if not _REC_NAME_RE.match(child.name):
                continue
            rec = self._read_json(child)
            if rec is None:
                continue
            out.append(rec)
        return out


# ── 싱글톤 + DI 헬퍼 ───────────────────────────────────────────────────────


def _resolve_base_dir() -> Path:
    """settings 또는 env 에서 base 경로 해석. 상대 경로는 backend/ 기준."""
    from ..core.config import settings, _BACKEND_DIR

    raw = getattr(settings, "INSTANCE_DB_DIR", None) or os.environ.get(
        "INSTANCE_DB_DIR"
    )
    if not raw:
        raw = "./data/instance_dbs"
    path = Path(raw)
    if not path.is_absolute():
        path = Path(_BACKEND_DIR) / path
    return path


@lru_cache(maxsize=1)
def _cached_store() -> InstanceDBStore:
    return InstanceDBStore(_resolve_base_dir())


def get_instance_db_store() -> InstanceDBStore:
    """FastAPI 의존성 + 노드 핸들러 공용 접근자.

    테스트는 ``reset_instance_db_store_cache()`` 로 캐시를 무효화하고
    ``INSTANCE_DB_DIR`` env 를 변경한 뒤 다시 호출하면 새 인스턴스를 얻는다.
    """
    return _cached_store()


def reset_instance_db_store_cache() -> None:
    """테스트 격리용 — 캐시된 store 싱글톤을 초기화."""
    _cached_store.cache_clear()


__all__ = [
    "InstanceDBStore",
    "get_instance_db_store",
    "reset_instance_db_store_cache",
]
