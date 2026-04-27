from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import qrcode

from claw_wechat_parser.config import Settings
from claw_wechat_parser.domain.account import WeixinAccount
from claw_wechat_parser.storage.accounts import normalize_account_id
from claw_wechat_parser.weixin.api import WeixinApi

log = logging.getLogger(__name__)


@dataclass(slots=True)
class LoginResult:
    connected: bool
    message: str
    account: WeixinAccount | None = None
    qrcode_url: str | None = None


def render_qr_ascii(data: str) -> str:
    qr = qrcode.QRCode(border=1)
    qr.add_data(data)
    qr.make(fit=True)
    matrix = qr.get_matrix()
    lines: list[str] = []
    for y in range(0, len(matrix), 2):
        row = []
        upper = matrix[y]
        lower = matrix[y + 1] if y + 1 < len(matrix) else [False] * len(upper)
        for up, low in zip(upper, lower, strict=False):
            if up and low:
                row.append("█")
            elif up and not low:
                row.append("▀")
            elif not up and low:
                row.append("▄")
            else:
                row.append(" ")
        lines.append("".join(row))
    return "\n".join(lines)


class WeixinAuthService:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def login_with_qr(self, *, timeout_s: float | None = None, verbose: bool = False) -> LoginResult:
        api = WeixinApi(self.settings)
        try:
            qr_resp = await api.fetch_qrcode(self.settings.ilink_bot_type)
            qrcode_id = str(qr_resp.get("qrcode") or "")
            qrcode_url = str(qr_resp.get("qrcode_img_content") or "")
            if not qrcode_id or not qrcode_url:
                return LoginResult(False, f"获取二维码失败：{qr_resp}")

            print("\n请使用微信扫描二维码并在手机端确认授权：\n", flush=True)
            print(render_qr_ascii(qrcode_url), flush=True)
            print("\n如果二维码显示异常，请打开以下链接扫码：", flush=True)
            print(qrcode_url, flush=True)
            print(flush=True)

            deadline = asyncio.get_event_loop().time() + (timeout_s or self.settings.login_timeout_s)
            current_base_url = "https://ilinkai.weixin.qq.com"
            scanned_printed = False
            while asyncio.get_event_loop().time() < deadline:
                remaining = max(0.1, deadline - asyncio.get_event_loop().time())
                poll_timeout = min(self.settings.long_poll_timeout_s, remaining)
                status_api = WeixinApi(self.settings, base_url=current_base_url)
                try:
                    status = await status_api.poll_qrcode_status(qrcode_id, timeout_s=poll_timeout)
                except Exception as exc:
                    if verbose:
                        log.warning("二维码状态轮询失败，将继续重试：%s", exc)
                    await asyncio.sleep(1)
                    continue
                finally:
                    await status_api.close()

                state = status.get("status")
                if state == "wait":
                    if verbose:
                        print(".", end="", flush=True)
                elif state == "scaned":
                    if not scanned_printed:
                        print("\n已扫码，请在微信继续确认...\n")
                        scanned_printed = True
                elif state == "scaned_but_redirect":
                    redirect_host = status.get("redirect_host")
                    if redirect_host:
                        current_base_url = f"https://{redirect_host}"
                        log.info("扫码状态重定向到 %s", current_base_url)
                elif state == "expired":
                    return LoginResult(False, "二维码已过期，请重新执行登录。", qrcode_url=qrcode_url)
                elif state == "confirmed":
                    raw_account_id = str(status.get("ilink_bot_id") or "")
                    token = str(status.get("bot_token") or "")
                    if not raw_account_id or not token:
                        return LoginResult(False, f"登录失败：服务端未返回 account/token：{status}")
                    account = WeixinAccount(
                        account_id=normalize_account_id(raw_account_id),
                        token=token,
                        base_url=str(status.get("baseurl") or current_base_url),
                        cdn_base_url=self.settings.cdn_base_url,
                        user_id=status.get("ilink_user_id"),
                    )
                    return LoginResult(True, "微信扫码登录成功", account=account, qrcode_url=qrcode_url)
                await asyncio.sleep(1)
            return LoginResult(False, "登录超时，请重试。", qrcode_url=qrcode_url)
        finally:
            await api.close()
