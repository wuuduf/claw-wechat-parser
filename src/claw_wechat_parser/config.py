from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_API_BASE_URL = "https://ilinkai.weixin.qq.com"
DEFAULT_CDN_BASE_URL = "https://novac2c.cdn.weixin.qq.com/c2c"


def _default_state_dir() -> Path:
    return Path(os.environ.get("CLAW_PARSER_STATE_DIR", "~/.claw-wechat-parser")).expanduser()


@dataclass(slots=True)
class Settings:
    """Runtime settings loaded from environment and CLI overrides."""

    state_dir: Path = _default_state_dir()
    api_base_url: str = os.environ.get("CLAW_PARSER_API_BASE_URL", DEFAULT_API_BASE_URL)
    cdn_base_url: str = os.environ.get("CLAW_PARSER_CDN_BASE_URL", DEFAULT_CDN_BASE_URL)
    ilink_bot_type: str = os.environ.get("CLAW_PARSER_ILINK_BOT_TYPE", "3")
    channel_version: str = os.environ.get("CLAW_PARSER_CHANNEL_VERSION", "0.1.0")
    ilink_app_id: str = os.environ.get("CLAW_PARSER_ILINK_APP_ID", "bot")
    api_timeout_s: float = float(os.environ.get("CLAW_PARSER_API_TIMEOUT_S", "15"))
    long_poll_timeout_s: float = float(os.environ.get("CLAW_PARSER_LONG_POLL_TIMEOUT_S", "35"))
    login_timeout_s: float = float(os.environ.get("CLAW_PARSER_LOGIN_TIMEOUT_S", "480"))
    cdn_upload_timeout_s: float = float(os.environ.get("CLAW_PARSER_CDN_UPLOAD_TIMEOUT_S", "180"))
    cdn_upload_retries: int = int(os.environ.get("CLAW_PARSER_CDN_UPLOAD_RETRIES", "3"))
    max_media_size_mb: int = int(os.environ.get("CLAW_PARSER_MAX_MEDIA_SIZE_MB", "80"))
    max_media_duration_s: int = int(os.environ.get("CLAW_PARSER_MAX_MEDIA_DURATION_S", "900"))
    max_concurrent_downloads: int = int(os.environ.get("CLAW_PARSER_MAX_CONCURRENT_DOWNLOADS", "2"))
    debounce_seconds: int = int(os.environ.get("CLAW_PARSER_DEBOUNCE_SECONDS", "300"))
    cache_max_gb: float = float(os.environ.get("CLAW_PARSER_CACHE_MAX_GB", "5"))
    bilibili_video_quality: str = os.environ.get("CLAW_PARSER_BILIBILI_VIDEO_QUALITY", "_720P")
    bilibili_video_codecs: str = os.environ.get("CLAW_PARSER_BILIBILI_VIDEO_CODECS", "AVC")
    bilibili_cookie: str = os.environ.get("CLAW_PARSER_BILIBILI_COOKIE", "")
    douyin_cookie: str = os.environ.get("CLAW_PARSER_DOUYIN_COOKIE", "")
    xhs_cookie: str = os.environ.get("CLAW_PARSER_XHS_COOKIE", "")
    instagram_cookie: str = os.environ.get("CLAW_PARSER_INSTAGRAM_COOKIE", "")
    youtube_cookie: str = os.environ.get("CLAW_PARSER_YOUTUBE_COOKIE", "")
    twitter_cookie: str = os.environ.get("CLAW_PARSER_TWITTER_COOKIE", "")

    @property
    def accounts_dir(self) -> Path:
        return self.state_dir / "accounts"

    @property
    def cache_dir(self) -> Path:
        return self.state_dir / "cache"

    @property
    def media_dir(self) -> Path:
        return self.cache_dir / "media"

    @property
    def render_dir(self) -> Path:
        return self.cache_dir / "render"

    def ensure_dirs(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.accounts_dir.mkdir(parents=True, exist_ok=True)
        self.media_dir.mkdir(parents=True, exist_ok=True)
        self.render_dir.mkdir(parents=True, exist_ok=True)


def load_settings(state_dir: str | Path | None = None) -> Settings:
    settings = Settings()
    if state_dir is not None:
        settings.state_dir = Path(state_dir).expanduser().resolve()
    settings.ensure_dirs()
    return settings
