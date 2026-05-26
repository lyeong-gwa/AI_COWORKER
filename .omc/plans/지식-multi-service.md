# 지식 위키 다중 서비스 확장 계획 (옵션 C)

> **목표 (1줄):** 현재 "CodeEyes 단일 서비스" 가정에 묶인 지식 위키 (66 페이지) 를 **frontmatter `service` 필드 신설 + 카테고리 기능형 재정의**를 통해 다중 서비스·다중 업무 위키로 확장한다.

생성일: 2026-05-26 · 작성자: Prometheus (planner) · 모드: 6시간 자율 실행

---

## 1. 배경 및 현재 상태 (검증된 사실)

| 항목 | 현황 | 근거 |
|---|---|---|
| 총 페이지 수 | 66 | `backend/data/knowledge/` 카테고리 4종 디렉토리 합산 |
| 사실상 서비스 | CodeEyes 1종 | 모든 카테고리가 CodeEyes 도메인 안 |
| 카테고리 enum | `codeeyes` (7) · `ito-portal-operations` (42) · `plugin-troubleshooting` (9) · `faq` (8) | `_schema.yaml:6-18` |
| 카테고리 강제 | `validate_category()` 가 `_schema.yaml.categories` enum 체크 | `knowledge_schema.py:166-179` |
| frontmatter 표준 키 | `title/category/tags/source/created` + Karpathy v2 의 `page_type/version/links/raw_source_id` | `knowledge_file_service.py:225-229` |
| 검색 노드 필터 | `category` 단일 또는 `categories` 다중 (`$in`) | `nodes/action/knowledge.py:87-89` |
| 브리핑 필터 | `categories` 다중 지원 | `services/knowledge_brief.py:144,166` |
| 그래프 필터 | `selectedCategory` 단일 | `pages/KnowledgeGraphPage.tsx:191` |

**문제:** 현재 4종 카테고리는 모두 CodeEyes 서비스의 하위 분류. "다른 서비스(예: GitHub 자동화, Jira 운영)" 가 추가되면 카테고리가 서비스 축과 기능 축에 혼재되어 RAG 정밀도와 사이드바 가독성이 동시에 무너진다.

---

## 2. 확정된 사용자 결정 (D1 ~ D7)

| # | 결정 | 한 줄 근거 |
|---|---|---|
| **D1** | frontmatter 에 `service` 필드 신설. **1 페이지 = 1 service.** | RAG / 사이드바 / 그래프 모두에서 1차 분류 키로 활용. multi-service 페이지는 cross-service link 로 표현. |
| **D2** | 카테고리는 **기능형**으로 재정의 (서비스명이 아니라 콘텐츠 종류). | 같은 기능 카테고리(`faq`, `troubleshooting`)가 여러 서비스에 공통 적용 가능. |
| **D3** | 기존 66 페이지 **전량 자동 마이그레이션** (LLM 으로 `service=codeeyes` 일괄 부여 + 카테고리는 기능형 매핑). | 운영 중단 0. 백업 후 일괄 적용. |
| **D4** | `service` enum 강제. `_schema.yaml` 의 새 `services:` 섹션에 정의된 것만 허용. 미정의 service 추가는 **운영자가 schema 편집**. | 무분별한 service 난립 방지. categories 와 동일 정책. |
| **D5** | 검색 / 브리핑 / 그래프 **모두 `service` 필터 지원**. | 단일 서비스 작업 컨텍스트에서 노이즈 차단. |
| **D6** | UI 사이드바 = **서비스 → 카테고리 → 페이지** 3단 계층. | 다중 서비스 환경에서 인지 부하 최소화. |
| **D7** | cross-service `[[link]]` **허용**. 단 그래프에서 색상/스타일 구분. | 서비스간 참조는 통합 워크플로우 설계 시 필수. 격리는 색상으로 표현. |

---

## 3. 본 plan 작성 중 결정한 default (D8 ~ D14)

