from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

MediaKind = Literal["image", "video", "audio", "file"]


@dataclass(slots=True)
class MediaAttachment:
    path: Path
    kind: MediaKind
    name: str | None = None
    mime_type: str | None = None


@dataclass(slots=True)
class InboundMessage:
    account_id: str
    from_user_id: str
    to_user_id: str
    text: str
    message_id: str
    timestamp_ms: int | None = None
    context_token: str | None = None
    raw: dict | None = None
    media: list[MediaAttachment] = field(default_factory=list)


@dataclass(slots=True)
class OutboundMessage:
    to_user_id: str
    text: str = ""
    context_token: str | None = None
    media: list[MediaAttachment] = field(default_factory=list)
