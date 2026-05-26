# Knowledge System 운영 가이드 (Karpathy v2)

> 본 문서는 운영자가 일상적으로 위키를 큐레이션·운영할 때 따라야 할 절차를 모아둔 핸드북이다.
> 시스템 설계 근거는 `.omc/plans/지식-karpathy-v2.md` 를 참조하고, 본 가이드는 그 규칙(§15) 을 운영자 친화 문체로 풀어쓴 실무 매뉴얼이다.

---

## 1. 개요 — 두 소비자(Consumer A / B)

위키는 **하나의 저장소**(`backend/data/knowledge/`) 를 **두 가지 패턴**으로 소비한다.

| 소비자 | 호출 경로 | 검색 방식 | 응답 단위 |
|--------|-----------|-----------|-----------|
| **Consumer A** — 워크플로우 `knowledge` 노드 (RAG) | `nodes/action/knowledge.py` → `vector_db.search()` | top_k 4~7 정밀 검색, page_type 필터 가능 | 청크 hit → 페이지 단위 dedup |
| **Consumer B** — CLI 어시스턴트 작업이해 | `POST /knowledge/brief` | 주제 + 카테고리 필터, page_type 가중치 적용 | 전체 페이지 + 카테고리 인덱스 + 최근 변경이력 |

```
                       ┌──────────────────────────┐
                       │  data/knowledge/         │
                       │   ├ _schema.yaml         │
                       │   ├ _log.md              │
                       │   ├ _index-{cat}.md      │
                       │   ├ _lint-report.md      │
                       │   └ {category}/{slug}.md │
                       └────────────┬─────────────┘
                                    │
                    ┌───────────────┴────────────────┐
                    │                                │
              ┌─────▼─────┐                   ┌──────▼──────┐
              │ Consumer A│                   │  Consumer B │
              │ workflow  │                   │   CLI brief │
              │ RAG node  │                   │             │
              └───────────┘                   └─────────────┘
```

공통 보장:

- **단일 진실 원천** (single source of truth) — 둘이 같은 파일·같은 ChromaDB 컬렉션을 조회.
- 두 소비자 모두 `page_type` 필터 / 카테고리 필터를 동일하게 활용.
- Schema layer 가 두 소비자 모두에게 같은 검증·정합성을 강제.

---

## 2. 페이지 생성 워크플로우

### 2.1 페이지 유형 선택 — `page_type` 결정 가이드

`_schema.yaml` 에 정의된 5종 enum 중 하나를 _반드시_ 선택해야 한다. 누락 시 422.

| page_type | 언제 쓰는가 | 예시 | 필수 링크 |
|-----------|------------|------|-----------|
| **Summary** | 원본 문서(들)를 짧게 요약. 입문용 페이지. | "ITO Portal 수용 절차 요약" | 권장: Entity/Concept 1개 이상 |
| **Entity** | 단일 대상(시스템·서비스·사람·문서) 사실 기술. | "CodeEyes 시스템" | 없음 (고아 페이지 검사 제외) |
| **Concept** | 추상 개념·정책·원칙 정의. | "MEMBER 권한 요청 원칙" | 없음 |
| **Comparison** | 2개 이상의 Entity/Concept 차이 비교. | "관리자 vs 사용자 분기 변경 규칙" | **최소 2개** (`min_links: 2`) |
| **Synthesis** | 운영 중 새 통찰. 여러 페이지를 종합. | "Q1 운영회고 — 권한 요청 병목 패턴" | 권장: Summary/Entity/Concept 다수 |

선택 팁:

- 원본 문서 1건을 요약하면 **Summary**.
- 다수 원본을 합쳐 운영 인사이트를 도출했으면 **Synthesis**.
- "X 가 무엇인가?" 에 답한다면 **Entity** 또는 **Concept**.
- "A 와 B 의 차이는?" 에 답한다면 **Comparison**.

### 2.2 slug 작성 규칙

- 영문 kebab-case 강제: 정규식 `^[a-z0-9]+(-[a-z0-9]+)*$`.
- 한글 slug 금지. 한글 제목이라도 slug 는 영문으로 변환해 입력 (예: "권한 요청 원칙" → `member-permission-rule`).
- 최대 64자. 단어는 하이픈으로 연결.
- 페이지 id = `{category}/{slug}` (예: `codeeyes/codeeyes-overview`). 이 id 가 파일 경로 `data/knowledge/codeeyes/codeeyes-overview.md` 와 일대일 대응한다.

### 2.3 `[[link]]` 작성 규칙

