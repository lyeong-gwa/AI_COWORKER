# 지식(Knowledge) 시스템 Karpathy "LLM Wiki" 정책 전환 — v2

> 본 문서는 AI 업무도우미의 Knowledge 모듈을 **Raw / Wiki / Schema 3계층** 으로 재편하기 위한 공식 실행 계획서다.
> 작성 컨텍스트: 사용자가 사전 인터뷰에서 결정 4건을 확정한 상태에서 작성된 plan 이며, 후속 단계(`/oh-my-claudecode:start-work`) 에서 executor 들이 본 문서를 단일 소스로 삼아 구현·검증한다.

---

## 1. 목표 (1줄 미션)

**`backend/data/knowledge/` 의 flat 67파일 RAG 저장소를 Karpathy LLM Wiki(3계층 + page_type + `[[link]]` 그래프 + on-demand lint)로 재구축하여, 두 소비자(워크플로우 RAG + CLI 어시스턴트 작업이해)가 공통으로 활용하는 "compounding artifact" 가 되도록 한다.**

---

## 1.1 Wiki 의 두 소비자 (Consumer A & B)

본 위키는 단일 저장소를 **두 가지 다른 패턴**으로 소비한다.

### Consumer A — 워크플로우 `knowledge` 노드 RAG (기존)
- **상황**: 워크플로우 실행 중 LLM API 호출 시, 프롬프트에 함께 주입할 도메인 컨텍스트 검색.
- **호출 경로**: `nodes/action/knowledge.py` → `vector_db.search()`
- **요건**: top_k 4~7 정밀 검색, page 단위로 dedup, page_type 필터 가능 (예: 운영 답변에는 Summary+Entity 만)
- **예시 시드**: "소스코드검증" 서비스 가이드 = ITO 답변 워크플로우의 핵심 컨텍스트

### Consumer B — CLI AI 어시스턴트 작업 이해 (신규)
- **상황**: 사용자가 CLI 로 AI 와 대화하며 워크플로우를 조립·수정·디버그할 때, AI 가 "사용자가 무엇을 하려는지" 파악·이해하기 위한 배경 지식 조회.
- **호출 경로**: `POST /knowledge/brief` (신규 §6.1.7) — 주제 또는 자유 쿼리 → Synthesis + Summary 위주 페이지 + 카테고리 인덱스 페이지를 동봉한 "briefing" 패키지 반환
- **요건**:
  - 페이지 단편이 아닌 **전체 페이지 + 인덱스** 반환 (CLI 가 사용자 작업 맥락을 broadly 파악)
  - 우선순위: Synthesis > Summary > Comparison > Entity > Concept
  - 응답에 `_index-{category}.md` 카테고리 인덱스 함께 포함
  - 변경이력(`_log.md` 최근 N건) 동봉 가능 (옵션)
- **예시**: 사용자가 "ITO 답변 워크플로우를 개선하고 싶다" → CLI 가 `/knowledge/brief?topic=ITO 답변` 호출 → 관련 Synthesis/Summary 페이지 + ito-portal-operations 카테고리 인덱스 + 최근 변경이력 → AI 가 충분한 컨텍스트로 사용자와 협업

### 공통 보장
- 두 소비자 모두 **같은 위키** 조회. 별도 사본 없음 (single source of truth).
- 두 소비자 모두 page_type 필터·카테고리 필터 동일 활용.
- Schema layer 가 두 소비자 모두에게 동일한 검증·정합성 적용.

---

## 2. 확정된 결정사항

### 2.1 사용자 사전 확정 (4건)

| # | 항목 | 결정 | 근거 |
|---|------|------|------|
| D1 | 전환 범위 | **Full v2** — 3계층 + lint + 교차참조 + index/log 동시 전환 | 부분 전환은 운영 중 inconsistency 폭증. 한 번에 일관된 정책 적용이 위험·비용 모두 낮다 |
| D2 | 기존 67개 데이터 | **archive 보존 후 제로스타트** — `data/knowledge-archive/` 로 이동, 신정책으로 재등록 | 기존 frontmatter 에 `page_type`/`links` 없음. in-place 마이그레이션 시 LLM 호출 67건 + 검증 비용이 archive→restore 보다 크다. archive 는 완전 가역 |
| D3 | Lint 트리거 | **on-demand only** — CLI/UI 버튼 명시 실행 | 자동 스케줄은 LLM 비용 예측 불가. 운영자가 큐레이션 주체("Human curates")라는 Karpathy 원칙과 정합 |
| D4 | 카테고리 운영 | **이번에 분화 포함** — `page_type` (5종) + 도메인 카테고리 (다중) | 단일 카테고리 "소스코드검증-운영가이드" 만으로는 Karpathy 의 Entity/Concept/Comparison 페이지 종류 표현 불가 |

### 2.2 본 plan 작성 중 합리적 default 로 결론 (의사결정)