| # | 결정 | 근거 |
|---|---|---|
| **D8** | 초기 service enum = `["codeeyes"]` (단 1종) 로 시작. 새 서비스 추가는 운영자가 `_schema.yaml` 편집 + reload API 호출. | D3 의 일괄 마이그레이션과 정합. 신규 service 는 실 수요 발생 시 추가. |
| **D9** | 신규 functional category enum 6종 = `["overview", "operations-guide", "troubleshooting", "faq", "integration", "policy"]`. | 현재 66 페이지를 분류 가능한 최소 셋. 기존 4종에 사실상 매핑됨. `member-management/installation` 등 세분화는 운영 중 필요 시 schema 편집으로 추가 (D4 와 동일 정책). |
| **D10** | 기존 카테고리 → 신 카테고리 매핑 규칙 (LLM 1차 분류 후 사람 spot-check):<br>• `codeeyes` (7) → `overview` (기본) · 일부 `integration`<br>• `ito-portal-operations` (42) → `operations-guide` (대부분) · `policy` (권한/규칙류) · `integration` (방화벽/연동류)<br>• `plugin-troubleshooting` (9) → `troubleshooting`<br>• `faq` (8) → `faq` | 파일명 prefix·키워드 기반 휴리스틱 + LLM 보정. |
| **D11** | **page id 형식 변경 없음.** 기존 `{category}/{slug}` 유지. service 는 frontmatter 안에서만 산다. | id 변경 시 모든 `[[link]]` 파괴. ROI 부정적. service 는 query 시 필터로만 활용. |
| **D12** | 디렉토리 구조 변경 없음. `data/knowledge/{category}/{slug}.md` 유지. (서비스별 sub-directory 만들지 않음.) | D11 과 동일 이유 + `list_md_files()` 재귀 깊이 안 늘어남. |
| **D13** | 마이그레이션 백업 = `backend/data/knowledge.backup-{YYYYMMDD-HHmm}/` 디렉토리 전체 복사. ChromaDB 도 `backend/data/chroma.backup-...` 로 복사. | 가역성 보장. Phase 5 검증 통과 후 30 일 뒤 삭제. |
| **D14** | service 필드 미존재(legacy) 페이지 → 런타임에서 `service = "unknown"` default. 검증 layer 는 **POST/PUT 시점에만 강제**. 기존 페이지 강제 거부 안 함. | Karpathy v2 의 page_type default 정책과 동일. 점진적 마이그레이션 호환. |

---

## 4. Must / Must NOT (가드레일)

### Must
- [ ] `_schema.yaml` 에 `services:` 섹션 추가 (D4)
- [ ] `KnowledgeFileDoc` 에 `service: str = "unknown"` 필드 추가
- [ ] `KnowledgeCreate` 에 `service: str` 필수 / `KnowledgeUpdate` 에 `service: Optional[str]`
- [ ] `validate_service()` 함수 신설 (categories 와 동일 패턴)
- [ ] `POST /knowledge` 와 `PUT /knowledge/{id}` 에서 service enum 검증 wiring (422 강제)
- [ ] `GET /knowledge?service=X` 필터 파라미터 추가
- [ ] `knowledge` 노드 config 에 `services: List[str]` 지원 (기존 `categories` 와 동일 패턴)
- [ ] `knowledge_brief.build_brief()` 에 `services` 파라미터 추가
- [ ] ChromaDB metadata 에 `service` 키 추가 (재인덱싱 필요)
- [ ] 사이드바 3단 계층 렌더 (서비스 → 카테고리 → 페이지)
- [ ] 그래프 페이지에서 service 필터 + service 별 노드 색상
- [ ] `ServiceBadge` 컴포넌트 (PageTypeBadge 와 동일 패턴)
- [ ] 마이그레이션 스크립트 `backend/scripts/migrate_service_field.py`
- [ ] 백업 디렉토리 자동 생성 (D13)
- [ ] Phase 별 자동 검증 (acceptance criteria) 통과 시점에만 다음 Phase 진입

