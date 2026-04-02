import tempfile
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_ALLOWED_DIRECTORIES = [".", tempfile.gettempdir()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MCP_", frozen=True)

    APP_NAME: str = "Parsival"
    PROCESS_POOL_SIZE: int = 4
    MAX_FILE_SIZE_MB: int = 500
    MAX_STREAM_FILE_SIZE_MB: int = 2048
    HYBRID_HASH_THRESHOLD_MB: int = 50

    REDIS_ENABLED: bool = False
    REDIS_URL: str | None = None
    REDIS_TTL: int = 3600

    SENTRY_ENABLED: bool = False
    SENTRY_DSN: str | None = None

    LIBREOFFICE_PATH: str | None = None
    MAX_LIBREOFFICE_WORKERS: int = 2
    SUBPROCESS_TIMEOUT_SEC: int = 30

    ALLOWED_DIRECTORIES: list[str] = _DEFAULT_ALLOWED_DIRECTORIES
    WORKSPACE_ROOT: str = "."


settings = Settings()
