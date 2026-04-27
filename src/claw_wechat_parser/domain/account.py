from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass(slots=True)
class WeixinAccount:
    account_id: str
    token: str
    base_url: str
    cdn_base_url: str
    user_id: str | None = None
    name: str | None = None
    saved_at: str | None = None
    enabled: bool = True

    def to_json(self) -> dict[str, Any]:
        data = asdict(self)
        data["saved_at"] = self.saved_at or datetime.now(UTC).isoformat()
        return data

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> WeixinAccount:
        return cls(
            account_id=str(data["account_id"]),
            token=str(data["token"]),
            base_url=str(data["base_url"]),
            cdn_base_url=str(data.get("cdn_base_url") or "https://novac2c.cdn.weixin.qq.com/c2c"),
            user_id=data.get("user_id"),
            name=data.get("name"),
            saved_at=data.get("saved_at"),
            enabled=bool(data.get("enabled", True)),
        )
