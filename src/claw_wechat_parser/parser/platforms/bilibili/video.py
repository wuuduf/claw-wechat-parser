from dataclasses import dataclass

from msgspec import Struct

from .common import Upper


class Stats(Struct):
    view: int
    danmaku: int
    reply: int
    favorite: int
    coin: int
    share: int
    like: int


class Page(Struct):
    part: str
    ctime: int
    duration: int
    first_frame: str | None = None


@dataclass(frozen=True, slots=True)
class PageInfo:
    index: int
    title: str
    duration: int
    timestamp: int
    cover: str | None = None


class VideoInfo(Struct):
    bvid: str
    title: str
    desc: str
    duration: int
    owner: Upper
    stat: Stats
    pubdate: int
    ctime: int
    pic: str | None = None
    pages: list[Page] | None = None

    @property
    def formatted_stats_info(self) -> str:
        stats_mapping = [
            ("👍", self.stat.like),
            ("🪙", self.stat.coin),
            ("⭐", self.stat.favorite),
            ("↩️", self.stat.share),
            ("💬", self.stat.reply),
            ("👀", self.stat.view),
            ("💭", self.stat.danmaku),
        ]
        parts = []
        for label, value in stats_mapping:
            formatted = f"{value / 10000:.1f}万" if value > 10000 else str(value)
            parts.append(f"{label} {formatted}")
        return " ".join(parts)

    def extract_info_with_page(self, page_num: int = 1) -> PageInfo:
        page_idx = page_num - 1
        title = self.title
        duration = self.duration
        cover = self.pic
        timestamp = self.pubdate
        if self.pages and len(self.pages) > 1:
            page_idx = page_idx % len(self.pages)
            page = self.pages[page_idx]
            title += f" | 分集 - {page.part}"
            duration = page.duration
            cover = page.first_frame
            timestamp = page.ctime
        return PageInfo(page_idx, title, duration, timestamp, cover)


class ModelResult(Struct):
    summary: str


class AIConclusion(Struct):
    model_result: ModelResult | None = None

    @property
    def summary(self) -> str:
        if self.model_result and self.model_result.summary:
            return f"AI总结: {self.model_result.summary}"
        return "该视频暂不支持AI总结"
