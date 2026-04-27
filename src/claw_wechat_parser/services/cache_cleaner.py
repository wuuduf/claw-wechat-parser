from __future__ import annotations

from claw_wechat_parser.config import Settings


class CacheCleaner:
    def __init__(self, settings: Settings):
        self.settings = settings

    def clean_if_needed(self) -> int:
        max_bytes = int(self.settings.cache_max_gb * 1024 * 1024 * 1024)
        files = [p for p in self.settings.cache_dir.rglob("*") if p.is_file()]
        total = sum(p.stat().st_size for p in files)
        if total <= max_bytes:
            return 0
        removed = 0
        for path in sorted(files, key=lambda p: p.stat().st_mtime):
            if total <= max_bytes:
                break
            size = path.stat().st_size
            path.unlink(missing_ok=True)
            total -= size
            removed += 1
        return removed
