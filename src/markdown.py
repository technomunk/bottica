"""Parsing of a markdown file into sections."""

from __future__ import annotations

from dataclasses import dataclass, field
from io import StringIO, TextIOWrapper
from typing import Iterable, Iterator, List, Optional, Type, overload


@dataclass(slots=True)
class Markdown:
    """
    A recursive markdown document section that starts with a heading
    and ends just before the next section of the same level.
    """

    level: int
    title: str
    content: str = ""
    subsections: List[Markdown] = field(default_factory=list)

    def __str__(self) -> str:
        return self.compose_content()

    @overload
    def __getitem__(self, index: int | str) -> Markdown:
        ...

    @overload
    def __getitem__(self, index: slice) -> Iterable[Markdown]:
        ...

    def __getitem__(self, index: int | slice | str) -> Markdown | Iterable[Markdown]:
        if isinstance(index, int | slice):
            return self.subsections[index]

        if not isinstance(index, str):
            raise TypeError("index should be int, slice or a string")

        for subsection in self.subsections:
            if subsection.title == index:
                return subsection

        raise KeyError(index)

    def __iter__(self) -> Iterator[Markdown]:
        return iter(self.subsections)

    def __bool__(self) -> bool:
        return bool(self.content) or bool(self.subsections)

    def compose_content(
        self,
        buffer: Optional[TextIOWrapper] = None,
        include_heading: bool = True,
    ) -> str:
        """
        Generate the content string for the whole markdown section.

        If a string-io object is provided it will be populated
        with content instead of returning a string.
        """
        if buffer is None:
            result: TextIOWrapper = StringIO()
        else:
            result = buffer

        if all([include_heading, self.heading, self.heading != " "]):
            result.write(self.heading)
            result.write("\n\n")

        if self.content:
            result.write(self.content)
            result.write("\n")

        for subsection in self.subsections:
            subsection.compose_content(result)

        # avoid allocating a string object without need
        return result.getvalue() if buffer is None else ""  # type: ignore

    @property
    def heading(self) -> str:
        return f"{'#' * self.level} {self.title}"

    @classmethod
    def parse(cls: Type[Markdown], document: TextIOWrapper) -> Markdown:
        """Parse a markdown file."""
        top = Markdown(0, "")
        content = StringIO()

        line = _peek_line(document)
        while line and not line.strip().startswith("#"):
            content.write(line.strip())
            content.write("\n")

            document.readline()
            line = _peek_line(document)

        top.content = content.getvalue()

        while line:
            subsection = cls._parse_level(document)
            top.subsections.append(subsection)
            line = _peek_line(document)

        return top

    @classmethod
    def parse_file(cls: Type[Markdown], filename: str) -> Markdown:
        """Shortcut for opening and parsing a file."""
        with open(filename, "r", encoding="utf8") as markdown_file:
            return cls.parse(markdown_file)

    @classmethod
    def _parse_level(cls: Type[Markdown], document: TextIOWrapper) -> Markdown:
        line = _peek_line(document).strip()
        level = _count_prefix(line, "#")
        assert level > 0, line
        result = Markdown(level, title=line.lstrip("#").lstrip())
        content = StringIO()

        document.readline()
        line = _peek_line(document)

        while line and not line.strip().startswith("#"):
            if stripped := line.strip():
                content.write(stripped)
                content.write("\n")

            document.readline()
            line = _peek_line(document)

        result.content = content.getvalue()
        while line:
            line_level = _count_prefix(line.strip(), "#")
            if line_level <= level:
                return result

            subsection = cls._parse_level(document)
            result.subsections.append(subsection)
            line = _peek_line(document)

        return result


def _peek_line(document: TextIOWrapper) -> str:
    position = document.tell()
    line = document.readline()
    document.seek(position)
    return line


def _count_prefix(line: str, prefix: str) -> int:
    count = 0
    for character in line:
        if character not in prefix:
            return count
        count += 1

    return count
