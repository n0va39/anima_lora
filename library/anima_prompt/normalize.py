"""Tag normalization utilities for Danbooru-style prompts."""

from __future__ import annotations

import re

_SPACE_RE = re.compile(r"\s+")


def normalize_tag(tag: str) -> str:
    """Normalize a tag for lookup and duplicate detection.

    Danbooru tags are case-insensitive in practice and frequently appear with
    either underscores or spaces. A leading ``@`` is kept because ANIMA uses it
    to mark artist tags.
    """

    text = tag.strip().replace("_", " ").lower()
    text = _SPACE_RE.sub(" ", text)
    if text.startswith("@"):
        text = "@" + text[1:].strip()
    return text


def lookup_key(tag: str) -> str:
    """Return the canonical DB lookup key, without ANIMA's artist marker."""

    normalized = normalize_tag(tag)
    return normalized[1:].strip() if normalized.startswith("@") else normalized


def render_artist_tag(tag: str) -> str:
    """Render an ANIMA artist tag with ``@`` and underscore-separated name."""

    key = lookup_key(tag)
    return "@" + key.replace(" ", "_")
