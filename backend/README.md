# AI 업무도우미 Backend

Python FastAPI 기반 백엔드 서버

## 기술 스택

- **FastAPI** - 비동기 웹 프레임워크
- **SQLAlchemy** - ORM (Async)
- **RestrictedPython** - 코드 샌드박스 실행
- **ChromaDB** - 벡터 데이터베이스
- **OpenAI/Anthropic** - LLM API

## 설치

```bash
# 가상환경 생성
python -m venv venv

# 활성화 (Windows)
venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt
```

## 환경 설정

```bash
# .env 파일 생성
cp .env.example .env

# .env 파일 수정하여 API 키 입력
```

## 실행

```bash
# 개발 서버
uvicorn app.main:app --reload --port 8000

# 또는
python -m uvicorn app.main:app --reload --port 8000
```

## API 문서

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 프로젝트 구조

```
backend/
├── app/
│   ├── api/              # API 라우트
│   │   └── routes/
│   │       ├── tasks.py
│   │       ├── knowledge.py
│   │       ├── tools.py
│   │       ├── nodes.py
│   │       └── workflows.py
│   ├── core/             # 핵심 설정
│   │   ├── config.py
│   │   └── database.py
│   ├── models/           # SQLAlchemy 모델
│   │   ├── task.py
│   │   ├── knowledge.py
│   │   ├── tool.py
│   │   ├── node.py
│   │   └── workflow.py
│   ├── schemas/          # Pydantic 스키마
│   ├── services/         # 비즈니스 로직
│   │   ├── tool_executor.py
│   │   ├── node_executor.py
│   │   ├── llm_client.py
│   │   └── workflow_engine.py
│   ├── sandbox/          # 코드 샌드박스
│   │   └── executor.py
│   └── main.py           # FastAPI 앱
├── requirements.txt
├── .env.example
└── README.md
```

## 샌드박스 코드 실행

RestrictedPython을 사용하여 안전한 코드 실행 환경 제공:

- 위험한 내장 함수 차단 (open, exec, eval 등)
- 허용된 모듈만 import 가능
- 실행 시간 제한

### 허용된 모듈

- `json`, `math`, `re`, `datetime`
- `collections`, `itertools`, `functools`
- `random`, `string`, `base64`
- `hashlib`, `uuid`, `decimal`, `statistics`

## API 엔드포인트

### Tasks
- `GET /api/v1/tasks` - 태스크 목록
- `POST /api/v1/tasks` - 태스크 생성
- `PATCH /api/v1/tasks/:id` - 태스크 수정
- `PATCH /api/v1/tasks/:id/status` - 상태 변경

### Knowledge
- `GET /api/v1/knowledge` - 문서 목록
- `POST /api/v1/knowledge` - 문서 생성
- `POST /api/v1/knowledge/:id/sync` - 벡터 DB 동기화
- `POST /api/v1/knowledge/search` - 유사도 검색

### Tools
- `GET /api/v1/tools` - 도구 목록
- `POST /api/v1/tools` - 도구 생성
- `POST /api/v1/tools/:id/test` - 도구 테스트

### Nodes
- `GET /api/v1/nodes` - 노드 목록
- `POST /api/v1/nodes` - 노드 생성
- `POST /api/v1/nodes/:id/test` - 노드 테스트

### Workflows
- `GET /api/v1/workflows` - 워크플로우 목록
- `POST /api/v1/workflows` - 워크플로우 생성
- `POST /api/v1/workflows/:id/execute` - 워크플로우 실행
- `GET /api/v1/workflows/executions/:id/stream` - 실행 로그 스트리밍 (SSE)
