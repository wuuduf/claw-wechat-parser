from typing import Any

from msgspec import Struct, convert


class AuthorInfo(Struct):
    name: str
    face: str
    mid: int
    pub_time: str
    pub_ts: int


class VideoArchive(Struct):
    aid: str
    bvid: str
    title: str
    desc: str
    cover: str


class OpusImage(Struct):
    url: str


class OpusSummary(Struct):
    text: str


class OpusContent(Struct):
    jump_url: str
    pics: list[OpusImage]
    summary: OpusSummary
    title: str | None = None


class DynamicMajor(Struct):
    type: str
    archive: VideoArchive | None = None
    opus: OpusContent | None = None

    @property
    def title(self) -> str | None:
        if self.type == "MAJOR_TYPE_ARCHIVE" and self.archive:
            return self.archive.title
        if self.type == "MAJOR_TYPE_OPUS" and self.opus:
            return self.opus.title
        return None

    @property
    def text(self) -> str | None:
        if self.type == "MAJOR_TYPE_ARCHIVE" and self.archive:
            return self.archive.desc
        if self.type == "MAJOR_TYPE_OPUS" and self.opus:
            return self.opus.summary.text
        return None

    @property
    def image_urls(self) -> list[str]:
        if self.type == "MAJOR_TYPE_OPUS" and self.opus:
            return [pic.url for pic in self.opus.pics]
        if self.type == "MAJOR_TYPE_ARCHIVE" and self.archive and self.archive.cover:
            return [self.archive.cover]
        return []


class DynamicModule(Struct):
    module_author: AuthorInfo
    module_dynamic: dict[str, Any] | None = None
    module_stat: dict[str, Any] | None = None

    @property
    def major_info(self) -> dict[str, Any] | None:
        return self.module_dynamic.get("major") if self.module_dynamic else None


class DynamicInfo(Struct):
    id_str: str
    type: str
    visible: bool
    modules: DynamicModule
    basic: dict[str, Any] | None = None

    @property
    def name(self) -> str:
        return self.modules.module_author.name

    @property
    def avatar(self) -> str:
        return self.modules.module_author.face

    @property
    def timestamp(self) -> int:
        return self.modules.module_author.pub_ts

    @property
    def _major(self) -> DynamicMajor | None:
        return convert(self.modules.major_info, DynamicMajor) if self.modules.major_info else None

    @property
    def title(self) -> str | None:
        return self._major.title if self._major else None

    @property
    def text(self) -> str | None:
        return self._major.text if self._major else None

    @property
    def image_urls(self) -> list[str]:
        return self._major.image_urls if self._major else []


class DynamicData(Struct):
    item: DynamicInfo
