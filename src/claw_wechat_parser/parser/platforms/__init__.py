# ruff: noqa: I001
# Import modules for BaseParser subclass registration.
from .bilibili import BilibiliParser
from .douyin import DouyinParser
from .instagram import InstagramParser
from .twitter import TwitterParser
from .xhs import XHSParser
from .youtube import YouTubeParser
from .generic import GenericUrlParser

__all__ = [
    "BilibiliParser",
    "DouyinParser",
    "GenericUrlParser",
    "InstagramParser",
    "TwitterParser",
    "XHSParser",
    "YouTubeParser",
]
