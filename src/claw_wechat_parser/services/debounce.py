from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass(slots=True)
class Debouncer:
    ttl_seconds: int
    _seen: dict[str, float] = field(default_factory=dict)

    def hit(self, scope: str, key: str) -> bool:
        if self.ttl_seconds <= 0:
            return False
        now = time.time()
        self._gc(now)
        compound = f"{scope}:{key}"
        if compound in self._seen and now - self._seen[compound] < self.ttl_seconds:
            return True
        self._seen[compound] = now
        return False

    def _gc(self, now: float) -> None:
        expired = [k for k, ts in self._seen.items() if now - ts >= self.ttl_seconds]
        for key in expired:
            self._seen.pop(key, None)
