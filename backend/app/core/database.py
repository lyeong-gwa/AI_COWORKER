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
    """데이터베이스 초기화 (테이블 생성).

    Karpathy v2 (Knowledge v2) 신규 테이블 — `knowledge_raw_sources`,
    `knowledge_changelog_entries` — 는 `Base.metadata.create_all` 가
    이미 존재하는 테이블은 건너뛰므로 idempotent.
    """
    # 모델 등록 보장 (import side-effect for create_all)
    from ..models import knowledge_raw, knowledge_changelog  # noqa: F401

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

    # 마이그레이션: warehouse_entries에 dedup_key 컬럼 추가
    async with engine.begin() as conn:
        try:
            await conn.execute(
                text("ALTER TABLE warehouse_entries ADD COLUMN dedup_key VARCHAR(128)")
            )
            print("[MIGRATE] warehouse_entries.dedup_key 컬럼 추가 완료")
        except Exception:
            pass  # 이미 존재하면 무시
        try:
            await conn.execute(
                text("CREATE INDEX IF NOT EXISTS ix_warehouse_entries_dedup_key ON warehouse_entries(dedup_key)")
            )
        except Exception:
            pass

    # 마이그레이션 (2026-05-27): workflows.schedule_config 컬럼 추가 (스케줄러 UI Phase A).
    # 기존 row 는 default JSON 으로 채운다. SQLite 는 ALTER TABLE ADD COLUMN 의 DEFAULT 에
    # 함수/표현식을 직접 받지 못하므로 NULL 로 추가한 뒤 UPDATE 로 일괄 채운다.
    async with engine.begin() as conn:
        try:
            cols = await conn.execute(text("PRAGMA table_info(workflows)"))
            col_names = [row[1] for row in cols.fetchall()]
            if "schedule_config" not in col_names:
                await conn.execute(
                    text("ALTER TABLE workflows ADD COLUMN schedule_config JSON")
                )
                # 기존 모든 워크플로우에 default 부여
                await conn.execute(
                    text(
                        "UPDATE workflows SET schedule_config = "
                        "'{\"enabled\": false, \"cronExpr\": \"0 * * * *\", \"timezone\": \"Asia/Seoul\"}' "
                        "WHERE schedule_config IS NULL"
                    )
                )
                print("[MIGRATE] workflows.schedule_config 컬럼 추가 + 기존 row default 부여")
            else:
                # 컬럼이 이미 있지만 NULL 인 row 가 있을 수 있다 (방어적)
                await conn.execute(
                    text(
                        "UPDATE workflows SET schedule_config = "
                        "'{\"enabled\": false, \"cronExpr\": \"0 * * * *\", \"timezone\": \"Asia/Seoul\"}' "
                        "WHERE schedule_config IS NULL"
                    )
                )
        except Exception as e:
            print(f"[MIGRATE] workflows.schedule_config 마이그레이션 스킵: {e}")

    # 마이그레이션 (2026-05-12): InstanceDB 파일시스템 재설계 — 구 SQLite 테이블 폐기.
    # 운영 잔재 1건이 있더라도 records 0건이므로 안전하게 drop.
    # 파일시스템(backend/data/instance_dbs/) 으로 이전됨.
    async with engine.begin() as conn:
        for tbl in ("instance_db_records", "instance_dbs"):
            try:
                await conn.execute(text(f"DROP TABLE IF EXISTS {tbl}"))
            except Exception:
                pass

    # 마이그레이션: ai_nodes 테이블에서 레거시 컬럼 제거
    # SQLite는 DROP COLUMN을 지원하지 않으므로 테이블 재구성
    async with engine.begin() as conn:
        try:
            cols = await conn.execute(text("PRAGMA table_info(ai_nodes)"))
            col_names = [row[1] for row in cols.fetchall()]
            if "linked_tool_ids" in col_names:
                # 현재 모델에 정의된 컬럼만 유지하여 테이블 재구성
                keep_cols = [c for c in col_names if c != "linked_tool_ids"]
                cols_str = ", ".join(keep_cols)
                await conn.execute(text(f"CREATE TABLE ai_nodes_new AS SELECT {cols_str} FROM ai_nodes"))
                await conn.execute(text("DROP TABLE ai_nodes"))
                await conn.execute(text("ALTER TABLE ai_nodes_new RENAME TO ai_nodes"))
                print("[MIGRATE] ai_nodes: linked_tool_ids 컬럼 제거 완료")
        except Exception as e:
            print(f"[MIGRATE] ai_nodes 마이그레이션 스킵: {e}")
