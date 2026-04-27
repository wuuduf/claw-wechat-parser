# Ensure platform parsers are registered on package import.
from . import platforms as platforms
from .base import BaseParser, handle
from .router import ParserRouter

__all__ = ["BaseParser", "ParserRouter", "handle", "platforms"]
