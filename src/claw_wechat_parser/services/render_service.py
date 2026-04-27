from __future__ import annotations

import hashlib
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from claw_wechat_parser.config import Settings
from claw_wechat_parser.domain.parse_result import ParseResult


class RenderService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def render_card(self, result: ParseResult) -> Path:
        digest = hashlib.sha256(result.to_text().encode()).hexdigest()[:24]
        path = self.settings.render_dir / f"{digest}.png"
        if path.exists():
            return path
        width, height = 900, 420
        img = Image.new("RGB", (width, height), "#f7f3e8")
        draw = ImageDraw.Draw(img)
        try:
            title_font = ImageFont.truetype("/System/Library/Fonts/PingFang.ttc", 34)
            body_font = ImageFont.truetype("/System/Library/Fonts/PingFang.ttc", 24)
        except Exception:
            title_font = ImageFont.load_default()
            body_font = ImageFont.load_default()
        draw.rounded_rectangle((24, 24, width - 24, height - 24), radius=28, fill="#fffaf0", outline="#23395d", width=3)
        draw.text((54, 52), result.header[:42], fill="#23395d", font=title_font)
        body = result.text or result.url or ""
        lines = []
        while body:
            lines.append(body[:34])
            body = body[34:]
            if len(lines) >= 6:
                break
        y = 122
        for line in lines:
            draw.text((54, y), line, fill="#2b2b2b", font=body_font)
            y += 40
        if result.url:
            draw.text((54, height - 76), result.url[:60], fill="#666666", font=body_font)
        img.save(path)
        return path
