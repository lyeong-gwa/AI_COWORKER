"""
시드 데이터 생성 스크립트

초기 샘플 데이터 생성 (프론트엔드 mockData 기반)
SKIP_SEED=1 환경변수로 시드 비활성화 가능 (페르소나 테스트용)
"""

import os
from datetime import datetime, timedelta
from sqlalchemy import select

from .models.task import Task, TaskStatus, TaskPriority
from .models.tool import ToolDefinition, ToolType
from .models.node import AINode
from .models.workflow import Workflow, WorkflowStatus, WorkflowNode, WorkflowConnection
from .core.database import async_session_maker
from .services.embedding.vector_db import get_vector_db
from .services.knowledge_file_service import write_md_file, read_md_file, _knowledge_dir


async def seed_database():
    """초기 데이터 시딩 (데이터가 없을 때만). SKIP_SEED=1로 비활성화 가능."""
    if os.environ.get("SKIP_SEED") == "1":
        print("[SKIP] SKIP_SEED=1 - 시드 데이터 비활성화됨")
        return

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
        # 3. Knowledge Documents (3개 - MD 파일로 생성)
        # ========================================
        knowledge_dir = _knowledge_dir()

        seed_docs = [
            {
                "id": "업무프로세스",
                "title": "회사 업무 프로세스 가이드",
                "content": """# 회사 업무 프로세스 가이드

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
3. AI 노드에서 컨텍스트로 활용""",
                "category": "가이드",
                "tags": ["프로세스", "업무"],
                "source": "internal",
            },
            {
                "id": "API규칙",
                "title": "API 개발 규칙",
                "content": """# API 개발 규칙

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
- 하위 호환성 유지""",
                "category": "개발",
                "tags": ["API", "규칙"],
                "source": "internal",
            },
            {
                "id": "FAQ",
                "title": "고객 지원 FAQ",
                "content": """# 고객 지원 FAQ

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
A. 모든 데이터는 암호화되어 저장되며, 정기적으로 백업됩니다.""",
                "category": "FAQ",
                "tags": ["고객지원", "FAQ"],
                "source": "customer_support",
            },
        ]

        docs = []
        for d in seed_docs:
            if not os.path.exists(os.path.join(knowledge_dir, f"{d['id']}.md")):
                doc = write_md_file(
                    doc_id=d["id"],
                    title=d["title"],
                    content=d["content"],
                    category=d["category"],
                    tags=d["tags"],
                    source=d["source"],
                )
                docs.append(doc)

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
    """코드아이즈 지식 데이터 증분 시딩 (이미 있으면 스킵). SKIP_SEED=1로 비활성화 가능."""
    if os.environ.get("SKIP_SEED") == "1":
        print("[SKIP] SKIP_SEED=1 - 지식 데이터 시딩 비활성화됨")
        return

    knowledge_dir = _knowledge_dir()

    # 코드아이즈_SLA 파일이 이미 있으면 스킵
    if os.path.exists(os.path.join(knowledge_dir, "코드아이즈_SLA.md")):
        print("[SKIP] 코드아이즈 지식 데이터가 이미 존재합니다")
        return

    print("[SEED] 코드아이즈 지식 데이터 시딩 시작...")

    codeeyes_docs = [
        {
            "id": "코드아이즈_서비스개요",
            "title": "코드아이즈 서비스 개요",
            "content": "코드아이즈(CodeEyes)는 소스코드 정적분석 서비스입니다.\n\n## 주요 기능\n- 소스코드의 보안 취약점, 코딩 규칙 위반, 품질 결함을 자동으로 검출\n- 정적분석 결과를 대시보드로 시각화하여 제공\n- CI/CD 파이프라인과 연동하여 자동 점검 가능\n\n## 지원 언어\nJava, C, C++, C#, Python, JavaScript",
            "category": "코드아이즈",
            "tags": ["서비스소개", "정적분석"],
            "source": "internal",
        },
        {
            "id": "코드아이즈_점검언어",
            "title": "코드아이즈 점검 언어 및 수집 규칙",
            "content": "# 코드아이즈 점검 언어 및 수집 규칙\n\n## 지원 점검 언어\nJava, C, C++, C#, Python, JavaScript\n\n## 미지원 언어\nTypeScript, Kotlin, Swift, Go, Rust",
            "category": "코드아이즈",
            "tags": ["점검언어", "수집파일"],
            "source": "internal",
        },
        {
            "id": "코드아이즈_민원응대",
            "title": "코드아이즈 민원 응대 가이드",
            "content": "# 코드아이즈 민원 응대 가이드\n\n점검 결과 이상 민원, 신규 언어 지원 요청, 점검 규칙 관련 민원 응대 절차",
            "category": "코드아이즈",
            "tags": ["민원", "응대"],
            "source": "internal",
        },
        {
            "id": "코드아이즈_용역비산정",
            "title": "코드아이즈 통합UI 용역비 산정 기준",
            "content": "# 코드아이즈 통합UI 용역비 산정 기준\n\n통합UI 용역비 산정 및 비율 분석",
            "category": "코드아이즈",
            "tags": ["용역비", "산정기준"],
            "source": "internal",
        },
        {
            "id": "코드아이즈_클라우드전환",
            "title": "코드아이즈 클라우드 전환 체크리스트",
            "content": "# 코드아이즈 온프레미스 -> Azure 클라우드 전환 체크리스트",
            "category": "코드아이즈",
            "tags": ["클라우드전환", "Azure"],
            "source": "internal",
        },
        {
            "id": "코드아이즈_보안규칙",
            "title": "코드아이즈 보안 취약점 점검 규칙",
            "content": "# 코드아이즈 보안 취약점 점검 규칙\n\n심각도 분류 및 주요 점검 규칙",
            "category": "코드아이즈",
            "tags": ["보안", "취약점"],
            "source": "internal",
        },
        {
            "id": "코드아이즈_사용자가이드",
            "title": "코드아이즈 사용자 가이드",
            "content": "# 코드아이즈 사용자 가이드\n\n계정 관리, 프로젝트 점검 방법",
            "category": "코드아이즈",
            "tags": ["사용자가이드", "로그인"],
            "source": "internal",
        },
        {
            "id": "코드아이즈_SLA",
            "title": "코드아이즈 서비스 수준 협약(SLA) 및 장애 대응",
            "content": "# 코드아이즈 서비스 수준 협약(SLA) 및 장애 대응\n\nSLA 기준, 장애 등급 분류",
            "category": "코드아이즈",
            "tags": ["SLA", "장애대응"],
            "source": "internal",
        },
    ]

    count = 0
    for d in codeeyes_docs:
        filepath = os.path.join(knowledge_dir, f"{d['id']}.md")
        if not os.path.exists(filepath):
            write_md_file(
                doc_id=d["id"],
                title=d["title"],
                content=d["content"],
                category=d["category"],
                tags=d["tags"],
                source=d["source"],
            )
            count += 1

    print(f"[OK] 코드아이즈 지식 데이터 {count}건 MD 파일 생성 완료")

    # ChromaDB 동기화
    try:
        vector_db = get_vector_db()
        from .services.knowledge_file_service import list_md_files, compute_hash
        all_docs = list_md_files()
        synced = 0
        for doc in all_docs:
            try:
                content_hash = compute_hash(doc.content)
                vector_db.add_document(
                    doc_id=doc.id,
                    content=doc.content,
                    metadata={
                        "title": doc.title,
                        "category": doc.category or "",
                        "source": doc.source or "",
                        "content_hash": content_hash,
                    },
                )
                synced += 1
            except Exception as e:
                print(f"  [WARN] 동기화 실패: {doc.id} - {e}")
        print(f"[OK] ChromaDB 동기화: {synced}/{len(all_docs)}건")
    except Exception as e:
        print(f"[WARN] ChromaDB 동기화 실패 (나중에 수동 동기화 필요): {e}")
