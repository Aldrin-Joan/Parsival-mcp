from pathlib import Path
from src.config import settings
from src.core.logging import get_logger

logger = get_logger(__name__)


class SecurityError(Exception):
    """Raised when a security boundary is violated."""
    pass


def _is_within_boundaries(target: Path) -> bool:
    """Checks if the target path is within allowed boundaries."""
    # 1. Check workspace root
    root = Path(settings.WORKSPACE_ROOT).resolve()
    if target.is_relative_to(root):
        return True

    # 2. Check extra allowed directories
    for allowed_str in settings.ALLOWED_DIRECTORIES:
        if target.is_relative_to(Path(allowed_str).resolve()):
            return True

    return False


def validate_safe_path(
    requested_path: str | Path,
    base_dir: Path | None = None
) -> Path:
    """
    Validates that a requested path is safe to access.

    Args:
        requested_path: The path provided by the user.
        base_dir: Optional base directory to check against.

    Returns:
        The resolved Path object.

    Raises:
        SecurityError: If the path is outside allowed boundaries or invalid.
        FileNotFoundError: If the file does not exist.
    """
    try:
        # 1. Resolve path (absolute, symlinks followed)
        target = Path(requested_path).resolve()

        # 2. Check boundaries
        if not _is_within_boundaries(target):
            logger.warning("security_violation", path=str(requested_path))
            raise SecurityError(f"Access denied: {requested_path}")

        # 3. Validation checks
        if not target.exists():
            raise FileNotFoundError(f"File not found: {requested_path}")

        if not target.is_file():
            raise SecurityError(f"Target is not a file: {requested_path}")

        return target

    except (ValueError, RuntimeError, SecurityError) as e:
        if isinstance(e, SecurityError):
            raise
        logger.error("path_validation_error", path=str(requested_path))
        raise SecurityError(f"Invalid path: {requested_path}") from e
