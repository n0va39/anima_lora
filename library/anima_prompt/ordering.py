"""ANIMA tag classification and ordering rules."""

from __future__ import annotations

from .models import TagInfo, TagSection
from .normalize import lookup_key

QUALITY_TAGS = {
    "masterpiece",
    "best quality",
    "high quality",
    "absurdres",
}
META_TAGS = {
    "highres",
    "official art",
    "scan",
}
YEAR_TAGS = {
    "oldest",
    "old",
    "recent",
    "newest",
}
SAFETY_TAGS = {
    "safe",
    "sensitive",
    "questionable",
    "explicit",
}

ANIMA_PERSON_COUNT_TAGS = frozenset(
    {
        "solo",
        "no humans",
        "multiple boys",
        "multiple girls",
        "multiple others",
        "1boy",
        "2boys",
        "3boys",
        "4boys",
        "5boys",
        "6+boys",
        "1girl",
        "2girls",
        "3girls",
        "4girls",
        "5girls",
        "6+girls",
        "1other",
        "2others",
        "3others",
        "4others",
        "5others",
        "6+others",
    }
)

SECTION_ORDER = {
    TagSection.QUALITY: 0,
    TagSection.META: 1,
    TagSection.YEAR: 2,
    TagSection.SAFETY: 3,
    TagSection.COUNT: 4,
    TagSection.CHARACTER: 5,
    TagSection.COPYRIGHT: 6,
    TagSection.ARTIST: 7,
    TagSection.GENERAL: 8,
    TagSection.UNKNOWN: 8,
}


def classify_tag(tag: str, info: TagInfo | None = None) -> TagSection:
    key = lookup_key(tag)
    if key in QUALITY_TAGS:
        return TagSection.QUALITY
    if key in META_TAGS:
        return TagSection.META
    if key in YEAR_TAGS:
        return TagSection.YEAR
    if key in SAFETY_TAGS:
        return TagSection.SAFETY
    if key in ANIMA_PERSON_COUNT_TAGS:
        return TagSection.COUNT
    if tag.strip().startswith("@"):
        return TagSection.ARTIST

    category_path = info.category_path if info else ()
    root = category_path[0] if category_path else ""
    if root == "캐릭터":
        return TagSection.CHARACTER
    if root in {"작품", "미디어"}:
        return TagSection.COPYRIGHT
    if root == "작가":
        return TagSection.ARTIST
    if root == "인물" and any(part == "인원수" for part in category_path):
        return TagSection.COUNT
    return TagSection.GENERAL if info is not None else TagSection.UNKNOWN


def section_sort_key(index: int, section: TagSection) -> tuple[int, int]:
    return (SECTION_ORDER.get(section, SECTION_ORDER[TagSection.UNKNOWN]), index)
