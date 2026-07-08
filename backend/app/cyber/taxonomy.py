from dataclasses import dataclass
from pathlib import Path

import yaml

TAXONOMY_PATH = Path(__file__).parent / "taxonomy.yaml"


@dataclass
class Taxonomy:
    content_types: list[str]
    technical_domains: list[str]
    levels: list[str]
    authority_sources: list[str]


def load_taxonomy(path: Path = TAXONOMY_PATH) -> Taxonomy:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return Taxonomy(
        content_types=data["content_type"],
        technical_domains=data["technical_domain"],
        levels=data["level"],
        authority_sources=data["authority_source"],
    )