### Must NOT
- [ ] **page id 형식 변경 금지** (D11) — `[[link]]` 파괴 방지
- [ ] **디렉토리 구조 변경 금지** (D12) — `data/knowledge/{category}/{slug}.md` 그대로
- [ ] **`workflow_engine.py` 수정 금지** (CLAUDE.md §9.5)
- [ ] **하위호환 깨기 금지** — legacy 페이지 (service 누락) 도 조회/검색 동작
- [ ] **`position/viewport` 부활 금지** (CLAUDE.md §9.4)
- [ ] **카테고리/서비스 enum 을 코드에 하드코딩 금지** — 항상 `_schema.yaml` 통해서만 정의
- [ ] **신규 도메인 특화 노드 신설 금지** — service 필터는 기존 `knowledge` 노드 config 확장으로
- [ ] **63개 백엔드 테스트 깨기 금지** — Phase 별 회귀 확인 필수

---

## 5. 데이터 모델 변경

### 5.1 `_schema.yaml` (확장)

```yaml
# data/knowledge/_schema.yaml
version: 3                    # bump (was 2)
schema_owner: human
last_curated: 2026-05-26

services:                     # NEW (D1, D4)
  - id: codeeyes
    title: CodeEyes 소스코드 검증
    description: CodeEyes 서비스/시스템/지침 전반
    color: "#3b82f6"          # 그래프 노드 색 (D7)

categories:                   # 기능형으로 재정의 (D2, D9)
  - id: overview
    title: 개요
    description: 서비스/시스템 전반 소개
  - id: operations-guide
    title: 운영 가이드
    description: 절차·플로우·일상 운영 가이드
  - id: troubleshooting
    title: 트러블슈팅
    description: 오류·장애·해결법
  - id: faq
    title: FAQ
    description: 자주 묻는 질문
  - id: integration
    title: 연동/통합
    description: 외부 시스템 연동·방화벽·API 통합
  - id: policy
    title: 정책/규칙
    description: 권한·규칙·승인 기준 등 정책류

page_types: (변경 없음 — Karpathy v2 5종 유지)
link_policy: (변경 없음)
filename_policy: (변경 없음)
```

### 5.2 `KnowledgeFileDoc` (dataclass 확장)

```python
# backend/app/services/knowledge_file_service.py
@dataclass
class KnowledgeFileDoc:
    id: str
    title: str
    content: str
    category: str = ""
    service: str = "unknown"   # NEW (D14)
    page_type: str = "Summary"
    tags: List[str] = field(default_factory=list)
    source: str = ""
    raw_source_id: Optional[str] = None
    version: int = 1
    links: List[str] = field(default_factory=list)
    created: str = ""
    updated: str = ""
    content_hash: str = ""
    sync_status: str = "not_synced"
    extra_metadata: Dict[str, Any] = field(default_factory=dict)
```

- `_STANDARD_KEYS` 에 `"service"` 추가 (`knowledge_file_service.py:225-229`).
- `build_md_file()` 가 `service` 인자를 받아 frontmatter 에 보존.
- `list_md_files()` / `read_md_file()` 가 `metadata.get("service", "unknown")` 으로 채움.

### 5.3 `KnowledgeCreate` / `KnowledgeUpdate` (pydantic 확장)

```python
class KnowledgeCreate(BaseModel):
    title: str
    content: str
    service: str = Field(..., min_length=1, description="_schema.yaml services enum")  # NEW
    category: str = Field(..., min_length=1)
    slug: str
    page_type: PageType
    tags: List[str] = []
    ...

class KnowledgeUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    service: Optional[str] = None     # NEW
    category: Optional[str] = None
    ...
```

### 5.4 ChromaDB metadata

기존 `{category, title, ...}` 에 `service` 키 추가. 재인덱싱 1회 필요 (Phase 4 의 마이그레이션 마지막 단계).

---

## 6. API 변경

### 6.1 POST `/api/v1/knowledge` (강제 검증 wiring)

