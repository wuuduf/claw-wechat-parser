from __future__ import annotations

import json
import logging
import re
from typing import Any, ClassVar

from msgspec import Struct, convert, field

from claw_wechat_parser.domain.parse_result import Platform
from claw_wechat_parser.parser.base import BaseParser, ParseException, handle

log = logging.getLogger(__name__)


class XHSParser(BaseParser):
    platform: ClassVar[Platform] = Platform(name="xhs", display_name="小红书")

    def __init__(self, settings):
        super().__init__(settings)
        self.headers.update(
            {
                "accept": (
                    "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
                    "image/webp,image/apng,*/*;q=0.8"
                )
            }
        )
        self.ios_headers.update(
            {
                "origin": "https://www.xiaohongshu.com",
                "x-requested-with": "XMLHttpRequest",
                "sec-fetch-site": "same-origin",
                "sec-fetch-mode": "cors",
                "sec-fetch-dest": "empty",
            }
        )
        if settings.xhs_cookie:
            self.headers["cookie"] = settings.xhs_cookie
            self.ios_headers["cookie"] = settings.xhs_cookie

    @handle("xhslink.com", r"xhslink\.com/[A-Za-z0-9._?%&+=/#@-]+")
    async def _parse_short_link(self, searched: re.Match[str]):
        url = f"https://{searched.group(0)}"
        return await self.parse_with_redirect(url, self.ios_headers)

    @handle(
        "xiaohongshu.com",
        r"(?:explore|discovery/item)/(?P<xhs_id>[0-9a-zA-Z]+)(?:\?(?P<query>[A-Za-z0-9._%&+=/#@-]+))?",
    )
    async def _parse_common(self, searched: re.Match[str]):
        xhs_id = searched.group("xhs_id")
        query = xhs_id + (f"?{searched.group('query')}" if searched.group("query") else "")
        domain = "https://www.xiaohongshu.com"
        try:
            return await self.parse_explore(f"{domain}/explore/{query}", xhs_id)
        except Exception as exc:
            log.warning("parse_explore failed: %s, fallback to discovery", exc)
            return await self.parse_discovery(f"{domain}/discovery/item/{query}")

    async def parse_explore(self, url: str, xhs_id: str):
        resp = await self.client.get(url, headers=self.headers)
        html = resp.text
        json_obj = self._extract_initial_state_json(html)
        note_data = json_obj.get("note", {}).get("noteDetailMap", {}).get(xhs_id, {}).get("note", {})
        if not note_data:
            raise ParseException("can't find note detail in json_obj")

        class Image(Struct):
            urlDefault: str

        class User(Struct):
            nickname: str
            avatar: str

        class NoteDetail(Struct):
            type: str
            title: str
            desc: str
            user: User
            imageList: list[Image] = field(default_factory=list)
            video: Video | None = None

            @property
            def image_urls(self) -> list[str]:
                return [item.urlDefault for item in self.imageList]

            @property
            def video_url(self) -> str | None:
                if self.type != "video" or not self.video:
                    return None
                return self.video.video_url

        note_detail = convert(note_data, type=NoteDetail)
        contents = []
        if video_url := note_detail.video_url:
            cover_url = note_detail.image_urls[0] if note_detail.image_urls else None
            contents.append(self.create_video_content(video_url, cover_url, headers=self.headers))
        elif image_urls := note_detail.image_urls:
            contents.extend(self.create_image_contents(image_urls, headers=self.headers))
        return self.result(
            title=note_detail.title,
            text=note_detail.desc,
            author=self.create_author(note_detail.user.nickname, note_detail.user.avatar),
            contents=contents,
            url=url,
        )

    async def parse_discovery(self, url: str):
        resp = await self.client.get(url, headers=self.ios_headers, follow_redirects=True)
        json_obj = self._extract_initial_state_json(resp.text)
        note_data_root = json_obj.get("noteData")
        if not note_data_root:
            raise ParseException("can't find noteData in json_obj")
        preload_data = note_data_root.get("normalNotePreloadData", {})
        note_data = note_data_root.get("data", {}).get("noteData", {})
        if not note_data:
            raise ParseException("can't find noteData in noteData.data")

        class Image(Struct):
            url: str
            urlSizeLarge: str | None = None

        class User(Struct):
            nickName: str
            avatar: str

        class NoteData(Struct):
            type: str
            title: str
            desc: str
            user: User
            time: int
            lastUpdateTime: int
            imageList: list[Image] = field(default_factory=list)
            video: Video | None = None

            @property
            def image_urls(self) -> list[str]:
                return [item.url for item in self.imageList]

            @property
            def video_url(self) -> str | None:
                if self.type != "video" or not self.video:
                    return None
                return self.video.video_url

        class NormalNotePreloadData(Struct):
            title: str
            desc: str
            imagesList: list[Image] = field(default_factory=list)

            @property
            def image_urls(self) -> list[str]:
                return [item.urlSizeLarge or item.url for item in self.imagesList]

        note = convert(note_data, type=NoteData)
        contents = []
        if video_url := note.video_url:
            if preload_data:
                preload = convert(preload_data, type=NormalNotePreloadData)
                img_urls = preload.image_urls
            else:
                img_urls = note.image_urls
            contents.append(
                self.create_video_content(
                    video_url,
                    img_urls[0] if img_urls else None,
                    headers=self.ios_headers,
                )
            )
        elif img_urls := note.image_urls:
            contents.extend(self.create_image_contents(img_urls, headers=self.ios_headers))
        return self.result(
            title=note.title,
            author=self.create_author(note.user.nickName, note.user.avatar),
            contents=contents,
            text=note.desc,
            timestamp=note.time // 1000,
            url=url,
        )

    def _extract_initial_state_json(self, html: str) -> dict[str, Any]:
        matched = re.search(r"window\.__INITIAL_STATE__=(.*?)</script>", html, re.S)
        if not matched:
            raise ParseException("小红书分享链接失效或内容已删除")
        json_str = matched.group(1).replace("undefined", "null")
        return json.loads(json_str)


class Stream(Struct):
    h264: list[dict[str, Any]] | None = None
    h265: list[dict[str, Any]] | None = None
    av1: list[dict[str, Any]] | None = None
    h266: list[dict[str, Any]] | None = None


class Media(Struct):
    stream: Stream


class Video(Struct):
    media: Media

    @property
    def video_url(self) -> str | None:
        stream = self.media.stream
        if stream.h265:
            return stream.h265[0]["masterUrl"]
        if stream.h264:
            return stream.h264[0]["masterUrl"]
        if stream.av1:
            return stream.av1[0]["masterUrl"]
        if stream.h266:
            return stream.h266[0]["masterUrl"]
        return None
