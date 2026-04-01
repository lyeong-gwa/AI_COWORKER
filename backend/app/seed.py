"""
시드 데이터 생성 스크립트

초기 샘플 데이터 생성 (프론트엔드 mockData 기반)
SKIP_SEED=1 환경변수로 시드 비활성화 가능 (페르소나 테스트용)
"""

import os
from datetime import datetime
from sqlalchemy import select

from .models.node import AINode
from .models.workflow import (
    Workflow, WorkflowNode, WorkflowConnection,
    WorkflowStatus,
)
from .models.api_definition import ApiDefinition
from .core.constants import NodeDefType
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
        result = await session.execute(select(AINode).limit(1))
        if result.scalar_one_or_none() is not None:
            print("[SKIP] 이미 시드 데이터가 존재합니다")
            await seed_knowledge_data()
            return

        print("[SEED] 시드 데이터 생성 시작...")

        # ========================================
        # 1. Knowledge Documents (3개 - MD 파일로 생성)
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
        # 3. AI Nodes (2개 - GitHub 커밋 진단 워크플로우용)
        # ========================================
        ai_nodes = [
            AINode(
                id="node-github-url-parser",
                name="GitHub URL 파서",
                description="GitHub URL에서 owner와 repo를 추출합니다.",
                category="유틸리티",
                icon="🔗",
                color="text-green-400",
                tags=["GitHub", "파싱", "URL"],
                system_prompt="당신은 GitHub URL 파싱 전문가입니다. 주어진 URL에서 owner와 repo를 정확히 추출하세요.",
                user_prompt_template="""다음 GitHub URL에서 owner와 repo를 추출하세요.

URL: {{input.githubUrl}}

반드시 아래 JSON 형식으로만 응답하세요:
{"owner": "추출된_owner", "repo": "추출된_repo"}""",
                input_schema={
                    "type": "object",
                    "properties": {
                        "githubUrl": {"type": "string", "description": "GitHub 리포지토리 URL"},
                    },
                    "required": ["githubUrl"],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "owner": {"type": "string"},
                        "repo": {"type": "string"},
                    },
                    "required": ["owner", "repo"],
                },
                output_enforcement={
                    "enabled": True,
                    "includeSchemaInPrompt": True,
                    "exampleOutput": '{"owner": "octocat", "repo": "Hello-World"}',
                    "validationEnabled": True,
                    "retryOnFailure": True,
                    "maxRetries": 2,
                },
                llm_config={
                    "model": "gpt-4o-mini",
                    "temperature": 0.1,
                    "maxTokens": 200,
                },
            ),
            AINode(
                id="node-commit-diagnosis",
                name="커밋 변경사항 진단기",
                description="커밋 변경사항 데이터를 분석하여 코드 변경 진단과 테스트 추천을 제공합니다.",
                category="분석",
                icon="🔍",
                color="text-orange-400",
                tags=["GitHub", "코드리뷰", "진단", "테스트"],
                system_prompt="당신은 시니어 소프트웨어 엔지니어이자 코드 리뷰 전문가입니다. GitHub 커밋 변경사항을 분석하여 체계적인 진단 보고서를 작성합니다.",
                user_prompt_template="""## 커밋 변경사항 진단 요청

**리포지토리**: {{input.owner}}/{{input.repo}}
**비교 범위**: {{input.commitId1}} → {{input.commitId2}}

### 변경사항 데이터:
{{input.compareData}}

---

위 변경사항을 분석하여 다음 JSON 형식으로 진단 결과를 작성하세요:

{
  "summary": "전체 변경 요약 (1-2문장)",
  "stats": {
    "totalFiles": 0,
    "additions": 0,
    "deletions": 0
  },
  "fileCategories": {
    "added": ["파일명"],
    "modified": ["파일명"],
    "removed": ["파일명"],
    "renamed": ["파일명"]
  },
  "riskAreas": [
    {
      "area": "위험 영역명",
      "severity": "상/중/하",
      "reason": "이유",
      "recommendation": "권장 조치"
    }
  ],
  "testRecommendations": [
    {
      "id": "TC-001",
      "target": "테스트 대상",
      "description": "테스트 설명",
      "priority": "상/중/하"
    }
  ]
}""",
                input_schema={
                    "type": "object",
                    "properties": {
                        "owner": {"type": "string", "description": "GitHub owner"},
                        "repo": {"type": "string", "description": "GitHub repo"},
                        "commitId1": {"type": "string", "description": "시작 커밋 SHA"},
                        "commitId2": {"type": "string", "description": "끝 커밋 SHA"},
                        "compareData": {"type": "string", "description": "GitHub Compare API 응답 데이터"},
                    },
                    "required": ["owner", "repo", "commitId1", "commitId2", "compareData"],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "summary": {"type": "string"},
                        "stats": {"type": "object"},
                        "fileCategories": {"type": "object"},
                        "riskAreas": {"type": "array"},
                        "testRecommendations": {"type": "array"},
                    },
                    "required": ["summary", "stats", "fileCategories", "riskAreas", "testRecommendations"],
                },
                output_enforcement={
                    "enabled": True,
                    "includeSchemaInPrompt": False,
                    "exampleOutput": None,
                    "validationEnabled": True,
                    "retryOnFailure": True,
                    "maxRetries": 2,
                },
                llm_config={
                    "model": "gpt-4o",
                    "temperature": 0.3,
                    "maxTokens": 4000,
                },
            ),
            AINode(
                id="node-code-review-md",
                name="코드 리뷰 MD 생성기",
                description="GitHub 커밋 diff를 분석하여 마크다운 형식의 코드 리뷰 보고서를 생성합니다.",
                category="분석",
                icon="📝",
                color="text-emerald-400",
                tags=["GitHub", "코드리뷰", "마크다운"],
                system_prompt="""당신은 10년 이상 경력의 시니어 소프트웨어 엔지니어이자 코드 리뷰 전문가입니다.
GitHub 커밋 비교 데이터(diff)를 분석하여 GitHub PR 리뷰 수준의 상세한 마크다운 코드 리뷰 보고서를 작성합니다.

핵심 원칙:
1. **실제 코드 diff를 반드시 포함**하세요. 각 파일의 patch 데이터에서 핵심 변경 부분을 diff 코드블록으로 보여주세요.
2. 각 diff 블록 바로 아래에 **인라인 코멘트**를 달아주세요 (GitHub PR 리뷰 스타일).
3. 코멘트는 severity 레벨을 포함하세요: 🔴 Critical, 🟡 Warning, 🔵 Info, ✅ Good.
4. 보안, 성능, 가독성, 유지보수성, 잠재 버그 관점에서 검토하세요.
5. 단순 설명이 아닌 **왜** 문제인지, **어떻게** 개선할 수 있는지 제안하세요.
6. 좋은 변경사항에 대해서도 구체적으로 칭찬하세요.
7. 출력은 반드시 순수한 마크다운 텍스트여야 합니다 (JSON이 아닙니다).
8. diff 코드블록은 ```diff 로 시작하세요.""",
                user_prompt_template="""## 코드 리뷰 요청

**리포지토리**: {{input.owner}}/{{input.repo}}
**비교 범위**: {{input.commitId1}} → {{input.commitId2}}

### 변경사항 데이터 (GitHub Compare API 응답):
{{input.compareData}}

---

위 데이터의 각 파일별 `patch` 필드에 실제 코드 diff가 포함되어 있습니다.
이를 분석하여 아래 형식의 상세 코드 리뷰 보고서를 작성하세요.

**중요**: 각 파일의 diff를 코드블록으로 직접 보여주고, 변경된 코드에 대해 인라인 코멘트를 달아주세요.

---

# 코드 리뷰 보고서

## 개요
- **리포지토리**: owner/repo
- **비교 범위**: commitId1 → commitId2
- **변경 통계**: N개 파일, +추가 / -삭제 라인
- **커밋 수**: N개

## 변경 요약
(전체 변경사항을 2-3문장으로 요약. 이번 변경의 목적과 영향을 설명)

## 파일별 상세 리뷰

### 📄 `파일경로/파일명.확장자`
**변경 유형**: modified | **라인 변경**: +N / -N

```diff
@@ -원본시작,원본줄수 +변경시작,변경줄수 @@
 컨텍스트 라인 (변경 없음)
-삭제된 코드
+추가된 코드
 컨텍스트 라인
```

> 🔵 **[Info]** 변경 설명: 무엇이 왜 변경되었는지 설명

```diff
@@ 다른 변경 부분 @@
-이전 코드
+새 코드
```

> 🟡 **[Warning]** null 체크가 누락되어 있습니다. `value != null` 조건을 추가하는 것을 권장합니다.

(파일별로 반복. patch가 긴 경우 핵심 변경부분만 발췌하여 보여주세요)

## 보안 검토
(보안 관련 이슈 목록. 없으면 "특이사항 없음")

## 성능 영향
(성능에 영향을 줄 수 있는 변경사항 분석)

## 종합 평가
- **위험도**: 🟢 낮음 / 🟡 중간 / 🔴 높음
- **승인 권장**: ✅ 승인 / ⚠️ 조건부 승인 / ❌ 수정 필요
- **주요 발견사항**: (가장 중요한 코멘트 1-3개 요약)

---
*이 리뷰는 AI가 자동 생성했습니다.*""",
                input_schema={
                    "type": "object",
                    "properties": {
                        "owner": {"type": "string", "description": "GitHub owner"},
                        "repo": {"type": "string", "description": "GitHub repo"},
                        "commitId1": {"type": "string", "description": "시작 커밋 SHA"},
                        "commitId2": {"type": "string", "description": "끝 커밋 SHA"},
                        "compareData": {"type": "string", "description": "GitHub Compare API 응답 데이터"},
                    },
                    "required": ["owner", "repo", "commitId1", "commitId2", "compareData"],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "markdown": {"type": "string", "description": "마크다운 형식의 코드 리뷰 보고서"},
                    },
                    "required": ["markdown"],
                },
                output_enforcement={
                    "enabled": True,
                    "includeSchemaInPrompt": True,
                    "validationEnabled": True,
                    "retryOnFailure": True,
                    "maxRetries": 2,
                },
                llm_config={
                    "model": "gpt-4o",
                    "temperature": 0.3,
                    "maxTokens": 8000,
                },
            ),
            AINode(
                id="node-inquiry-answer-gen",
                name="문의글 답변 생성기",
                description="문의글 내용과 관련 지식을 기반으로 적절한 답변을 자동 생성합니다.",
                category="자동화",
                icon="💬",
                color="#8b5cf6",
                tags=["답변생성", "LLM", "문의글"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "board_id": {"type": "number", "description": "문의글 ID"},
                        "title": {"type": "string", "description": "문의 제목"},
                        "description": {"type": "string", "description": "문의 내용"},
                        "category": {"type": "string", "description": "문의 카테고리"},
                        "member_id": {"type": "string", "description": "작성자 ID"},
                        "knowledge": {"type": "array", "description": "관련 지식 목록", "items": {"type": "object"}},
                    },
                    "required": ["title", "description"],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "board_id": {"type": "number", "description": "문의글 ID"},
                        "title": {"type": "string", "description": "문의 제목"},
                        "answer": {"type": "string", "description": "생성된 답변"},
                        "replyer": {"type": "string", "description": "답변자 이름", "default": "AI어시스턴트"},
                        "confidence": {"type": "string", "description": "답변 신뢰도 (높음/중간/낮음)"},
                        "referencedKnowledge": {"type": "array", "description": "참조한 지식 문서 제목 목록 (제공된 모든 지식 포함)", "items": {"type": "string"}},
                    },
                    "required": ["board_id", "title", "answer", "replyer", "referencedKnowledge"],
                },
                system_prompt="""당신은 소스코드검증 시스템의 고객 문의 답변 전문가입니다.
사용자의 문의에 대해 제공된 지식 문서를 참고하여 정확하고 친절한 답변을 작성합니다.

답변 작성 원칙:
1. 제공된 지식 문서의 내용을 최대한 활용하세요.
2. 지식 문서에 없는 내용은 추측하지 마세요.
3. 존칭을 사용하고 친절하며 전문적인 어투를 유지하세요.
4. 구체적인 절차나 경로가 있다면 단계별로 안내하세요.
5. 답변에 확신이 없는 부분은 confidence를 "낮음"으로 표시하세요.
6. referencedKnowledge에는 제공된 지식 문서의 제목을 **빠짐없이 모두** 포함하세요.""",
                user_prompt_template="""## 문의 정보
- 문의번호: {{input.board_id}}
- 제목: {{input.title}}
- 카테고리: {{input.category}}
- 작성자: {{input.member_id}}
- 내용: {{input.description}}

## 참고 지식 문서
{{input.knowledge}}

위 문의에 대해 참고 지식을 활용하여 답변을 JSON 형식으로 작성하세요.""",
                llm_config={
                    "model": "gpt-4o-mini",
                    "temperature": 0.3,
                    "maxTokens": 1500,
                },
                output_enforcement={
                    "enabled": True,
                    "includeSchemaInPrompt": True,
                    "validationEnabled": True,
                    "retryOnFailure": True,
                    "maxRetries": 2,
                },
                is_active=True,
            ),
            AINode(
                id="node-spec-table-gen",
                name="스펙 테이블 생성기",
                description="시스템 스펙 지식 문서를 분석하여 항목/설명/비고 마크다운 테이블로 정리합니다.",
                category="분석",
                icon="📊",
                color="text-cyan-400",
                tags=["스펙", "테이블", "마크다운", "지식"],
                system_prompt="""당신은 서비스 인프라 스펙 문서를 표준 양식으로 정리하는 전문가입니다.
제공된 지식 문서(스펙 데이터 + 양식 정의)를 분석하여, 양식에 맞는 마크다운 테이블을 생성합니다.

핵심 원칙:
1. 지식 문서 중 '양식' 태그가 있는 문서는 출력 형식의 템플릿으로 사용하세요.
2. 지식 문서 중 '인프라' 태그가 있는 문서는 실제 데이터 소스로 사용하세요.
3. 반드시 다음 두 가지 표준 양식을 모두 생성하세요:
   - **서비스정보표**: 서비스 기본정보(서비스명/약칭/총서버대수/OS/DBMS/호스트명규칙) + 환경별 구성 요약(서버수/네트워크/호스트명범위/IP범위)
   - **서버쌍구성표**: 환경별로 AP-DB 쌍 구성(쌍번호/AP호스트명/AP IP/DB호스트명/DB IP/OS/DBMS/네트워크대역/비고)
4. 양식의 placeholder (예: (서비스명), (N대)) 를 실제 데이터로 채우세요.
5. 출력은 반드시 순수한 마크다운 텍스트여야 합니다 (JSON이 아닙니다).
6. 데이터가 없는 항목은 '-' 로 표시하세요.""",
                user_prompt_template="""## 스펙 테이블 생성 요청

**시스템명**: {{input.system_name}}
**카테고리**: {{input.category}}

### 관련 지식 문서:
{{input.knowledge}}

---

위 지식 문서들을 분석하여 아래 두 양식의 마크다운 테이블을 작성하세요.
양식 문서(서비스정보표 양식, 서버쌍구성표 양식)의 구조를 따르되, 스펙 데이터로 실제 값을 채우세요.

# {{input.system_name}} 스펙 테이블

## 1. 서비스정보표

### 서비스 기본정보

| 항목 | 내용 | 비고 |
|------|------|------|
| 서비스명 | (스펙에서 추출) | |
| 서비스 약칭 | (스펙에서 추출) | |
| 총 서버 대수 | (N대) | 운영 N대 + 개발 N대 |
| 운영체제 | (OS명 버전) | |
| DBMS | (DB명 버전) | |
| 호스트명 규칙 | (네이밍 패턴) | |

### 환경별 구성 요약

| 항목 | 운영 환경 | 개발 환경 | 비고 |
|------|----------|----------|------|
| 서버 총 대수 | | | |
| AP 서버 수 | | | |
| DB 서버 수 | | | |
| 네트워크 대역 | | | |
| AP 호스트명 범위 | | | |
| DB 호스트명 범위 | | | |
| AP IP 범위 | | | |
| DB IP 범위 | | | |

## 2. 서버쌍구성표

### [운영] 서버쌍구성표

| 쌍 번호 | AP 호스트명 | AP IP | DB 호스트명 | DB IP | OS | DBMS | 네트워크 대역 | 비고 |
|---------|------------|-------|------------|-------|-----|------|-------------|------|
| 1 | | | | | | | | |

### [개발] 서버쌍구성표

| 쌍 번호 | AP 호스트명 | AP IP | DB 호스트명 | DB IP | OS | DBMS | 네트워크 대역 | 비고 |
|---------|------------|-------|------------|-------|-----|------|-------------|------|
| 1 | | | | | | | | |

---

모든 서버 정보를 빠짐없이 포함하세요. 실제 데이터로 각 셀을 채우세요.""",
                input_schema={
                    "type": "object",
                    "properties": {
                        "system_name": {"type": "string", "description": "시스템명 또는 검색 키워드"},
                        "category": {"type": "string", "description": "지식 카테고리 (예: 소스코드검증)"},
                        "knowledge": {"type": "array", "description": "검색된 지식 문서 목록", "items": {"type": "object"}},
                    },
                    "required": ["system_name"],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "markdown": {"type": "string", "description": "마크다운 테이블 형식의 스펙 정리"},
                    },
                    "required": ["markdown"],
                },
                output_enforcement={
                    "enabled": False,
                    "includeSchemaInPrompt": False,
                    "validationEnabled": False,
                    "retryOnFailure": False,
                    "maxRetries": 0,
                },
                llm_config={
                    "model": "gpt-4o",
                    "temperature": 0.3,
                },
            ),
        ]

        for ai_node in ai_nodes:
            session.add(ai_node)

        # ========================================
        # 4. API Definitions (도구-API 지식 문서 마이그레이션)
        # ========================================
        api_definitions = [
            ApiDefinition(
                id="api-support-view",
                name="시스템 문의글 조회 API",
                description="시스템에 등록된 문의글 목록을 조회하는 API입니다.",
                icon="📋",
                color="text-blue-400",
                category="내부시스템",
                tags=["API", "문의글", "조회", "support"],
                method="GET",
                url_template="http://localhost:8000/rest-comm/support/view-list",
                headers={"Content-Type": "application/json"},
                body_template=None,
                auth_type="none",
                auth_config={},
                parameters=[],
                response_schema={
                    "fields": [
                        {"field": "board_id", "type": "number", "description": "문의글 고유 ID"},
                        {"field": "title", "type": "string", "description": "문의 제목"},
                        {"field": "category", "type": "string", "description": "문의 카테고리"},
                        {"field": "description", "type": "string", "description": "문의 내용"},
                        {"field": "status", "type": "string", "description": "처리 상태 (신규, 확인중, 답변완료)"},
                        {"field": "member_id", "type": "string", "description": "작성자 ID"},
                        {"field": "reg_date", "type": "string", "description": "등록일시"},
                    ],
                    "example": None,
                },
            ),
            ApiDefinition(
                id="api-gh-compare",
                name="GitHub 두 커밋 비교 API",
                description="두 개의 커밋(base, head)을 비교하여 변경된 파일 목록, 코드 diff, 커밋 이력을 조회합니다.",
                icon="🔀",
                color="text-green-400",
                category="GitHub",
                tags=["GitHub", "커밋비교"],
                method="GET",
                url_template="https://api.github.com/repos/{{owner}}/{{repo}}/compare/{{base}}...{{head}}",
                headers={
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                body_template=None,
                auth_type="bearer",
                auth_config={"token": "{{token}}"},
                parameters=[
                    {"name": "owner", "in": "path", "type": "string", "required": True, "description": "레포지토리 소유자", "default": None},
                    {"name": "repo", "in": "path", "type": "string", "required": True, "description": "레포지토리 이름", "default": None},
                    {"name": "base", "in": "path", "type": "string", "required": True, "description": "기준 커밋 SHA 또는 브랜치명", "default": None},
                    {"name": "head", "in": "path", "type": "string", "required": True, "description": "비교 대상 커밋 SHA 또는 브랜치명", "default": None},
                    {"name": "token", "in": "header", "type": "string", "required": False, "description": "GitHub 개인 액세스 토큰 (공개 리포는 불필요)", "default": None},
                ],
                response_schema={
                    "fields": [
                        {"field": "status", "type": "string", "description": "비교 상태 (ahead, behind, identical, diverged)"},
                        {"field": "ahead_by", "type": "number", "description": "head가 base보다 앞선 커밋 수"},
                        {"field": "behind_by", "type": "number", "description": "head가 base보다 뒤쳐진 커밋 수"},
                        {"field": "total_commits", "type": "number", "description": "두 커밋 사이 총 커밋 수"},
                        {"field": "commits", "type": "array", "description": "커밋 객체 배열"},
                        {"field": "files", "type": "array", "description": "변경된 파일 배열"},
                    ],
                    "example": None,
                },
            ),
            ApiDefinition(
                id="api-gh-get-commit",
                name="GitHub 커밋 상세 조회 API",
                description="특정 커밋의 상세 정보를 조회합니다.",
                icon="📝",
                color="text-green-400",
                category="GitHub",
                tags=["GitHub", "커밋"],
                method="GET",
                url_template="https://api.github.com/repos/{{owner}}/{{repo}}/commits/{{ref}}",
                headers={
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                body_template=None,
                auth_type="bearer",
                auth_config={"token": "{{token}}"},
                parameters=[
                    {"name": "owner", "in": "path", "type": "string", "required": True, "description": "레포지토리 소유자", "default": None},
                    {"name": "repo", "in": "path", "type": "string", "required": True, "description": "레포지토리 이름", "default": None},
                    {"name": "ref", "in": "path", "type": "string", "required": True, "description": "커밋 SHA 또는 브랜치명", "default": None},
                    {"name": "token", "in": "header", "type": "string", "required": False, "description": "GitHub PAT (공개 리포는 불필요)", "default": None},
                ],
                response_schema={"fields": [], "example": None},
            ),
            ApiDefinition(
                id="api-gh-contents",
                name="GitHub 파일 내용 조회 API",
                description="레포지토리의 특정 경로에 있는 파일 내용을 조회합니다.",
                icon="📄",
                color="text-green-400",
                category="GitHub",
                tags=["GitHub", "파일"],
                method="GET",
                url_template="https://api.github.com/repos/{{owner}}/{{repo}}/contents/{{path}}",
                headers={
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                body_template=None,
                auth_type="bearer",
                auth_config={"token": "{{token}}"},
                parameters=[
                    {"name": "owner", "in": "path", "type": "string", "required": True, "description": "레포지토리 소유자", "default": None},
                    {"name": "repo", "in": "path", "type": "string", "required": True, "description": "레포지토리 이름", "default": None},
                    {"name": "path", "in": "path", "type": "string", "required": True, "description": "파일 경로", "default": None},
                    {"name": "token", "in": "header", "type": "string", "required": False, "description": "GitHub PAT (공개 리포는 불필요)", "default": None},
                ],
                response_schema={"fields": [], "example": None},
            ),
            ApiDefinition(
                id="api-gh-list-commits",
                name="GitHub 커밋 이력 조회 API",
                description="레포지토리의 커밋 이력을 조회합니다.",
                icon="📋",
                color="text-green-400",
                category="GitHub",
                tags=["GitHub", "커밋이력"],
                method="GET",
                url_template="https://api.github.com/repos/{{owner}}/{{repo}}/commits",
                headers={
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                body_template=None,
                auth_type="bearer",
                auth_config={"token": "{{token}}"},
                parameters=[
                    {"name": "owner", "in": "path", "type": "string", "required": True, "description": "레포지토리 소유자", "default": None},
                    {"name": "repo", "in": "path", "type": "string", "required": True, "description": "레포지토리 이름", "default": None},
                    {"name": "token", "in": "header", "type": "string", "required": False, "description": "GitHub PAT (공개 리포는 불필요)", "default": None},
                ],
                response_schema={"fields": [], "example": None},
            ),
            ApiDefinition(
                id="api-send-result2",
                name="sendResult2 API",
                description="소스코드 정적분석 결과를 외부 시스템에 전송하는 API입니다.",
                icon="📤",
                color="text-purple-400",
                category="소스코드검증",
                tags=["소스코드검증", "결과전송"],
                method="POST",
                url_template="https://example.com/api/sendResult2",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": "Bearer {{token}}",
                },
                body_template='{"projectId": "{{projectId}}", "resultType": "{{resultType}}", "data": {{data}}}',
                auth_type="bearer",
                auth_config={"token": "{{token}}"},
                parameters=[
                    {"name": "token", "in": "header", "type": "string", "required": True, "description": "인증 토큰", "default": None},
                    {"name": "projectId", "in": "body", "type": "string", "required": True, "description": "프로젝트 ID", "default": None},
                    {"name": "resultType", "in": "body", "type": "string", "required": True, "description": "결과 유형 (full/summary)", "default": None},
                    {"name": "data", "in": "body", "type": "object", "required": True, "description": "분석 결과 데이터", "default": None},
                ],
                response_schema={
                    "fields": [
                        {"field": "code", "type": "int", "description": "응답코드 (200=성공)"},
                        {"field": "message", "type": "string", "description": "응답 메시지"},
                        {"field": "requestId", "type": "string", "description": "요청 추적 ID"},
                    ],
                    "example": None,
                },
            ),
            ApiDefinition(
                id="api-get-project-status",
                name="getProjectStatus API",
                description="프로젝트의 현재 점검 상태를 조회하는 API입니다.",
                icon="🔍",
                color="text-purple-400",
                category="소스코드검증",
                tags=["소스코드검증", "프로젝트조회"],
                method="GET",
                url_template="https://example.com/api/projects/{{projectId}}/status",
                headers={
                    "Authorization": "Bearer {{token}}",
                    "Accept": "application/json",
                },
                body_template=None,
                auth_type="bearer",
                auth_config={"token": "{{token}}"},
                parameters=[
                    {"name": "projectId", "in": "path", "type": "string", "required": True, "description": "프로젝트 ID (URL 경로)", "default": None},
                    {"name": "token", "in": "header", "type": "string", "required": True, "description": "인증 토큰", "default": None},
                ],
                response_schema={
                    "fields": [
                        {"field": "projectId", "type": "string", "description": "프로젝트 ID"},
                        {"field": "status", "type": "string", "description": "점검 상태 (pending/running/completed/failed)"},
                        {"field": "progress", "type": "number", "description": "진행률 (0~100)"},
                        {"field": "lastCheckedAt", "type": "string", "description": "마지막 점검 일시"},
                    ],
                    "example": None,
                },
            ),
        ]

        for api_def in api_definitions:
            session.add(api_def)

        # ========================================
        # 5. Workflow - 문의글 자동 답변 파이프라인
        # ========================================
        wf = Workflow(
            id="factory-main",
            name="문의글 자동 답변",
            description="문의글 조회 → 분리 → 신규 필터 → 지식 검색 → 답변 생성 파이프라인",
            status=WorkflowStatus.ACTIVE,
            tags=["문의글", "자동답변", "RAG"],
            viewport={"x": 0, "y": 0, "zoom": 1},
            trigger={"type": "manual", "config": {}},
            variables={},
        )
        session.add(wf)

        # 워크플로우 노드 6개
        wf_nodes = [
            WorkflowNode(
                id="wfn-api-start",
                workflow_id="factory-main",
                node_id="api-start",
                definition_type=NodeDefType.API_START.value,
                ai_node_id=None,
                name="문의글 조회",
                position={"x": 50, "y": 250},
                config={
                    "mode": "manual",
                    "apiDefinitionId": "api-support-view",
                    "docId": "api_support_view_list",
                    "docTitle": "시스템 문의글 조회 API",
                    "method": "GET",
                    "url": "http://localhost:8000/rest-comm/support/view-list",
                    "inputFields": [],
                    "defaultParams": {},
                },
                input_mapping={},
            ),
            WorkflowNode(
                id="wfn-unpacker",
                workflow_id="factory-main",
                node_id="unpacker",
                definition_type=NodeDefType.UNPACKER.value,
                ai_node_id=None,
                name="문의글 분리",
                position={"x": 350, "y": 250},
                config={"arrayField": "data.data"},
                input_mapping={},
            ),
            WorkflowNode(
                id="wfn-sorter",
                workflow_id="factory-main",
                node_id="sorter",
                definition_type=NodeDefType.SORTER.value,
                ai_node_id=None,
                name="신규 문의 필터",
                position={"x": 650, "y": 250},
                config={
                    "rules": [
                        {"id": "rule-1", "field": "status", "operator": "equals", "value": "신규", "label": "신규 문의"}
                    ]
                },
                input_mapping={},
            ),
            WorkflowNode(
                id="wfn-knowledge",
                workflow_id="factory-main",
                node_id="knowledge",
                definition_type=NodeDefType.KNOWLEDGE.value,
                ai_node_id=None,
                name="관련 지식 검색",
                position={"x": 950, "y": 250},
                config={
                    "searchField": "title",
                    "category": "소스코드검증",
                    "tags": [],
                    "maxResults": 5,
                },
                input_mapping={},
            ),
            WorkflowNode(
                id="wfn-llm",
                workflow_id="factory-main",
                node_id="node-inquiry-answer-gen",
                definition_type=NodeDefType.AI_CUSTOM.value,
                ai_node_id="node-inquiry-answer-gen",
                name="답변 생성기",
                position={"x": 1250, "y": 250},
                config={},
                input_mapping={
                    "board_id": "$.board_id",
                    "title": "$.title",
                    "description": "$.description",
                    "category": "$.category",
                    "member_id": "$.member_id",
                    "knowledge": "$.knowledge",
                },
            ),
            WorkflowNode(
                id="wfn-warehouse",
                workflow_id="factory-main",
                node_id="result",
                definition_type=NodeDefType.RESULT.value,
                ai_node_id=None,
                name="답변 보관함",
                position={"x": 1600, "y": 250},
                config={},
                input_mapping={},
            ),
        ]

        # ── 코드 리뷰 MD 파이프라인 (아래쪽) ──
        cr_nodes = [
            WorkflowNode(
                id="cr-form-start",
                workflow_id="factory-main",
                node_id="form-start",
                definition_type=NodeDefType.FORM_START.value,
                ai_node_id=None,
                name="코드리뷰 입력",
                position={"x": 50, "y": 550},
                config={
                    "mode": "manual",
                    "fields": [
                        {"name": "owner", "label": "GitHub Owner", "type": "text", "required": True},
                        {"name": "repo", "label": "GitHub Repo", "type": "text", "required": True},
                        {"name": "commitId1", "label": "시작 커밋 SHA", "type": "text", "required": True},
                        {"name": "commitId2", "label": "끝 커밋 SHA", "type": "text", "required": True},
                        {"name": "token", "label": "GitHub Token (선택)", "type": "text", "required": False},
                    ],
                },
                input_mapping={},
            ),
            WorkflowNode(
                id="cr-api-compare",
                workflow_id="factory-main",
                node_id="api-call",
                definition_type=NodeDefType.API_CALL.value,
                ai_node_id=None,
                name="GitHub 커밋 비교",
                position={"x": 350, "y": 550},
                config={
                    "apiDefinitionId": "api-gh-compare",
                },
                input_mapping={
                    "owner": "$.owner",
                    "repo": "$.repo",
                    "base": "$.commitId1",
                    "head": "$.commitId2",
                    "token": "$.token",
                },
            ),
            WorkflowNode(
                id="cr-reviewer",
                workflow_id="factory-main",
                node_id="node-code-review-md",
                definition_type=NodeDefType.AI_CUSTOM.value,
                ai_node_id="node-code-review-md",
                name="코드 리뷰 생성",
                position={"x": 650, "y": 550},
                config={},
                input_mapping={
                    "owner": "$.owner",
                    "repo": "$.repo",
                    "commitId1": "$.commitId1",
                    "commitId2": "$.commitId2",
                    "compareData": "$.data",
                },
            ),
            WorkflowNode(
                id="cr-warehouse",
                workflow_id="factory-main",
                node_id="markdown-viewer",
                definition_type=NodeDefType.MARKDOWN_VIEWER.value,
                ai_node_id=None,
                name="리뷰 보고서",
                position={"x": 950, "y": 550},
                config={},
                input_mapping={},
            ),
        ]

        for wf_node in wf_nodes:
            session.add(wf_node)
        for cr_node in cr_nodes:
            session.add(cr_node)

        # ── 스펙 테이블 생성 파이프라인 (하단) ──
        st_nodes = [
            WorkflowNode(
                id="st-form-start",
                workflow_id="factory-main",
                node_id="form-start",
                definition_type=NodeDefType.FORM_START.value,
                ai_node_id=None,
                name="스펙 검색 입력",
                position={"x": 100, "y": 680},
                config={"mode": "manual"},
                input_mapping={},
            ),
            WorkflowNode(
                id="st-knowledge",
                workflow_id="factory-main",
                node_id="knowledge",
                definition_type=NodeDefType.KNOWLEDGE.value,
                ai_node_id=None,
                name="스펙 지식 검색",
                position={"x": 480, "y": 680},
                config={"searchField": "system_name", "category": "소스코드검증-스펙", "maxResults": 10},
                input_mapping={},
            ),
            WorkflowNode(
                id="st-table-gen",
                workflow_id="factory-main",
                node_id="node-spec-table-gen",
                definition_type=NodeDefType.AI_CUSTOM.value,
                ai_node_id="node-spec-table-gen",
                name="스펙 테이블 생성",
                position={"x": 860, "y": 680},
                config={},
                input_mapping={
                    "system_name": "$.system_name",
                    "category": "$.category",
                    "knowledge": "$.knowledge",
                },
            ),
            WorkflowNode(
                id="st-viewer",
                workflow_id="factory-main",
                node_id="markdown-viewer",
                definition_type=NodeDefType.MARKDOWN_VIEWER.value,
                ai_node_id=None,
                name="스펙 테이블 보기",
                position={"x": 1240, "y": 680},
                config={},
                input_mapping={},
            ),
        ]

        for st_node in st_nodes:
            session.add(st_node)

        # 워크플로우 연결선 — 문의글 파이프라인 5개
        wf_connections = [
            WorkflowConnection(
                id="edge-1",
                workflow_id="factory-main",
                source_node_id="wfn-api-start",
                target_node_id="wfn-unpacker",
                source_handle="output",
                target_handle="input",
            ),
            WorkflowConnection(
                id="edge-2",
                workflow_id="factory-main",
                source_node_id="wfn-unpacker",
                target_node_id="wfn-sorter",
                source_handle="output",
                target_handle="input",
            ),
            WorkflowConnection(
                id="edge-3",
                workflow_id="factory-main",
                source_node_id="wfn-sorter",
                target_node_id="wfn-knowledge",
                source_handle="rule-rule-1",
                target_handle="input",
            ),
            WorkflowConnection(
                id="edge-4",
                workflow_id="factory-main",
                source_node_id="wfn-knowledge",
                target_node_id="wfn-llm",
                source_handle="output",
                target_handle="input",
            ),
            WorkflowConnection(
                id="edge-5",
                workflow_id="factory-main",
                source_node_id="wfn-llm",
                target_node_id="wfn-warehouse",
                source_handle="output",
                target_handle="input",
            ),
        ]

        # 코드리뷰 파이프라인 연결선 3개
        cr_connections = [
            WorkflowConnection(
                id="cr-edge-f1",
                workflow_id="factory-main",
                source_node_id="cr-form-start",
                target_node_id="cr-api-compare",
                source_handle="output",
                target_handle="input",
            ),
            WorkflowConnection(
                id="cr-edge-f2",
                workflow_id="factory-main",
                source_node_id="cr-api-compare",
                target_node_id="cr-reviewer",
                source_handle="output",
                target_handle="input",
            ),
            WorkflowConnection(
                id="cr-edge-f3",
                workflow_id="factory-main",
                source_node_id="cr-reviewer",
                target_node_id="cr-warehouse",
                source_handle="output",
                target_handle="input",
            ),
        ]

        for wf_conn in wf_connections:
            session.add(wf_conn)
        for cr_conn in cr_connections:
            session.add(cr_conn)

        # 스펙 테이블 파이프라인 연결선 3개
        st_connections = [
            WorkflowConnection(
                id="st-edge-1",
                workflow_id="factory-main",
                source_node_id="st-form-start",
                target_node_id="st-knowledge",
                source_handle="output",
                target_handle="input",
            ),
            WorkflowConnection(
                id="st-edge-2",
                workflow_id="factory-main",
                source_node_id="st-knowledge",
                target_node_id="st-table-gen",
                source_handle="output",
                target_handle="input",
            ),
            WorkflowConnection(
                id="st-edge-3",
                workflow_id="factory-main",
                source_node_id="st-table-gen",
                target_node_id="st-viewer",
                source_handle="output",
                target_handle="input",
            ),
        ]

        for st_conn in st_connections:
            session.add(st_conn)

        # ── 산출물 자동생성 파이프라인 ──
        dl_nodes = [
            WorkflowNode(
                id="dl-form-start",
                workflow_id="factory-main",
                node_id="form-start",
                definition_type=NodeDefType.FORM_START.value,
                ai_node_id=None,
                name="산출물 생성 입력",
                position={"x": 100, "y": 1100},
                config={
                    "mode": "manual",
                    "fields": [
                        {"name": "github_url", "label": "GitHub 마일스톤 URL", "type": "text", "required": True, "placeholder": "https://github.com/owner/repo/milestone/1"},
                        {"name": "milestone_number", "label": "마일스톤 번호", "type": "number", "required": False, "placeholder": "URL에 포함된 경우 생략 가능"},
                        {"name": "github_token", "label": "GitHub 토큰", "type": "password", "required": False, "placeholder": "ghp_xxx (공개 저장소는 생략 가능)"},
                    ],
                },
                config_overrides={},
                input_mapping={},
            ),
            WorkflowNode(
                id="dl-deliverable-gen",
                workflow_id="factory-main",
                node_id="deliverable-generator",
                definition_type="deliverable-generator",
                ai_node_id=None,
                name="산출물 생성기",
                position={"x": 500, "y": 1100},
                config={},
                config_overrides={},
                input_mapping={
                    "github_url": "$.github_url",
                    "milestone_number": "$.milestone_number",
                    "github_token": "$.github_token",
                },
            ),
            WorkflowNode(
                id="dl-viewer",
                workflow_id="factory-main",
                node_id="markdown-viewer",
                definition_type=NodeDefType.MARKDOWN_VIEWER.value,
                ai_node_id=None,
                name="산출물 문서 보기",
                position={"x": 900, "y": 1000},
                config={},
                config_overrides={},
                input_mapping={},
            ),
            WorkflowNode(
                id="dl-warehouse",
                workflow_id="factory-main",
                node_id="result",
                definition_type=NodeDefType.RESULT.value,
                ai_node_id=None,
                name="산출물 보관함",
                position={"x": 900, "y": 1200},
                config={},
                config_overrides={},
                input_mapping={},
            ),
        ]

        for dl_node in dl_nodes:
            session.add(dl_node)

        dl_connections = [
            WorkflowConnection(
                id="dl-edge-1",
                workflow_id="factory-main",
                source_node_id="dl-form-start",
                target_node_id="dl-deliverable-gen",
                source_handle="output",
                target_handle="input",
            ),
            WorkflowConnection(
                id="dl-edge-2",
                workflow_id="factory-main",
                source_node_id="dl-deliverable-gen",
                target_node_id="dl-viewer",
                source_handle="output",
                target_handle="input",
            ),
            WorkflowConnection(
                id="dl-edge-3",
                workflow_id="factory-main",
                source_node_id="dl-deliverable-gen",
                target_node_id="dl-warehouse",
                source_handle="output",
                target_handle="input",
            ),
        ]

        for dl_conn in dl_connections:
            session.add(dl_conn)

        # ========================================
        # 6. Workflow - GitHub 커밋 변경 진단
        # ========================================
        wf2 = Workflow(
            id="wf-github-commit-diag",
            name="GitHub 커밋 변경 진단",
            description="GitHub 커밋 비교 → AI 진단 보고서 생성 워크플로우",
            status=WorkflowStatus.ACTIVE,
            tags=["GitHub", "커밋진단", "자동화"],
            viewport={"x": 0, "y": 0, "zoom": 1},
            trigger={"type": "form", "config": {}},
            variables={},
        )
        session.add(wf2)

        wf2_nodes = [
            WorkflowNode(
                id="wfn-trigger",
                workflow_id="wf-github-commit-diag",
                node_id="trigger",
                definition_type=NodeDefType.FORM_START.value,
                ai_node_id=None,
                name="입력 폼",
                position={"x": 50, "y": 250},
                config={
                    "fields": [
                        {"name": "githubUrl", "label": "GitHub URL", "type": "text", "required": True},
                        {"name": "commitId1", "label": "시작 커밋 SHA", "type": "text", "required": True},
                        {"name": "commitId2", "label": "끝 커밋 SHA", "type": "text", "required": True},
                        {"name": "token", "label": "GitHub Token (공개 리포는 빈값)", "type": "text", "required": False},
                    ],
                },
                input_mapping={},
            ),
            WorkflowNode(
                id="wfn-parser",
                workflow_id="wf-github-commit-diag",
                node_id="node-github-url-parser",
                definition_type=NodeDefType.AI_CUSTOM.value,
                ai_node_id="node-github-url-parser",
                name="URL 파서",
                position={"x": 350, "y": 250},
                config={},
                input_mapping={
                    "githubUrl": "$.githubUrl",
                },
            ),
            WorkflowNode(
                id="wfn-gh-compare",
                workflow_id="wf-github-commit-diag",
                node_id="api-call",
                definition_type=NodeDefType.API_CALL.value,
                ai_node_id=None,
                name="GitHub 커밋 비교",
                position={"x": 650, "y": 250},
                config={
                    "apiDefinitionId": "api-gh-compare",
                },
                input_mapping={
                    "owner": "$.owner",
                    "repo": "$.repo",
                    "base": "$.commitId1",
                    "head": "$.commitId2",
                    "token": "$.token",
                },
            ),
            WorkflowNode(
                id="wfn-diagnosis",
                workflow_id="wf-github-commit-diag",
                node_id="node-commit-diagnosis",
                definition_type=NodeDefType.AI_CUSTOM.value,
                ai_node_id="node-commit-diagnosis",
                name="커밋 진단기",
                position={"x": 950, "y": 250},
                config={},
                input_mapping={
                    "owner": "$.owner",
                    "repo": "$.repo",
                    "commitId1": "$.commitId1",
                    "commitId2": "$.commitId2",
                    "compareData": "$.data",
                },
            ),
            WorkflowNode(
                id="wfn-result",
                workflow_id="wf-github-commit-diag",
                node_id="result",
                definition_type=NodeDefType.RESULT.value,
                ai_node_id=None,
                name="진단 결과",
                position={"x": 1250, "y": 250},
                config={},
                input_mapping={},
            ),
        ]

        for n in wf2_nodes:
            session.add(n)

        wf2_connections = [
            WorkflowConnection(
                id="diag-edge-1",
                workflow_id="wf-github-commit-diag",
                source_node_id="wfn-trigger",
                target_node_id="wfn-parser",
                source_handle="output",
                target_handle="input",
            ),
            WorkflowConnection(
                id="diag-edge-2",
                workflow_id="wf-github-commit-diag",
                source_node_id="wfn-parser",
                target_node_id="wfn-gh-compare",
                source_handle="output",
                target_handle="input",
            ),
            WorkflowConnection(
                id="diag-edge-3",
                workflow_id="wf-github-commit-diag",
                source_node_id="wfn-gh-compare",
                target_node_id="wfn-diagnosis",
                source_handle="output",
                target_handle="input",
            ),
            WorkflowConnection(
                id="diag-edge-4",
                workflow_id="wf-github-commit-diag",
                source_node_id="wfn-diagnosis",
                target_node_id="wfn-result",
                source_handle="output",
                target_handle="input",
            ),
        ]

        for c in wf2_connections:
            session.add(c)

        # ========================================
        # 7. Workflow 3: GitHub 코드 리뷰 → MD 출력
        # ========================================
        wf3 = Workflow(
            id="wf-github-code-review",
            name="GitHub 코드 리뷰 MD 생성",
            description="GitHub 커밋 diff를 분석하여 마크다운 형식의 코드 리뷰 보고서를 생성하는 워크플로우",
            status=WorkflowStatus.ACTIVE,
            tags=["GitHub", "코드리뷰", "마크다운", "자동화"],
            viewport={"x": 0, "y": 0, "zoom": 1},
            trigger={"type": "form", "config": {}},
            variables={},
        )
        session.add(wf3)

        wf3_nodes = [
            WorkflowNode(
                id="cr-trigger",
                workflow_id="wf-github-code-review",
                node_id="trigger",
                definition_type=NodeDefType.FORM_START.value,
                ai_node_id=None,
                name="입력 폼",
                position={"x": 50, "y": 250},
                config={
                    "fields": [
                        {"name": "githubUrl", "label": "GitHub URL", "type": "text", "required": True},
                        {"name": "commitId1", "label": "시작 커밋 SHA", "type": "text", "required": True},
                        {"name": "commitId2", "label": "끝 커밋 SHA", "type": "text", "required": True},
                        {"name": "token", "label": "GitHub Token (공개 리포는 빈값)", "type": "text", "required": False},
                    ],
                },
                input_mapping={},
            ),
            WorkflowNode(
                id="cr-parser",
                workflow_id="wf-github-code-review",
                node_id="node-github-url-parser",
                definition_type=NodeDefType.AI_CUSTOM.value,
                ai_node_id="node-github-url-parser",
                name="URL 파서",
                position={"x": 350, "y": 250},
                config={},
                input_mapping={
                    "githubUrl": "$.githubUrl",
                },
            ),
            WorkflowNode(
                id="cr-gh-compare",
                workflow_id="wf-github-code-review",
                node_id="api-call",
                definition_type=NodeDefType.API_CALL.value,
                ai_node_id=None,
                name="GitHub 커밋 비교",
                position={"x": 650, "y": 250},
                config={
                    "apiDefinitionId": "api-gh-compare",
                },
                input_mapping={
                    "owner": "$.owner",
                    "repo": "$.repo",
                    "base": "$.commitId1",
                    "head": "$.commitId2",
                    "token": "$.token",
                },
            ),
            WorkflowNode(
                id="cr-review",
                workflow_id="wf-github-code-review",
                node_id="node-code-review-md",
                definition_type=NodeDefType.AI_CUSTOM.value,
                ai_node_id="node-code-review-md",
                name="코드 리뷰 생성",
                position={"x": 950, "y": 250},
                config={},
                input_mapping={
                    "owner": "$.owner",
                    "repo": "$.repo",
                    "commitId1": "$.commitId1",
                    "commitId2": "$.commitId2",
                    "compareData": "$.data",
                },
            ),
            WorkflowNode(
                id="cr-result",
                workflow_id="wf-github-code-review",
                node_id="result",
                definition_type=NodeDefType.RESULT.value,
                ai_node_id=None,
                name="리뷰 결과",
                position={"x": 1250, "y": 250},
                config={},
                input_mapping={},
            ),
        ]

        for n in wf3_nodes:
            session.add(n)

        wf3_connections = [
            WorkflowConnection(
                id="cr-edge-1",
                workflow_id="wf-github-code-review",
                source_node_id="cr-trigger",
                target_node_id="cr-parser",
                source_handle="output",
                target_handle="input",
            ),
            WorkflowConnection(
                id="cr-edge-2",
                workflow_id="wf-github-code-review",
                source_node_id="cr-parser",
                target_node_id="cr-gh-compare",
                source_handle="output",
                target_handle="input",
            ),
            WorkflowConnection(
                id="cr-edge-3",
                workflow_id="wf-github-code-review",
                source_node_id="cr-gh-compare",
                target_node_id="cr-review",
                source_handle="output",
                target_handle="input",
            ),
            WorkflowConnection(
                id="cr-edge-4",
                workflow_id="wf-github-code-review",
                source_node_id="cr-review",
                target_node_id="cr-result",
                source_handle="output",
                target_handle="input",
            ),
        ]

        for c in wf3_connections:
            session.add(c)

        # ========================================
        # Commit
        # ========================================
        await session.commit()
        print(f"[OK] 시드 데이터 생성 완료:")
        print(f"  - Documents: {len(docs)}개")
        print(f"  - AI Nodes: {len(ai_nodes)}개")
        print(f"  - API Definitions: {len(api_definitions)}개")
        print(f"  - Workflow: 1개 (노드 {len(wf_nodes)+len(cr_nodes)}개, 연결 {len(wf_connections)+len(cr_connections)}개)")
        print(f"  - Workflow 2: wf-github-commit-diag (노드 {len(wf2_nodes)}개, 연결 {len(wf2_connections)}개)")
        print(f"  - Workflow 3: wf-github-code-review (노드 {len(wf3_nodes)}개, 연결 {len(wf3_connections)}개)")

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
