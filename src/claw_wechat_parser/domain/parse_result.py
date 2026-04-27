from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

ContentKind = Literal["text", "image", "video", "audio", "file"]


@dataclass(slots=True)
class Platform:
    name: str
    display_name: str


@dataclass(slots=True)
class Author:
    name: str
    avatar_url: str | None = None
    description: str | None = None


@dataclass(slots=True)
class MediaContent:
    kind: ContentKind
    url: str | None = None
    path: Path | None = None
    text: str | None = None
    name: str | None = None
    mime_type: str | None = None
    cover_url: str | None = None
    duration: float = 0.0
    headers: dict[str, str] = field(default_factory=dict)
    audio_url: str | None = None


@dataclass(slots=True)
class ParseResult:
    platform: Platform
    author: Author | None = None
    title: str | None = None
    text: str | None = None
    url: str | None = None
    timestamp: int | None = None
    contents: list[MediaContent] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def header(self) -> str:
        parts = [self.platform.display_name]
        if self.author:
            parts.append(f"@{self.author.name}")
        if self.title:
            parts.append(self.title)
        return " | ".join(parts)

    def get_resource_id(self) -> str:
        src = self.url or self.title or self.text or repr(self.extra)
        return hashlib.sha256(src.encode("utf-8", "ignore")).hexdigest()

    def to_text(self) -> str:
        lines = [self.header]
        if self.text:
            lines.append(self.text)
        if self.url:
            lines.append(f"链接: {self.url}")
        info = self.extra.get("info")
        if info:
            lines.append(str(info))
        return "\n".join(x for x in lines if x).strip()
