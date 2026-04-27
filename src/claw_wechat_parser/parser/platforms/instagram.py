from __future__ import annotations

import asyncio
import html
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any, ClassVar
from urllib.parse import urlparse

from claw_wechat_parser.domain.parse_result import MediaContent, Platform
from claw_wechat_parser.parser.base import BaseParser, ParseException, handle
from claw_wechat_parser.parser.platforms._ytdlp import (
    cookie_header_to_netscape_file,
    iter_entries,
    select_media_urls,
    ytdlp_extract_info,
)

log = logging.getLogger(__name__)


class InstagramParser(BaseParser):
    platform: ClassVar[Platform] = Platform(name="instagram", display_name="Instagram")

    def __init__(self, settings):
        super().__init__(settings)
        self.headers.update(
            {
                "Origin": "https://www.instagram.com",
                "Referer": "https://www.instagram.com/",
            }
        )
        self.cookie_header = settings.instagram_cookie.strip()
        if self.cookie_header:
            self.headers["Cookie"] = self.cookie_header
        self.cookie_file = cookie_header_to_netscape_file(
            settings,
            name="instagram",
            domain="instagram.com",
            cookie_header=self.cookie_header,
        )

    @handle(
        "instagram.com",
        r"https?://(?:www\.)?instagram\.com/(?:p|reel|reels|tv|share)/[A-Za-z0-9._?%&=+\-/#]+",
    )
    @handle(
        "instagr.am",
        r"https?://(?:www\.)?instagr\.am/(?:p|reel|reels|tv)/[A-Za-z0-9._?%&=+\-/#]+",
    )
    async def _parse(self, searched: re.Match[str]):
        url = searched.group(0)
        final_url = await self.get_final_url(url, headers=self.headers)
        kind = self._kind(final_url)
        is_video_url = kind in {"reel", "reels", "tv"}
        shortcode = self._extract_shortcode(final_url) or self._extract_shortcode(url)
        base_prefix = f"ig_{shortcode}" if shortcode else "ig"

        info: dict[str, Any] | None = None
        try:
            info = await ytdlp_extract_info(
                final_url,
                headers=self.headers,
                cookie_header=self.cookie_header,
                cookie_file=self.cookie_file,
                max_attempts=2,
            )
        except Exception as exc:
            log.warning("Instagram yt-dlp failed: %s", exc)

        contents: list[MediaContent] = []
        meta: dict[str, Any] = info or {}
        if info:
            entries = iter_entries(info)
            for idx, entry in enumerate(entries, start=1):
                if not isinstance(entry, dict):
                    continue
                meta = entry
                video_url, audio_url = select_media_urls(entry, max_height=720)
                duration = float(entry.get("duration") or 0)
                if video_url:
                    contents.append(
                        self.create_video_content(
                            video_url,
                            self._thumbnail(entry),
                            duration,
                            headers=self.headers,
                            audio_url=audio_url,
                            name=f"{base_prefix}_{idx}.mp4",
                        )
                    )
                    continue
                image_url = self._image_url(entry)
                if image_url:
                    contents.append(
                        self.create_image_content(
                            image_url,
                            headers=self.headers,
                            text=entry.get("description") or entry.get("title"),
                        )
                    )

        if not contents and not is_video_url:
            for idx, image_url in enumerate(await self._gallery_dl_image_urls(final_url), start=1):
                suffix = Path(urlparse(image_url).path).suffix or ".jpg"
                contents.append(
                    self.create_image_content(
                        image_url,
                        headers=self.headers,
                        text=f"{base_prefix}_{idx}{suffix}",
                    )
                )

        if not contents:
            raise ParseException("未找到可下载的 Instagram 媒体")

        author_name = None
        for key in ("uploader", "uploader_id", "channel", "creator"):
            val = meta.get(key) if isinstance(meta, dict) else None
            if isinstance(val, str) and val:
                author_name = val
                break
        author = self.create_author(author_name) if author_name else None

        return self.result(
            title=(meta.get("title") if isinstance(meta, dict) else None) or (info or {}).get("title"),
            text=(meta.get("description") if isinstance(meta, dict) else None),
            author=author,
            contents=contents,
            timestamp=(meta.get("timestamp") if isinstance(meta, dict) else None),
            url=final_url,
        )

    async def _gallery_dl_image_urls(self, url: str) -> list[str]:
        cmd = [sys.executable, "-m", "gallery_dl", "-j"]
        if self.cookie_file and self.cookie_file.exists():
            cmd += ["--cookies", str(self.cookie_file)]
        cmd.append(url)
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            raise ParseException(f"gallery-dl 解析失败: {stderr.decode(errors='ignore').strip()}")

        text = stdout.decode(errors="ignore").strip()
        if not text:
            raise ParseException("gallery-dl 输出为空")

        urls: list[str] = []
        errors: list[str] = []

        def handle_item(item: object) -> None:
            if isinstance(item, list):
                if len(item) >= 2 and item[0] == -1 and isinstance(item[1], dict):
                    message = item[1].get("message")
                    if isinstance(message, str):
                        errors.append(message)
                    return
                if len(item) >= 3 and item[0] == 3 and isinstance(item[1], str):
                    urls.append(self._clean_url(item[1]))
                    return
                if len(item) >= 2 and item[0] == 3 and isinstance(item[1], dict):
                    for key in ("url", "display_url"):
                        val = item[1].get(key)
                        if isinstance(val, str):
                            urls.append(self._clean_url(val))
                            return
            if isinstance(item, dict):
                for key in ("url", "display_url"):
                    val = item.get(key)
                    if isinstance(val, str):
                        urls.append(self._clean_url(val))
                        return

        try:
            data = json.loads(text)
            if isinstance(data, list):
                for item in data:
                    handle_item(item)
            else:
                handle_item(data)
        except json.JSONDecodeError:
            for line in text.splitlines():
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                handle_item(item)

        if not urls:
            if errors:
                raise ParseException(f"gallery-dl 解析失败: {errors[0]}")
            raise ParseException("gallery-dl 未返回图片链接")
        return urls

    @staticmethod
    def _clean_url(url: str) -> str:
        return html.unescape(url)

    @staticmethod
    def _extract_shortcode(url: str) -> str | None:
        path = urlparse(url).path
        if matched := re.search(r"/(?:p|reel|reels|tv)/([A-Za-z0-9_-]+)/?", path):
            return matched.group(1)
        return None

    @staticmethod
    def _kind(url: str) -> str:
        path = urlparse(url).path
        if matched := re.search(r"/(p|reel|reels|tv|share)/", path):
            return matched.group(1)
        return ""

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
    def _image_url(info: dict[str, Any]) -> str | None:
        for key in ("url", "display_url", "thumbnail"):
            val = info.get(key)
            if isinstance(val, str) and val:
                ext = info.get("ext")
                mime = info.get("mime_type")
                vcodec = info.get("vcodec")
                if key == "url" and (vcodec not in (None, "none") or ext in {"mp4", "webm"}):
                    continue
                if isinstance(mime, str) and mime.startswith("video/"):
                    continue
                return val
        return None