- **권장**: id 기반 — `[[ito-portal-operations/member-permission]]`
- **허용**: 제목 기반 — `[[MEMBER 권한 요청 원칙]]` (lint 가 id 로 정규화 권고)
- **금지**: 외부 URL 을 `[[...]]` 로 표기. 외부는 일반 마크다운 `[text](url)` 사용.
- 신규 페이지 작성 시 본문에 **최소 1개 이상** 관련 페이지 링크 권장 (Entity 제외, 고아 방지).

### 2.4 POST `/knowledge` 호출 예시

```bash
curl -X POST http://localhost:8002/api/v1/knowledge \
  -H "Content-Type: application/json" \
  -d '{
    "category": "codeeyes",
    "slug": "codeeyes-overview",
    "page_type": "Summary",
    "title": "CodeEyes 서비스 개요",
    "content": "본문 ... [[codeeyes/codeeyes-system]] 참조",
    "tags": ["서비스개요"]
  }'
```

응답에 `warnings` 가 있으면 (예: outgoing link 0건) 운영자가 검토하여 보강한다.

---

## 3. Lint 운영

### 3.1 수동 실행 시점 (D3 — on-demand only)

자동 스케줄러는 **절대 도입하지 않는다**. 다음 상황에 운영자가 명시 실행한다:

| 시점 | 이유 |
|------|------|
| 새 카테고리 추가 직후 | 기존 페이지의 카테고리 enum 위반 일괄 감지 |
| 대량 import / restore-from-archive 직후 | 신규 페이지의 schema·link 정합성 확인 |
| 분기 회고 시 | 의미적 중복·모순·구식 페이지 검토 |
| 운영자가 본문을 외부에서 수정 후 | broken_link 와 backlink 정합성 점검 |

### 3.2 API 호출

```bash
# 정적 검사만 (LLM 비호출, cost=0)
curl -X POST http://localhost:8002/api/v1/knowledge/lint \
  -H "Content-Type: application/json" \
  -d '{"dry_run": true}'

# 정적+동적 (LLM 호출 — duplicate/contradiction/outdated)
curl -X POST http://localhost:8002/api/v1/knowledge/lint \
  -H "Content-Type: application/json" \
  -d '{"dry_run": false, "llm_enabled": true}'

# 특정 카테고리만
curl -X POST http://localhost:8002/api/v1/knowledge/lint \
  -H "Content-Type: application/json" \
  -d '{"categories": ["codeeyes"], "dry_run": false}'
```

### 3.3 보고서 해석 — `data/knowledge/_lint-report.md`

| 섹션 | 의미 | 대응 |
|------|------|------|
| **Summary** | errors / warnings / info / llm_calls / estimated_cost | errors > 0 이면 우선 조치 |
| **1. Duplicates** | 동일 카테고리 내 cosine > 0.92 페어 | LLM verdict `MERGE_CANDIDATE` 면 검토 후 병합 |
| **2. Contradictions** | 같은 주제 다른 주장 페이지 | LLM 근거 확인 후 한쪽 갱신 또는 Concept 페이지로 통합 |
| **3. Orphans** | backlink 0 인 비-Entity 페이지 | 다른 페이지에서 `[[link]]` 추가 또는 Entity 로 page_type 변경 |
| **4. Outdated** | 본문에 날짜 패턴 + `_log.md` 에 최근 변경 없음 | LLM 의 한 줄 이유 확인 후 갱신 |
| **5. Broken Cross-References** | `[[...]]` 가 존재하지 않는 페이지 | 링크 수정 또는 페이지 신규 등록 |
| **6. Schema Violations** | 카테고리 enum, page_type enum, slug regex, min_links 위반 | 즉시 수정 (errors 분류) |

`_lint-history/{ts}.md` 에 같은 내용 백업 — 과거 비교 시 참조.

### 3.4 비용 가시화

| 옵션 | 동작 | 비용 |
|------|------|------|
| `dry_run=true` | 정적 검사만 | $0.00 |
| `dry_run=false, llm_enabled=false` | 정적 검사 + dynamic 섹션 (none) | $0.00 |
| `dry_run=false, llm_enabled=true` | 정적 + 동적 (LLM batch 5건, temperature=0.1) | 견적: ~$0.14/회 (66 페이지 기준) |

---

## 4. 그래프 활용 (Graph 페이지)

