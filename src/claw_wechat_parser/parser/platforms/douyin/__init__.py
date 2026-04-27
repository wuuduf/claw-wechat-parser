from __future__ import annotations

import logging
import re
from typing import ClassVar

import msgspec

from claw_wechat_parser.domain.parse_result import Platform
from claw_wechat_parser.parser.base import BaseParser, ParseException, handle

log = logging.getLogger(__name__)


class DouyinParser(BaseParser):
    platform: ClassVar[Platform] = Platform(name="douyin", display_name="抖音")

    def __init__(self, settings):
        super().__init__(settings)
        self.cookie_header = settings.douyin_cookie.strip()
        if self.cookie_header:
            self.ios_headers["Cookie"] = self.cookie_header
            self.android_headers["Cookie"] = self.cookie_header

    @handle("v.douyin", r"v\.douyin\.com/[a-zA-Z0-9_\-]+")
    @handle("jx.douyin", r"jx\.douyin\.com/[a-zA-Z0-9_\-]+")
    async def _parse_short_link(self, searched: re.Match[str]):
        url = f"https://{searched.group(0)}"
        return await self.parse_with_redirect(url)

    @handle("douyin", r"douyin\.com/(?P<ty>video|note)/(?P<vid>\d+)")
    @handle("iesdouyin", r"iesdouyin\.com/share/(?P<ty>slides|video|note)/(?P<vid>\d+)")
    @handle("m.douyin", r"m\.douyin\.com/share/(?P<ty>slides|video|note)/(?P<vid>\d+)")
    @handle(
        "jingxuan.douyin",
        r"jingxuan\.douyin.com/m/(?P<ty>slides|video|note)/(?P<vid>\d+)",
    )
    async def _parse_douyin(self, searched: re.Match[str]):
        ty, vid = searched.group("ty"), searched.group("vid")
        if ty == "slides":
            return await self.parse_slides(vid)
        errors = []
        for url in (self._build_m_douyin_url(ty, vid), self._build_iesdouyin_url(ty, vid)):
            try:
                return await self.parse_video(url)
            except ParseException as exc:
                errors.append(str(exc))
        raise ParseException("分享已删除或资源直链提取失败: " + " | ".join(errors[-2:]))

    async def parse_with_redirect(self, url: str):
        resp = await self.client.get(url, headers=self.ios_headers, follow_redirects=False)
        self._update_cookies(resp)
        redirect_url = resp.headers.get("Location", url)
        if redirect_url == url:
            raise ParseException(f"无法重定向 URL: {url}")
        keyword, searched = self.search_url(redirect_url)
        return await self.parse(keyword, searched)

    @staticmethod
    def _build_iesdouyin_url(ty: str, vid: str) -> str:
        return f"https://www.iesdouyin.com/share/{ty}/{vid}"

    @staticmethod
    def _build_m_douyin_url(ty: str, vid: str) -> str:
        return f"https://m.douyin.com/share/{ty}/{vid}"

    def _update_cookies(self, resp) -> None:
        cookies = []
        for item in resp.headers.get_list("set-cookie"):
            first = item.split(";", 1)[0]
            if first and "=" in first:
                cookies.append(first)
        if cookies:
            self.cookie_header = "; ".join(cookies)
            self.ios_headers["Cookie"] = self.cookie_header
            self.android_headers["Cookie"] = self.cookie_header

    async def parse_video(self, url: str):
        resp = await self.client.get(url, headers=self.ios_headers, follow_redirects=False)
        self._update_cookies(resp)
        if resp.status_code != 200:
            raise ParseException(f"status: {resp.status_code}")
        matched = re.search(r"window\._ROUTER_DATA\s*=\s*(.*?)</script>", resp.text, re.S)
        if not matched or not matched.group(1):
            raise ParseException("can't find _ROUTER_DATA in html")
        from .video import RouterData

        video_data = msgspec.json.decode(matched.group(1).strip(), type=RouterData).video_data
        contents = []
        if image_urls := video_data.image_urls:
            contents.extend(self.create_image_contents(image_urls, headers=self.ios_headers))
        elif video_url := video_data.video_url:
            duration_s = (video_data.video.duration / 1000) if video_data.video else 0
            contents.append(
                self.create_video_content(
                    video_url,
                    video_data.cover_url,
                    duration_s,
                    headers=self.ios_headers,
                    name="douyin.mp4",
                )
            )
        return self.result(
            title=video_data.desc,
            author=self.create_author(video_data.author.nickname, video_data.avatar_url),
            contents=contents,
            timestamp=video_data.create_time,
            url=url,
        )

    async def parse_slides(self, video_id: str):
        url = "https://www.iesdouyin.com/web/api/v2/aweme/slidesinfo/"
        params = {"aweme_ids": f"[{video_id}]", "request_source": "200"}
        resp = await self.client.get(url, params=params, headers=self.android_headers)
        self._update_cookies(resp)
        resp.raise_for_status()
        from .slides import SlidesInfo

        slides_info = msgspec.json.decode(resp.content, type=SlidesInfo)
        if not slides_info.aweme_details:
            raise ParseException("can't find slides data")
        slides_data = slides_info.aweme_details[0]
        contents = self.create_image_contents(slides_data.image_urls, headers=self.android_headers)
        contents.extend(
            self.create_video_content(url, headers=self.android_headers)
            for url in slides_data.dynamic_urls
        )
        return self.result(
            title=slides_data.desc,
            author=self.create_author(slides_data.name, slides_data.avatar_url),
            contents=contents,
            timestamp=slides_data.create_time,
            url=f"https://www.iesdouyin.com/share/slides/{video_id}",
        )
