"""
AI 업무도우미 Backend API

FastAPI 기반 백엔드 서버 (v1.2 - references in API response)
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi import APIRouter
import os

from .core.config import settings
from .core.database import init_db
from .api import api_router


# ── 외부 시스템 Mock 라우터 ────────────────────────────
mock_router = APIRouter(prefix="/rest-comm", tags=["Mock External APIs"])


@mock_router.get("/support/view-list")
async def mock_support_view_list():
    """문의글 조회 목 API (외부 시스템 시뮬레이션)"""
    return {
        "data": [
            {
                "board_id": 1041,
                "title": "VPN 접속이 안됩니다",
                "category": "인프라",
                "description": "재택근무 중 VPN 연결 시 '인증 실패' 오류가 발생합니다. 비밀번호 초기화 후에도 동일 증상입니다.",
                "status": "신규",
                "member_id": "user_kim",
                "reg_date": "2026-03-03 09:15:00",
            },
            {
                "board_id": 1042,
                "title": "ERP 권한 요청",
                "category": "권한관리",
                "description": "신규 입사자 이정호(사번 20260301) ERP 구매모듈 조회/승인 권한 부여 요청드립니다.",
                "status": "신규",
                "member_id": "user_park",
                "reg_date": "2026-03-03 10:30:00",
            },
            {
                "board_id": 1043,
                "title": "프린터 드라이버 오류",
                "category": "장비",
                "description": "3층 복합기(HP-M630) 인쇄 시 '드라이버를 찾을 수 없음' 에러가 납니다. OS 업데이트 후 발생.",
                "status": "확인중",
                "member_id": "user_lee",
                "reg_date": "2026-03-02 16:45:00",
            },
            {
                "board_id": 1044,
                "title": "메일 수신 지연 문의",
                "category": "인프라",
                "description": "외부 메일이 30분 이상 지연되어 수신됩니다. 오전 9시부터 계속 발생 중입니다.",
                "status": "신규",
                "member_id": "user_choi",
                "reg_date": "2026-03-03 11:00:00",
            },
        ]
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    """애플리케이션 생명주기 관리"""
    # 시작 시
    print(f"[START] {settings.APP_NAME} v{settings.APP_VERSION} 시작")

    # 데이터 디렉토리 생성 (backend/ 기준)
    from .core.config import _BACKEND_DIR
    os.makedirs(os.path.join(_BACKEND_DIR, "data"), exist_ok=True)
    os.makedirs(os.path.join(_BACKEND_DIR, "data", "knowledge"), exist_ok=True)

    # 데이터베이스 초기화
    await init_db()
    print("[OK] 데이터베이스 초기화 완료")

    # 시드 데이터 생성
    from .seed import seed_database
    await seed_database()

    # 좀비 큐/실행 정리 (이전 서버 비정상 종료 시 잔존 데이터)
    await _cleanup_zombie_state()

    yield

    # 종료 시
    print("[BYE] 서버 종료")


async def _cleanup_zombie_state():
    """서버 시작 시 이전 실행의 좀비 상태 정리"""
    from .core.database import async_session_maker
    from sqlalchemy import text

    async with async_session_maker() as db:
        # 1) 좀비 큐 아이템 삭제 (PROCESSING/PENDING 상태로 남은 것)
        r1 = await db.execute(
            text("DELETE FROM node_queue_items WHERE status IN ('PROCESSING', 'PENDING')")
        )
        # 2) 좀비 실행 FAILED 처리 (RUNNING 상태로 남은 것)
        r2 = await db.execute(
            text(
                "UPDATE workflow_executions SET status='FAILED', "
                "error_message='서버 재시작으로 인한 강제 종료' "
                "WHERE status='RUNNING'"
            )
        )
        await db.commit()

        q_count = r1.rowcount
        e_count = r2.rowcount
        if q_count or e_count:
            print(f"[CLEANUP] 좀비 큐 {q_count}건 삭제, 좀비 실행 {e_count}건 FAILED 처리")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI 기반 업무 관리 및 워크플로우 자동화 API",
    lifespan=lifespan,
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API 라우터 등록
app.include_router(api_router, prefix=settings.API_V1_PREFIX)

# 외부 시스템 Mock 라우터 (워크플로우 테스트용)
app.include_router(mock_router)


@app.get("/")
async def root():
    """헬스 체크"""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
    }


@app.get("/health")
async def health_check():
    """상세 헬스 체크"""
    return {
        "status": "healthy",
        "database": "connected",
        "version": settings.APP_VERSION,
    }
