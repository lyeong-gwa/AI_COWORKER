# InstanceDB 파일시스템 재설계 종합 설계서

**작성일:** 2026-05-12
**작성자:** Planner (oh-my-claudecode)
**상태:** 완료 (Phase 1-7 전부 architect 승인, 2026-05-12)

---

## 1. 배경과 목표

### 1.1 현재 구조 (제거 대상)

| 구분 | 현재 |
|------|------|
| 저장소 | SQLite 2테이블 (`instance_dbs`, `instance_db_records`) |
| 메타 | name·description·**schema**·tags |
| record | id·instance_db_id·data·**dedup_key**·source_*·created_at |
| 검증 | JSON Schema 강제 (등록 시 빈 객체 거부, insert 시 jsonschema.validate) |
| 중복 차단 | 부분 유니크 인덱스 + SHA1 dedup_key 해시 |
| 노드 | `instance-db-insert` (sourceMode·dedupKey·skipOnDuplicate·schema 검증), `instance-db-lookup` (by_key·filter 모드) |

### 1.2 새 구조 (목표)

> **1 InstanceDB = 1 폴더, 1 record = 1 JSON 파일. JSON Schema·dedup_key 제거.**

```
backend/data/instance_dbs/
  {db_id}/
    meta.json                  # 메타 (name, description, tags, 시각)
    rec-{8자hex}.json          # record 1
    rec-{8자hex}.json          # record 2
```

### 1.3 사용자 확정 결정 (인터뷰 결과)

| 항목 | 결정 |
|------|------|
| 저장 형태 | 폴더(`{db_id}/`) + record 파일(`rec-{uuid}.json`) |
| JSON Schema 검증 | **제거** (자유 JSON) |
| dedup_key | **제거** — 파일명은 무조건 `rec-{uuid}`, 중복 차단은 노드 책임 |
| 출처 추적 | record JSON 내부 `_source` 메타로 유지 |
| 마이그레이션 | **데이터 폐기** — 운영DB 1건(records 0)도 잔재로 보고 삭제 |
| config 호환성 | **과감히 정리** — `dedupKeyTemplate`, `skipOnDuplicate` 등 제거, catalog 재정의 |

---

## 2. 데이터 모델

### 2.1 `meta.json`

```json
{
  "id": "idb-a1b2c3d4",
  "name": "inquiries",
  "description": "ITO 문의글 컬렉션",
  "tags": ["문의", "ito"],
  "createdBy": "cli",
  "createdAt": "2026-05-12T03:00:00.000000",
  "updatedAt": "2026-05-12T03:00:00.000000"
}
```

### 2.2 `rec-{uuid}.json`

```json
{
  "id": "rec-a1b2c3d4",
  "data": {
    "title": "서버 장애",
    "state": "신규"
  },
  "_source": {
    "workflowId": "wf-cb35a866",
    "executionId": "exec-8e14b83e",
    "warehouseId": null
  },
  "createdAt": "2026-05-12T03:00:01.123456"
}
```

- `_source` 각 필드는 null 허용. `instance-db-insert` 노드가 실행 컨텍스트에서 자동 채움.
- `data`는 자유 JSON. 검증 없음.

---

## 3. API 변경

### 3.1 REST 엔드포인트

| 메서드 | 경로 | 변경 |
|--------|------|------|
| POST | `/api/v1/instance-dbs` | 요청에서 `schema` 필드 제거. 응답에서 `schema` 키 제거. |
| GET  | `/api/v1/instance-dbs` | 응답에서 `schema` 키 제거. q 검색은 메타 폴더 스캔 기반. |
| GET  | `/api/v1/instance-dbs/{id}` | 동일 |
| PUT  | `/api/v1/instance-dbs/{id}` | `schema` 필드 제거 |
| DELETE | `/api/v1/instance-dbs/{id}` | 폴더 삭제. 참조 검증 + force 옵션 유지 |
| GET  | `/api/v1/instance-dbs/{id}/records` | `dedupKey` 쿼리 제거. `sourceWorkflowId`/`sourceExecutionId` 유지 (record._source 기반 in-memory 필터). |
| GET  | `/api/v1/instance-dbs/{id}/records/{rid}` | 동일 |

### 3.2 응답 형식 (camelCase 유지)

```json
{
  "id": "idb-a1b2c3d4",
  "name": "inquiries",
  "description": "...",
  "tags": [...],
  "createdBy": "cli",
  "createdAt": "...",
  "updatedAt": "..."
}
```

record 응답에서 `dedupKey` 필드 제거. `sourceWorkflowId`/`sourceExecutionId`/`sourceWarehouseId`는 `_source`에서 직렬화.

---

## 4. 노드 핸들러 변경

### 4.1 `instance-db-insert`

**제거:** `dedupKeyTemplate`, `skipOnDuplicate`, JSON Schema 검증

**유지:**
- `instanceDbId` (필수)
- `sourceMode`: `warehouse` | `input` | `auto`
- `dataTemplate` (input 모드)

