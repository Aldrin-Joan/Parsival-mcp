from src.config import settings


def test_config_defaults():
    assert settings.APP_NAME == "Parsival"
    assert settings.HYBRID_HASH_THRESHOLD_MB == 50
    assert settings.REDIS_ENABLED is False
    assert settings.SENTRY_ENABLED is False
