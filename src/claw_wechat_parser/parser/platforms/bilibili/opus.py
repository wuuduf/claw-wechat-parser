from collections.abc import Generator
from typing import Any

from msgspec import Struct


class TextNode(Struct, tag="TextNode"):
    text: str


class ImageNode(Struct, tag="ImageNode"):
    url: str
    alt: str | None = None


class Author(Struct):
    name: str
    face: str
    mid: int
    pub_time: str
    pub_ts: int


class Image(Struct):
    url: str


class Pic(Struct):
    pics: list[Image]
    style: int


class Text(Struct):
    nodes: list[dict[str, Any]]


class Paragraph(Struct):
    para_type: int
    text: Text | None = None
    pic: Pic | None = None


class Content(Struct):
    paragraphs: list[Paragraph]


class Module(Struct):
    module_type: str
    module_author: Author | None = None
    module_content: Content | None = None


class Basic(Struct):
    title: str


class Info(Struct):
    id_str: str
    type: int
    modules: list[Module]
    basic: Basic | None = None


class OpusItem(Struct):
    item: Info

    @property
    def title(self) -> str | None:
        return self.item.basic.title if self.item.basic else None

    @property
    def name_avatar(self) -> tuple[str, str]:
        author_module = next(module.module_author for module in self.item.modules if module.module_author)
        return author_module.name, author_module.face

    @property
    def timestamp(self) -> int | None:
        for module in self.item.modules:
            if module.module_type == "MODULE_TYPE_AUTHOR" and module.module_author:
                return module.module_author.pub_ts
        return None

    def gen_text_img(self) -> Generator[TextNode | ImageNode, None, None]:
        for module in self.item.modules:
            if module.module_type == "MODULE_TYPE_CONTENT" and module.module_content:
                for paragraph in module.module_content.paragraphs:
                    if paragraph.text and paragraph.text.nodes:
                        text = self._extract_text_from_nodes(paragraph.text.nodes).strip()
                        if text:
                            yield TextNode(text="\n\n" + text)
                    if paragraph.pic and paragraph.pic.pics:
                        for pic in paragraph.pic.pics:
                            yield ImageNode(url=pic.url)

    def _extract_text_from_nodes(self, nodes: list[dict[str, Any]]) -> str:
        text = ""
        for node in nodes:
            if node.get("type") in ["TEXT_NODE_TYPE_WORD", "TEXT_NODE_TYPE_RICH"] and node.get("word"):
                text += node["word"].get("words", "")
        return text
