from __future__ import annotations

import asyncio
import hashlib
import mimetypes
import shutil
from pathlib import Path

import httpx

from claw_wechat_parser.config import Settings
from claw_wechat_parser.domain.message import MediaAttachment
from claw_wechat_parser.domain.parse_result import MediaContent


class DownloadService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.max_bytes = settings.max_media_size_mb * 1024 * 1024

    async def download(self, content: MediaContent) -> MediaAttachment | None:
        if content.path:
            return MediaAttachment(
                path=content.path,
                kind="file" if content.kind == "file" else content.kind,  # type: ignore[arg-type]
                name=content.name,
                mime_type=content.mime_type,
            )
        if not content.url:
            return None

        if content.kind == "video" and content.audio_url:
            path = await self._download_and_merge(content)
        else:
            path = await self._download_url(
                content.url,
                headers=content.headers,
                kind=content.kind,
                mime_type=content.mime_type,
            )
        return MediaAttachment(
            path=path,
            kind="file" if content.kind == "file" else content.kind,  # type: ignore[arg-type]
            name=content.name,
            mime_type=content.mime_type,
        )

    def _suffix_for(self, url: str, kind: str, mime_type: str | None) -> str:
        suffix = Path(url.split("?", 1)[0]).suffix
        if suffix and len(suffix) <= 8:
            return suffix
        if mime_type and (guessed := mimetypes.guess_extension(mime_type)):
            return guessed
        return {"image": ".jpg", "video": ".mp4", "audio": ".mp3"}.get(kind, ".bin")

    async def _download_url(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        kind: str = "file",
        mime_type: str | None = None,
        suffix: str | None = None,
        digest_extra: str = "",
    ) -> Path:
        suffix = suffix or self._suffix_for(url, kind, mime_type)
        digest = hashlib.sha256(f"{url}|{digest_extra}".encode()).hexdigest()[:24]
        path = self.settings.media_dir / f"{digest}{suffix}"
        exists_and_nonzero = await asyncio.to_thread(lambda: path.exists() and path.stat().st_size > 0)
        if exists_and_nonzero:
            return path

        req_headers = {"User-Agent": "Mozilla/5.0", **(headers or {})}
        async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
            async with client.stream("GET", url, headers=req_headers) as resp:
                resp.raise_for_status()
                size = 0
                with path.open("wb") as f:
                    async for chunk in resp.aiter_bytes(1024 * 512):
                        size += len(chunk)
                        if size > self.max_bytes:
                            path.unlink(missing_ok=True)
                            raise RuntimeError(
                                f"媒体超过大小限制：{self.settings.max_media_size_mb} MB"
                            )
                        f.write(chunk)
        return path

    async def _download_and_merge(self, content: MediaContent) -> Path:
        if not content.url or not content.audio_url:
            raise RuntimeError("缺少视频或音频下载地址")
        digest = hashlib.sha256(f"{content.url}|{content.audio_url}".encode()).hexdigest()[:24]
        output = self.settings.media_dir / f"{digest}.mp4"
        exists_and_nonzero = await asyncio.to_thread(
            lambda: output.exists() and output.stat().st_size > 0
        )
        if exists_and_nonzero:
            return output

        video_path = await self._download_url(
            content.url,
            headers=content.headers,
            kind="video",
            suffix=".video.mp4",
            digest_extra="video",
        )
        audio_path = await self._download_url(
            content.audio_url,
            headers=content.headers,
            kind="audio",
            suffix=".audio.m4a",
            digest_extra="audio",
        )
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise RuntimeError("需要 ffmpeg 合并音视频，但系统未找到 ffmpeg")
        proc = await asyncio.create_subprocess_exec(
            ffmpeg,
            "-y",
            "-i",
            str(video_path),
            "-i",
            str(audio_path),
            "-c",
            "copy",
            str(output),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            output.unlink(missing_ok=True)
            raise RuntimeError(f"ffmpeg 合并失败：{stderr.decode(errors='ignore')[-500:]}")
        return output