```python
# backend/app/api/routes/knowledge.py
try:
    validate_service(payload.service)      # NEW
    validate_category(payload.category)
    validate_page_type(payload.page_type)
    validate_slug(payload.slug)
except SchemaValidationError as e:
    raise HTTPException(status_code=422, detail=...)
```

### 6.2 PUT `/api/v1/knowledge/{id}` — service 변경 허용 (validate)

### 6.3 GET `/api/v1/knowledge?service={id}&category={id}` — 필터 파라미터

기존 `category` query 와 동일 패턴. 둘 다 동시 사용 가능. `service=codeeyes&category=faq` → AND 결합.

### 6.4 GET `/api/v1/knowledge/services` — 신규 엔드포인트

`_schema.yaml` 의 services 목록을 `[{id, title, description, color, pageCount}]` 로 반환. 사이드바 1단 렌더용. (categories 엔드포인트가 이미 있다고 가정 — 없으면 `list_services()` 헬퍼 신설.)

### 6.5 `knowledge` 노드 config 확장

```python
# backend/app/nodes/action/knowledge.py
# 기존 categories 와 동일 패턴
services_raw = config.get('services', [])
if isinstance(services_raw, str):
    services_raw = [services_raw] if services_raw else []

# ChromaDB where_filter 에 service 추가
where_filter = {}
if categories: where_filter['category'] = {'$in': categories} if len(categories) > 1 else categories[0]
if services:   where_filter['service']  = {'$in': services}   if len(services)   > 1 else services[0]
```

`useCases` 와 카탈로그 (`GET /api/v1/nodes/catalog`) 의 `knowledge` 노드 스펙에 `services` 필드 명세 추가.

### 6.6 `knowledge_brief.build_brief()` 시그니처 확장

```python
def build_brief(
    query: str,
    top_k: int = 5,
    categories: Optional[List[str]] = None,
    services: Optional[List[str]] = None,     # NEW
    ...
) -> dict: ...
```

ChromaDB `where_filter` + 비-벡터 fallback 모두에 service 필터 적용 (`knowledge_brief.py:144,166` 와 동일 위치).

### 6.7 그래프 API 응답 metadata

`/api/v1/knowledge/graph` (또는 KnowledgeGraphPage 가 사용하는 엔드포인트) 의 응답 node 객체에 `service` 키 추가. 프론트가 색상 매핑에 사용.

### 6.8 `POST /api/v1/knowledge/schema/reload` (이미 존재 가정)

`_schema.yaml` 편집 후 캐시 무효화 트리거. services 추가 시 호출 (D4 운영 흐름).

---

## 7. 마이그레이션 절차 (66 페이지 일괄 재태깅)

### 7.1 백업 (D13)

```bash
cd backend
cp -r data/knowledge   data/knowledge.backup-$(date +%Y%m%d-%H%M)
cp -r data/chroma      data/chroma.backup-$(date +%Y%m%d-%H%M)
```

### 7.2 마이그레이션 스크립트 — `backend/scripts/migrate_service_field.py`

**책임:**
1. `data/knowledge/` 의 모든 `.md` 파일 스캔 (`_` prefix 제외).
2. 각 페이지의 현 frontmatter 파싱.
3. **service 부여:** 전부 `"codeeyes"` (D3 일괄). 추후 다른 서비스 도입 시 별도 스크립트.
4. **category 재매핑:** D10 규칙 + LLM 보정.
   - 현 category 가 `plugin-troubleshooting` → `troubleshooting` (확정)
   - 현 category 가 `faq` → `faq` (확정)
   - 현 category 가 `codeeyes` → `overview` 기본, 파일명에 `integration`/`api` 포함 시 `integration`
   - 현 category 가 `ito-portal-operations` → **LLM 1회 호출** 로 본문 요약 후 분류:
     - 권한·승인·규칙 → `policy`
     - 방화벽·연동·GitHub → `integration`
     - 그 외 절차/플로우 → `operations-guide`
