from pathlib import Path

import httpx

from app.cyber.connectors import anssi
from app.cyber.connectors.base import RawItemRef

FIXTURES = Path(__file__).parent / "fixtures"


def _fake_fetch(fixture_name: str):
    text = (FIXTURES / fixture_name).read_text(encoding="utf-8")

    def _fetch(url: str) -> httpx.Response:
        return httpx.Response(200, content=text.encode("utf-8"))

    return _fetch


def test_list_items_parses_listing_and_skips_the_nav_link(monkeypatch):
    monkeypatch.setattr(anssi, "fetch", _fake_fetch("anssi_listing.html"))

    items = anssi.list_items()

    assert len(items) == 2
    assert items[0].url == "https://www.cyber.gouv.fr/actualites/exemple-de-publication-test/"
    assert items[0].title == "Exemple de publication de test"
    assert items[0].published_at.year == 2026
    assert items[0].published_at.month == 1
    assert items[0].published_at.day == 3
    # Second card's date is in the French "4 janvier 2026" long form.
    assert items[1].published_at.month == 1
    assert items[1].published_at.day == 4


def test_fetch_item_extracts_article_text(monkeypatch):
    monkeypatch.setattr(anssi, "fetch", _fake_fetch("anssi_article.html"))
    ref = RawItemRef(
        url="https://www.cyber.gouv.fr/actualites/exemple-de-publication-test/",
        title="Exemple de publication de test",
        published_at=None,
    )

    item = anssi.fetch_item(ref)

    assert "durcissement reseau" in item.text
    assert "Menu ANSSI" not in item.text
    assert "Pied de page" not in item.text
