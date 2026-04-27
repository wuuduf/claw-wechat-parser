from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import mimetypes
import os
from dataclasses import dataclass
from pathlib import Path

import httpx
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7

from claw_wechat_parser.weixin.api import WeixinApi
from claw_wechat_parser.weixin.types import UploadMediaType

log = logging.getLogger(__name__)


@dataclass(slots=True)
class UploadedMedia:
    filekey: str
    aeskey_hex: str
    download_param: str
    raw_size: int
    cipher_size: int
    media_type: UploadMediaType
    file_name: str
    mime_type: str

    @property
    def aeskey_base64(self) -> str:
        return base64.b64encode(bytes.fromhex(self.aeskey_hex)).decode()


def aes_ecb_encrypt_pkcs7(data: bytes, key: bytes) -> bytes:
    padder = PKCS7(128).padder()
    padded = padder.update(data) + padder.finalize()
    encryptor = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
    return encryptor.update(padded) + encryptor.finalize()


def guess_upload_media_type(path: Path, explicit: str | None = None) -> tuple[UploadMediaType, str]:
    mime = explicit or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    if mime.startswith("image/"):
        return UploadMediaType.IMAGE, mime
    if mime.startswith("video/"):
        return UploadMediaType.VIDEO, mime
    return UploadMediaType.FILE, mime


def build_cdn_upload_url(cdn_base_url: str, upload_param: str, filekey: str) -> str:
    return f"{cdn_base_url.rstrip('/')}/upload/{filekey}?{upload_param.lstrip('?')}"


class WeixinCdnClient:
    def __init__(
        self,
        api: WeixinApi,
        cdn_base_url: str,
        *,
        upload_timeout_s: float = 180,
        upload_retries: int = 3,
    ):
        self.api = api
        self.cdn_base_url = cdn_base_url
        self.upload_timeout_s = upload_timeout_s
        self.upload_retries = max(1, upload_retries)

    async def upload(
        self, path: Path, to_user_id: str, *, mime_type: str | None = None
    ) -> UploadedMedia:
        path = await asyncio.to_thread(lambda: path.expanduser().resolve())
        plaintext = await asyncio.to_thread(path.read_bytes)
        raw_size = len(plaintext)
        raw_md5 = hashlib.md5(plaintext).hexdigest()
        filekey = os.urandom(16).hex()
        aeskey = os.urandom(16)
        ciphertext = aes_ecb_encrypt_pkcs7(plaintext, aeskey)
        media_type, mime = guess_upload_media_type(path, mime_type)

        resp = await self.api.get_upload_url(
            {
                "filekey": filekey,
                "media_type": int(media_type),
                "to_user_id": to_user_id,
                "rawsize": raw_size,
                "rawfilemd5": raw_md5,
                "filesize": len(ciphertext),
                "no_need_thumb": True,
                "aeskey": aeskey.hex(),
            }
        )
        upload_full_url = (resp.get("upload_full_url") or "").strip()
        upload_param = resp.get("upload_param")
        if upload_full_url:
            upload_url = upload_full_url
        elif upload_param:
            upload_url = build_cdn_upload_url(self.cdn_base_url, str(upload_param), filekey)
        else:
            raise RuntimeError(f"getuploadurl 未返回上传地址：{resp}")

        timeout = httpx.Timeout(
            self.upload_timeout_s,
            connect=min(30.0, self.upload_timeout_s),
            read=self.upload_timeout_s,
            write=self.upload_timeout_s,
            pool=min(30.0, self.upload_timeout_s),
        )
        last_exc: Exception | None = None
        log.info(
            "CDN 上传开始：file=%s raw=%.2fMB encrypted=%.2fMB type=%s retries=%s timeout=%ss",
            path.name,
            raw_size / 1024 / 1024,
            len(ciphertext) / 1024 / 1024,
            media_type.name,
            self.upload_retries,
            self.upload_timeout_s,
        )
        async with httpx.AsyncClient(timeout=timeout) as client:
            for attempt in range(1, self.upload_retries + 1):
                try:
                    upload_resp = await client.post(
                        upload_url,
                        content=ciphertext,
                        headers={"Content-Type": "application/octet-stream"},
                    )
                    upload_resp.raise_for_status()
                    download_param = upload_resp.headers.get("x-encrypted-param")
                    if not download_param:
                        raise RuntimeError("CDN 上传响应缺少 x-encrypted-param")
                    log.info("CDN 上传成功：file=%s attempt=%s", path.name, attempt)
                    break
                except (httpx.HTTPError, RuntimeError) as exc:
                    last_exc = exc
                    if attempt >= self.upload_retries:
                        raise RuntimeError(
                            f"CDN 上传失败：file={path.name} size={raw_size / 1024 / 1024:.2f}MB "
                            f"attempts={self.upload_retries} error={exc}"
                        ) from exc
                    delay = min(10, 2**attempt)
                    log.warning(
                        "CDN 上传失败，%ss 后重试：file=%s attempt=%s/%s error=%s",
                        delay,
                        path.name,
                        attempt,
                        self.upload_retries,
                        exc,
                    )
                    await asyncio.sleep(delay)
            else:
                raise RuntimeError(f"CDN 上传失败：{last_exc}")

        return UploadedMedia(
            filekey=filekey,
            aeskey_hex=aeskey.hex(),
            download_param=download_param,
            raw_size=raw_size,
            cipher_size=len(ciphertext),
            media_type=media_type,
            file_name=path.name,
            mime_type=mime,
        )