5. **frontmatter 덮어쓰기** — `service` 추가 + `category` 갱신 + `version +1`.
6. **디렉토리 이동:** 기존 `{old_category}/` 에서 `{new_category}/` 로 파일 이동.
7. **링크 갱신:** `[[old-category/slug]]` → `[[new-category/slug]]` (D11 위반 아님 — id 형식 자체는 그대로, category 가 바뀌므로 slug 앞부분만 치환).
8. **changelog** 적재 (페이지당 KnowledgeChangelogEntry 1건).
9. **ChromaDB 재인덱싱** — 전체 컬렉션 재구축 (`POST /api/v1/knowledge/rebuild-index?categories=null`).
10. **결과 리포트:** `backend/data/knowledge/_migration-multi-service-report.md` 생성.
    - 페이지별 (old_category, new_category, service, 변경 사유) 표
    - 실패 항목 별도 섹션
    - 후속 사람 확인 필요 (spot-check 대상) 표시

**실행 모드:**
- `--dry-run` : 변경 없이 리포트만
- `--apply` : 실제 적용
- `--page-id <id>` : 단일 페이지만 (디버그용)

### 7.3 LLM 호출 견적 (12절 참조)

---

## 8. 프론트엔드 변경

### 8.1 사이드바 3단 계층 (D6)

`pages/KnowledgeViewerPage.tsx` 의 sidebar 영역을 다음 트리로 재구성:

```
[서비스 1: CodeEyes (66)]               ← 1단 (접기 기본 펼침)
  ├─ [overview (8)]                     ← 2단
  │    ├─ codeeyes-service-overview     ← 3단 (페이지)
  │    └─ ...
  ├─ [operations-guide (28)]
  ├─ [policy (10)]
  ├─ [integration (4)]
  ├─ [troubleshooting (9)]
  └─ [faq (8)]
```

- 상태: `expandedServices: Set<string>` + 기존 `expandedCategories: Set<string>`.
- groupBy 로직을 `byCategory: Map<category, docs[]>` → `byService: Map<service, Map<category, docs[]>>` 2중 grouping 으로 확장.
- 각 노드에 페이지 카운트 배지.

### 8.2 `ServiceBadge` 컴포넌트 — `components/knowledge/ServiceBadge.tsx`

- 입력: `service: string`, `color?: string`
- 렌더: 색상 dot + 서비스 title (또는 id).
- 페이지 상세 헤더의 `PageTypeBadge` 옆에 배치.

### 8.3 그래프 페이지 (D5, D7)

- `KnowledgeGraphPage.tsx`:
  - service 필터 셀렉트 추가 (`selectedService` state).
  - 노드 색상: `node.service` → `_schema.yaml` 의 `services[i].color` 매핑.
  - cross-service 엣지: dashed 선 + 양 끝 노드 색상 그라데이션.
  - 범례 (legend) 에 서비스별 색상 표시.

### 8.4 검색 / 필터 (KnowledgeViewerPage)

- 상단 필터 바에 service 다중 선택 (이미 categories 가 있다면 동일 패턴).
- `knownServices` state 신설 (`useEffect` 로 `GET /api/v1/knowledge/services` 호출).
- `rebuildIndex` 호출 시 `{ services: [...], categories: [...] }` 동시 전송 가능.

### 8.5 페이지 등록/편집 모달

- `service` 셀렉트 추가 (필수 입력).
- enum 은 `knownServices` 에서. validation 실패 시 422 응답 표시.

---

## 9. 5 Phase 실행 순서

### Phase 1 — 스키마/모델 백엔드 기반 (no breaking)

**대상 파일:**
- `backend/data/knowledge/_schema.yaml` (services 추가 + categories 재정의를 **enum 확장 mode** 로 — 기존 4 category 도 당분간 유지하여 마이그레이션 전 깨짐 방지)
- `backend/app/services/knowledge_schema.py` — `validate_service()`, `list_services()`, `KnowledgeSchema.services`, `service_ids` property
- `backend/app/services/knowledge_file_service.py` — `KnowledgeFileDoc.service`, `build_md_file(service=...)`, `_STANDARD_KEYS`
- `backend/app/schemas/knowledge.py` — `KnowledgeCreate.service`, `KnowledgeUpdate.service`

