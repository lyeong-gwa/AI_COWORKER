"""
시드 데이터 생성 스크립트

초기 샘플 데이터 생성 (프론트엔드 mockData 기반)
"""

from datetime import datetime, timedelta
from sqlalchemy import select

from .models.task import Task, TaskStatus, TaskPriority
from .models.tool import ToolDefinition, ToolType
from .models.knowledge import KnowledgeDocument, SyncStatus
from .models.node import AINode
from .models.workflow import Workflow, WorkflowStatus, WorkflowNode, WorkflowConnection
from .core.database import async_session_maker
from .services.embedding.vector_db import get_vector_db


async def seed_database():
    """초기 데이터 시딩 (데이터가 없을 때만)"""
    async with async_session_maker() as session:
        # 이미 데이터가 있는지 확인
        result = await session.execute(select(Task).limit(1))
        if result.scalar_one_or_none() is not None:
            print("[SKIP] 이미 시드 데이터가 존재합니다")
            await seed_knowledge_data()
            return

        print("[SEED] 시드 데이터 생성 시작...")

        # ========================================
        # 1. Tasks (5개)
        # ========================================
        tasks = [
            Task(
                id="task-1",
                title="API 문서 정리",
                description="REST API 엔드포인트 문서화 작업",
                status=TaskStatus.IN_PROGRESS,
                priority=TaskPriority.HIGH,
                assignee_id="user-1",
                assignee_name="김철수",
                tags=["문서", "API"],
                due_date=datetime.utcnow() + timedelta(days=3),
                todos=[
                    {"id": "todo-1", "text": "엔드포인트 목록 작성", "completed": True},
                    {"id": "todo-2", "text": "요청/응답 예시 작성", "completed": False},
                ],
                comments=[
                    {
                        "id": "comment-1",
                        "authorId": "user-2",
                        "authorName": "박영희",
                        "content": "예시 코드도 추가해주세요",
                        "createdAt": datetime.utcnow().isoformat(),
                    }
                ],
                activity_log=[
                    {
                        "id": "log-1",
                        "userId": "user-1",
                        "userName": "김철수",
                        "action": "태스크 생성",
                        "detail": "새 태스크를 생성했습니다",
                        "timestamp": (datetime.utcnow() - timedelta(days=1)).isoformat(),
                    }
                ],
            ),
            Task(
                id="task-2",
                title="버그 수정: 로그인 실패 오류",
                description="로그인 시 간헐적으로 발생하는 500 에러 수정",
                status=TaskStatus.REVIEW,
                priority=TaskPriority.URGENT,
                assignee_id="user-3",
                assignee_name="이민수",
                tags=["버그", "인증"],
                due_date=datetime.utcnow() + timedelta(days=1),
                todos=[
                    {"id": "todo-3", "text": "에러 로그 분석", "completed": True},
                    {"id": "todo-4", "text": "수정 사항 테스트", "completed": True},
                    {"id": "todo-5", "text": "PR 생성", "completed": True},
                ],
                comments=[],
                activity_log=[],
            ),
            Task(
                id="task-3",
                title="데이터베이스 마이그레이션 스크립트 작성",
                description="사용자 테이블 스키마 변경에 따른 마이그레이션 스크립트",
                status=TaskStatus.TODO,
                priority=TaskPriority.MEDIUM,
                assignee_id="user-1",
                assignee_name="김철수",
                tags=["데이터베이스", "마이그레이션"],
                due_date=datetime.utcnow() + timedelta(days=7),
                todos=[],
                comments=[],
                activity_log=[],
            ),
            Task(
                id="task-4",
                title="대시보드 UI 개선",
                description="사용자 피드백 반영한 대시보드 UI 개선",
                status=TaskStatus.BACKLOG,
                priority=TaskPriority.LOW,
                assignee_id=None,
                assignee_name=None,
                tags=["UI", "프론트엔드"],
                due_date=None,
                todos=[],
                comments=[],
                activity_log=[],
            ),
            Task(
                id="task-5",
                title="성능 테스트 및 최적화",
                description="주요 API 엔드포인트 성능 테스트 및 병목 구간 최적화",
                status=TaskStatus.DONE,
                priority=TaskPriority.HIGH,
                assignee_id="user-2",
                assignee_name="박영희",
                tags=["성능", "최적화"],
                due_date=datetime.utcnow() - timedelta(days=2),
                todos=[
                    {"id": "todo-6", "text": "부하 테스트", "completed": True},
                    {"id": "todo-7", "text": "캐싱 전략 적용", "completed": True},
                ],
                comments=[],
                activity_log=[],
            ),
        ]

        for task in tasks:
            session.add(task)

        # ========================================
        # 2. Tool Definitions (5개 - 각 타입별 1개)
        # ========================================
        tools = [
            ToolDefinition(
                id="tool-1",
                name="날씨 API 호출",
                description="OpenWeatherMap API를 통해 실시간 날씨 정보 조회",
                icon="🌤️",
                color="text-blue-400",
                type=ToolType.API_CALL,
                config={
                    "method": "GET",
                    "urlTemplate": "https://api.openweathermap.org/data/2.5/weather?q={{city}}&appid={{apiKey}}",
                    "headers": {"Content-Type": "application/json"},
                    "bodyTemplate": None,
                    "authType": "query_param",
                    "authConfig": {"key": "appid", "value": "{{apiKey}}"},
                },
                tags=["날씨", "API"],
            ),
            ToolDefinition(
                id="tool-2",
                name="CSV 파일 읽기",
                description="CSV 형식의 데이터 파일을 읽어 JSON으로 변환",
                icon="📄",
                color="text-green-400",
                type=ToolType.FILE_READ,
                config={
                    "pathTemplate": "{{filePath}}",
                    "encoding": "utf-8",
                },
                tags=["파일", "CSV"],
            ),
            ToolDefinition(
                id="tool-3",
                name="보고서 생성",
                description="JSON 데이터를 받아 마크다운 보고서 파일로 저장",
                icon="📝",
                color="text-purple-400",
                type=ToolType.FILE_WRITE,
                config={
                    "pathTemplate": "./reports/{{reportName}}.md",
                    "mode": "overwrite",
                },
                tags=["파일", "보고서"],
            ),
            ToolDefinition(
                id="tool-4",
                name="데이터 변환 스크립트",
                description="Python 코드를 실행하여 데이터 변환 수행",
                icon="🐍",
                color="text-yellow-400",
                type=ToolType.CODE_EXECUTE,
                config={
                    "language": "python",
                    "code": "def transform(data):\n    return [item.upper() for item in data]",
                    "inputMapping": {"data": "$.input.items"},
                },
                tags=["코드", "변환"],
            ),
            ToolDefinition(
                id="tool-5",
                name="사용자 데이터 조회",
                description="PostgreSQL에서 사용자 정보를 조회하는 쿼리",
                icon="🗄️",
                color="text-cyan-400",
                type=ToolType.DATABASE_QUERY,
                config={
                    "connectionId": "postgres-main",
                    "queryTemplate": "SELECT * FROM users WHERE department = '{{department}}' LIMIT {{limit}}",
                },
                tags=["데이터베이스", "쿼리"],
            ),
        ]

        for tool in tools:
            session.add(tool)

        # ========================================
        # 3. Knowledge Documents (3개)
        # ========================================
        docs = [
            KnowledgeDocument(
                id="doc-1",
                title="회사 업무 프로세스 가이드",
                filename="업무프로세스.md",
                content="""# 회사 업무 프로세스 가이드

## 1. 태스크 생성 프로세스
1. 칸반 보드에서 백로그 컬럼에 태스크 생성
2. 담당자 배정 및 우선순위 설정
3. 상세 설명 및 체크리스트 작성

## 2. 워크플로우 실행 프로세스
1. 워크플로우 빌더에서 노드 구성
2. 트리거 설정 (수동/스케줄/웹훅)
3. 활성화 후 실행

## 3. 문서 관리 프로세스
1. 지식 베이스에 문서 업로드
2. 자동 벡터화 및 임베딩 생성
3. AI 노드에서 컨텍스트로 활용
""",
                summary="회사의 태스크, 워크플로우, 문서 관리 프로세스에 대한 가이드",
                vector_id="vec-1",
                sync_status=SyncStatus.SYNCED,
                last_synced_at=datetime.utcnow(),
                token_count=156,
                source="internal",
                category="가이드",
                tags=["프로세스", "업무"],
                doc_metadata={"author": "관리자", "version": "1.0"},
            ),
            KnowledgeDocument(
                id="doc-2",
                title="API 개발 규칙",
                filename="API규칙.md",
                content="""# API 개발 규칙

## 네이밍 컨벤션
- REST 엔드포인트: 소문자 + 하이픈 (kebab-case)
- 예시: /api/v1/user-profiles

## 에러 처리
- HTTP 상태 코드 표준 준수
- 에러 응답 형식: { "error": { "code": "ERROR_CODE", "message": "..." } }

## 인증
- JWT 토큰 사용
- Authorization 헤더: Bearer {token}

## 버전 관리
- URL에 버전 명시 (/api/v1/, /api/v2/)
- 하위 호환성 유지
""",
                summary="API 개발 시 준수해야 할 규칙 및 컨벤션",
                vector_id="vec-2",
                sync_status=SyncStatus.SYNCED,
                last_synced_at=datetime.utcnow(),
                token_count=98,
                source="internal",
                category="개발",
                tags=["API", "규칙"],
                doc_metadata={"author": "개발팀", "version": "2.1"},
            ),
            KnowledgeDocument(
                id="doc-3",
                title="고객 지원 FAQ",
                filename="FAQ.md",
                content="""# 고객 지원 FAQ

## Q1. 비밀번호를 잊어버렸어요
A. 로그인 페이지에서 "비밀번호 찾기"를 클릭하고 이메일을 입력하세요. 재설정 링크가 전송됩니다.

## Q2. 워크플로우가 실행되지 않아요
A. 다음을 확인해주세요:
- 워크플로우 상태가 "활성"인지 확인
- 트리거 설정이 올바른지 확인
- 연결된 노드에 에러가 없는지 확인

## Q3. 파일 업로드 크기 제한은?
A. 최대 10MB까지 업로드 가능합니다. 더 큰 파일은 클라우드 스토리지 링크를 사용하세요.

## Q4. 데이터는 안전한가요?
A. 모든 데이터는 암호화되어 저장되며, 정기적으로 백업됩니다.
""",
                summary="자주 묻는 질문과 답변 모음",
                vector_id=None,
                sync_status=SyncStatus.PENDING,
                last_synced_at=None,
                token_count=0,
                source="customer_support",
                category="FAQ",
                tags=["고객지원", "FAQ"],
                doc_metadata={"department": "CS"},
            ),
        ]

        for doc in docs:
            session.add(doc)

        # ========================================
        # 4. AI Nodes (3개 - 툴과 연결)
        # ========================================
        nodes = [
            AINode(
                id="node-1",
                name="날씨 기반 업무 추천",
                description="현재 날씨 정보를 바탕으로 적절한 업무를 추천",
                category="업무관리",
                icon="🌦️",
                color="text-blue-500",
                tags=["날씨", "추천"],
                linked_tool_ids=["tool-1"],
                knowledge={
                    "linkedIds": ["doc-1"],
                    "filters": {"category": "가이드"},
                    "maxTokens": 1000,
                },
                system_prompt="당신은 업무 효율성 전문가입니다. 날씨 정보를 고려하여 사용자에게 적절한 업무를 추천해주세요.",
                user_prompt_template="현재 날씨는 {{weather}}입니다. 오늘 진행하면 좋을 업무를 추천해주세요.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "city": {"type": "string", "description": "도시명"},
                    },
                    "required": ["city"],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "tasks": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "추천 업무 목록",
                        }
                    },
                    "required": ["tasks"],
                },
                llm_config={"model": "gpt-4o-mini", "temperature": 0.7, "maxTokens": 1500},
            ),
            AINode(
                id="node-2",
                name="데이터 분석 및 보고서 생성",
                description="CSV 데이터를 읽어 분석 후 마크다운 보고서 생성",
                category="데이터분석",
                icon="📊",
                color="text-green-500",
                tags=["데이터", "보고서"],
                linked_tool_ids=["tool-2", "tool-3"],
                knowledge={
                    "linkedIds": ["doc-1", "doc-2"],
                    "filters": {},
                    "maxTokens": 2000,
                },
                system_prompt="당신은 데이터 분석가입니다. CSV 데이터를 분석하고 인사이트를 도출하여 보고서를 작성하세요.",
                user_prompt_template="다음 데이터를 분석하고 주요 인사이트를 보고서로 작성해주세요:\n{{data}}",
                input_schema={
                    "type": "object",
                    "properties": {
                        "filePath": {"type": "string", "description": "CSV 파일 경로"},
                    },
                    "required": ["filePath"],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "insights": {"type": "array", "items": {"type": "string"}},
                        "reportPath": {"type": "string"},
                    },
                    "required": ["insights", "reportPath"],
                },
                llm_config={"model": "gpt-4o", "temperature": 0.5, "maxTokens": 3000},
            ),
            AINode(
                id="node-3",
                name="사용자 정보 조회 및 처리",
                description="부서별 사용자 정보를 조회하고 Python으로 데이터 변환",
                category="데이터베이스",
                icon="👥",
                color="text-purple-500",
                tags=["사용자", "데이터베이스"],
                linked_tool_ids=["tool-4", "tool-5"],
                knowledge={
                    "linkedIds": [],
                    "filters": {},
                    "maxTokens": 1000,
                },
                system_prompt="당신은 데이터 엔지니어입니다. 데이터베이스 쿼리 결과를 적절히 변환하여 제공하세요.",
                user_prompt_template="{{department}} 부서의 사용자 목록을 조회하고 이름을 대문자로 변환해주세요.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "department": {"type": "string"},
                        "limit": {"type": "number", "default": 10},
                    },
                    "required": ["department"],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "users": {"type": "array", "items": {"type": "object"}},
                    },
                    "required": ["users"],
                },
                llm_config={"model": "gpt-4o-mini", "temperature": 0.3, "maxTokens": 2000},
            ),
        ]

        for node in nodes:
            session.add(node)

        # ========================================
        # 5. Workflow with Nodes and Connections
        # ========================================
        workflow = Workflow(
            id="workflow-1",
            name="일일 업무 추천 자동화",
            description="매일 아침 날씨를 확인하고 적절한 업무를 추천하는 워크플로우",
            status=WorkflowStatus.ACTIVE,
            viewport={"x": 0, "y": 0, "zoom": 1},
            trigger={"type": "schedule", "config": {"cron": "0 9 * * *", "timezone": "Asia/Seoul"}},
            variables={"defaultCity": "Seoul"},
            tags=["업무관리", "자동화"],
        )
        session.add(workflow)

        # Workflow Nodes
        workflow_nodes = [
            WorkflowNode(
                id="wf-node-1",
                workflow_id="workflow-1",
                node_id="node-1",
                name="날씨 조회",
                position={"x": 100, "y": 100},
                config_overrides={},
                input_mapping={},
            ),
            WorkflowNode(
                id="wf-node-2",
                workflow_id="workflow-1",
                node_id="node-2",
                name="데이터 분석",
                position={"x": 400, "y": 100},
                config_overrides={"temperature": 0.6},
                input_mapping={"filePath": "$.wf-node-1.output.reportPath"},
            ),
            WorkflowNode(
                id="wf-node-3",
                workflow_id="workflow-1",
                node_id="node-3",
                name="사용자 알림",
                position={"x": 700, "y": 100},
                config_overrides={},
                input_mapping={"department": "$.input.department"},
            ),
        ]

        for wf_node in workflow_nodes:
            session.add(wf_node)

        # Workflow Connections
        connections = [
            WorkflowConnection(
                id="conn-1",
                workflow_id="workflow-1",
                source_node_id="wf-node-1",
                target_node_id="wf-node-2",
                condition=None,
            ),
            WorkflowConnection(
                id="conn-2",
                workflow_id="workflow-1",
                source_node_id="wf-node-2",
                target_node_id="wf-node-3",
                condition=None,
            ),
        ]

        for conn in connections:
            session.add(conn)

        # ========================================
        # Commit
        # ========================================
        await session.commit()
        print(f"[OK] 시드 데이터 생성 완료:")
        print(f"  - Tasks: {len(tasks)}개")
        print(f"  - Tools: {len(tools)}개")
        print(f"  - Documents: {len(docs)}개")
        print(f"  - AI Nodes: {len(nodes)}개")
        print(f"  - Workflows: 1개 (노드 {len(workflow_nodes)}개, 연결 {len(connections)}개)")

        # 코드아이즈 지식 데이터 증분 시딩
        await seed_knowledge_data()


