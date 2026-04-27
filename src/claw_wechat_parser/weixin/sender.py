from __future__ import annotations

import logging
from pathlib import Path

from claw_wechat_parser.domain.message import MediaAttachment, OutboundMessage
from claw_wechat_parser.weixin.api import WeixinApi
from claw_wechat_parser.weixin.cdn import UploadedMedia, WeixinCdnClient
from claw_wechat_parser.weixin.types import (
    MessageItemType,
    MessageState,
    MessageType,
    UploadMediaType,
)

log = logging.getLogger(__name__)


class WeixinSender:
    def __init__(self, api: WeixinApi, cdn_base_url: str):
        self.api = api
        self.cdn = WeixinCdnClient(api, cdn_base_url)

    @staticmethod
    def _text_item(text: str) -> dict:
        return {"type": int(MessageItemType.TEXT), "text_item": {"text": text}}

    @staticmethod
    def _media_item(uploaded: UploadedMedia) -> dict:
        media_ref = {
            "encrypt_query_param": uploaded.download_param,
            "aes_key": uploaded.aeskey_base64,
            "encrypt_type": 1,
        }
        if uploaded.media_type == UploadMediaType.IMAGE:
            return {
                "type": int(MessageItemType.IMAGE),
                "image_item": {"media": media_ref, "mid_size": uploaded.cipher_size},
            }
        if uploaded.media_type == UploadMediaType.VIDEO:
            return {
                "type": int(MessageItemType.VIDEO),
                "video_item": {"media": media_ref, "video_size": uploaded.cipher_size},
            }
        return {
            "type": int(MessageItemType.FILE),
            "file_item": {
                "media": media_ref,
                "file_name": uploaded.file_name,
                "len": str(uploaded.raw_size),
            },
        }

    async def send_items(
        self,
        to_user_id: str,
        items: list[dict],
        *,
        context_token: str | None = None,
    ) -> None:
        # 与 openclaw-weixin 保持一致：每次只发一个 item，降低协议兼容风险。
        for item in items:
            msg = {
                "from_user_id": "",
                "to_user_id": to_user_id,
                "message_type": int(MessageType.BOT),
                "message_state": int(MessageState.FINISH),
                "item_list": [item],
                "context_token": context_token,
            }
            await self.api.send_message(msg)

    async def send_text(self, to_user_id: str, text: str, *, context_token: str | None = None) -> None:
        if not text:
            return
        await self.send_items(to_user_id, [self._text_item(text)], context_token=context_token)

    async def send_media(
        self,
        to_user_id: str,
        media: MediaAttachment | Path,
        *,
        text: str = "",
        context_token: str | None = None,
    ) -> None:
        path = media.path if isinstance(media, MediaAttachment) else Path(media)
        mime_type = media.mime_type if isinstance(media, MediaAttachment) else None
        items = []
        if text:
            items.append(self._text_item(text))
        uploaded = await self.cdn.upload(path, to_user_id, mime_type=mime_type)
        items.append(self._media_item(uploaded))
        await self.send_items(to_user_id, items, context_token=context_token)

    async def send_outbound(self, outbound: OutboundMessage) -> None:
        if outbound.text and not outbound.media:
            await self.send_text(outbound.to_user_id, outbound.text, context_token=outbound.context_token)
            return
        if outbound.text:
            await self.send_text(outbound.to_user_id, outbound.text, context_token=outbound.context_token)
        for media in outbound.media:
            await self.send_media(outbound.to_user_id, media, context_token=outbound.context_token)
