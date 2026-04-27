from __future__ import annotations

from claw_wechat_parser.domain.message import InboundMessage
from claw_wechat_parser.weixin.types import MessageItemType


def text_from_item_list(items: list[dict] | None) -> str:
    if not items:
        return ""
    for item in items:
        if item.get("type") == int(MessageItemType.TEXT):
            text = ((item.get("text_item") or {}).get("text"))
            if text:
                return str(text)
        if item.get("type") == int(MessageItemType.VOICE):
            text = ((item.get("voice_item") or {}).get("text"))
            if text:
                return str(text)
    return ""


def weixin_message_to_inbound(msg: dict, account_id: str) -> InboundMessage:
    from_user_id = str(msg.get("from_user_id") or "")
    return InboundMessage(
        account_id=account_id,
        from_user_id=from_user_id,
        to_user_id=str(msg.get("to_user_id") or from_user_id),
        text=text_from_item_list(msg.get("item_list")),
        message_id=str(msg.get("message_id") or msg.get("client_id") or ""),
        timestamp_ms=msg.get("create_time_ms"),
        context_token=msg.get("context_token"),
        raw=msg,
    )
