import re
from datetime import datetime

from app.cyber.connectors.base import RawItem, RawItemRef
from app.cyber.http_client import fetch

name = "anssi"
authority_source = "ANSSI"

LISTING_URL = "https://www.cyber.gouv.fr/actualites"
BASE_URL = "https://www.cyber.gouv.fr"

_MONTHS_FR = {
    "janvier": 1, "février": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "août": 8, "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12,
}


def list_items() -> list[RawItemRef]:
    response = fetch(LISTING_URL)
    return _parse_listing(response.text)


def _parse_listing(html: str) -> list[RawItemRef]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    items: list[RawItemRef] = []
    seen_urls: set[str] = set()

    for link in soup.select("h3 a[href*='/actualites/']"):
        href = link.get("href", "")
        if not href or href.rstrip("/") == "/actualites":
            continue
        url = href if href.startswith("http") else f"{BASE_URL}{href}"
        if url in seen_urls:
            continue
        seen_urls.add(url)
        title = link.get_text(strip=True)
        published_at = _find_published_date(link)
        items.append(RawItemRef(url=url, title=title, published_at=published_at))
    return items


def _find_published_date(link_tag) -> datetime | None:
    """The 'Publié le ...' text sits near the link inside the same card, not
    inside the <a> itself -- walk up to the enclosing card and search its
    text. Handles both numeric (03/01/2026) and French long-form (4 janvier
    2026) dates, both seen on the real site."""
    card = link_tag.find_parent(["article", "div", "li"])
    if card is None:
        return None
    card_text = card.get_text()

    numeric = re.search(r"Publié le (\d{1,2})/(\d{1,2})/(\d{4})", card_text)
    if numeric:
        day, month, year = numeric.groups()
        return datetime(int(year), int(month), int(day))

    long_form = re.search(
        r"Publié le (\d{1,2}) (" + "|".join(_MONTHS_FR) + r") (\d{4})", card_text
    )
    if long_form:
        day, month_name, year = long_form.groups()
        return datetime(int(year), _MONTHS_FR[month_name], int(day))

    return None


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
