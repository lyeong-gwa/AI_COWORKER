# 예제 데이터 주입 가이드 (Example Data Injection Guide)

AI 업무도우미는 **빈 상태**로 기동됩니다(시드 없음). 이 문서는 다른 사용자/AI가 자신의 용도에 맞춰 **AI 노드, API 정의, 워크플로우, 지식 문서**를 직접 주입하는 방법을 설명합니다.

## 목차
1. [시스템 객체 구조](#1-시스템-객체-구조)
2. [Base URL 및 공통 규약](#2-base-url-및-공통-규약)
3. [AI Node 주입](#3-ai-node-주입)
4. [API Definition 주입](#4-api-definition-주입)
5. [Knowledge 문서 주입](#5-knowledge-문서-주입)
6. [Workflow 주입](#6-workflow-주입)
7. [배치 주입(Export/Import 번들)](#7-배치-주입exportimport-번들)
8. [권장 주입 시나리오](#8-권장-주입-시나리오)

---

## 1. 시스템 객체 구조

| 객체 | 역할 | 저장 위치 | 재사용 |
|---|---|---|---|
| **AI Node** (`AINode`) | 재사용 가능한 **프롬프트 + 출력스키마 + LLM설정** 템플릿 | SQLite `ai_nodes` | 여러 워크플로우에서 인스턴스로 배치 |
| **API Definition** (`ApiDefinition`) | **HTTP 호출 스펙**(URL/헤더/파라미터/인증) | SQLite `api_definitions` | 여러 워크플로우의 `api-call`/`api-start` 노드가 참조 |
| **Knowledge Doc** | **마크다운 + 벡터 임베딩**(RAG 컨텍스트) | `data/knowledge/{id}.md` + ChromaDB | 지식 검색 노드에서 활용 |
| **Workflow** (`Workflow` + `WorkflowNode` + `WorkflowConnection`) | 노드 그래프(=실행 파이프라인) | SQLite 3테이블 | 실행 단위 |

**노드 핸들러**(`backend/app/nodes/**/*.py`의 `@NodeHandlerRegistry.register`) 자체는 **시스템 코드**이므로 주입이 아니라 **구현** 대상입니다. 주입으로 다루는 건 위 4종의 **데이터 객체**뿐입니다.

---

## 2. Base URL 및 공통 규약

| 항목 | 값 |
|---|---|
| Backend Base URL | `http://localhost:8002/api/v1` |
| 인증 | 없음(로컬 토이 플랫폼) |
| 바디 인코딩 | `Content-Type: application/json; charset=utf-8` |
| 필드 네이밍 | **camelCase** (예: `urlTemplate`, `systemPrompt`) |

> 한글 포함 JSON을 curl로 보낼 때는 UTF-8 파일로 저장 후 `--data-binary @file.json`을 쓰거나, 아래 Python 예시처럼 `urllib.request`를 사용하세요. Windows 쉘에서 직접 인라인하면 인코딩 깨짐.

---

## 3. AI Node 주입

### 3.1 엔드포인트
```
POST /api/v1/nodes
```

### 3.2 스키마 핵심 필드

| 필드 | 필수 | 설명 |
|---|---|---|
| `name`, `description` | ✓ | 표시명/설명 |
| `category` | | 예: "유틸리티", "분석", "자동화" |
| `icon`, `color`, `tags` | | UI 표시 |
| `systemPrompt` | | 시스템 롤 프롬프트 |
| `userPromptTemplate` | ✓(실용) | `{{input.fieldName}}` 플레이스홀더 지원 |
| `inputSchema`, `outputSchema` | | JSON Schema 형식 (type/properties/required) |
| `outputEnforcement` | | `{enabled, includeSchemaInPrompt, exampleOutput, validationEnabled, retryOnFailure, maxRetries}` |
| `llmConfig` | | `{model, temperature, maxTokens}` |

### 3.3 최소 예시 (Python)

```python
import urllib.request, json
payload = {
    "name": "요약 생성기",
    "description": "긴 텍스트를 3문단으로 요약",
    "category": "자동화",
    "icon": "📝",
    "color": "text-blue-400",
    "tags": ["요약", "NLP"],
    "systemPrompt": "당신은 간결한 한국어 요약 전문가입니다.",
    "userPromptTemplate": "다음 내용을 3문단으로 요약하세요.\n\n{{input.text}}",
    "inputSchema": {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"]
    },
    "outputSchema": {
        "type": "object",
        "properties": {"summary": {"type": "string"}},
        "required": ["summary"]
    },
    "outputEnforcement": {"enabled": True, "includeSchemaInPrompt": True, "validationEnabled": True, "retryOnFailure": True, "maxRetries": 2},
    "llmConfig": {"model": "gpt-4o-mini", "temperature": 0.3, "maxTokens": 1500}
}
req = urllib.request.Request(
    "http://localhost:8002/api/v1/nodes",
    data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
    headers={"Content-Type": "application/json; charset=utf-8"},
    method="POST",
)
print(json.loads(urllib.request.urlopen(req).read())["id"])
```

---

## 4. API Definition 주입

### 4.1 엔드포인트
```
POST /api/v1/api-definitions
```

### 4.2 스키마 핵심 필드

| 필드 | 설명 |
|---|---|
| `name`, `description`, `category`, `tags` | 메타 |
| `method` | `GET` / `POST` / `PUT` / `DELETE` / `PATCH` |
| `urlTemplate` | `{{var}}` 템플릿 지원 (예: `http://host/users/{{userId}}`) |
| `headers` | `{키: 값}` (값에 `{{var}}` 가능) |
| `bodyTemplate` | POST/PUT/PATCH용 문자열 템플릿 |
| `authType` | `none` / `bearer` / `basic` / `api_key` |
| `authConfig` | authType별: bearer→`{token}`, api_key→`{headerName, apiKey}` |
| `parameters` | `[{name, in, type, required, description, default}]` (in: `path`/`query`/`header`/`body`) |
| `responseSchema` | `{fields: [...], example: ...}` (선택) |

> **중요**: `parameters`에 `in: "query"`로 선언된 항목은 `api-call`/`api-start` 노드가 실행 시 자동으로 URL 쿼리스트링에 추가합니다. 값의 출처 우선순위: 업스트림 belt > 노드 `defaultParams` > 파라미터 `default`.

### 4.3 최소 예시

```json
{
  "name": "정적분석 문의글 조회",
  "method": "GET",
  "urlTemplate": "http://localhost:8000/api/inquiries",
  "headers": {"Content-Type": "application/json"},
  "authType": "none",
  "parameters": [
    {"name": "state", "in": "query", "type": "string", "required": false, "description": "상태 필터(신규/처리중/완료)"}
  ],
  "category": "정적분석",
  "tags": ["inquiry"]
}
```

---

## 5. Knowledge 문서 주입

### 5.1 엔드포인트
```
POST /api/v1/knowledge        # 단건 생성 (body: {id, title, content, category, tags, source})
POST /api/v1/knowledge/sync    # 파일 스캔 후 벡터 DB 재동기화
```

### 5.2 파일 저장 위치
```
backend/data/knowledge/{id}.md
```
프론트엔드 매터/본문 포맷이므로, 직접 `.md` 파일을 만들어 놓고 `/knowledge/sync`를 호출해도 됩니다.

### 5.3 예시

```python
payload = {
    "id": "onboarding-checklist",
    "title": "신규 입사자 온보딩 체크리스트",
    "content": "# 온보딩 체크리스트\n\n1. 계정 발급\n2. VPN 설정\n...",
    "category": "HR",
    "tags": ["온보딩", "HR"],
    "source": "internal",
}
```

---

## 6. Workflow 주입

### 6.1 엔드포인트
```
POST /api/v1/workflows
```

### 6.2 스키마 핵심 필드 (요약)

```jsonc
{
  "name": "문의글 자동 답변",
  "description": "",
  "tags": [],
  "trigger": {"type": "manual", "config": {}},
  "viewport": {"x": 0, "y": 0, "zoom": 1},
  "variables": {},
  "nodes": [
    {
      "id": "n1",                        // 워크플로우 내 고유 ID
      "nodeId": "api-start",             // 핸들러 타입 (trigger/action/logic/ai/output의 type)
      "definitionType": "api-start",     // nodeId와 동일하게 맞추는 게 안전
      "aiNodeId": null,                  // AINode 참조 (ai-custom일 때만)
      "name": "문의글 조회",
      "position": {"x": 100, "y": 100},
      "config": {                        // 핸들러별 설정
        "apiDefinitionId": "api-xxx",
        "defaultParams": {"state": "신규"}
      },
      "inputMapping": {},                // {필드명: "$.상위belt경로"}
      "configOverrides": {}
    }
    // ... 추가 노드
  ],
  "connections": [
    {"id": "e1", "sourceNodeId": "n1", "targetNodeId": "n2"}
  ]
}
```

### 6.3 노드 `nodeId`(=핸들러 타입) 주요 목록

| category | 값 예시 |
|---|---|
| trigger | `manual`, `form-start`, `api-start`, `schedule-trigger` |
| action | `api-call`, `http-request`, `knowledge` (지식검색), `webhook-notify`, `excel-export`, `warehouse-query`, `deliverable-generator`, `send-email` |
| ai | `ai-custom` (AINode 참조), `ai-api-router` (분류기) |
| logic | `condition`, `sorter`, `unpacker`, `mapper` |
| output | `warehouse`, `markdown-viewer` |

전체 타입은 `backend/app/core/constants.py::NodeDefType` 참고.

### 6.4 주의사항

- `nodeId`와 `definitionType`은 **동일한 핸들러 타입**으로 맞추세요.
- `ai-custom` 노드는 `aiNodeId`(AINode 참조) 필수.
- `api-call`/`api-start` 노드는 `config.apiDefinitionId`(ApiDefinition 참조) 필수.
- 노드 간 데이터 흐름은 `connections` + 각 노드의 `inputMapping`으로 제어.

---

## 7. 배치 주입(Export/Import 번들)

다른 환경에서 만든 데이터를 한번에 가져올 때 사용. 자기 자신의 export 결과를 그대로 재주입해도 됩니다.

| 엔드포인트 | 용도 |
|---|---|
| `GET  /api/v1/export/nodes` | AI 노드 전체 export |
| `POST /api/v1/import/nodes` | AI 노드 import (배열 body) |
| `GET  /api/v1/export/api-definitions` | API 정의 export |
| `POST /api/v1/import/api-definitions` | API 정의 import |
| `GET  /api/v1/export/knowledge` | 지식 export |
| `POST /api/v1/import/knowledge` | 지식 import |
| `GET  /api/v1/export/workflows` | 워크플로우 전체 export (번들: nodes + api-defs + knowledge 포함) |
| `GET  /api/v1/export/workflows/{id}` | 워크플로우 단건 export (의존성 동봉) |
| `POST /api/v1/import/workflows` | 워크플로우 import (의존성 자동 생성) |
| `GET  /api/v1/local-files` | `backend/data/download/` 내 번들 파일 목록 |
| `POST /api/v1/import/local/{filename}` | 로컬 번들 파일 import |

**권장 순서(의존성 해결)**: Knowledge → AI Node → API Definition → Workflow.
(`import/workflows`는 번들에 포함된 의존성을 자동 생성하므로 단일 호출로 충분한 경우가 많음)

---

## 8. 권장 주입 시나리오

### 시나리오 A: 새 워크플로우 1개만 만들 경우
1. (필요 시) `POST /api-definitions`로 외부 API 스펙 등록
2. (필요 시) `POST /nodes`로 AI 프롬프트 템플릿 등록
3. `POST /workflows`로 그래프 생성

### 시나리오 B: 다른 환경의 데이터를 복제
1. 원본 환경에서 `GET /export/workflows/{id}` → JSON 저장
2. 대상 환경에서 `POST /import/workflows`로 동일 JSON 업로드

### 시나리오 C: 지식만 대량 투입 (RAG 전용)
1. `backend/data/knowledge/`에 `.md` 파일 다수 복사
2. `POST /api/v1/knowledge/sync` 호출 → ChromaDB 자동 동기화

### 시나리오 D: AI 에이전트가 자동으로 예제 투입
위 curl/Python 예시를 그대로 사용. 개별 엔드포인트는 멱등적이지 않으므로, 중복 방지를 원하면 `id` 필드를 명시하고 기존 존재 확인 후 주입하거나 upsert 성격의 import 엔드포인트를 사용하세요.

---

## 9. 참고 자료

- 노드 핸들러 구현: `backend/app/nodes/{trigger|action|ai|logic|output}/*.py`
- 스키마 정의: `backend/app/schemas/{node,api_definition,workflow,knowledge}.py`
- 모델 정의: `backend/app/models/*.py`
- 노드 타입 상수: `backend/app/core/constants.py::NodeDefType`
- Export/Import 구현: `backend/app/api/routes/export_import.py`
