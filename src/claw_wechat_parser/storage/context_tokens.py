from __future__ import annotations

import json
from pathlib import Path

from claw_wechat_parser.storage.accounts import normalize_account_id


class ContextTokenStore:
    def __init__(self, state_dir: Path):
        self.dir = state_dir / "context_tokens"
        self.dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, dict[str, str]] = {}

    def _path(self, account_id: str) -> Path:
        return self.dir / f"{normalize_account_id(account_id)}.json"

    def _load_account(self, account_id: str) -> dict[str, str]:
        account_id = normalize_account_id(account_id)
        if account_id in self._cache:
            return self._cache[account_id]
        path = self._path(account_id)
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self._cache[account_id] = {str(k): str(v) for k, v in data.items()}
                    return self._cache[account_id]
            except Exception:
                pass
        self._cache[account_id] = {}
        return self._cache[account_id]

    def get(self, account_id: str, user_id: str) -> str | None:
        return self._load_account(account_id).get(user_id)

    def set(self, account_id: str, user_id: str, token: str) -> None:
        account_id = normalize_account_id(account_id)
        data = self._load_account(account_id)
        data[user_id] = token
        self._path(account_id).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
