import time
import urllib.robotparser as robotparser
from urllib.parse import urlparse

import httpx

from app.config import get_settings

_last_request_at: dict[str, float] = {}
_robots_parsers: dict[str, str | None] = {}


def is_allowed(robots_txt: str, user_agent: str, url: str) -> bool:
    """Pure function (no network) so it's directly unit-testable: parses a
    robots.txt string and checks whether `user_agent` may fetch `url`."""
    parser = robotparser.RobotFileParser()
    parser.parse(robots_txt.splitlines())
    return parser.can_fetch(user_agent, url)


def _sleep_duration(last_request_monotonic: float | None, now: float, min_interval: float) -> float:
    """Pure function: how long to sleep before the next request to a domain
    we've already hit, given `now` and the last request's monotonic time."""
    if last_request_monotonic is None:
        return 0.0
    elapsed = now - last_request_monotonic
    return max(0.0, min_interval - elapsed)


def _get_robots_txt(domain: str) -> str | None:
    try:
        response = httpx.get(f"https://{domain}/robots.txt", timeout=10)
        return response.text if response.status_code == 200 else None
    except httpx.HTTPError:
        return None


def fetch(url: str) -> httpx.Response:
    """GET a URL, respecting robots.txt and a per-domain rate limit. Raises
    PermissionError if robots.txt disallows the path for our User-Agent."""
    settings = get_settings()
    domain = urlparse(url).netloc

    if domain not in _robots_parsers:
        robots_txt = _get_robots_txt(domain)
        _robots_parsers[domain] = robots_txt
    robots_txt = _robots_parsers[domain]
    if robots_txt is not None and not is_allowed(robots_txt, settings.cyber_user_agent, url):
        raise PermissionError(f"robots.txt disallows fetching {url} for {settings.cyber_user_agent}")

    now = time.monotonic()
    wait = _sleep_duration(_last_request_at.get(domain), now, settings.cyber_rate_limit_seconds)
    if wait > 0:
        time.sleep(wait)
    _last_request_at[domain] = time.monotonic()

    response = httpx.get(url, headers={"User-Agent": settings.cyber_user_agent}, timeout=20, follow_redirects=True)
    response.raise_for_status()
    return response
