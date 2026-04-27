from __future__ import annotations

from pathlib import Path

from claw_wechat_parser.storage.accounts import normalize_account_id


class SyncBufStore:
    def __init__(self, state_dir: Path):
        self.dir = state_dir / "sync"
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, account_id: str) -> Path:
        return self.dir / f"{normalize_account_id(account_id)}.buf"

    def load(self, account_id: str) -> str:
        path = self._path(account_id)
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def save(self, account_id: str, buf: str) -> None:
        self._path(account_id).write_text(buf or "", encoding="utf-8")