| # | 항목 | 결정 | 근거 |
|---|------|------|------|
| D5 | 페이지 ID 형식 | `{category}/{slug}` (slug 는 영문 kebab-case, 신규 등록 시 LLM 이 한글 제목→영문 slug 생성). 파일명 = `{slug}.md`, 디렉토리 = 카테고리 | 한글 파일명은 OS·Git·URL 호환성 이슈. slug 기반은 stable id 보장. 카테고리 = 디렉토리는 grep·find 친화적 |
| D6 | 링크 표기 | **id 기반 권장** — `[[category/slug]]` (호환: `[[Title]]` 도 lint 가 자동 id 로 정규화 권고) | id 는 title 변경에도 깨지지 않음. Obsidian-style title link 는 사람이 쓰기 편하지만 rename 시 깨짐 |
| D7 | 청킹 정책 | **하이브리드** — 1024 토큰 미만 단일 벡터, 그 이상은 800 토큰 청크 + 100 토큰 overlap, 페이지 단위 메타데이터 보존 | 현 데이터 평균 ~500 토큰 (1벡터 적합), 신규 Synthesis 페이지는 길어질 가능성 → 청킹 필요 |
| D8 | Raw layer 저장 형식 | binary blob 그대로 `data/knowledge-raw/{yyyy}/{mm}/{uuid}.{ext}` + DB row(`RawSource`) 로 메타 보관 | "원본 불변" 원칙. DB 는 search/dedup 용 인덱스 |
| D9 | Schema 검증 위치 | `app/services/knowledge_schema.py` 신규 모듈 + Pydantic validator + API 진입점에서 enum 강제 | 검증을 한 곳에 모아야 lint 와 정책이 동일 소스 |
| D10 | 버전 관리 | `version: int` 자동 증가, `KnowledgeChangelogEntry` 테이블에 diff_summary(LLM 생성) 적재. body 전체 히스토리는 git 의존 (data/ 가 git 추적이라는 가정) | DB 에 full snapshot 보관은 비용↑. diff_summary 만으로 운영자 가독성 충분 |
| D11 | Lint 보고서 | `data/knowledge/_lint-report.md` 단일 파일 매 실행 시 덮어쓰기, `_lint-history/{timestamp}.md` 백업 | 최신만 보면 되는 게 일반. 과거 비교 필요 시 history 폴더 참조 |
| D12 | DELETE 시 backlink 보호 | **409 Conflict 반환, `?force=true` 쿼리로 강제 삭제 가능. 강제 삭제 시 backlink 보유 페이지에 `[[deleted:...]]` 마커 자동 삽입** | 무방비 삭제 = 그래프 무결성 파괴. 강제 옵션은 운영자 책임 |
| D13 | Lint LLM 모델 | `agent_service` 의 기본 모델(=설정값) 재사용. 대량 호출이므로 `temperature=0.1`, batch 5건 | 모델 선택은 시스템 설정 일관성. lint 는 결정성 필요 |
| D14 | `-1` suffix 중복 파일 처리 | archive 이동 시 `_DUPLICATE_REVIEW/` 서브폴더로 격리, 운영자가 수동 병합 결정 | 자동 병합은 데이터 손실 위험 |
| D15 | ChromaDB 컬렉션명 | 기존 `knowledge` → 신규 `knowledge_v2` (롤백 가능). v1 컬렉션은 archive 와 함께 30일 보존 후 삭제 | 동일 이름 drop&recreate 는 비가역. 신규 이름은 무중단 전환 가능 |

---

## 3. 현재 상태 (마이그레이션 출발점)

| 항목 | 현황 |
|------|------|
| 데이터 위치 | `backend/data/knowledge/` flat |
| 파일 수 | **66 .md** (사전 정보 67 → 실측 66) |
| 단일 카테고리 | "소스코드검증-운영가이드" |
| `-1` suffix 중복 파일 | **3건** — `configurationcollectionrenewal-1.md`, `예외-처리-불가반려-기준-1.md`, `통합UI-개요-페이지대시보드-기능-1.md` |
| frontmatter 필드 | `title, category, tags, source, created, extra_metadata` |
| 모델 | `app/services/knowledge_file_service.py:KnowledgeFileDoc` |
| API 라우터 | `app/api/routes/knowledge.py` |
| 검색 노드 | `app/nodes/action/knowledge.py` |
| 임베딩 | ChromaDB + ONNX 로컬 (LLM 독립), 청킹 없음 |
| LLM 헬퍼 | `agent_service.generate_document_update()`, `generate_document_content()` 이미 존재 |
| `[[link]]` | 0건 |
| `index.md` / `log.md` | 없음 |
| `page_type` | 없음 |
| `version` 필드 | 없음 |
| 프론트 페이지 | `frontend/src/pages/KnowledgeViewerPage.tsx` |

---

## 4. Must Have / Must NOT Have

