from src.core.logging import get_logger


def test_get_logger():
    logger = get_logger("test")
    assert logger is not None
    logger.info("ok")
