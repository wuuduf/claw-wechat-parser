from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import yt_dlp

from claw_wechat_parser.config import Settings

log = logging.getLogger(__name__)


def cookie_header_to_netscape_file(
    settings: Settings,
    *,
    name: str,
    domain: str,
    cookie_header: str,
) -> Path | None:
    cookie_header = cookie_header.strip()
    if not cookie_header:
        return None
    cookie_dir = settings.state_dir / "cookies"
    cookie_dir.mkdir(parents=True, exist_ok=True)
    path = cookie_dir / f"{name}.cookies.txt"
    lines = ["# Netscape HTTP Cookie File"]
    for part in cookie_header.split(";"):
        if "=" not in part:
            continue
        key, value = part.strip().split("=", 1)
        if not key:
            continue
        # domain, include_subdomains, path, secure, expiry, name, value
        lines.append(f".{domain}\tTRUE\t/\tTRUE\t0\t{key}\t{value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


async def ytdlp_extract_info(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    cookie_header: str = "",
    cookie_file: Path | None = None,
    max_attempts: int = 2,
) -> dict[str, Any]:
    opts: dict[str, Any] = {
        "quiet": True,
        "skip_download": True,
        "noplaylist": False,
        "extract_flat": False,
    }
    if headers:
        opts["http_headers"] = dict(headers)
    if cookie_header:
        opts.setdefault("http_headers", {})["Cookie"] = cookie_header
    if cookie_file and await asyncio.to_thread(cookie_file.exists):
        opts["cookiefile"] = str(cookie_file)

    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:  # type: ignore[no-untyped-call]
                raw = await asyncio.to_thread(ydl.extract_info, url, False)
            if isinstance(raw, dict):
                return raw
            raise RuntimeError("yt-dlp returned non-dict info")
        except Exception as exc:  # pragma: no cover - network/extractor dependent
            last_exc = exc
            log.warning("yt-dlp extract failed (%s/%s): %s", attempt, max_attempts, exc)
            if attempt < max_attempts:
                await asyncio.sleep(min(2 * attempt, 5))
    raise RuntimeError(f"yt-dlp 解析失败: {last_exc}")


def iter_entries(info: dict[str, Any]) -> list[dict[str, Any]]:
    if info.get("_type") == "playlist":
        entries = info.get("entries") or []
        return [entry for entry in entries if isinstance(entry, dict)]
    return [info]


def codec_is_none(codec: Any) -> bool:
    return codec in (None, "none", "audio only", "video only")


def format_url(fmt: dict[str, Any]) -> str | None:
    url = fmt.get("url")
    if not isinstance(url, str) or not url:
        return None
    protocol = fmt.get("protocol")
    if isinstance(protocol, str) and not protocol.startswith("http"):
        return None
    return url


def best_video_format(formats: list[dict[str, Any]], *, max_height: int = 720) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    for fmt in formats:
        if not isinstance(fmt, dict) or not format_url(fmt):
            continue
        if codec_is_none(fmt.get("vcodec")):
            continue
        if not codec_is_none(fmt.get("acodec")):
            continue
        height = fmt.get("height")
        if isinstance(height, int) and height > max_height:
            continue
        candidates.append(fmt)
    if not candidates:
        return None

    def sort_key(fmt: dict[str, Any]) -> tuple[int, int, int]:
        vcodec = fmt.get("vcodec") or ""
        prefer_avc = 1 if isinstance(vcodec, str) and ("avc" in vcodec or "h264" in vcodec) else 0
        height = fmt.get("height")
        tbr = fmt.get("tbr")
        return (
            prefer_avc,
            int(height) if isinstance(height, int) else 0,
            int(tbr) if isinstance(tbr, int | float) else 0,
        )

    return max(candidates, key=sort_key)


def best_audio_format(formats: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    for fmt in formats:
        if not isinstance(fmt, dict) or not format_url(fmt):
            continue
        if codec_is_none(fmt.get("acodec")):
            continue
        if not codec_is_none(fmt.get("vcodec")):
            continue
        candidates.append(fmt)
    if not candidates:
        return None

    def sort_key(fmt: dict[str, Any]) -> tuple[int, int]:
        abr = fmt.get("abr")
        tbr = fmt.get("tbr")
        return (
            int(abr) if isinstance(abr, int | float) else 0,
            int(tbr) if isinstance(tbr, int | float) else 0,
        )

    return max(candidates, key=sort_key)


def best_av_format(formats: list[dict[str, Any]], *, max_height: int = 720) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    for fmt in formats:
        if not isinstance(fmt, dict) or not format_url(fmt):
            continue
        if codec_is_none(fmt.get("vcodec")) or codec_is_none(fmt.get("acodec")):
            continue
        height = fmt.get("height")
        if isinstance(height, int) and height > max_height:
            continue
        candidates.append(fmt)
    if not candidates:
        return None

    def sort_key(fmt: dict[str, Any]) -> tuple[int, int, int]:
        vcodec = fmt.get("vcodec") or ""
        prefer_avc = 1 if isinstance(vcodec, str) and ("avc" in vcodec or "h264" in vcodec) else 0
        height = fmt.get("height")
        tbr = fmt.get("tbr")
        return (
            prefer_avc,
            int(height) if isinstance(height, int) else 0,
            int(tbr) if isinstance(tbr, int | float) else 0,
        )

    return max(candidates, key=sort_key)


def select_media_urls(info: dict[str, Any], *, max_height: int = 720) -> tuple[str | None, str | None]:
    formats = info.get("formats")
    if isinstance(formats, list) and formats:
        video_fmt = best_video_format(formats, max_height=max_height)
        audio_fmt = best_audio_format(formats)
        if video_fmt and audio_fmt:
            return format_url(video_fmt), format_url(audio_fmt)
        combined = best_av_format(formats, max_height=max_height)
        if combined:
            return format_url(combined), None
    url = info.get("url")
    if isinstance(url, str) and url:
        return url, None
    return None, None
