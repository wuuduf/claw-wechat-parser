# Architecture

## Runtime flow

1. `WeixinAuthService` 获取二维码并轮询登录状态。
2. `AccountStore` 保存 `account_id/token/base_url/user_id`。
3. `WeixinPoller` 使用 `getupdates` 长轮询新消息。
4. `weixin.inbound` 将原始微信消息转换成平台无关的 `InboundMessage`。
5. `ParseService` 执行防抖和解析器路由。
6. `ParserRouter` 基于「关键词 + 正则」匹配 `BaseParser` 子类。
7. 平台解析器返回 `ParseResult`。
8. `DownloadService` 下载解析结果中的媒体，`RenderService` 生成兜底卡片。
9. `WeixinSender` 上传媒体到微信 CDN 并调用 `sendmessage` 回复。

## Compatibility notes from astrbot_plugin_parser

- `ParseResult`/`MediaContent` 已保留核心语义，但移除了 AstrBot 消息组件。
- `MessageSender` 的职责由 `WeixinSender` 接管。
- QQ 合并转发无法在微信里等价实现，后续会降级为多条发送/文件打包。
- QQ 表情仲裁对微信无意义，后续多实例部署时改成 SQLite/Redis 锁。

## Migrated parser status

- `parser.platforms.bilibili`: migrated from `astrbot_plugin_parser/core/parsers/bilibili`, including video, audio-only `bm...`, dynamic, live room, favorite list, read/article-to-opus, and opus parsing. Bilibili DASH video/audio URLs are represented as one `MediaContent` with `audio_url`; `DownloadService` merges them via `ffmpeg`.
- `parser.platforms.douyin`: migrated short-link redirect, `window._ROUTER_DATA` video/note extraction, and slides API extraction.
- `parser.platforms.xhs`: migrated short-link redirect, `window.__INITIAL_STATE__` extraction for `explore` and `discovery/item`. XHS may return security/404 pages without a valid cookie; configure `CLAW_PARSER_XHS_COOKIE` when needed.

- `parser.platforms.instagram`: migrated for Instagram post/reel/tv/share URLs. It uses `yt-dlp` first and falls back to `gallery-dl` for image posts. `CLAW_PARSER_INSTAGRAM_COOKIE` is converted to a local Netscape cookie file for extractors.
- `parser.platforms.youtube`: migrated for YouTube watch/shorts/youtu.be URLs plus `ym<url>` audio mode. Media streams are selected from yt-dlp formats and merged by the shared download service when separate audio/video streams are returned.
- `parser.platforms.twitter`: migrated for x.com/twitter.com status URLs through xdown.app HTML extraction. It supports image, MP4, and GIF download links exposed by the service.
