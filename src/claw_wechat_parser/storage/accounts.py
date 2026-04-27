from __future__ import annotations

import json
import os
from pathlib import Path

from claw_wechat_parser.domain.account import WeixinAccount


def normalize_account_id(raw: str) -> str:
    return raw.replace("@", "-").replace(".", "-").replace(":", "-").replace("/", "-")


class AccountStore:
    def __init__(self, accounts_dir: Path):
        self.accounts_dir = accounts_dir
        self.accounts_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, account_id: str) -> Path:
        return self.accounts_dir / f"{normalize_account_id(account_id)}.json"

    def save(self, account: WeixinAccount) -> Path:
        account.account_id = normalize_account_id(account.account_id)
        path = self._path(account.account_id)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(account.to_json(), ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)
        try:
            path.chmod(0o600)
        except OSError:
            pass
        return path

    def load(self, account_id: str) -> WeixinAccount | None:
        path = self._path(account_id)
        if not path.exists():
            return None
        return WeixinAccount.from_json(json.loads(path.read_text(encoding="utf-8")))

    def list(self) -> list[WeixinAccount]:
        accounts: list[WeixinAccount] = []
        for path in sorted(self.accounts_dir.glob("*.json")):
            try:
                accounts.append(WeixinAccount.from_json(json.loads(path.read_text(encoding="utf-8"))))
            except Exception:
                continue
        return accounts

    def remove(self, account_id: str) -> bool:
        path = self._path(account_id)
        if path.exists():
            path.unlink()
            return True
        return False