**동작:**
1. InstanceDB 폴더 존재 확인 (없으면 ValueError)
2. sourceMode 분기로 `record_data` 결정
3. `rec-{uuid}.json` 생성: `id`, `data=record_data`, `_source={workflowId, executionId, warehouseId}`, `createdAt`
4. 원자적 write+rename
5. 출력: `{ recordId: str, instanceDbId: str }`

### 4.2 `instance-db-lookup`

**제거:** `by_key` 모드, `keyTemplate`

**유지:**
- `instanceDbId` (필수)
- `filterTemplate` (선택, 비어있으면 전체 매칭)
- `limit` (default 10)
- 동작: `mode` config 키 폐기 — filter만 남음

**동작:**
1. InstanceDB 폴더 존재 확인
2. `rec-*.json` 폴더 스캔 (최신순 정렬, mtime 기준)
3. 각 record 로드 후 `_matches_filter(record.data, rendered_filter)` AND 평가
4. limit 도달 또는 폴더 끝까지
5. 출력: `{ found, count, record, records, instanceDbId }` (포맷 동일)

### 4.3 Sorter 노드

`config.rules[*].dataSource == 'instance-db'` 인 rule의 `instanceDbId` 참조 검사는 그대로. 단 rule이 dedup_key를 활용하는 패턴이 있다면 그것은 제거 대상 — 코드 확인 필요.

---

## 5. 스토리지 레이어 (신규 모듈)

### 5.1 `app/services/instance_db_store.py`

파일시스템 기반 store. 노드 핸들러·라우트가 공통으로 사용.

```python
class InstanceDBStore:
    def __init__(self, base_dir: Path): ...

    # 메타 CRUD
    def create_meta(self, name, description, tags) -> dict: ...
    def list_meta(self, q: str | None = None) -> list[dict]: ...
    def get_meta(self, db_id: str) -> dict | None: ...
    def update_meta(self, db_id: str, **fields) -> dict: ...
    def delete_db(self, db_id: str) -> None: ...   # 폴더 통째

    # records
    def insert_record(self, db_id: str, data: dict, source: dict) -> dict: ...
    def list_records(self, db_id: str, *, limit, offset,
                     source_workflow_id=None, source_execution_id=None) -> tuple[list[dict], int]: ...
    def get_record(self, db_id: str, rec_id: str) -> dict | None: ...
```

**경로 결정:**
- 기본: `backend/data/instance_dbs/`
- 환경변수 override: `INSTANCE_DB_DIR` (테스트에서 tmp 폴더 주입용)

**동시성:**
- FastAPI 단일 워커 가정. 프로세스 내 `asyncio.Lock` 1개로 폴더 단위 직렬화 (테이블 락 수준).
- 쓰기는 `write-then-rename` 패턴 (`.tmp` → rename) 으로 원자성 확보.
- 토이 프로젝트 부하 가정이므로 lock 입도는 store 1개로 충분.

**검색 (q 파라미터):**
- 모든 `*/meta.json` 스캔. name·description 부분 일치.
- 폴더 수가 백 단위면 충분히 빠름.

---

## 6. 마이그레이션

### 6.1 Alembic 마이그레이션

- 새 revision 1개: `instance_dbs`, `instance_db_records` 테이블 drop
- 운영DB의 잔재 1건(idb-6d52e5f9)도 자연스럽게 폐기

### 6.2 데이터 이전

**없음.** 운영 records 0건 + 잔재 1건만 존재. 폐기 결정.

`backend/data/instance_dbs/` 폴더는 빈 상태로 시작.

### 6.3 코드 정리 대상

| 파일 | 처리 |
|------|------|
| `app/models/instance_db.py` | **삭제** |
| `app/schemas/instance_db.py` | 재작성 (schema·dedupKey 필드 제거) |
| `app/api/routes/instance_dbs.py` | 재작성 (store 의존) |
| `app/nodes/action/instance_db_insert.py` | 재작성 |
| `app/nodes/action/instance_db_lookup.py` | 재작성 |
| `app/nodes/catalog.py` | instance-db-* 카탈로그 정의 갱신 |
| `app/nodes/common.py` | `compute_dedup_key` 사용처 검토 → 미사용이면 제거 |
| `app/nodes/logic/sorter.py` | instance-db 데이터소스 rule의 dedup 의존 검사·정리 |
| `app/core/database.py` | InstanceDB import 라인 제거 |
| `app/services/instance_db_store.py` | **신규 작성** |

---

## 7. Phase 분할

### Phase 1 — 스토어·모델·마이그레이션 (executor)

- `app/services/instance_db_store.py` 신규 작성 (lock·write-then-rename·폴더 스캔)
- `app/schemas/instance_db.py` 재작성 (schema_·dedupKey 필드 제거)
- `app/models/instance_db.py` 삭제 + `database.py`·`__init__.py` import 정리
- Alembic 마이그레이션 추가 (테이블 drop)
- 단독 store 유닛테스트 신규 작성 (`tests/test_instance_db_store.py`)

**검증:** store 유닛테스트 통과.

### Phase 2 — 라우트 (executor)

