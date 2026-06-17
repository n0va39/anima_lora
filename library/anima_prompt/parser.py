"""Danbooru-style prompt and caption parsing."""

from __future__ import annotations

from .models import ParsedPrompt


def parse_prompt(text: str, *, profile: str = "prompt") -> ParsedPrompt:
    """Parse prompt text into raw tag tokens.

    ``prompt`` profile prefers comma-separated tags. ``caption`` profile keeps
    newline-separated captions as newline-separated output. For convenience,
    caption text that has no newline but has commas is parsed as comma-separated
    input; this lets CLI checks inspect existing prompt snippets without
    converting line-based caption files to comma style.
    """

    profile = (profile or "prompt").strip().lower()
    if profile == "caption" and "\n" in text:
        delimiter = "\n"
        tokens = [part.strip() for part in text.splitlines()]
    else:
        delimiter = ", "
        tokens = [part.strip() for part in text.split(",")]
    tokens = [part for part in tokens if part]
    return ParsedPrompt(
        text=text,
        tokens=tuple(tokens),
        delimiter=delimiter,
        profile=profile,
    )


def render_tags(tags: list[str], delimiter: str) -> str:
    if delimiter == "\n":
        return "\n".join(tags)
    return ", ".join(tags)
