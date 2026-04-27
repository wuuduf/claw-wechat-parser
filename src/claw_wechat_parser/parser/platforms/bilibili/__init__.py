from __future__ import annotations

import logging
from re import Match
from typing import ClassVar

from bilibili_api import request_settings, select_client
from bilibili_api.opus import Opus
from bilibili_api.video import Video, VideoCodecs, VideoQuality
from msgspec import convert

from claw_wechat_parser.domain.parse_result import MediaContent, Platform
from claw_wechat_parser.parser.base import BaseParser, DownloadException, ParseException, handle

from .login import BilibiliLogin

log = logging.getLogger(__name__)

try:
    select_client("curl_cffi")
    request_settings.set("impersonate", "chrome131")
except Exception as exc:  # pragma: no cover - depends on optional runtime backend
    log.debug("bilibili_api curl_cffi backend setup skipped: %s", exc)


class BilibiliParser(BaseParser):
    platform: ClassVar[Platform] = Platform(name="bilibili", display_name="B站")

    def __init__(self, settings):
        super().__init__(settings)
        self.headers.update(
            {
                "Referer": "https://www.bilibili.com/",
                "Origin": "https://www.bilibili.com",
            }
        )
        self.video_quality = getattr(
            VideoQuality,
            str(settings.bilibili_video_quality).upper(),
            VideoQuality._720P,
        )
        self.video_codecs = getattr(
            VideoCodecs,
            str(settings.bilibili_video_codecs).upper(),
            VideoCodecs.AVC,
        )
        self.login = BilibiliLogin(settings)

    @handle("b23.tv", r"b23\.tv/[A-Za-z\d\._?%&+\-=/#]+")
    @handle("bili2233", r"bili2233\.cn/[A-Za-z\d\._?%&+\-=/#]+")
    async def _parse_short_link(self, searched: Match[str]):
        return await self.parse_with_redirect(f"https://{searched.group(0)}")

    @handle("BV", r"^(?P<bvid>BV[0-9a-zA-Z]{10})(?:\s)?(?P<page_num>\d{1,3})?$")
    @handle(
        "bilibili.com/video/BV",
        r"bilibili\.com(?:/video)?/(?P<bvid>BV[0-9a-zA-Z]{10})(?:\?p=(?P<page_num>\d{1,3}))?",
    )
    async def _parse_bv(self, searched: Match[str]):
        bvid = str(searched.group("bvid"))
        page_num = int(searched.group("page_num") or 1)
        return await self.parse_video(bvid=bvid, page_num=page_num)

    @handle("bm", r"^bm(?P<bvid>BV[0-9a-zA-Z]{10})(?:\s(?P<page_num>\d{1,3}))?$")
    async def _parse_bv_audio(self, searched: Match[str]):
        bvid = searched.group("bvid")
        page = int(searched.group("page_num") or 1)
        _v_url, a_url = await self.extract_download_urls(bvid=bvid, page_index=page - 1)
        if not a_url:
            raise ParseException("未找到音频链接")
        return self.result(
            title=f"BiliBili_audio_{bvid}",
            contents=[self.create_audio_content(a_url, headers=self.headers)],
            url=a_url,
        )

    @handle("av", r"^av(?P<avid>\d{6,})(?:\s)?(?P<page_num>\d{1,3})?$")
    @handle(
        "bilibili.com/video/av",
        r"bilibili\.com(?:/video)?/av(?P<avid>\d{6,})(?:\?p=(?P<page_num>\d{1,3}))?",
    )
    async def _parse_av(self, searched: Match[str]):
        avid = int(searched.group("avid"))
        page_num = int(searched.group("page_num") or 1)
        return await self.parse_video(avid=avid, page_num=page_num)

    @handle("/dynamic/", r"bilibili\.com/dynamic/(?P<dynamic_id>\d+)")
    @handle("t.bili", r"t\.bilibili\.com/(?P<dynamic_id>\d+)")
    async def _parse_dynamic(self, searched: Match[str]):
        return await self.parse_dynamic(int(searched.group("dynamic_id")))

    @handle("live.bili", r"live\.bilibili\.com/(?P<room_id>\d+)")
    async def _parse_live(self, searched: Match[str]):
        return await self.parse_live(int(searched.group("room_id")))

    @handle("/favlist", r"favlist\?fid=(?P<fav_id>\d+)")
    async def _parse_favlist(self, searched: Match[str]):
        return await self.parse_favlist(int(searched.group("fav_id")))

    @handle("/read/", r"bilibili\.com/read/cv(?P<read_id>\d+)")
    async def _parse_read(self, searched: Match[str]):
        return await self.parse_read_with_opus(int(searched.group("read_id")))

    @handle("/opus/", r"bilibili\.com/opus/(?P<opus_id>\d+)")
    async def _parse_opus(self, searched: Match[str]):
        return await self.parse_opus(int(searched.group("opus_id")))

    async def parse_video(
        self,
        *,
        bvid: str | None = None,
        avid: int | None = None,
        page_num: int = 1,
    ):
        from .video import AIConclusion, VideoInfo

        video = await self._get_video(bvid=bvid, avid=avid)
        video_info = convert(await video.get_info(), VideoInfo)
        page_info = video_info.extract_info_with_page(page_num)
        text_parts = []
        if video_info.desc:
            text_parts.append(f"简介: {video_info.desc}")
        text_parts.append(video_info.formatted_stats_info)
        author = self.create_author(video_info.owner.name, video_info.owner.face)

        ai_summary = ""
        credential = await self.login.credential
        if credential:
            try:
                cid = await video.get_cid(page_info.index)
                ai_summary = convert(await video.get_ai_conclusion(cid), AIConclusion).summary
            except Exception as exc:
                ai_summary = f"AI总结获取失败: {exc}"

        url = f"https://bilibili.com/{video_info.bvid}"
        if page_info.index > 0:
            url += f"?p={page_info.index + 1}"

        v_url, a_url = await self.extract_download_urls(video=video, page_index=page_info.index)
        content = self.create_video_content(
            v_url,
            page_info.cover,
            page_info.duration,
            headers=self.headers,
            audio_url=a_url,
            name=f"{video_info.bvid}-{page_info.index + 1}.mp4",
        )
        return self.result(
            url=url,
            title=page_info.title,
            timestamp=page_info.timestamp,
            text="\n".join(text_parts),
            author=author,
            contents=[content],
            extra={"info": ai_summary} if ai_summary else {},
        )

    async def parse_dynamic(self, dynamic_id: int):
        from bilibili_api.dynamic import Dynamic

        from .dynamic import DynamicData

        dynamic = Dynamic(dynamic_id, await self.login.credential)
        dynamic_info = convert(await dynamic.get_info(), DynamicData).item
        contents = self.create_image_contents(dynamic_info.image_urls, headers=self.headers)
        return self.result(
            title=dynamic_info.title,
            text=dynamic_info.text,
            timestamp=dynamic_info.timestamp,
            author=self.create_author(dynamic_info.name, dynamic_info.avatar),
            contents=contents,
            url=f"https://t.bilibili.com/{dynamic_id}",
        )

    async def parse_opus(self, opus_id: int):
        opus = Opus(opus_id, await self.login.credential)
        return await self._parse_opus_obj(opus, f"https://www.bilibili.com/opus/{opus_id}")

    async def parse_read_with_opus(self, read_id: int):
        from bilibili_api.article import Article

        article = Article(read_id)
        return await self._parse_opus_obj(
            await article.turn_to_opus(), f"https://www.bilibili.com/read/cv{read_id}"
        )

    async def _parse_opus_obj(self, bili_opus: Opus, url: str | None = None):
        from .opus import ImageNode, OpusItem, TextNode

        opus_data = convert(await bili_opus.get_info(), OpusItem)
        contents: list[MediaContent] = []
        current_text = ""
        for node in opus_data.gen_text_img():
            if isinstance(node, ImageNode):
                contents.append(self.create_image_content(node.url, text=current_text.strip()))
                current_text = ""
            elif isinstance(node, TextNode):
                current_text += node.text
        return self.result(
            title=opus_data.title,
            author=self.create_author(*opus_data.name_avatar),
            timestamp=opus_data.timestamp,
            contents=contents,
            text=current_text.strip(),
            url=url,
        )

    async def parse_live(self, room_id: int):
        from bilibili_api.live import LiveRoom

        from .live import RoomData

        room = LiveRoom(room_display_id=room_id, credential=await self.login.credential)
        room_data = convert(await room.get_room_info(), RoomData)
        contents: list[MediaContent] = []
        if room_data.cover:
            contents.append(self.create_image_content(room_data.cover, headers=self.headers))
        if room_data.keyframe:
            contents.append(self.create_image_content(room_data.keyframe, headers=self.headers))
        return self.result(
            url=f"https://live.bilibili.com/{room_id}",
            title=room_data.title,
            text=room_data.detail,
            contents=contents,
            author=self.create_author(room_data.name, room_data.avatar),
        )

    async def parse_favlist(self, fav_id: int):
        from bilibili_api.favorite_list import get_video_favorite_list_content

        from .favlist import FavData

        fav_dict = await get_video_favorite_list_content(fav_id)
        if fav_dict.get("medias") is None:
            raise ParseException("收藏夹内容为空，或被风控")
        favdata = convert(fav_dict, FavData)
        contents = [
            self.create_image_content(fav.cover, text=fav.desc, headers=self.headers)
            for fav in favdata.medias
        ]
        return self.result(
            title=favdata.title,
            timestamp=favdata.timestamp,
            author=self.create_author(favdata.info.upper.name, favdata.info.upper.face),
            contents=contents,
            url=f"https://space.bilibili.com/favlist?fid={fav_id}",
        )

    async def _get_video(self, *, bvid: str | None = None, avid: int | None = None) -> Video:
        credential = await self.login.credential
        if avid:
            return Video(aid=avid, credential=credential)
        if bvid:
            return Video(bvid=bvid, credential=credential)
        raise ParseException("avid 和 bvid 至少指定一项")

    async def extract_download_urls(
        self,
        video: Video | None = None,
        *,
        bvid: str | None = None,
        avid: int | None = None,
        page_index: int = 0,
    ) -> tuple[str, str | None]:
        from bilibili_api.video import (
            AudioStreamDownloadURL,
            VideoDownloadURLDataDetecter,
            VideoStreamDownloadURL,
        )

        if video is None:
            video = await self._get_video(bvid=bvid, avid=avid)
        download_url_data = await video.get_download_url(page_index=page_index)
        detecter = VideoDownloadURLDataDetecter(download_url_data)
        streams = detecter.detect_best_streams(
            video_max_quality=self.video_quality,
            codecs=[self.video_codecs],
            no_dolby_video=True,
            no_hdr=True,
        )
        video_stream = streams[0]
        if not isinstance(video_stream, VideoStreamDownloadURL):
            raise DownloadException("未找到可下载的视频流")
        audio_stream = streams[1] if len(streams) > 1 else None
        if not isinstance(audio_stream, AudioStreamDownloadURL):
            return video_stream.url, None
        return video_stream.url, audio_stream.url