- **API**: `GET /knowledge/graph?category=<cat>&page_type=<pt>` (둘 다 옵션)
- **UI**: 프론트엔드 `/knowledge/graph` 경로 (KnowledgeGraphPage)
- **응답 구조**:
  ```json
  {
    "nodes": [
      {"id": "codeeyes/codeeyes-overview", "title": "...", "page_type": "Summary", "category": "codeeyes", "links_count": 3, "backlinks_count": 5}
    ],
    "edges": [
      {"from": "codeeyes/codeeyes-overview", "to": "codeeyes/codeeyes-system", "is_broken": false}
    ]
  }
  ```
- **활용**:
  - 고립된 노드(links_count=0 + backlinks_count=0) 식별 → orphan 후보
  - `is_broken=true` 엣지 식별 → broken_link lint 와 교차 검증
  - 카테고리 필터로 도메인별 클러스터 시각화

---

## 5. Archive 복원 절차 (P6 핵심)

### 5.1 개요

`backend/data/knowledge-archive/` 에 보존된 legacy 66파일을 **원본 보존** 한 채로 신정책 형식으로 _신규 등록_ 한다. archive 파일은 **삭제되지 않는다**.

### 5.2 단계 — dry_run 먼저, 보고서 검토, 그 다음 실제 실행

#### 단계 1 — dry_run (안전)

```bash
# LLM 미사용 (휴리스틱만, cost=0) — 가장 안전
curl -X POST http://localhost:8002/api/v1/knowledge/restore-from-archive \
  -H "Content-Type: application/json" \
  -d '{
    "dry_run": true,
    "llm_enabled": false,
    "archive_subpath": "소스코드검증-운영가이드",
    "max_files": 200
  }'
```

응답:
```json
{
  "would_restore": [
    {
      "archive_path": "소스코드검증-운영가이드/CodeEyes-서비스-개요.md",
      "new_id": "codeeyes/codeeyes",
      "category": "codeeyes",
      "page_type": "Summary",
      "rationale": "휴리스틱 — 파일명에 'codeeyes' 포함",
      "llm_used": false
    }
  ],
  "failed": [
    {"archive_path": "...empty.md", "reason": "본문이 비어 있습니다"}
  ],
  "summary": {
    "total": 63,
    "would_restore_count": 60,
    "failed_count": 3,
    "llm_calls": 0,
    "estimated_cost_usd": 0.0
  },
  "report_path": "data/knowledge/_restore-report.md"
}
```

#### 단계 2 — LLM 활성 dry_run (선택, 분류 정확도 향상)

```bash
curl -X POST http://localhost:8002/api/v1/knowledge/restore-from-archive \
  -H "Content-Type: application/json" \
  -d '{
    "dry_run": true,
    "llm_enabled": true,
    "category_hint": "codeeyes",
    "max_files": 200
  }'
```

LLM 이 본문을 읽고 적절한 category/page_type/slug 를 추정. 결과는 `summary.estimated_cost_usd` 로 비용 확인.

#### 단계 3 — 보고서 검토

운영자가 `data/knowledge/_restore-report.md` 를 열어 다음을 확인:

- **`would_restore` 표**: 각 archive 파일의 새 `new_id`, `category`, `page_type`, `rationale` 검토
- **`failed` 표**: 빈 본문 / schema 위반 / id 충돌 — 이유 확인 후 archive 파일 수정 또는 skip 결정
- 분류가 부적절한 페이지가 다수면 `category_hint` 조정 또는 archive 파일의 frontmatter 보정 후 재실행

#### 단계 4 — 실제 실행

```bash
curl -X POST http://localhost:8002/api/v1/knowledge/restore-from-archive \
  -H "Content-Type: application/json" \
  -d '{
    "dry_run": false,
    "llm_enabled": true,
    "category_hint": "codeeyes",
    "max_files": 200
  }'
```

- 실제로 `data/knowledge/{category}/{slug}.md` 가 생성됨
- ChromaDB knowledge_v2 컬렉션에 임베딩 적재
- `_log.md` 에 `create` 행 추가
- `_index-{category}.md` 재생성
- changelog entry (DB) 적재
- archive 원본은 **그대로 유지** (검증된 가역성)

#### 단계 5 — 후속 검증

```bash
# 1) lint 로 신규 페이지 정합성 점검
curl -X POST http://localhost:8002/api/v1/knowledge/lint \
  -H "Content-Type: application/json" \
  -d '{"dry_run": true}'

# 2) index 확인
ls "backend/data/knowledge/codeeyes/_index-codeeyes.md"

# 3) brief 로 검색 가능성 확인
curl -X POST http://localhost:8002/api/v1/knowledge/brief \
  -H "Content-Type: application/json" \
  -d '{"topic": "codeeyes", "categories": ["codeeyes"]}'
```

