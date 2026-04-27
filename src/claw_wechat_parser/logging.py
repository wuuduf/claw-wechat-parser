from __future__ import annotations

import logging
import re
from typing import Any

TOKEN_PAT = re.compile(r"(Bearer\s+)[A-Za-z0-9._~+/=-]+", re.I)


def redact(value: Any) -> str:
    text = str(value)
    text = TOKEN_PAT.sub(r"\1***", text)
    for key in ("bot_token", "token", "Authorization", "aes_key", "aeskey"):
        text = re.sub(rf'("?{key}"?\s*[:=]\s*")([^"\s]+)(")', r"\1***\3", text, flags=re.I)
    return text


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