**검증:**
- `pytest -q` 63개 그대로 PASS
- 새 테스트: `validate_service()` 단위 (enum miss → 422, schema 부재 → soft pass)
- `_schema.yaml` 로드 캐시 mtime 갱신 동작
- legacy frontmatter (service 누락) 도 list_md_files() 에서 `service="unknown"` 으로 정상 반환

**Acceptance:**
- `python -m pytest backend/tests -q` 0 fail
- `GET /api/v1/knowledge` 응답 각 doc 에 `service: "unknown"` 필드 노출

---

### Phase 2 — API 진입점 wiring + 노드/브리프 필터

**대상 파일:**
- `backend/app/api/routes/knowledge.py` — POST/PUT 에 `validate_service()` 호출, GET 의 `service` query 파라미터, `GET /services` 엔드포인트
- `backend/app/nodes/action/knowledge.py` — config 의 `services` 처리 + ChromaDB where_filter 결합
- `backend/app/services/knowledge_brief.py` — `build_brief(services=...)`
- `backend/app/nodes/catalog.py` — `knowledge` 노드 스펙에 `services` 필드 명세

**검증:**
- 새 통합 테스트:
  - POST 시 `service` 미존재 → 422
  - POST 시 `service` 존재 (codeeyes) → 201 + 저장
  - GET `?service=codeeyes` 필터 동작
  - knowledge 노드 워크플로우 실행 → `services` 필터 결과 검증
- `GET /api/v1/nodes/catalog` 응답에 `services` 필드 명세 포함

**Acceptance:**
- `pytest -q` 63 + 신규 테스트 모두 PASS
- 카탈로그 응답 변경 사항 frontend 빌드 영향 없음 (선택형 필드)

---

### Phase 3 — 프론트엔드 (사이드바 3단, ServiceBadge, 그래프)

**대상 파일:**
- `frontend/src/pages/KnowledgeViewerPage.tsx` — 사이드바 그루핑 로직, service 필터 바, 모달 service 셀렉트
- `frontend/src/components/knowledge/ServiceBadge.tsx` (신규)
- `frontend/src/pages/KnowledgeGraphPage.tsx` — service 필터, 노드 색상, cross-service 엣지 스타일, 범례
- `frontend/src/types/knowledge.ts` (또는 동등) — `service: string` 타입 추가
- `frontend/src/services/knowledgeApi.ts` — `getServices()`, `search/rebuild` 의 `services` 파라미터

**검증:**
- `npm run build` 0 에러 0 warning (warning 무시 정책 없음)
- Playwright 스크린샷 (필수, `_참고자료/screenshots/multi-service-sidebar.png` 등):
  1. 사이드바 3단 트리 펼침 상태
  2. 그래프 색상 구분 (현 시점에는 codeeyes 1색만 보이지만 범례 표시 확인)
  3. 페이지 상세 ServiceBadge 노출
  4. 페이지 편집 모달 service 셀렉트
- TypeScript 컴파일 0 에러

**Acceptance:**
- 위 스크린샷 4종 캡처 완료
- 사이드바에서 서비스/카테고리 노드 클릭 → 페이지 필터링 동작
- 그래프에서 service 필터 변경 시 노드 가시성 변경 동작

---

### Phase 4 — 마이그레이션 (66 페이지 일괄 재태깅)

**전제:** Phase 1~3 완료. backend/frontend 모두 service 필드 처리 가능 상태.

**절차:**
1. `backend/data/knowledge.backup-{ts}/` + `backend/data/chroma.backup-{ts}/` 백업 생성
2. `python backend/scripts/migrate_service_field.py --dry-run` 실행 → `_migration-report.md` 검토
3. 운영자 spot-check (5분):
   - `ito-portal-operations` → policy/integration/operations-guide 분류 결과 5건 무작위 확인
   - 잘못된 분류 발견 시 스크립트의 keyword 규칙 보정
