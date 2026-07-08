from app.cyber.http_client import is_allowed, _sleep_duration


ROBOTS_TXT = """User-agent: *
Disallow: /pdf
Disallow: /fiche/
"""


def test_is_allowed_true_for_unrestricted_path():
    assert is_allowed(ROBOTS_TXT, "StudyCopilotCyberBot/0.1", "https://example.org/avis/x") is True


def test_is_allowed_false_for_disallowed_path():
    assert is_allowed(ROBOTS_TXT, "StudyCopilotCyberBot/0.1", "https://example.org/fiche/x") is False


def test_sleep_duration_zero_on_first_request():
    assert _sleep_duration(last_request_monotonic=None, now=100.0, min_interval=3.0) == 0.0


def test_sleep_duration_waits_remaining_time():
    assert _sleep_duration(last_request_monotonic=100.0, now=101.0, min_interval=3.0) == 2.0


def test_sleep_duration_zero_once_interval_elapsed():
    assert _sleep_duration(last_request_monotonic=100.0, now=105.0, min_interval=3.0) == 0.0
