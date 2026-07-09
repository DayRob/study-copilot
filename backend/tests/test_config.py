from app.config import get_settings


def test_cyber_settings_defaults():
    settings = get_settings()
    assert settings.cyber_connectors == ["anssi", "cert_fr"]
    assert settings.cyber_rate_limit_seconds == 3.0
    assert "StudyCopilotCyberBot" in settings.cyber_user_agent