4. `python backend/scripts/migrate_service_field.py --apply` 실행
5. 파일 이동 후 `[[link]]` 자동 갱신 (스크립트 7.2.7)
6. ChromaDB 전체 재인덱싱: `POST /api/v1/knowledge/rebuild-index` (categories=null)
7. `_schema.yaml` 의 **legacy category 4종 삭제** (`codeeyes`, `ito-portal-operations`, `plugin-troubleshooting` 만 — `faq` 는 신 enum 에도 존재). reload.

**검증:**
- 마이그레이션 후 `GET /api/v1/knowledge` 응답:
  - 모든 doc 의 `service == "codeeyes"`
  - 모든 doc 의 `category` 가 신 enum 6종 중 하나
- 페이지 카운트 합계 = 66 (유실 0)
- 모든 `[[link]]` 가 신 카테고리 경로로 갱신됨 (`grep -r "\[\[ito-portal-operations" backend/data/knowledge/` → 0 hit)
- ChromaDB 재인덱싱 후 `POST /api/v1/knowledge/search?query=...` 결과 metadata 에 service 키 존재

**Acceptance:**
- 위 4종 검증 모두 통과
- `_migration-report.md` 가 backend/data/knowledge/ 에 존재
- 백업 디렉토리 2종 존재
- 63 backend test PASS

**롤백 (실패 시):**
```bash
rm -rf backend/data/knowledge
mv backend/data/knowledge.backup-{ts} backend/data/knowledge
rm -rf backend/data/chroma
mv backend/data/chroma.backup-{ts} backend/data/chroma
```

---

### Phase 5 — 통합 검증 + 사용자 인수

**검증:**
- end-to-end:
  1. CLI 로 새 페이지 등록 (`service=codeeyes, category=faq`) → 200
  2. 동일 등록 `service=unknown` → 422 (enum 강제 확인)
  3. CLI 로 `service=codeeyes` 만 필터한 검색 → 페이지 결과 반환
  4. 워크플로우에 knowledge 노드 `services=["codeeyes"]` 로 등록 → 실행 후 결과에 service 메타 포함
  5. 웹 UI 사이드바에서 서비스 → 카테고리 → 페이지 클릭 → 정상 라우팅
  6. 그래프 페이지에서 service 필터 동작
- architect agent 호출 (opus) — 변경 전수 검증
- 사용자 데모 (스크린샷 4종 첨부)

**Acceptance:**
- architect REJECTED 0건
- 사용자 확인: "통과"

---

## 10. 검증 기준 종합

| Phase | 백엔드 테스트 | 프론트 빌드 | 추가 산출물 |
|---|---|---|---|
| 1 | 63 + 신규 단위 PASS | — | `_schema.yaml` v3 |
| 2 | 신규 통합 4건 PASS | — | catalog 응답 변화 |
| 3 | (변경 없음) | 0 err 0 warn | 스크린샷 4종 |
| 4 | 재인덱싱 후 PASS | — | `_migration-report.md` + 백업 2종 |
| 5 | full PASS | full PASS | architect approved |

---

## 11. 리스크 / 가역성

| 리스크 | 영향 | 대응 |
|---|---|---|
| LLM 분류 오류 (ito-portal-operations → policy vs operations-guide) | 운영 가이드가 정책으로 분류되면 검색 노이즈 | dry-run + 운영자 spot-check 5건 + 추후 frontmatter 수정으로 보정 가능 (PUT) |
| `[[link]]` 자동 갱신 실패 | broken link 발생 | lint 가 `[[deleted:{id}]]` 마커로 식별 + 운영자 수동 보정 |
| ChromaDB 재인덱싱 실패 | 검색 중단 | chroma 백업 즉시 복원 (D13) |
| 사이드바 3단 계층 UX 열화 | 사용자 클릭수 증가 | service 1종 상황에서는 1단 자동 펼침 + 추후 서비스 2종+ 시 재평가 |
| schema 캐시 stale | 신규 service 추가가 즉시 반영 안 됨 | `POST /api/v1/knowledge/schema/reload` 호출 (이미 존재 가정, 없으면 Phase 2 에서 신설) |
| 테스트 회귀 | 63개 중 깨짐 | Phase 별 회귀 PASS 강제. 깨질 시 Phase 진입 금지 |

