"""
AI 업무도우미 Backend API

FastAPI 기반 백엔드 서버 (v1.2 - references in API response)
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os

from .core.config import settings
from .core.database import init_db
from .seed import seed_database
from .api import api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """애플리케이션 생명주기 관리"""
    # 시작 시
    print(f"[START] {settings.APP_NAME} v{settings.APP_VERSION} 시작")

    # 데이터 디렉토리 생성
    os.makedirs("./data", exist_ok=True)

    # 데이터베이스 초기화
    await init_db()
    print("[OK] 데이터베이스 초기화 완료")

    # 시드 데이터 확인 및 생성
    await seed_database()
    print("[OK] 시드 데이터 확인 완료")

    yield

    # 종료 시
    print("[BYE] 서버 종료")


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
