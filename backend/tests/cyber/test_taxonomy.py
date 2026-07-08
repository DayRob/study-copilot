from app.cyber.taxonomy import load_taxonomy


def test_load_taxonomy_returns_all_axes():
    taxonomy = load_taxonomy()
    assert "guide_bonnes_pratiques" in taxonomy.content_types
    assert "reseau" in taxonomy.technical_domains
    assert taxonomy.levels == ["fondamental", "avance"]
    assert "ANSSI" in taxonomy.authority_sources
    assert "CERT-FR" in taxonomy.authority_sources
