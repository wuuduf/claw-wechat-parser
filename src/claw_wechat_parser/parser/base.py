from __future__ import annotations

import re
from abc import ABC
from collections.abc import Awaitable, Callable
from re import Match, Pattern
from typing import ClassVar, TypeVar, cast

import httpx

from claw_wechat_parser.config import Settings
from claw_wechat_parser.domain.parse_result import Author, MediaContent, ParseResult, Platform

T = TypeVar("T", bound="BaseParser")
HandlerFunc = Callable[[T, Match[str]], Awaitable[ParseResult]]
_KEY_PATTERNS = "_key_patterns"

COMMON_HEADER = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}
IOS_HEADER = {
    **COMMON_HEADER,
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
}
ANDROID_HEADER = {
    **COMMON_HEADER,
    "User-Agent": "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36",
}


class ParseException(RuntimeError):
    """Raised when a parser cannot resolve the requested resource."""


class DownloadException(RuntimeError):
    """Raised when a media download URL cannot be produced."""


def handle(keyword: str, pattern: str) -> Callable[[HandlerFunc[T]], HandlerFunc[T]]:
    def decorator(func: HandlerFunc[T]) -> HandlerFunc[T]:
        patterns = getattr(func, _KEY_PATTERNS, [])
        patterns.append((keyword, re.compile(pattern)))
        setattr(func, _KEY_PATTERNS, patterns)
        return func

    return decorator


class BaseParser(ABC):
    _registry: ClassVar[list[type[BaseParser]]] = []
    platform: ClassVar[Platform]
    _handlers: ClassVar[dict[str, HandlerFunc]]
    _key_patterns: ClassVar[list[tuple[str, Pattern[str]]]]

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if ABC not in cls.__bases__:
            BaseParser._registry.append(cls)
        cls._handlers = {}
        cls._key_patterns = []
        for _attr_name, attr in cls.__dict__.items():
            if callable(attr) and hasattr(attr, _KEY_PATTERNS):
                handler = cast(HandlerFunc, attr)
                for keyword, pattern in getattr(attr, _KEY_PATTERNS):
                    cls._handlers[keyword] = handler
                    cls._key_patterns.append((keyword, pattern))
        cls._key_patterns.sort(key=lambda x: -len(x[0]))

    def __init__(self, settings: Settings):
        self.settings = settings
        self.headers = COMMON_HEADER.copy()
        self.ios_headers = IOS_HEADER.copy()
        self.android_headers = ANDROID_HEADER.copy()
        self.client = httpx.AsyncClient(timeout=settings.api_timeout_s, follow_redirects=True)

    @classmethod
    def get_all_subclasses(cls) -> list[type[BaseParser]]:
        return list(cls._registry)

    @classmethod
    def key_patterns(cls) -> list[tuple[str, Pattern[str]]]:
        return list(cls._key_patterns)

    async def close(self) -> None:
        await self.client.aclose()

    async def parse(self, keyword: str, match: Match[str]) -> ParseResult:
        return await self._handlers[keyword](self, match)

    @classmethod
    def result(cls, **kwargs) -> ParseResult:
        return ParseResult(platform=cls.platform, **kwargs)

    @classmethod
    def search_url(cls, url: str) -> tuple[str, Match[str]]:
        for keyword, pattern in cls._key_patterns:
            if keyword not in url:
                continue
            if matched := pattern.search(url):
                return keyword, matched
        raise ParseException(f"无法匹配 URL: {url}")

    async def get_redirect_url(self, url: str, headers: dict[str, str] | None = None) -> str:
        resp = await self.client.get(url, headers=headers or self.headers, follow_redirects=False)
        if resp.status_code >= 400:
            raise ParseException(f"重定向请求失败: HTTP {resp.status_code}")
        return resp.headers.get("Location", url)

    async def get_final_url(self, url: str, headers: dict[str, str] | None = None) -> str:
        resp = await self.client.get(url, headers=headers or self.headers, follow_redirects=True)
        if resp.status_code >= 400:
            raise ParseException(f"URL 请求失败: HTTP {resp.status_code}")
        return str(resp.url)

    async def parse_with_redirect(
        self, url: str, headers: dict[str, str] | None = None
    ) -> ParseResult:
        redirect_url = await self.get_redirect_url(url, headers=headers or self.headers)
        if redirect_url == url:
            raise ParseException(f"无法重定向 URL: {url}")
        keyword, searched = self.search_url(redirect_url)
        return await self.parse(keyword, searched)

    def create_author(
        self,
        name: str,
        avatar_url: str | None = None,
        description: str | None = None,
    ) -> Author:
        return Author(name=name, avatar_url=avatar_url, description=description)

    def create_video_content(
        self,
        url: str,
        cover_url: str | None = None,
        duration: float = 0.0,
        *,
        headers: dict[str, str] | None = None,
        audio_url: str | None = None,
        name: str | None = None,
    ) -> MediaContent:
        return MediaContent(
            kind="video",
            url=url,
            cover_url=cover_url,
            duration=duration,
            headers=headers or {},
            audio_url=audio_url,
            name=name,
            mime_type="video/mp4",
        )

    def create_audio_content(
        self,
        url: str,
        duration: float = 0.0,
        *,
        headers: dict[str, str] | None = None,
        name: str | None = None,
    ) -> MediaContent:
        return MediaContent(
            kind="audio",
            url=url,
            duration=duration,
            headers=headers or {},
            name=name,
            mime_type="audio/mpeg",
        )

    def create_image_contents(
        self, urls: list[str], *, headers: dict[str, str] | None = None
    ) -> list[MediaContent]:
        return [MediaContent(kind="image", url=url, headers=headers or {}) for url in urls]

    def create_image_content(
        self,
        url: str,
        *,
        text: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> MediaContent:
        return MediaContent(kind="image", url=url, text=text, headers=headers or {})
