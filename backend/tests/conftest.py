"""Pytest 공용 설정 — backend/ 루트를 sys.path 에 추가하고 app 초기화 순서를 고정.

tests/ 는 backend/ 하위에 있지만, `app.*` 임포트가 `backend/` 기준이어야 하므로
sys.path 를 조정한다. 또한 `app.nodes` 패키지가 circular import 로 부분 초기화되는
상황을 피하기 위해 세션 시작 시 FastAPI ``app`` 을 먼저 임포트하여 초기화 순서를 고정한다.

InstanceDB 격리 (2026-05-12 재설계 후):
- 세션 단위 fixture 가 ``INSTANCE_DB_DIR`` env 를 tmp 폴더로 강제하고 store
  싱글톤 캐시를 비운다. 테스트는 운영 ``backend/data/instance_dbs/`` 와 분리된다.
"""

import os
import sys

_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

# ── 운영 인스턴스DB 격리 (FastAPI app 임포트 _이전_에 env 주입) ──────────
# settings 는 pydantic-settings 가 인스턴스화 시점에 env 를 읽으므로
# 가장 먼저 임시 경로를 환경변수에 설정한다. 같은 세션 내 모든 테스트가
# 이 경로를 공유한다 (격리 fixture 가 매 테스트마다 캐시를 비우고 폴더를 정리).
import tempfile

_TEST_INSTANCE_DB_DIR = tempfile.mkdtemp(prefix="omc_instance_dbs_test_")
os.environ["INSTANCE_DB_DIR"] = _TEST_INSTANCE_DB_DIR

# FastAPI 애플리케이션 전체를 먼저 로드하여 모듈 의존 순서를 안정화.
from app.main import app as _app  # noqa: F401  (import-ordering fix, env-after)

# settings 가 이미 _app import 과정에서 평가되었을 수 있으므로 명시 override.
from app.core.config import settings  # noqa: E402

settings.INSTANCE_DB_DIR = _TEST_INSTANCE_DB_DIR

import shutil  # noqa: E402

import pytest  # noqa: E402

from app.services.instance_db_store import reset_instance_db_store_cache  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_instance_db_store(tmp_path_factory):
    """매 테스트마다 깨끗한 InstanceDB 폴더 + store 싱글톤을 보장.

    autouse 라 모든 테스트에 적용된다. instance_db 와 무관한 테스트도 부작용이 없으며,
    잔재 누적 가능성을 차단한다.
    """
    test_dir = tmp_path_factory.mktemp("instance_dbs")
    settings.INSTANCE_DB_DIR = str(test_dir)
    os.environ["INSTANCE_DB_DIR"] = str(test_dir)
    reset_instance_db_store_cache()
    yield
    # 정리 — fixture 의 tmp_path_factory 가 알아서 처리하지만 명시적으로 cache reset
    reset_instance_db_store_cache()


def pytest_sessionfinish(session, exitstatus):  # noqa: D401
    """세션 종료 시 모듈 임시 폴더 제거."""
    try:
        shutil.rmtree(_TEST_INSTANCE_DB_DIR, ignore_errors=True)
    except Exception:
        pass
