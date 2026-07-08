from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass
class RawItemRef:
    url: str
    title: str
    published_at: datetime | None


@dataclass
class RawItem:
    url: str
    title: str
    published_at: datetime | None
    text: str


class Connector(Protocol):
    """Documents the shape every connector module (anssi.py, cert_fr.py,
    ...) must expose. Connectors are plain modules, not classes -- matches
    the rest of this codebase's style (ingestion/*.py)."""

    name: str
    authority_source: str

    def list_items(self) -> list[RawItemRef]: ...
    def fetch_item(self, ref: RawItemRef) -> RawItem: ...
