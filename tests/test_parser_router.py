import pytest

from claw_wechat_parser.config import load_settings
from claw_wechat_parser.parser import ParserRouter


@pytest.fixture
def router(tmp_path):
    settings = load_settings(tmp_path)
    r = ParserRouter(settings)
    r.register_all()
    return r


def test_bilibili_bv_match(router):
    matched = router.match("BV1xx411c7mD")
    assert matched is not None
    assert matched.parser.platform.name == "bilibili"


def test_bilibili_full_url_beats_generic(router):
    matched = router.match("https://www.bilibili.com/video/BV1xx411c7mD")
    assert matched is not None
    assert matched.parser.platform.name == "bilibili"


def test_douyin_match(router):
    matched = router.match("https://www.douyin.com/video/7521023890996514083")
    assert matched is not None
    assert matched.parser.platform.name == "douyin"


def test_xhs_match(router):
    matched = router.match("https://www.xiaohongshu.com/explore/68e8e3fa00000000030342ec")
    assert matched is not None
    assert matched.parser.platform.name == "xhs"


def test_instagram_match(router):
    matched = router.match("https://www.instagram.com/reel/C1234567890/")
    assert matched is not None
    assert matched.parser.platform.name == "instagram"


def test_youtube_match(router):
    matched = router.match("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert matched is not None
    assert matched.parser.platform.name == "youtube"


def test_youtube_audio_prefix_match(router):
    matched = router.match("ymhttps://youtu.be/dQw4w9WgXcQ")
    assert matched is not None
    assert matched.parser.platform.name == "youtube"
    assert matched.keyword == "ymhttp"


def test_twitter_match(router):
    matched = router.match("https://x.com/jack/status/20")
    assert matched is not None
    assert matched.parser.platform.name == "twitter"


def test_twitter_legacy_domain_match(router):
    matched = router.match("https://twitter.com/jack/status/20")
    assert matched is not None
    assert matched.parser.platform.name == "twitter"


@pytest.mark.asyncio
async def test_bilibili_parse_smoke(tmp_path):
    settings = load_settings(tmp_path)
    r = ParserRouter(settings)
    r.register_all()
    try:
        # parse() would hit network for full parser; this smoke test only verifies handler lookup.
        matched = r.match("BV1xx411c7mD")
        assert matched is not None
        assert matched.keyword == "BV"
    finally:
        await r.close()
