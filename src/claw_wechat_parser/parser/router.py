from __future__ import annotations

from dataclasses import dataclass
from re import Match, Pattern

from claw_wechat_parser.config import Settings
from claw_wechat_parser.domain.parse_result import ParseResult
from claw_wechat_parser.parser.base import BaseParser


@dataclass(slots=True)
class ParserMatch:
    keyword: str
    match: Match[str]
    parser: BaseParser


class ParserRouter:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.parsers: dict[str, BaseParser] = {}
        self.patterns: list[tuple[str, Pattern[str], BaseParser]] = []

    def register_all(self) -> None:
        for cls in BaseParser.get_all_subclasses():
            parser = cls(self.settings)
            for keyword, pattern in cls.key_patterns():
                self.parsers[keyword] = parser
                self.patterns.append((keyword, pattern, parser))
        self.patterns.sort(key=lambda x: -len(x[0]))

    def match(self, text: str) -> ParserMatch | None:
        for keyword, pattern, parser in self.patterns:
            if keyword not in text:
                continue
            if match := pattern.search(text):
                return ParserMatch(keyword=keyword, match=match, parser=parser)
        return None

    async def parse(self, text: str) -> ParseResult | None:
        matched = self.match(text)
        if not matched:
            return None
        return await matched.parser.parse(matched.keyword, matched.match)

    async def close(self) -> None:
        seen: set[int] = set()
        for parser in self.parsers.values():
            if id(parser) in seen:
                continue
            seen.add(id(parser))
            await parser.close()
