from typing import List, Union
from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "AERIS-X — AI-Enabled Fleet Readiness & Predictive Maintenance Platform"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    SECRET_KEY: str = "aeris-x-dev-secret-key-change-in-prod"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours for hackathon ease
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    SEED: int = 42

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./aeris_x.db"
    DATABASE_URL_SYNC: str = "sqlite:///./aeris_x.db"
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # CORS
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8000",
    ]

    # Air-gapped / Synthetic policy
    SYNTHETIC_DATA_BANNER: str = "SYNTHETIC DEMONSTRATION DATA — NOT REAL AIRCRAFT PERFORMANCE"
    ENABLE_DOCUMENT_OCR: bool = True
    ENABLE_COPILOT: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="allow",
    )


settings = Settings()
