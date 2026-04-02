import ast
import json
import tempfile
from pathlib import Path
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_ALLOWED_DIRECTORIES = [".", tempfile.gettempdir()]


def _normalize_dir(path_str: str) -> str:
    resolved = Path(path_str).expanduser().resolve()
    return str(resolved)


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

    ALLOWED_DIRECTORIES: str | list[str] = _DEFAULT_ALLOWED_DIRECTORIES
    WORKSPACE_ROOT: str = "."
    TRANSPORT: str = "fastmcp"

    @field_validator("TRANSPORT", mode="before")
    def _normalize_transport(cls, v):
        if not isinstance(v, str):
            raise ValueError("TRANSPORT must be a string")

        normalized = v.strip().lower()
        if normalized not in {"fastmcp", "stdio"}:
            raise ValueError("TRANSPORT must be one of: fastmcp, stdio")
        return normalized

    @field_validator("ALLOWED_DIRECTORIES", mode="before")
    def _normalize_allowed_directories(cls, v):
        if isinstance(v, str):
            text = v.strip()
            if not text:
                return []

            if text.startswith("[") and text.endswith("]"):
                parsed = None
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError:
                    try:
                        parsed = ast.literal_eval(text)
                    except (ValueError, SyntaxError):
                        parsed = None

                if isinstance(parsed, list):
                    return [_normalize_dir(str(x)) for x in parsed if x and isinstance(x, str)]

            # Accept common delimiter patterns from VS Code vars
            parts = [p.strip() for p in text.replace("|", ";").replace(",", ";").split(";") if p.strip()]
            if parts:
                return [_normalize_dir(p) for p in parts]

            return [_normalize_dir(text)]

        if isinstance(v, (list, tuple)):
            return [_normalize_dir(str(x)) for x in v if x is not None]

        raise ValueError("ALLOWED_DIRECTORIES must be a list[str] or parseable string")

    @property
    def is_stdio_transport(self) -> bool:
        return self.TRANSPORT == "stdio"


settings = Settings()