### 4.1 Must Have
- `data/knowledge-raw/` 신설 (Layer 1)
- `data/knowledge/{category}/` 디렉토리 구조 (Layer 2)
- `data/knowledge/_schema.yaml` (Layer 3)
- `_index-{category}.md`, `_log.md` 자동 생성·갱신
- `KnowledgeFileDoc` 에 `page_type, version, links, raw_source_id` 추가
- `[[category/slug]]` 파서 + backlink 계산
- on-demand lint API + UI 버튼
- Obsidian-style graph 시각화 페이지
- 기존 66파일 무손실 archive 보존
- ChromaDB v2 컬렉션 분리(롤백 가능)
- pytest 회귀 0 + frontend build 0 에러
- architect 최종 검증 통과

### 4.2 Must NOT Have
- 기존 66파일 in-place 변환 (archive 후 재등록 방식만)
- 자동 lint 스케줄러 (cron, on-write 트리거)
- 컬렉션 동일 이름 drop (반드시 신규 이름)
- LLM 의 자동 카테고리 신설 (카테고리 추가는 인간 승인 필수)
- 한글 파일명 신규 생성 (slug 영문 강제)
- 단일 카테고리로의 회귀

---

## 5. 데이터 모델 변경

### 5.1 `KnowledgeFileDoc` 확장

```python
# app/services/knowledge_file_service.py
class KnowledgeFileDoc(BaseModel):
    id: str                       # = "{category}/{slug}"
    title: str
    content: str
    category: str                 # _schema.yaml enum 강제
    page_type: Literal["Summary", "Entity", "Concept", "Comparison", "Synthesis"]  # NEW
    tags: list[str] = []
    source: str | None = None
    raw_source_id: str | None = None      # NEW — RawSource FK
    version: int = 1                       # NEW — PUT 마다 +1
    links: list[str] = []                  # NEW — [[...]] 파싱 결과, id 정규화 후
    # backlinks 는 계산값 (별도 GET 엔드포인트), 본 모델에는 미저장
    created: datetime
    updated: datetime
    content_hash: str
    sync_status: Literal["synced", "pending", "error"]
    extra_metadata: dict[str, Any] = {}
```

### 5.2 신규 모델

```python
# app/models/knowledge_raw.py (신규)
class RawSource(BaseModel):
    id: str                          # uuid4
    filename: str
    mime: str
    size: int
    content_hash: str                # SHA-256
    uploaded_at: datetime
    original_blob_path: str          # data/knowledge-raw/yyyy/mm/{uuid}.{ext}
    derived_knowledge_ids: list[str] = []  # 본 raw 에서 파생된 wiki 페이지들

# app/models/knowledge_changelog.py (신규)
class KnowledgeChangelogEntry(BaseModel):
    id: str                          # uuid4
    knowledge_id: str                # FK
    version: int
    timestamp: datetime
    operator: str                    # api caller (=user) or "system:lint"
    diff_summary: str                # LLM 생성 한 줄 요약
    change_type: Literal["create", "update", "delete", "lint-fix"]
```

### 5.3 디렉토리 구조 (전환 후)

```
backend/data/
├── knowledge-raw/                       # Layer 1 — 불변 원본
│   └── 2026/05/{uuid}.{ext}
├── knowledge-archive/                   # 마이그레이션 백업
│   ├── 소스코드검증-운영가이드/         # 기존 카테고리명 유지
│   │   └── *.md (63건)
│   └── _DUPLICATE_REVIEW/               # -1 suffix 3건 격리
└── knowledge/                           # Layer 2 — Wiki
    ├── _schema.yaml                     # Layer 3 — 운영 규칙
    ├── _log.md                          # append-only 변경이력
    ├── _index-{category}.md             # 카테고리별 자동 인덱스
    ├── _lint-report.md                  # 최신 lint 결과
    ├── _lint-history/{timestamp}.md     # 과거 lint 보고서
    └── {category}/
        └── {slug}.md
```

---

## 6. API 변경

### 6.1 신규 엔드포인트

| Method | Path | 목적 | 응답 |
|--------|------|------|------|
| POST | `/knowledge/raw` | 원본 파일 업로드, blob 저장 + RawSource row 생성 | `RawSource` |
| GET | `/knowledge/{id}/backlinks` | 이 페이지를 가리키는 모든 페이지 id 목록 | `{id, backlinks: list[str]}` |
| POST | `/knowledge/lint` | on-demand 전체 점검. body: `{categories?: list[str], dry_run?: bool}` | `{report_path, summary}` |
| POST | `/knowledge/index/rebuild` | `_index-{category}.md` 전체 재생성 | `{rebuilt: list[str]}` |
| GET | `/knowledge/graph` | 링크 그래프 — nodes(id,title,page_type,category), edges(from,to) | `{nodes, edges}` |
| POST | `/knowledge/restore-from-archive` | archive 의 .md 를 LLM 으로 신정책 형식 변환·재등록 (옵션 `category_hint`, `dry_run`) | `{restored: list[str], failed: list[{path, reason}]}` |
| POST | `/knowledge/brief` | **Consumer B 전용** — CLI 어시스턴트 작업이해용 briefing. body: `{topic?: str, query?: str, categories?: list[str], maxPages?: int=8, includeLog?: bool=true}` | `{pages: [{id, title, page_type, category, content, score}], indexes: [{category, content}], recentChanges?: [{timestamp, id, summary}]}` |