### 5.3 안전 default 와 제약

| 항목 | default | 이유 |
|------|---------|------|
| `dry_run` | `true` | 실수로 대량 등록 방지 |
| `max_files` | 200 | 비용 가드 |
| `llm_enabled` | `true` (사용자 명시 시) | 분류 정확도 ↑. cost 통제는 `llm_enabled=false` |
| archive 원본 | **삭제 안 됨** | 가역성 보장 |
| 한글 slug | **금지** (LLM/휴리스틱이 영문 변환) | OS·Git·URL 호환 |

---

## 6. 카테고리 추가 절차

1. `backend/data/knowledge/_schema.yaml` 의 `categories` 리스트에 신규 항목 추가:
   ```yaml
   categories:
     - id: new-category
       title: 신규 카테고리
       description: 한 줄 설명
   ```
2. 서버 재기동 (또는 `POST /knowledge/schema/reload` — 향후 추가 검토).
3. 다음 호출 시 schema 자동 reload (mtime 기반). `data/knowledge/new-category/` 디렉토리는 첫 페이지 등록 시 자동 생성.
4. `_index-new-category.md` 도 첫 페이지 등록 시 자동 생성. 또는 `POST /knowledge/index/rebuild` 로 즉시 생성:
   ```bash
   curl -X POST http://localhost:8002/api/v1/knowledge/index/rebuild \
     -H "Content-Type: application/json" \
     -d '{"categories": ["new-category"]}'
   ```

---

## 7. 에러 대응 표

| 상황 | HTTP | 의미 | 대응 |
|------|------|------|------|
| `page_type` 누락 / 잘못된 enum | **422** | schema 검증 위반 | 5종 enum (Summary/Entity/Concept/Comparison/Synthesis) 중 하나 명시 |
| `category` 가 schema 미정의 | **422** | enum 위반 | `_schema.yaml` 의 카테고리 추가 또는 valid 값 사용 |
| `slug` 가 한글/대문자/언더스코어 포함 | **422** | regex 위반 | 영문 kebab-case 로 재작성 (`^[a-z0-9]+(-[a-z0-9]+)*$`) |
| POST `id` 충돌 (기존 페이지 존재) | **409** | 동일 `{category}/{slug}` 페이지 존재 | 다른 slug 사용 또는 기존 페이지 PUT |
| DELETE 시 backlink 보유 | **409** | 그래프 무결성 보호 | (a) 가리키는 페이지 수정 후 재삭제, (b) `?force=true` 로 강제 (자동 `[[deleted:...]]` 마커 삽입) |
| restore-from-archive 결과 `failed` 에 schema 위반 | (200) | 분류 결과가 enum 위반 | `category_hint` 명시 또는 archive frontmatter 보정 |
| 청킹 임계 (1024 토큰 이상) | 자동 처리 | 800 토큰 슬라이딩 + 100 overlap 자동 적용 | 별도 조치 불요 — 청크 hit 은 page 단위로 dedup |
| ChromaDB sync 실패 | (best-effort) | 파일은 보존됨, 로그에 경고 | `POST /knowledge/sync` 로 수동 재동기화 |

---

## 8. 일상 운영 체크리스트

| 주기 | 작업 | 도구 |
|------|------|------|
| 매 페이지 등록 직후 | warnings 확인 (응답 body) | POST `/knowledge` |
| 매주 | lint dry_run | POST `/knowledge/lint` `{dry_run: true}` |
| 매월 | lint 동적 (LLM) | POST `/knowledge/lint` `{dry_run: false, llm_enabled: true}` |
| 분기 | 그래프 시각화 검토 | GET `/knowledge/graph` (UI 또는 API) |
| 새 카테고리 추가 직후 | lint + index/rebuild | POST `/knowledge/lint`, POST `/knowledge/index/rebuild` |
| 대량 import 직후 | restore (dry_run → 검토 → real) → lint | POST `/knowledge/restore-from-archive`, POST `/knowledge/lint` |

---

## 9. 참고 문서

- 설계서: `.omc/plans/지식-karpathy-v2.md` (D1~D15 결정 근거 포함)
- 데이터 모델: `backend/app/services/knowledge_file_service.py`
- Schema layer: `backend/app/services/knowledge_schema.py`
- 운영 규칙(plan §15): `.omc/plans/지식-karpathy-v2.md` §15