async def seed_knowledge_data():
    """코드아이즈 지식 데이터 증분 시딩 (이미 있으면 스킵)"""
    async with async_session_maker() as session:
        # doc-11이 이미 있으면 스킵
        result = await session.execute(
            select(KnowledgeDocument).where(KnowledgeDocument.id == "doc-11")
        )
        if result.scalar_one_or_none() is not None:
            print("[SKIP] 코드아이즈 지식 데이터가 이미 존재합니다")
            return

        print("[SEED] 코드아이즈 지식 데이터 시딩 시작...")

        docs = [
            KnowledgeDocument(
                id="doc-4",
                title="코드아이즈 서비스 개요",
                filename="코드아이즈_서비스개요.md",
                content="""# 코드아이즈 서비스 개요

코드아이즈(CodeEyes)는 소스코드 정적분석 서비스입니다.

## 주요 기능
- 소스코드의 보안 취약점, 코딩 규칙 위반, 품질 결함을 자동으로 검출
- 정적분석 결과를 대시보드로 시각화하여 제공
- CI/CD 파이프라인과 연동하여 자동 점검 가능

## 지원 언어
Java, C, C++, C#, Python, JavaScript

## 점검 항목
- 보안 취약점 (SQL Injection, XSS, 경로 조작 등)
- 코딩 규칙 위반 (네이밍, 복잡도, 중복 코드 등)
- 품질 결함 (Null 참조, 리소스 누수, 예외 처리 미비 등)

## 산출물
- 점검 결과 보고서 (PDF/Excel)
- 취약점 목록 및 조치 가이드
- 코드 품질 점수 및 추이 그래프
""",
                summary="코드아이즈 소스코드 정적분석 서비스의 주요 기능, 지원 언어, 점검 항목 안내",
                vector_id="vec-4",
                sync_status=SyncStatus.SYNCED,
                last_synced_at=datetime.utcnow(),
                token_count=180,
                source="internal",
                category="코드아이즈",
                tags=["서비스소개", "정적분석"],
                doc_metadata={"author": "서비스팀", "version": "1.0"},
            ),
            KnowledgeDocument(
                id="doc-5",
                title="코드아이즈 점검 언어 및 수집 규칙",
                filename="코드아이즈_점검언어.md",
                content="""# 코드아이즈 점검 언어 및 수집 규칙

## 지원 점검 언어
코드아이즈가 정적분석을 지원하는 언어는 다음과 같습니다:
- Java (.java)
- C (.c, .h)
- C++ (.cpp, .hpp, .cc)
- C# (.cs)
- Python (.py)
- JavaScript (.js)

## 미지원 언어 (중요)
다음 언어들은 점검 대상이 아닙니다:
- **TypeScript (.ts, .tsx)** — 점검언어가 아님
- Kotlin (.kt)
- Swift (.swift)
- Go (.go)
- Rust (.rs)

## 수집 파일 규칙
- 수집 파일 수는 **지원 언어의 소스 파일만** 카운트합니다
- 미지원 언어 파일은 수집 대상에서 제외됩니다
- 예: TypeScript 프로젝트의 경우 .ts 파일은 수집되지 않으므로 수집 파일 수가 매우 적게 나옵니다

## 준수율 계산 방식
- 준수율 = (위반 없는 파일 수 / 전체 수집 파일 수) × 100
- 미지원 언어 사용 비중이 높으면 수집 파일이 적어 준수율이 상대적으로 낮게 나타날 수 있습니다
- 이는 서비스 오류가 아닌 정상적인 동작입니다

## 자주 발생하는 오해
- "TypeScript 프로젝트인데 수집 파일이 적어요" → TypeScript는 미지원 언어이므로 정상
- "준수율이 갑자기 낮아졌어요" → 미지원 언어 파일 비중 증가 가능성 확인 필요
""",
                summary="코드아이즈 지원/미지원 점검 언어, 수집 파일 규칙, 준수율 계산 방식 안내",
                vector_id="vec-5",
                sync_status=SyncStatus.SYNCED,
                last_synced_at=datetime.utcnow(),
                token_count=250,
                source="internal",
                category="코드아이즈",
                tags=["점검언어", "수집파일", "준수율"],
                doc_metadata={"author": "기술지원팀", "version": "2.0"},
            ),
            KnowledgeDocument(
                id="doc-6",
                title="코드아이즈 민원 응대 가이드",
                filename="코드아이즈_민원응대.md",
                content="""# 코드아이즈 민원 응대 가이드

## 민원 유형별 응대 절차

### 1. 점검 결과 이상 민원
**증상**: "점검 결과가 이상합니다", "수집 파일이 적습니다", "준수율이 낮습니다"

**응대 절차**:
1. 프로젝트에서 사용하는 **주요 개발 언어** 확인
2. 코드아이즈 **지원 언어 목록**과 대조 (Java, C, C++, C#, Python, JavaScript)
3. **미지원 언어** 사용 여부 체크 (TypeScript, Kotlin, Go 등)
4. 미지원 언어 사용 시 → 수집 파일 미카운트로 인한 정상 동작임을 안내
5. 지원 언어만 사용하는데 이상한 경우 → 기술지원팀 에스컬레이션

**답변 템플릿**:
"안녕하세요, 코드아이즈 점검 결과에 대해 문의해주셔서 감사합니다.
확인 결과, 해당 프로젝트에서 [미지원 언어]를 사용하고 계신 것으로 파악됩니다.
코드아이즈는 현재 Java, C, C++, C#, Python, JavaScript를 지원하며,
[미지원 언어]는 점검 대상에 포함되지 않아 수집 파일 수가 적게 나타나는 것은 정상적인 동작입니다.
추가 문의사항이 있으시면 말씀해주세요."

### 2. 신규 언어 지원 요청 민원
**증상**: "XX 언어도 지원해주세요"

**응대 절차**:
1. 현재 미지원 언어임을 안내
2. 요청을 기능개선 요청으로 접수
3. 검토 예정 일정 안내 (구체적 일정이 없으면 "검토 후 안내" 표현)

### 3. 점검 규칙 관련 민원
**증상**: "이 규칙이 왜 위반인가요?", "오탐 같습니다"

**응대 절차**:
1. 해당 규칙의 점검 기준 설명
2. 오탐 여부 확인 (코드 샘플 요청)
3. 오탐 확인 시 → 규칙 예외 처리 방법 안내 또는 기술지원 에스컬레이션
""",
                summary="코드아이즈 서비스 관련 민원 유형별 응대 절차 및 답변 템플릿",
                vector_id="vec-6",
                sync_status=SyncStatus.SYNCED,
                last_synced_at=datetime.utcnow(),
                token_count=320,
                source="internal",
                category="코드아이즈",
                tags=["민원", "응대", "FAQ"],
                doc_metadata={"author": "CS팀", "version": "1.5"},
            ),
            KnowledgeDocument(
                id="doc-7",
                title="코드아이즈 통합UI 용역비 산정 기준",
                filename="코드아이즈_용역비산정.md",
                content="""# 코드아이즈 통합UI 용역비 산정 기준

## 1. 현황
- 전체 용역 공수: 약 17MM (솔루션 6.9MM 제외)
- 통합UI 검증 개발: 12.86MM (전체의 약 76%)
- 솔루션 연동 공수: 6.9MM (고정값)

## 2. 비율 분석
| 구분 | 공수 | 비율 |
|------|------|------|
| 솔루션 (핵심 분석 엔진) | 6.9MM | 35% |
| 통합UI (포털/프론트엔드) | 12.86MM | 65% |

- 통합UI가 솔루션 대비 약 1.9배 높게 산정됨
- 적정 비율: 솔루션 대비 최대 1:1 (50:50)

## 3. 통합UI 역할 범위
- 결과 조회/리포팅
- 분석 요청 관리
- 스케줄링 관리
- 사용자/권한 관리
- 대시보드/통계
- 외부 시스템 연동

## 4. 세부 공수 확인 사항
- 화면 수: 총 30개
- 화면별 복잡도: 단순/중간/복잡 분류
- 기능별 공수 산출 근거
- 신규 개발 vs 기존 기능 전환 여부

## 5. 조정 기준
- 세부 내역 미제시 시 → 솔루션 공수와 동일 수준(6.9MM)으로 조정
- 복합 포털 역할 입증 시 → 최대 1:1.5 비율까지 인정 가능
""",
                summary="코드아이즈 통합UI 용역비 산정 기준, 비율 분석, 조정 기준 안내",
                vector_id="vec-7",
                sync_status=SyncStatus.SYNCED,
                last_synced_at=datetime.utcnow(),
                token_count=280,
                source="internal",
                category="코드아이즈",
                tags=["용역비", "산정기준", "통합UI"],
                doc_metadata={"author": "사업관리팀", "version": "1.0"},
            ),
            KnowledgeDocument(
                id="doc-8",
                title="코드아이즈 클라우드 전환 체크리스트",
                filename="코드아이즈_클라우드전환.md",
                content="""# 코드아이즈 온프레미스 → Azure 클라우드 전환 체크리스트

## 전환 환경 요약
| 항목 | AS-IS | TO-BE |
|------|-------|-------|
| 인프라 | 온프레미스 | Azure |
| JDK | 1.8 | 17 |
| WAS | Tomcat 8.5 | Tomcat 11 |
| DB | Tibero | PostgreSQL |
| 아키텍처 | WAS 단일 | Web/WAS 분리 + 이중화 |
| 화면 수 | 30개 | - |
| 쿼리 수 | 260개 (MyBatis) | - |

## 핵심 전환 항목

### JDK 1.8 → 17
- javax → jakarta 패키지 전환 필수
- JAXB 등 제거 모듈 별도 의존성 추가
- Spring Boot 2.x → 3.x 업그레이드
- 전체 라이브러리 호환성 검토 필요

### Tibero → PostgreSQL
- SQL 문법 전환: ROWNUM→LIMIT, NVL→COALESCE, DECODE→CASE 등
- 260개 MyBatis Mapper 전수 검토
- 데이터 타입 매핑: VARCHAR2→VARCHAR, NUMBER→NUMERIC, CLOB→TEXT

### Web/WAS 분리 + 이중화
- 세션 관리: Redis 기반 세션 클러스터링 권장
- 파일 공유: Azure Files 또는 Blob Storage
- Load Balancer 구성

## 과소 산정 위험 항목
- JDK 9단계 메이저 버전 점프
- 이기종 DB 전환 (260개 쿼리 재작성)
- 이중화 신규 도입에 따른 아키텍처 변경
""",
                summary="코드아이즈 온프레미스에서 Azure로의 클라우드 전환 시 주요 체크리스트 및 위험 항목",
                vector_id="vec-8",
                sync_status=SyncStatus.SYNCED,
                last_synced_at=datetime.utcnow(),
                token_count=350,
                source="internal",
                category="코드아이즈",
                tags=["클라우드전환", "Azure", "마이그레이션"],
                doc_metadata={"author": "인프라팀", "version": "1.0"},
            ),
            KnowledgeDocument(
                id="doc-9",
                title="코드아이즈 보안 취약점 점검 규칙",
                filename="코드아이즈_보안규칙.md",
                content="""# 코드아이즈 보안 취약점 점검 규칙

## 심각도 분류
| 등급 | 설명 | 예시 |
|------|------|------|
| Critical | 즉시 조치 필요, 외부 공격 가능 | SQL Injection, 원격 코드 실행 |
| High | 높은 위험, 조기 조치 권장 | XSS, 경로 조작, 하드코딩 비밀번호 |
| Medium | 중간 위험, 계획적 조치 | 불완전한 입력 검증, 약한 암호화 |
| Low | 낮은 위험, 코드 품질 개선 | 미사용 변수, 불필요한 import |
| Info | 정보성, 참고사항 | 코딩 스타일 권고 |

## 주요 점검 규칙 (상위 10개)

### 1. SQL Injection (Critical)
- 사용자 입력을 직접 쿼리에 삽입하는 패턴 검출
- 조치: PreparedStatement 또는 파라미터 바인딩 사용

### 2. XSS (High)
- 사용자 입력을 HTML에 직접 출력하는 패턴 검출
- 조치: 출력 시 이스케이프 처리

### 3. 경로 조작 (High)
- 사용자 입력으로 파일 경로를 구성하는 패턴 검출
- 조치: 경로 정규화 및 허용 목록 검증

### 4. 하드코딩된 비밀번호 (High)
- 소스코드 내 비밀번호 문자열 리터럴 검출
- 조치: 환경변수 또는 시크릿 관리 서비스 사용

### 5. Null Pointer Dereference (Medium)
- Null 가능성이 있는 객체 직접 접근 검출
- 조치: Null 체크 추가 또는 Optional 사용

## 심각도 표시 관련 민원 응대
- 심각도는 해당 규칙의 보안 영향도에 따라 자동 분류됩니다
- 프로젝트 특성에 따라 심각도를 커스터마이징할 수 있습니다
- 오탐이 의심되는 경우 코드 샘플과 함께 기술지원팀에 문의하세요
""",
                summary="코드아이즈 보안 취약점 심각도 분류, 주요 점검 규칙, 심각도 관련 민원 응대 방법",
                vector_id="vec-9",
                sync_status=SyncStatus.SYNCED,
                last_synced_at=datetime.utcnow(),
                token_count=310,
                source="internal",
                category="코드아이즈",
                tags=["보안", "취약점", "점검규칙", "심각도"],
                doc_metadata={"author": "보안팀", "version": "2.0"},
            ),
            KnowledgeDocument(
                id="doc-10",
                title="코드아이즈 사용자 가이드",
                filename="코드아이즈_사용자가이드.md",
                content="""# 코드아이즈 사용자 가이드

## 계정 관련

### 로그인/로그아웃
- 코드아이즈 포털(https://codeeyes.example.com)에 접속
- 사번과 비밀번호로 로그인
- 초기 비밀번호: 사번 + @Temp (예: 20230001@Temp)
- 90일마다 비밀번호 변경 필요

### 비밀번호 관련 문제
- 5회 연속 실패 시 계정 잠금 (30분 후 자동 해제)
- 비밀번호 찾기: 로그인 페이지 → '비밀번호 초기화' 클릭
- 비밀번호 규칙: 영문+숫자+특수문자 포함 8자 이상

## 프로젝트 점검

### 점검 요청 방법
1. '프로젝트 관리' 메뉴 → '새 점검 요청'
2. Git 저장소 URL 또는 소스코드 ZIP 업로드
3. 점검 언어 선택 (자동 감지 가능)
4. '점검 시작' 클릭

### 점검 결과 확인
- 점검 완료 후 이메일 알림 발송
- 대시보드에서 요약 → 상세 결과 드릴다운
- 결과 보고서 PDF/Excel 다운로드 가능

### 결과 해석
- 준수율: 위반 없는 파일 / 전체 수집 파일 × 100
- 취약점 수: 심각도별 취약점 건수
- 추이 그래프: 과거 점검 대비 개선/악화 추이

## 자주 묻는 질문
Q: 점검 시간은 얼마나 걸리나요?
A: 프로젝트 규모에 따라 다르며, 보통 10만 라인 기준 15~30분 소요됩니다.

Q: 오탐은 어떻게 처리하나요?
A: 해당 취약점 → '오탐 신고' 버튼 → 코드 샘플 첨부 → 기술팀 검토 후 처리
""",
                summary="코드아이즈 서비스 사용법: 계정 관리, 로그인, 점검 요청, 결과 해석, FAQ",
                vector_id="vec-10",
                sync_status=SyncStatus.SYNCED,
                last_synced_at=datetime.utcnow(),
                token_count=340,
                source="internal",
                category="코드아이즈",
                tags=["사용자가이드", "로그인", "점검요청"],
                doc_metadata={"author": "서비스팀", "version": "3.0"},
            ),
            KnowledgeDocument(
                id="doc-11",
                title="코드아이즈 서비스 수준 협약(SLA) 및 장애 대응",
                filename="코드아이즈_SLA.md",
                content="""# 코드아이즈 서비스 수준 협약(SLA) 및 장애 대응

## SLA 기준
| 항목 | 기준 | 비고 |
|------|------|------|
| 서비스 가용률 | 99.5% (월 기준) | 계획된 점검 제외 |
| 점검 응답시간 | 10만 라인 이하 30분 내 | 대기열 상태에 따라 변동 |
| 장애 통보 | 장애 인지 후 30분 이내 | 이메일 + 포털 공지 |
| 장애 복구 | Critical 4시간, High 8시간, Medium 24시간 | 영업일 기준 |
| 기술지원 응답 | 일반 1영업일, 긴급 4시간 이내 | 근무시간 기준 |

## 장애 등급 분류
| 등급 | 정의 | 대응 |
|------|------|------|
| P1 (Critical) | 서비스 전체 중단 | 즉시 대응, 최우선 복구 |
| P2 (High) | 주요 기능 장애 | 4시간 내 복구 착수 |
| P3 (Medium) | 부분 기능 장애 | 1영업일 내 복구 착수 |
| P4 (Low) | 경미한 이슈 | 정기 배포 시 반영 |

## 점검 서버 구성
- 분석 서버 3대 (Active-Active 구성)
- 부하분산: 라운드 로빈 방식
- 장애 시: 남은 서버로 자동 전환 (처리 시간 증가 가능)

## 정기 점검 일정
- 매월 첫째 주 일요일 02:00~06:00 (4시간)
- 사전 공지: 5영업일 전 이메일 + 포털 공지

## 장애 이력 조회
- 포털 → '서비스 상태' 메뉴에서 최근 90일 장애 이력 확인 가능
- 장애 발생 시 장애보고서 자동 생성 및 공유
""",
                summary="코드아이즈 SLA 기준, 장애 등급 분류, 점검 서버 구성, 정기 점검 일정 안내",
                vector_id="vec-11",
                sync_status=SyncStatus.SYNCED,
                last_synced_at=datetime.utcnow(),
                token_count=300,
                source="internal",
                category="코드아이즈",
                tags=["SLA", "장애대응", "서비스수준"],
                doc_metadata={"author": "운영팀", "version": "1.0"},
            ),
        ]

        for doc in docs:
            await session.merge(doc)

        await session.commit()
        print(f"[OK] 코드아이즈 지식 데이터 시딩 완료: {len(docs)}건")

        # ChromaDB에 동기화
        try:
            vector_db = get_vector_db()
            for doc in docs:
                vector_db.add_document(
                    doc_id=doc.id,
                    content=doc.content,
                    metadata={
                        "title": doc.title,
                        "category": doc.category,
                        "tags": ",".join(doc.tags) if doc.tags else "",
                    },
                )
            print(f"[OK] ChromaDB 동기화 완료: {len(docs)}건")
        except Exception as e:
            print(f"[WARN] ChromaDB 동기화 실패 (DB 시딩은 완료): {e}")
