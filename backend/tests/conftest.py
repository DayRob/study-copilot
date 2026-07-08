import pytest

from app.config import get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    """Settings is an lru_cache singleton; clear it around each test so a
    test that monkeypatches env vars doesn't leak into the next test."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