### 6.2 변경 엔드포인트

| Method | Path | 변경 사항 |
|--------|------|----------|
| POST | `/knowledge` | `page_type` 필수, `[[...]]` 자동 파싱→`links`, `_log.md` 자동 append, `_index-{category}.md` 갱신, 카테고리 enum 검증 |
| PUT | `/knowledge/{id}` | `version` 자동 증가, `KnowledgeChangelogEntry` 자동 적재 (diff_summary 는 LLM 생성, fallback: "version bumped"), `links` 재파싱 |
| DELETE | `/knowledge/{id}` | backlinks 존재 시 `409 Conflict`. `?force=true` 시 강제 삭제 + backlink 보유 페이지에 `[[deleted:{id}]]` 마커 자동 치환 |
| POST | `/knowledge/search` | 응답에 `page_type`, `version`, `links` 포함 |

### 6.3 검색 노드(`nodes/action/knowledge.py`) 변경

신규 파라미터:

| 파라미터 | 타입 | 기본 | 설명 |
|---------|------|------|------|
| `pageTypes` | `list[str]` | `[]` | Summary/Entity/Concept/Comparison/Synthesis 필터 |
| `minScore` | `float` | `0.0` | 임계점수 미만 결과 제거 |
| `expandBacklinks` | `bool` | `false` | hit 결과에 1-hop backlink 페이지 자동 추가 |

---

## 7. 청킹(Chunking) 정책

| 조건 | 정책 |
|------|------|
| 문서 토큰 수 < 1024 | 청킹 없음. 페이지 전체 = 1 벡터 |
| 1024 이상 | 800 토큰 슬라이딩 윈도우, 100 토큰 overlap |
| 청크 메타 | `{page_id, chunk_index, chunk_total, page_type, category, version}` |
| 토큰 카운터 | ONNX 임베딩 모델의 토크나이저 재사용 (tiktoken 의존 회피) |
| 청크별 ID | `{page_id}#chunk-{idx}` (ChromaDB 의 doc id) |
| 검색 결과 | 청크 hit → page_id dedup → 페이지 단위로 반환 (한 페이지에서 여러 청크 hit 시 max score 채택) |

**근거:** 현 66파일 평균 길이가 짧아 대부분 1벡터로 충분. 신규 Synthesis 페이지는 길어질 것을 대비하여 청킹 인프라는 미리 마련. dedup 으로 검색 페이로드 비대화 방지.

---

## 8. Schema Layer 구현

### 8.1 `_schema.yaml` 구조

```yaml
# data/knowledge/_schema.yaml
version: 2
schema_owner: human
last_curated: 2026-05-26

categories:
  - id: ito-portal-operations
    title: ITO Portal 운영
    description: ITO Portal 수용·권한·연동 관련 운영 가이드
  - id: codeeyes
    title: CodeEyes 소스코드 검증
    description: CodeEyes 서비스/시스템/지침
  - id: plugin-troubleshooting
    title: 플러그인 트러블슈팅
    description: 이클립스 플러그인 오류·로그인·파싱 등
  - id: faq
    title: FAQ
    description: 자주 묻는 질문 모음

page_types:
  Summary:
    purpose: 원본(들)을 요약. 빠르게 훑기 위함.
    must_link: [Entity, Concept]
  Entity:
    purpose: 사람·시스템·서비스·문서 등 명확한 대상 1개를 기술.
    must_link: []
  Concept:
    purpose: 추상 개념·정책·원칙을 정의.
    must_link: []
  Comparison:
    purpose: 2개 이상의 Entity/Concept 차이를 비교.
    must_link: [Entity, Concept]    # 비교 대상은 반드시 링크
    min_links: 2
  Synthesis:
    purpose: 운영 중 발견된 새로운 통합 통찰(Query→환류).
    must_link: [Summary, Entity, Concept]

link_policy:
  format: "[[category/slug]]"
  legacy_title_link_allowed: true       # [[Title]] 도 허용, lint 가 정규화 권고
  broken_link_marker: "[[deleted:{id}]]"

filename_policy:
  slug_pattern: "^[a-z0-9]+(-[a-z0-9]+)*$"
  max_slug_length: 64
  enforce_english_slug: true            # 한글 slug 금지
```

### 8.2 검증 강제 위치

