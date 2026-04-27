from __future__ import annotations

import html
import re
from typing import ClassVar

from claw_wechat_parser.domain.parse_result import MediaContent, Platform
from claw_wechat_parser.parser.base import BaseParser, handle

URL_RE = r"(?P<url>https?://[^\s<>\"'，。！？、]+)"


def _meta(content: str, *names: str) -> str | None:
    for name in names:
        patterns = [
            rf'<meta[^>]+property=["\']{re.escape(name)}["\'][^>]+content=["\']([^"\']+)["\']',
            rf'<meta[^>]+name=["\']{re.escape(name)}["\'][^>]+content=["\']([^"\']+)["\']',
            rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']{re.escape(name)}["\']',
        ]
        for pat in patterns:
            m = re.search(pat, content, re.I | re.S)
            if m:
                return html.unescape(m.group(1)).strip()
    return None


def _title(content: str) -> str | None:
    if m := re.search(r"<title[^>]*>(.*?)</title>", content, re.I | re.S):
        return html.unescape(re.sub(r"\s+", " ", m.group(1))).strip()
    return None


class GenericUrlParser(BaseParser):
    platform: ClassVar[Platform] = Platform(name="generic", display_name="网页链接")

    @handle("http", URL_RE)
    @handle("https", URL_RE)
    async def parse_url(self, match: re.Match[str]):
        url = match.group("url")
        title = None
        desc = None
        image = None
        try:
            resp = await self.client.get(
                url,
                headers={"User-Agent": "Mozilla/5.0 claw-wechat-parser/0.1"},
                follow_redirects=True,
            )
            ctype = resp.headers.get("content-type", "")
            if "text/html" in ctype and resp.text:
                body = resp.text[:512_000]
                title = _meta(body, "og:title", "twitter:title") or _title(body)
                desc = _meta(body, "og:description", "description", "twitter:description")
                image = _meta(body, "og:image", "twitter:image")
        except Exception as exc:
            desc = f"抓取网页元信息失败：{exc}"

        contents = []
        if image and image.startswith("http"):
            contents.append(MediaContent(kind="image", url=image))
        return self.result(title=title or "链接", text=desc, url=url, contents=contents)
