from __future__ import annotations

import logging
import re
from typing import Any, ClassVar

from claw_wechat_parser.domain.parse_result import MediaContent, Platform
from claw_wechat_parser.parser.base import BaseParser, ParseException, handle
from claw_wechat_parser.parser.platforms._ytdlp import (
    cookie_header_to_netscape_file,
    iter_entries,
    select_media_urls,
    ytdlp_extract_info,
)

log = logging.getLogger(__name__)


class YouTubeParser(BaseParser):
    platform: ClassVar[Platform] = Platform(name="youtube", display_name="YouTube")

    def __init__(self, settings):
        super().__init__(settings)
        self.headers.update({"Referer": "https://www.youtube.com/"})
        self.cookie_header = settings.youtube_cookie.strip()
        if self.cookie_header:
            self.headers["Cookie"] = self.cookie_header
        self.cookie_file = cookie_header_to_netscape_file(
            settings,
            name="youtube",
            domain="youtube.com",
            cookie_header=self.cookie_header,
        )

    @handle("youtu", r"https?://(?:www\.)?youtu\.be/[A-Za-z\d._?%&+\-=/#]+")
    @handle(
        "youtube",
        r"https?://(?:www\.)?youtube\.com/(?:watch|shorts)(?:/[A-Za-z\d_-]+|\?v=[A-Za-z\d_-]+)[A-Za-z\d._?%&+\-=/#]*",
    )
    async def _parse_video(self, searched: re.Match[str]):
        return await self.parse_video(searched.group(0), audio_only=False)

    @handle(
        "ymhttp",
        r"^ym(?P<url>https?://(?:www\.)?(?:youtu\.be/[A-Za-z\d_-]+|youtube\.com/(?:watch|shorts)(?:\?v=[A-Za-z\d_-]+|/[A-Za-z\d_-]+))[A-Za-z\d._?%&+\-=/#]*)",
    )
    async def ym(self, searched: re.Match[str]):
        return await self.parse_video(searched.group("url"), audio_only=True)

    async def parse_video(self, url: str, *, audio_only: bool):
        try:
            info = await ytdlp_extract_info(
                url,
                headers=self.headers,
                cookie_header=self.cookie_header,
                cookie_file=self.cookie_file,
                max_attempts=2,
            )
        except Exception as exc:
            raise ParseException(str(exc)) from exc

        entry = iter_entries(info)[0]
        duration = float(entry.get("duration") or 0)
        thumbnail = self._thumbnail(entry)
        contents: list[MediaContent] = []

        if thumbnail:
            contents.append(self.create_image_content(thumbnail, headers=self.headers))

        if duration <= self.settings.max_media_duration_s:
            if audio_only:
                audio_url = self._audio_url(entry)
                if audio_url:
                    contents.append(
                        self.create_audio_content(
                            audio_url,
                            duration,
                            headers=self.headers,
                            name=f"youtube_{entry.get('id') or 'audio'}.m4a",
                        )
                    )
            else:
                video_url, audio_url = select_media_urls(entry, max_height=720)
                if video_url:
                    contents.append(
                        self.create_video_content(
                            video_url,
                            thumbnail,
                            duration,
                            headers=self.headers,
                            audio_url=audio_url,
                            name=f"youtube_{entry.get('id') or 'video'}.mp4",
                        )
                    )

        if len(contents) == 0:
            raise ParseException("未找到可下载的 YouTube 媒体")

        return self.result(
            title=entry.get("title") or info.get("title"),
            author=self._author(entry),
            contents=contents,
            timestamp=entry.get("timestamp") or info.get("timestamp"),
            url=entry.get("webpage_url") or url,
        )

    def _author(self, info: dict[str, Any]):
        name = info.get("channel") or info.get("uploader") or info.get("uploader_id")
        if not isinstance(name, str) or not name:
            return None
        avatar = None
        thumbnails = info.get("channel_thumbnail") or info.get("thumbnails")
        if isinstance(thumbnails, list) and thumbnails:
            item = thumbnails[-1]
            if isinstance(item, dict) and isinstance(item.get("url"), str):
                avatar = item["url"]
        return self.create_author(name, avatar, info.get("channel_description"))

    @staticmethod
    def _thumbnail(info: dict[str, Any]) -> str | None:
        thumbnail = info.get("thumbnail")
        if isinstance(thumbnail, str) and thumbnail:
            return thumbnail
        thumbnails = info.get("thumbnails")
        if isinstance(thumbnails, list) and thumbnails:
            item = thumbnails[-1]
            if isinstance(item, dict) and isinstance(item.get("url"), str):
                return item["url"]
        return None

    @staticmethod
    def _audio_url(info: dict[str, Any]) -> str | None:
        from claw_wechat_parser.parser.platforms._ytdlp import best_audio_format, format_url

        formats = info.get("formats")
        if isinstance(formats, list):
            fmt = best_audio_format(formats)
            if fmt:
                return format_url(fmt)
        url = info.get("url")
        return url if isinstance(url, str) else None
