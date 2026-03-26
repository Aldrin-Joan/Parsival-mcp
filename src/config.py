from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MCP_", frozen=True)

    APP_NAME: str = "Parsival"
    PROCESS_POOL_SIZE: int = 4
    MAX_FILE_SIZE_MB: int = 500
    HYBRID_HASH_THRESHOLD_MB: int = 50

    REDIS_ENABLED: bool = False
    REDIS_URL: str | None = None
    REDIS_TTL: int = 3600

    SENTRY_ENABLED: bool = False
    SENTRY_DSN: str | None = None

    LIBREOFFICE_PATH: str | None = None
    MAX_LIBREOFFICE_WORKERS: int = 2
    SUBPROCESS_TIMEOUT_SEC: int = 30


settings = Settings()