**가역성:** Phase 4 까지는 백업으로 완전 복원 가능. Phase 5 통과 후 30일 시점에 운영자 결정으로 백업 폐기.

---

## 12. 비용 견적 (LLM 호출 / 토큰)

| 항목 | 회수 | 입력 토큰/회 | 출력 토큰/회 | 총 토큰 |
|---|---|---|---|---|
| Phase 4 마이그레이션 LLM 분류 (`ito-portal-operations` 42 페이지) | 42 | ~1,500 (페이지 본문 요약 + 분류 프롬프트) | ~50 (분류 결과 JSON) | ~65k |
| 기타 카테고리 휴리스틱만 사용 | 24 | 0 | 0 | 0 |
| **합계 LLM 비용** | 42회 | | | ~65k 토큰 |

claude-haiku 기준 약 $0.02 (입력 $0.25/M + 출력 $1.25/M). claude-sonnet 기준 약 $0.20.

**권고:** scientist-low (haiku) 또는 executor (sonnet) 가 분류 LLM 으로 충분. opus 불요.

---

## 13. 산출물 / 위임 계획

| Phase | 위임 대상 agent | model | 산출 파일 (대표) |
|---|---|---|---|
| 1 | `oh-my-claudecode:executor` | sonnet | `_schema.yaml` v3, `knowledge_schema.py`, `knowledge_file_service.py`, `schemas/knowledge.py` |
| 2 | `oh-my-claudecode:executor` | sonnet | `api/routes/knowledge.py`, `nodes/action/knowledge.py`, `services/knowledge_brief.py`, `nodes/catalog.py` |
| 3 | `oh-my-claudecode:designer` | sonnet | `pages/KnowledgeViewerPage.tsx`, `pages/KnowledgeGraphPage.tsx`, `components/knowledge/ServiceBadge.tsx`, `services/knowledgeApi.ts`, `types/knowledge.ts` + 스크린샷 4종 |
| 4 | `oh-my-claudecode:executor` | sonnet | `backend/scripts/migrate_service_field.py`, `_migration-report.md` |
| 5 | `oh-my-claudecode:architect` | opus | architect verification report (인라인) |

---

## 14. Definition of Done

- [ ] Phase 1~5 모든 Acceptance 통과
- [ ] 63 backend test + 신규 단위/통합 모두 PASS
- [ ] `npm run build` 0 err 0 warn
- [ ] 66 페이지 모두 신 service/category 부여 완료 + 유실 0
- [ ] cross-service `[[link]]` 1건 이상 수동 테스트 (운영자가 임의 페이지에 추가 → 그래프에 dashed 엣지 렌더 확인)
- [ ] `_schema.yaml` v3 schema_owner=human, last_curated 갱신
- [ ] architect approved
- [ ] 스크린샷 4종 `_참고자료/screenshots/` 저장
- [ ] `_migration-report.md` + 백업 2종 보존

---

## 15. 부록 — 향후 확장 (이 plan 범위 밖)

- **D8 후속:** 새 service (예: `github-automation`, `jira-ops`) 추가 → `_schema.yaml` 편집 + reload 만 으로 즉시 가능. 페이지 등록은 CLI 통해 `service=github-automation` 명시.
- **page-multi-service:** 1 페이지 = N service 가 필요해지면 `service: str` → `services: List[str]` 마이그레이션 필요. 현 plan 은 단일 service 로 고정 (D1).
- **service 별 brief template:** consumer B brief 가 service 별로 다른 톤을 요구하면 `knowledge_brief.py` 에 template 분기.
- **service 단위 권한:** 사용자/팀별 service 접근 제어. 현 plan 범위 밖.

---

**End of plan.**