| Layer | 파일 | 검증 |
|-------|------|------|
| Pydantic | `app/services/knowledge_file_service.py` | `category` enum, `page_type` enum, `slug` regex |
| Service | `app/services/knowledge_schema.py` (신규) | `_schema.yaml` 로드·캐시, `validate_category()`, `validate_page_type()`, `validate_slug()`, `validate_links()` |
| API | `app/api/routes/knowledge.py` | 진입 시 schema validator 호출 후 422 반환 |
| Lint | 동일 모듈 재사용 | lint 도 동일 검증 통해 위반 사항 보고 |

---

## 9. Lint 알고리즘

### 9.1 단계별 흐름

```
POST /knowledge/lint
└─ 1. 전체 페이지 로드 (DB + 파일)
   ├─ 2. 정적 검사 (LLM 미호출, 즉시)
   │   ├─ Schema 검증: 카테고리·page_type·slug 위반
   │   ├─ 깨진 링크: [[...]] 가 존재하지 않는 페이지 가리킴
   │   ├─ 고아 페이지: 어떤 페이지도 link/backlink 하지 않음 (단 Entity 제외)
   │   ├─ page_type 최소 링크 위반 (예: Comparison min_links=2)
   │   └─ 파일명 정책 위반
   ├─ 3. 동적 검사 (LLM 호출, batch 5건)
   │   ├─ 의미적 중복 후보: 동일 카테고리 내 코사인 유사도 > 0.92 페어 → LLM 에 "중복인가?" 질의
   │   ├─ 모순: title/intro 의 핵심 주장과 충돌하는 다른 페이지 검출
   │   └─ 구식 의심: source 의 mtime > 90일 + content 에 날짜·버전 패턴 포함 시 LLM 에 "최신성 점검 필요?" 질의
   ├─ 4. 보고서 생성: _lint-report.md (덮어쓰기) + _lint-history/{ts}.md (백업)
   └─ 5. 응답: {report_path, summary: {error_count, warning_count, info_count}}
```

### 9.2 `_lint-report.md` 섹션 형식

```markdown
# Knowledge Lint Report — 2026-05-26 14:30

## Summary
- Errors: 3
- Warnings: 12
- Info: 28
- LLM calls: 23 (estimated cost: $0.18)

## 1. Duplicates (의미적 중복 후보)
- [[codeeyes/codeeyes-overview]] ↔ [[codeeyes/codeeyes-system-overview]] (cosine=0.94, LLM verdict: MERGE_CANDIDATE)

## 2. Contradictions (모순)
- [[ito-portal-operations/member-permission]] vs [[ito-portal-operations/branch-change-rule-user]] (LLM: 권한 위계 설명 불일치)

## 3. Orphans (고아 페이지)
- [[faq/faq-pm-자동-등록변경]] — page_type=Summary 이나 어떤 페이지도 링크하지 않음

## 4. Outdated (구식 의심)
- [[codeeyes/codeeyes-target-languages]] (source mtime=2024-08-01, "최신성 검토 권고")

## 5. Broken Cross-References (깨진 링크)
- [[ito-portal-operations/deprecated-rule]] in [[faq/faq-summary]] (대상 페이지 없음)

## 6. Schema Violations
- `소스코드검증-운영가이드/branchchangeruleuser.md` — 카테고리 enum 위반 (legacy 카테고리)
```

### 9.3 LLM 비용 견적

| 항목 | 수치 |
|------|------|
| 페이지 수 (초기) | ~66 |
| 평균 토큰/페이지 | 500 |
| 정적 검사 LLM 호출 | 0 |
| 동적 검사 — 중복 후보 평균 | ~8 페어 × 1500토큰 in / 100토큰 out = ~13K |
| 동적 검사 — 모순 의심 | ~5 페어 × 2000 / 150 = ~11K |
| 동적 검사 — 구식 | ~10 페이지 × 800 / 50 = ~8K |
| **합계 1회 lint** | **~32K 토큰 in, ~3K 토큰 out** |
| Sonnet 4.7 가격 가정 (in $3/M, out $15/M) | ~$0.14 / 회 |

규모가 100배 커져도 $14/회 수준이므로 on-demand 정책의 비용은 통제 가능.

---

## 10. 마이그레이션 절차 (제로스타트)

### 10.1 단계 (사람이 한 번에 실행)