- `app/api/routes/instance_dbs.py` 재작성. 메타 CRUD 5 + records GET 2.
- 참조 차단(`_count_workflow_references`) 로직 유지.
- `test_instance_dbs_api.py` 갱신.

**검증:** API 테스트 통과 + 운영 8002 재기동 후 curl 시나리오.

### Phase 3 — 노드 핸들러 + catalog (executor)

- `instance_db_insert.py` / `instance_db_lookup.py` 재작성.
- `app/nodes/catalog.py` instance-db-* 정의 갱신.
- `compute_dedup_key` 미사용 확인 후 제거 (또는 보존하되 라우트/노드에서만 분리).
- `test_instance_db_insert_handler.py` / `test_instance_db_lookup_handler.py` 갱신.

**검증:** 노드 테스트 통과 + 전체 회귀 105개 유지.

### Phase 4 — 테스트 격리 (executor)

- `tests/conftest.py` 또는 fixture에 `INSTANCE_DB_DIR` env override → tmp 폴더
- 기존 instance_db 관련 테스트가 운영 `data/instance_dbs/` 와 분리되어 동작하도록 보장
- 잔재 누적 가능성 차단

**검증:** 테스트 실행 후 `backend/data/instance_dbs/` 변화 없음 확인.

### Phase 5 — 프론트엔드 (designer)

- 인스턴스DB 목록·상세 화면이 `schema` 필드 제거된 응답 처리
- records 조회 화면의 `dedupKey` 컬럼·필터 제거
- TypeScript 타입 갱신

**검증:** `npm run build` 0 에러 + Playwright E2E (기존 5개 시나리오) 통과.

### Phase 6 — 문서·메모리 (writer + 직접)

- 본 설계서 status를 `완료`로 갱신
- `CLAUDE.md` 노드 표·플로우의 instance-db-* config 키 정정
- `ORCHESTRATION.md` 영향 없음 (C3 계약 무변) — 변경 로그만 추가
- 메모리: `project_ai_assistant_redesign.md` 보강

### Phase 7 — Architect 검증

- 회귀 105개 통과 evidence
- 운영 8002 재기동 후 메타 등록 → record 적재 → 조회 smoke test
- `backend/data/instance_dbs/` 폴더 구조 직접 확인
- 잔재(`테스트 InstanceDB` 같은) 0건 확인

---

## 8. 영향받는 외부 문서

| 파일 | 변경 라인 |
|------|----------|
| `AI 업무도우미/CLAUDE.md` | §4 노드 표의 `instance-db-insert`/`instance-db-lookup` 한 줄 용도 정정. §5.3 인스턴스DB CRUD 섹션의 응답 형식 정정 (schema 키 제거). |
| `ORCHESTRATION.md` | 변경 로그 한 줄 추가 (2026-05-12 [변경] InstanceDB 파일시스템 재설계 완료) |
| `AI 업무도우미/docs/redesign-plan.md` | 후속 변경 이력 한 단락 추가 |

---

## 9. 리스크와 대응

| 리스크 | 대응 |
|--------|------|
| 워크플로우가 `instance-db-insert` config의 제거된 키(`dedupKeyTemplate` 등)를 들고 있어 실행 실패 | 핸들러에서 제거된 키는 무시(warn 로그만) + 마이그레이션 시 운영 워크플로우 점검 |
| Sorter rule이 dedup_key 의존 | 코드 grep으로 사전 식별 + Phase 3에서 함께 정리 |
| 파일시스템 동시성 (중복 쓰기) | asyncio.Lock + write-then-rename. 토이 부하라 단일 lock으로 충분 |
| 테스트가 운영 폴더 오염 | Phase 4에서 env override fixture 강제 |
| 폴더명 충돌 (특수문자 name) | name은 한국어 허용이므로 폴더명에 직접 쓰지 않음 — `idb-{uuid}` 만 폴더로. name은 meta.json 안에. |

---

## 10. 호환성·롤백

- Alembic 마이그레이션은 단방향 drop. 롤백 필요 시 backup → restore. 운영 데이터 0건이라 실질 손실 없음.
- 워크플로우 호환: 기존 운영 워크플로우 중 instance-db-* 노드를 쓰는 것이 있는지 사전 점검 (현재 없을 것으로 추정 — 잔재 1건의 records가 0이므로).

---

## 11. 완료 기준

- [x] 전체 회귀 120개 테스트 통과
- [x] 새 store 유닛테스트 신규 추가분 통과 (18개)
- [x] `backend/data/instance_dbs/` 디렉토리 구조 정상 (architect smoke test)
- [x] 운영 8002 재기동 후 메타 + record CRUD smoke test 정상 (architect 직접 수행)
- [x] 잔재 0건 (`instance_dbs` 테이블 부재 + 폴더 깨끗 + 프론트엔드 dedupKey grep 0)
- [x] CLAUDE.md / docs / ORCHESTRATION.md 갱신
- [x] architect 검증 통과 (APPROVED_WITH_CAVEATS — 본 체크리스트 갱신으로 caveat 해소)
