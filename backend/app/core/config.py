"""
Application Configuration
"""

import os
from pathlib import Path
from typing import Optional, List
from pydantic_settings import BaseSettings
from functools import lru_cache

# backend/ 디렉토리를 기준 경로로 설정 (CWD 무관하게 동작)
_BACKEND_DIR = str(Path(__file__).resolve().parent.parent.parent)


class Settings(BaseSettings):
    """애플리케이션 설정"""

    # 기본 설정
    APP_NAME: str = "AI 업무도우미 API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True

    # API 설정
    API_V1_PREFIX: str = "/api/v1"
    CORS_ORIGINS: List[str] = ["http://localhost:5173", "http://localhost:5174", "http://localhost:5175", "http://localhost:5176", "http://localhost:5177", "http://localhost:5178", "http://localhost:3000", "http://localhost:9090"]

    # 데이터베이스
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/app.db"

    # Redis (Celery 브로커)
    REDIS_URL: str = "redis://localhost:6379/0"

    # Vector DB (ChromaDB)
    CHROMA_PERSIST_DIR: str = "./data/chroma"
    CHROMA_COLLECTION_NAME: str = "knowledge_base"

    # 지식 문서 디렉토리
    KNOWLEDGE_DIR: str = "./data/knowledge"

    # 로컬 임베딩 모델 (ONNX Runtime + tokenizers)
    ONNX_MODEL_PATH: str = "./models/onnx/jhgan_ko-sroberta-multitask"
    MODEL_CACHE_DIR: str = "./models"

    # LLM 설정
    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    DEFAULT_LLM_PROVIDER: str = "openai"  # openai | azure | anthropic | custom_api
    DEFAULT_MODEL: str = "gpt-4o-mini"

    # Azure OpenAI Service
    AZURE_OPENAI_ENDPOINT: Optional[str] = None
    AZURE_OPENAI_API_KEY: Optional[str] = None
    AZURE_OPENAI_DEPLOYMENT: Optional[str] = None
    AZURE_OPENAI_API_VERSION: str = "2024-02-15-preview"

    # 타 시스템 API (Custom API) 설정
    CUSTOM_API_URL: Optional[str] = None      # API 엔드포인트 URL
    CUSTOM_API_KEY: Optional[str] = None      # API 인증 키
    CUSTOM_API_MODEL: Optional[str] = None    # 기본 모델명
    CUSTOM_API_TIMEOUT: int = 60              # 타임아웃 (초)

    # External LLM (우회 LLM 시스템 - Dify/Agent Builder 호환)
    EXTERNAL_LLM: Optional[str] = None                # 외부 LLM 사용 플래그 ("true"/"1"/"yes" 설정시 활성)
    EXTERNAL_LLM_API_KEY: Optional[str] = None        # 우회 시스템 인증 키 (Bearer Token)
    EXTERNAL_LLM_API_URL: Optional[str] = None        # 우회 시스템 엔드포인트 URL (/v1/chat-messages)

    # 샌드박스 설정
    SANDBOX_TIMEOUT_SECONDS: int = 10
    SANDBOX_MAX_OUTPUT_SIZE: int = 1024 * 1024  # 1MB

    # 워크플로우 실행 설정
    WORKFLOW_MAX_NODES: int = 100
    WORKFLOW_MAX_EXECUTION_TIME: int = 300  # 5분
    WORKFLOW_NODE_TIMEOUT: int = 60  # 노드당 1분

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """설정 싱글톤"""
    return Settings()


settings = get_settings()