```
[Step 1] DB 백업
  └─ pg_dump or sqlite cp (의존 DB 따라). archive 디렉토리에 dump 보관

[Step 2] 파일 archive
  └─ mv backend/data/knowledge/* backend/data/knowledge-archive/소스코드검증-운영가이드/
  └─ mv 3건 (-1 suffix) → knowledge-archive/_DUPLICATE_REVIEW/

[Step 3] 신규 디렉토리 생성
  └─ mkdir backend/data/knowledge-raw
  └─ mkdir backend/data/knowledge (빈 디렉토리)
  └─ mkdir backend/data/knowledge/_lint-history

[Step 4] Schema · Index · Log 초기화
  └─ data/knowledge/_schema.yaml (8.1 의 내용 그대로 commit)
  └─ data/knowledge/_log.md  (헤더만)
  └─ data/knowledge/_index-*.md (카테고리당 빈 인덱스)

[Step 5] ChromaDB 처리
  └─ 신규 컬렉션 knowledge_v2 생성 (v1 은 보존, 30일 후 cron 으로 drop 옵션)

[Step 6] 검증
  └─ pytest backend/tests
  └─ 프론트 build (vite)
  └─ /knowledge/lint dry_run → 0 페이지 보고서 정상

[Step 7] (선택) Archive 재등록
  └─ 운영자 결정 후 POST /knowledge/restore-from-archive
  └─ LLM 이 page_type/slug/links 추정 → dry_run 으로 검토 후 실제 등록
```

### 10.2 가역성 보장

| 위험 | 완화책 |
|------|--------|
| 데이터 손실 | archive 는 mv (cp 아님) 후에도 30일 보존, ChromaDB v1 컬렉션 동시 보존 |
| 잘못된 재등록 | restore-from-archive 는 default `dry_run=true`, 운영자가 결과 확인 후 실제 실행 |
| 카테고리 오분류 | restore 시 LLM 이 `category_hint` 없으면 미분류로 보고 후 중단 |

---

## 11. 프론트엔드 변경

| 파일 | 변경 |
|------|------|
| `frontend/src/pages/KnowledgeViewerPage.tsx` | page_type 배지, version 표시, links/backlinks 패널, "Lint 실행" / "Index 재생성" 버튼 |
| `frontend/src/pages/KnowledgeGraphPage.tsx` (신규) | `/knowledge/graph` 경로, vis-network 또는 react-flow 로 노드·엣지 시각화. 클릭→상세 페이지 |
| `frontend/src/components/knowledge/LintReportViewer.tsx` (신규) | `_lint-report.md` 렌더, 섹션별 collapsible |
| `frontend/src/components/knowledge/LinksPanel.tsx` (신규) | 본문 우측에 outgoing links / incoming backlinks 표 |
| `frontend/src/components/knowledge/PageTypeBadge.tsx` (신규) | 5종 page_type 색상 코드 일관 |
| `frontend/src/services/knowledgeApi.ts` | 신규 엔드포인트 6종 클라이언트 메서드 추가 |
| `frontend/src/App.tsx` | `/knowledge/graph` 라우트 추가 |

---

## 12. Phase 별 실행 순서

| Phase | 산출 | 예상 작업량 | 차단 요건(=다음 phase 진입 조건) |
|-------|------|-------------|-------------------------------|
| **P1. 모델·스키마·마이그레이션 인프라** | `KnowledgeFileDoc` 확장, `RawSource`, `KnowledgeChangelogEntry` 모델, `_schema.yaml`, archive 이동 스크립트, Alembic(or 동등) migration | M | `pytest` green, archive 66건 보존 확인, ChromaDB v2 컬렉션 생성 |
| **P2. API — 기본 CRUD + schema 검증** | POST/PUT/DELETE 변경, `/knowledge/raw`, `/knowledge/{id}/backlinks`, log/index 자동 갱신 | M | API 단위 테스트 100% pass, OpenAPI 스펙 갱신 |
| **P3. 링크 그래프 + 청킹** | `[[...]]` 파서, backlink 계산, `/knowledge/graph`, 청킹·임베딩 파이프라인 | M | 더미 데이터 5건으로 그래프 API 200 응답, 청크 검색 dedup 동작 |
| **P4. Lint** | `/knowledge/lint`, 정적/동적 검사, `_lint-report.md` 생성, `/knowledge/index/rebuild` | L | dummy 5건에 의도적 위반 심어두고 lint 보고서가 모든 카테고리 항목 포함 검증 |
| **P5. 프론트엔드** | KnowledgeViewerPage 개편, 신규 페이지 3종, 라우트, 신규 컴포넌트 | M | `npm run build` 0 에러, lint 0 warning, 모든 신규 페이지 수동 smoke test |
| **P6. Archive 복원 CLI + 운영자 핸드오프** | `/knowledge/restore-from-archive`, CLI 문서, 운영 가이드 갱신, architect 최종 검증 | M | dry_run 으로 archive 66건 변환 결과 보고, architect APPROVED |

---

## 13. 검증 기준 (Phase 별 acceptance)

### P1
- [ ] Alembic upgrade head 성공 (or 동등 migration)
- [ ] `data/knowledge-archive/` 에 66건 .md 존재
- [ ] `data/knowledge-archive/_DUPLICATE_REVIEW/` 에 3건 존재
- [ ] `data/knowledge/_schema.yaml` 로드 가능 (pyyaml)
- [ ] `pytest backend/tests` 회귀 0
- [ ] ChromaDB 에 `knowledge_v2` 컬렉션 존재, v1 도 보존

