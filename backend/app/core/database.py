"""
Database Configuration - SQLAlchemy Async
"""

import os
from typing import AsyncGenerator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from .config import settings, _BACKEND_DIR


def _resolve_db_url(url: str) -> str:
    """SQLite 상대 경로를 backend/ 기준으로 변환"""
    # sqlite+aiosqlite:///./data/app.db → backend/data/app.db
    prefix = "sqlite+aiosqlite:///"
    if url.startswith(prefix):
        path = url[len(prefix):]
        if not os.path.isabs(path):
            path = os.path.join(_BACKEND_DIR, path)
        return prefix + path
    return url


# Async Engine
engine = create_async_engine(
    _resolve_db_url(settings.DATABASE_URL),
    echo=settings.DEBUG,
    future=True,
)

# Async Session Factory
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """모델 베이스 클래스"""
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """의존성 주입용 DB 세션 제공"""
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db() -> None:
    """데이터베이스 초기화 (테이블 생성)"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 마이그레이션: 기존 테이블에 누락된 컬럼 추가
    async with engine.begin() as conn:
        for col in ["source_handle", "target_handle"]:
            try:
                await conn.execute(
                    text(f"ALTER TABLE workflow_connections ADD COLUMN {col} VARCHAR(50)")
                )
            except Exception:
                pass  # 이미 존재하면 무시
