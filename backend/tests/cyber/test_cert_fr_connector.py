from pathlib import Path

import httpx
import pytest

from app.cyber.connectors import cert_fr
from app.cyber.connectors.base import RawItemRef

FIXTURES = Path(__file__).parent / "fixtures"


def _fake_fetch(fixture_name: str):
    text = (FIXTURES / fixture_name).read_text(encoding="utf-8")

    def _fetch(url: str) -> httpx.Response:
        return httpx.Response(200, content=text.encode("utf-8"))

    return _fetch


def test_list_items_parses_rss_feed(monkeypatch):
    monkeypatch.setattr(cert_fr, "FEED_URLS", ["https://www.cert.ssi.gouv.fr/avis/feed/"])
    monkeypatch.setattr(cert_fr, "fetch", _fake_fetch("cert_fr_avis_feed.xml"))

    items = cert_fr.list_items()

    assert len(items) == 2
    assert items[0].url == "https://www.cert.ssi.gouv.fr/avis/CERTFR-2026-AVI-0001/"
    assert "exemple de produit" in items[0].title
    assert items[0].published_at.year == 2026
    assert items[0].published_at.month == 1
    assert items[0].published_at.day == 1


def test_fetch_item_extracts_article_text(monkeypatch):
    monkeypatch.setattr(cert_fr, "fetch", _fake_fetch("cert_fr_article.html"))
    ref = RawItemRef(
        url="https://www.cert.ssi.gouv.fr/avis/CERTFR-2026-AVI-0001/",
        title="Multiples vulnerabilites dans un exemple de produit (01 janvier 2026)",
        published_at=None,
    )

    item = cert_fr.fetch_item(ref)

    assert "execution de code arbitraire" in item.text
    assert "Menu de navigation" not in item.text
    assert "Pied de page" not in item.text
    assert item.url == ref.url
