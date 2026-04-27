from __future__ import annotations

import logging

from claw_wechat_parser.config import Settings
from claw_wechat_parser.domain.message import InboundMessage, OutboundMessage
from claw_wechat_parser.domain.parse_result import ParseResult
from claw_wechat_parser.parser import ParserRouter
from claw_wechat_parser.parser.base import ParseException
from claw_wechat_parser.services.debounce import Debouncer
from claw_wechat_parser.services.download_service import DownloadService
from claw_wechat_parser.services.render_service import RenderService

log = logging.getLogger(__name__)


class ParseService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.router = ParserRouter(settings)
        self.router.register_all()
        self.debouncer = Debouncer(settings.debounce_seconds)
        self.downloader = DownloadService(settings)
        self.renderer = RenderService(settings)

    async def close(self) -> None:
        await self.router.close()

    async def parse_message(self, inbound: InboundMessage) -> OutboundMessage | None:
        if not inbound.text.strip():
            return None
        try:
            parsed = await self.router.parse(inbound.text)
        except ParseException as exc:
            return OutboundMessage(
                to_user_id=inbound.from_user_id,
                text=f"解析失败：{exc}",
                context_token=inbound.context_token,
            )
        if parsed is None:
            return None
        scope = inbound.from_user_id or inbound.account_id
        if self.debouncer.hit(scope, parsed.get_resource_id()):
            log.info("防抖命中，跳过发送：scope=%s resource=%s", scope, parsed.get_resource_id())
            return None
        return await self.build_outbound(inbound, parsed)

    async def build_outbound(self, inbound: InboundMessage, parsed: ParseResult) -> OutboundMessage:
        media = []
        text = parsed.to_text()
        # MVP 策略：优先下载解析器给出的图片；没有媒体时生成一张信息卡片。
        for content in parsed.contents[:4]:
            if content.kind in {"image", "video", "audio", "file"}:
                try:
                    attachment = await self.downloader.download(content)
                    if attachment:
                        media.append(attachment)
                except Exception as exc:
                    text += f"\n媒体下载失败：{exc}"
        if not media:
            card = self.renderer.render_card(parsed)
            from claw_wechat_parser.domain.message import MediaAttachment

            media.append(MediaAttachment(path=card, kind="image", mime_type="image/png"))
        return OutboundMessage(
            to_user_id=inbound.from_user_id,
            text=text,
            context_token=inbound.context_token,
            media=media,
        )
