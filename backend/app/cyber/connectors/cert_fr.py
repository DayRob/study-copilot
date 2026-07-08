from datetime import datetime, timezone

import feedparser

from app.cyber.connectors.base import RawItem, RawItemRef
from app.cyber.http_client import fetch

name = "cert_fr"
authority_source = "CERT-FR"

# CERT-FR publishes separate RSS feeds per bulletin category; both are
# allowed by https://www.cert.ssi.gouv.fr/robots.txt (only /pdf, /tar, /js,
# /fonts, /fiche/ are disallowed there).
FEED_URLS = [
    "https://www.cert.ssi.gouv.fr/avis/feed/",
    "https://www.cert.ssi.gouv.fr/alerte/feed/",
]


def list_items() -> list[RawItemRef]:
    items: list[RawItemRef] = []
    for feed_url in FEED_URLS:
        response = fetch(feed_url)
        parsed = feedparser.parse(response.text)
        for entry in parsed.entries:
            items.append(
                RawItemRef(url=entry.link, title=entry.title, published_at=_entry_published_at(entry))
            )
    return items


def _entry_published_at(entry) -> datetime | None:
    if getattr(entry, "published_parsed", None) is None:
        return None
    return datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)


def fetch_item(ref: RawItemRef) -> RawItem:
    response = fetch(ref.url)
    text = _extract_article_text(response.text)
    return RawItem(url=ref.url, title=ref.title, published_at=ref.published_at, text=text)


def _extract_article_text(html: str) -> str:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()
    main = soup.find("main") or soup.find("article") or soup
    return "\n".join(line.strip() for line in main.get_text("\n").splitlines() if line.strip())
