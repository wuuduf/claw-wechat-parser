from __future__ import annotations

import asyncio
import logging

from claw_wechat_parser.config import Settings
from claw_wechat_parser.domain.account import WeixinAccount
from claw_wechat_parser.services.parse_service import ParseService
from claw_wechat_parser.storage.context_tokens import ContextTokenStore
from claw_wechat_parser.storage.sync_buf import SyncBufStore
from claw_wechat_parser.weixin.api import WeixinApi
from claw_wechat_parser.weixin.inbound import weixin_message_to_inbound
from claw_wechat_parser.weixin.sender import WeixinSender

log = logging.getLogger(__name__)

SESSION_EXPIRED_ERRCODE = -14


class WeixinPoller:
    def __init__(self, settings: Settings, account: WeixinAccount):
        self.settings = settings
        self.account = account
        self.sync_store = SyncBufStore(settings.state_dir)
        self.token_store = ContextTokenStore(settings.state_dir)
        self.parse_service = ParseService(settings)
        self.api = WeixinApi(settings, base_url=account.base_url, token=account.token)
        self.sender = WeixinSender(self.api, account.cdn_base_url, settings)
        self._stop = asyncio.Event()

    async def close(self) -> None:
        self._stop.set()
        await self.parse_service.close()
        await self.api.close()

    async def run_forever(self) -> None:
        account_id = self.account.account_id
        get_updates_buf = self.sync_store.load(account_id)
        log.info("微信轮询启动：account=%s base=%s", account_id, self.account.base_url)
        consecutive_errors = 0
        while not self._stop.is_set():
            try:
                resp = await self.api.get_updates(get_updates_buf)
                ret = resp.get("ret", 0)
                errcode = resp.get("errcode", 0)
                if ret not in (0, None) or errcode not in (0, None):
                    if ret == SESSION_EXPIRED_ERRCODE or errcode == SESSION_EXPIRED_ERRCODE:
                        log.error("微信会话过期，请重新扫码登录：account=%s", account_id)
                        await asyncio.sleep(300)
                        continue
                    raise RuntimeError(f"getupdates failed: ret={ret} errcode={errcode} errmsg={resp.get('errmsg')}")

                if resp.get("get_updates_buf"):
                    get_updates_buf = str(resp["get_updates_buf"])
                    self.sync_store.save(account_id, get_updates_buf)

                for raw_msg in resp.get("msgs") or []:
                    inbound = weixin_message_to_inbound(raw_msg, account_id)
                    if inbound.context_token and inbound.from_user_id:
                        self.token_store.set(account_id, inbound.from_user_id, inbound.context_token)
                    log.info("收到微信消息：from=%s text=%r", inbound.from_user_id, inbound.text[:80])
                    outbound = await self.parse_service.parse_message(inbound)
                    if outbound is None:
                        continue
                    await self.sender.send_outbound(outbound)
                consecutive_errors = 0
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                consecutive_errors += 1
                delay = min(30, 2 * consecutive_errors)
                log.exception("微信轮询错误，将在 %ss 后重试：%s", delay, exc)
                await asyncio.sleep(delay)