### P2
- [ ] page_type 누락 시 POST → 422
- [ ] 카테고리 enum 위반 시 → 422
- [ ] PUT 시 version 자동 증가, changelog 적재
- [ ] DELETE 시 backlink 있으면 409, `?force=true` 로 통과
- [ ] `_log.md` 에 매 변경 append
- [ ] `_index-{category}.md` 자동 갱신

### P3
- [ ] `[[category/slug]]` 파싱, links 필드 자동 채움
- [ ] backlinks API → 정확한 역참조 목록
- [ ] /knowledge/graph 응답 nodes/edges 유효
- [ ] 1024 토큰 초과 문서 청킹·다중 벡터 저장
- [ ] 검색 시 청크 dedup → 페이지 단위 결과

### P4
- [ ] 의도적 위반 케이스 5종 모두 lint 보고서에 표시
- [ ] LLM 호출 batch 동작
- [ ] `_lint-report.md` 덮어쓰기, `_lint-history/` 백업

### P5
- [ ] `npm run build` exit 0
- [ ] 모든 신규 페이지 라우팅 200
- [ ] page_type 배지 5종 모두 색상 구분
- [ ] 그래프 페이지에서 노드 클릭 → 상세 이동

### P6 (최종)
- [ ] restore-from-archive dry_run 보고서 운영자 검토 가능
- [ ] architect 검증 PROMPT: "현 구현이 Karpathy 정책 + 본 plan 결정사항 D1~D15 와 일치하는가?" → APPROVED
- [ ] 사용자 수동 acceptance

---

## 14. 리스크 및 완화

| 리스크 | 영향 | 완화책 |
|--------|------|--------|
| LLM lint 비용 폭증 | 운영비 | on-demand only(D3), batch 5건, 회당 ~$0.14 견적 가시화 |
| ChromaDB drop 비가역 | 데이터 손실 | 신규 컬렉션 `knowledge_v2` 분리(D15), v1 30일 보존 |
| 청킹 도입으로 RAG 페이로드 증가 | 워크플로우 latency | 검색 노드 dedup 강화 (페이지 단위 max-score) |
| `-1` suffix 중복 자동병합 사고 | 데이터 손실 | `_DUPLICATE_REVIEW/` 격리(D14), 운영자 수동 결정 |
| 한글 slug 강제로 인한 기존 운영자 혼란 | 학습 비용 | `restore-from-archive` 가 LLM 으로 한글→영문 slug 생성, 매핑표를 보고서로 함께 출력 |
| 카테고리 enum 강제로 신규 카테고리 추가 마찰 | 운영 속도 | `_schema.yaml` 편집 + 서버 재시작이면 충분. CLI `/knowledge/schema add-category` 도 P6 에 포함 검토 |
| backlink 보유 페이지 강제 삭제 시 그래프 손상 | 무결성 | `[[deleted:{id}]]` 마커로 visibly 깨진 링크 표식, lint 가 즉시 보고 |
| Wiki 페이지 신규 등록 시 LLM 의 잘못된 slug 생성 | 충돌 | slug regex 위반 시 422, 운영자 수동 입력 fallback |
| 본 plan 의 가정 — `data/` 가 git 추적 — 위반 | 변경이력 손실 | P1 에서 `.gitignore` 검토하고 위반 시 `KnowledgeChangelogEntry` 에 body snapshot 저장 옵션 추가 |

---

## 15. 운영 규칙 (Schema layer 의 인간 가독본)

### 15.1 카테고리 추가 절차
1. `_schema.yaml` 의 `categories` 에 `{id, title, description}` 추가
2. 서버 재시작 또는 POST `/knowledge/schema/reload` (P6 에 포함 검토)
3. `data/knowledge/{new-category}/` 디렉토리 자동 생성
4. `_index-{new-category}.md` 자동 생성

### 15.2 page_type 선택 가이드

| page_type | 언제 쓰는가 | 예시 |
|-----------|------------|------|
| **Summary** | 원본 문서(들)를 짧게 요약. 입문용. | "ITO Portal 수용 절차 요약" |
| **Entity** | 단일 대상(시스템·서비스·사람·문서) 사실 기술 | "CodeEyes 시스템" |
| **Concept** | 추상 개념·정책·원칙 정의 | "MEMBER 권한 요청 원칙" |
| **Comparison** | 2개 이상의 Entity/Concept 차이 | "관리자 vs 사용자 분기 변경 규칙" |
| **Synthesis** | 운영 중 새 통찰. 여러 페이지를 종합. | "Q1 운영회고 — 권한 요청 병목 패턴" |

