from __future__ import annotations

import re
from itertools import chain
from typing import Any, ClassVar

from bs4 import BeautifulSoup, Tag

from claw_wechat_parser.domain.parse_result import ParseResult, Platform
from claw_wechat_parser.parser.base import BaseParser, ParseException, handle


class TwitterParser(BaseParser):
    platform: ClassVar[Platform] = Platform(name="twitter", display_name="Twitter/X")

    def __init__(self, settings):
        super().__init__(settings)
        self.headers.update(
            {
                "Accept": "application/json, text/plain, */*",
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": "https://xdown.app",
                "Referer": "https://xdown.app/",
            }
        )
        if settings.twitter_cookie:
            self.headers["Cookie"] = settings.twitter_cookie
        self.xdown_url = "https://xdown.app/api/ajaxSearch"

    async def _req_xdown_api(self, url: str) -> dict[str, Any]:
        resp = await self.client.post(
            self.xdown_url,
            data={"q": url, "lang": "zh-cn"},
            headers=self.headers,
        )
        if resp.status_code >= 400:
            raise ParseException(f"xdown API HTTP {resp.status_code}")
        data = resp.json()
        if not isinstance(data, dict):
            raise ParseException("xdown API 返回格式异常")
        return data

    @handle("x.com/", r"https?://x\.com/[0-9A-Za-z_]{1,20}/status/[0-9]+[A-Za-z\d._?%&+\-=/#]*")
    @handle(
        "twitter.com",
        r"https?://(?:www\.)?twitter\.com/[0-9A-Za-z_]{1,20}/status/[0-9]+[A-Za-z\d._?%&+\-=/#]*",
    )
    async def _parse(self, searched: re.Match[str]) -> ParseResult:
        url = searched.group(0)
        resp = await self._req_xdown_api(url)
        if resp.get("status") != "ok":
            raise ParseException(str(resp.get("mess") or resp.get("message") or "解析失败"))
        html_content = resp.get("data")
        if not isinstance(html_content, str) or not html_content:
            raise ParseException("解析失败，数据为空")
        return self.parse_twitter_html(html_content, url)

    def parse_twitter_html(self, html_content: str, source_url: str | None = None) -> ParseResult:
        soup = BeautifulSoup(html_content, "html.parser")
        title = None
        cover_url = None
        video_url = None
        images_urls: list[str] = []
        gif_urls: list[str] = []

        thumb_tag = soup.find("img")
        if isinstance(thumb_tag, Tag) and (cover := thumb_tag.get("src")):
            cover_url = str(cover)

        tw_button_tags = soup.find_all("a", class_="tw-button-dl")
        abutton_tags = soup.find_all("a", class_="abutton")
        for tag in chain(tw_button_tags, abutton_tags):
            if not isinstance(tag, Tag):
                continue
            href = tag.get("href")
            if href is None:
                continue
            href = str(href)
            text = tag.get_text(strip=True)
            if "下载 MP4" in text or "Download MP4" in text:
                video_url = href
                break
            if "下载图片" in text or "Download Photo" in text or "Download Image" in text:
                images_urls.append(href)
            elif "下载 gif" in text.lower() or "download gif" in text.lower():
                gif_urls.append(href)

        title_tag = soup.find("h3")
        if title_tag:
            title = title_tag.get_text(strip=True)

        contents = []
        if video_url:
            contents.append(self.create_video_content(video_url, cover_url, headers=self.headers))
        if images_urls:
            contents.extend(self.create_image_contents(images_urls, headers=self.headers))
        if gif_urls:
            contents.extend(
                self.create_video_content(url, cover_url, headers=self.headers) for url in gif_urls
            )
        if not contents and cover_url:
            contents.append(self.create_image_content(cover_url, headers=self.headers))
        if not contents:
            raise ParseException("未找到可下载的 Twitter/X 媒体")

        return self.result(
            title=title,
            author=self.create_author("无用户名"),
            contents=contents,
            url=source_url,
        )