### 15.3 `[[link]]` 작성 규칙
- **권장**: id 기반 — `[[ito-portal-operations/member-permission]]`
- **허용**: 제목 기반 — `[[MEMBER 권한 요청 원칙]]` (lint 가 id 로 정규화 권고)
- **금지**: 외부 URL 을 `[[...]]` 로 표기 (외부는 일반 `[text](url)` 사용)
- 신규 페이지 작성 시 본문에 최소 1개 이상 관련 페이지 `[[link]]` 권장 (Entity 제외, 고아 방지)

### 15.4 신규 문서 등록 시 필수 체크
1. **id 충돌**: `{category}/{slug}` 가 이미 존재하면 422
2. **page_type 명시**: 누락 시 422
3. **카테고리 valid**: enum 미존재 시 422
4. **의미적 중복 검토 권고**: 동일 카테고리 내 cosine ≥ 0.92 페이지 존재 시 응답에 `warnings: [...]` 동봉 (block 아닌 권고)
5. **링크 권고**: outgoing link 0건 + page_type ≠ Entity 면 응답 warning

### 15.5 Lint 운영 권고 주기
- **수동**: 새 카테고리 추가 직후, 대량 import 직후, 분기 회고 시
- **자동 스케줄러는 도입하지 않음** (D3)

---

## 16. Commit Strategy

| Phase | Commit 분할 |
|-------|-------------|
| P1 | (a) 모델 추가, (b) Alembic migration, (c) archive 이동 스크립트, (d) `_schema.yaml` 추가 |
| P2 | (a) API 변경 — POST/PUT/DELETE, (b) `/raw`, `/backlinks`, (c) log/index 자동 갱신, (d) 테스트 |
| P3 | (a) link parser, (b) backlink 계산, (c) graph API, (d) 청킹 파이프라인, (e) 검색 노드 변경 |
| P4 | (a) 정적 lint, (b) 동적 lint(LLM), (c) report 생성, (d) index/rebuild API |
| P5 | (a) services/knowledgeApi.ts, (b) KnowledgeViewerPage 개편, (c) 신규 페이지 3종, (d) 컴포넌트 4종 |
| P6 | (a) restore-from-archive, (b) CLI 문서, (c) 운영 가이드, (d) architect 검증 후 release tag |

**ITO 오케스트레이션 프로젝트의 atomic commit 원칙** 준수. 각 commit 은 단독으로 빌드·테스트 가능해야 함.

---

## 17. Success Criteria (전체)

- [ ] Karpathy 3계층(Raw / Wiki / Schema) 가 디렉토리 + 모델 + 서비스 모두에 구현됨
- [ ] 66개 기존 파일 archive 무손실 보존, 신규 정책 ChromaDB `knowledge_v2` 동작
- [ ] page_type 5종 enum 강제, 카테고리 enum 강제
- [ ] `[[category/slug]]` 파싱 + backlink 계산 + 그래프 시각화
- [ ] `_index-*.md` `_log.md` 자동 유지
- [ ] on-demand lint 가 6개 섹션(중복·모순·고아·구식·깨진 링크·schema 위반) 모두 점검
- [ ] `KnowledgeChangelogEntry` 적재 + version 자동 증가
- [ ] DELETE 시 backlink 보호 (409 + force)
- [ ] 프론트엔드 build 0 에러, 신규 페이지 3종 동작
- [ ] pytest 회귀 0
- [ ] architect 최종 검증 APPROVED

---

## 19. Seed 콘텐츠 — 첫 Raw 소스 (사용자 명시)

사용자가 명시한 우선순위 시드: **"소스코드검증" 서비스 운영 가이드**.

- archive 의 66파일 중 단일 카테고리 `소스코드검증-운영가이드` 가 본 시드의 원천. 따라서 P6 의 `/knowledge/restore-from-archive` 가 가장 먼저 처리해야 할 raw 묶음.
- P1 의 `_schema.yaml` 에 `categories.codeeyes` 와 `categories.ito-portal-operations` 가 사전 정의되어 있어야, restore 시 LLM 이 적절히 분류 가능.
- 본 raw 가 시드 역할을 함으로써:
  - Consumer A: ITO 답변 워크플로우(`wf-790b5a19`) 가 첫 사용처. 기존 검증된 RAG 동선이 그대로 작동.
  - Consumer B: CLI 어시스턴트가 "소스코드검증 워크플로우 손대고 싶다"는 사용자 의도 파악 시 즉시 briefing 가능한 데이터셋 확보.

## 20. Out of Scope (본 plan 외)

- 외부 SaaS 위키(Confluence, Notion) 동기화
- 다국어 (i18n) 페이지
- 사용자 단위 권한·열람 제한 (현 시스템에 권한 모델 부재)
- 실시간 협업 편집
- Archive 의 자동 재등록 (운영자 명시 실행만)
- LLM 의 자동 카테고리 신설

---

**계획서 끝.**

> 본 plan 의 모든 결정은 D1~D15 표에 근거를 명시했다. 후속 architect 검증 시 D# 참조로 합리성 확인 가능.
