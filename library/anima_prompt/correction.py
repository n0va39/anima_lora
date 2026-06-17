"""Prompt inspection and correction."""

from __future__ import annotations

from .knowledge import PromptKnowledgeBase
from .models import CorrectionResult, TagToken
from .normalize import lookup_key, normalize_tag, render_artist_tag
from .ordering import classify_tag, section_sort_key
from .parser import parse_prompt, render_tags


def _render_token(raw: str, section_name: str) -> str:
    if section_name == "artist":
        return render_artist_tag(raw)
    normalized = normalize_tag(raw)
    return normalized[1:] if normalized.startswith("@") else normalized


def inspect_prompt(
    text: str,
    *,
    profile: str = "prompt",
    knowledge_base: PromptKnowledgeBase | None = None,
) -> CorrectionResult:
    """Parse and classify a prompt without reordering it."""

    kb = knowledge_base or PromptKnowledgeBase.empty()
    parsed = parse_prompt(text, profile=profile)
    tokens: list[TagToken] = []
    unknown: list[str] = []
    seen: set[str] = set()
    duplicates: list[str] = []

    for raw in parsed.tokens:
        normalized = normalize_tag(raw)
        key = lookup_key(normalized)
        info = kb.lookup(normalized)
        section = classify_tag(normalized, info)
        dedupe_key = key
        if dedupe_key in seen:
            duplicates.append(normalized)
        else:
            seen.add(dedupe_key)
        if info is None:
            unknown.append(normalized)
        tokens.append(
            TagToken(
                raw=raw,
                normalized=normalized,
                lookup_key=key,
                text=_render_token(normalized, section.value),
                known=info is not None,
                section=section,
                category_path=info.category_path if info else (),
                source=info.source if info else None,
            )
        )

    return CorrectionResult(
        text=text,
        original_text=text,
        tokens=tuple(tokens),
        unknown_tags=tuple(unknown),
        duplicate_tags=tuple(duplicates),
        warnings=(),
        changed=False,
        report={
            "profile": parsed.profile,
            "delimiter": parsed.delimiter,
            "sections": [token.section.value for token in tokens],
        },
    )


def correct_prompt(
    text: str,
    *,
    profile: str = "prompt",
    knowledge_base: PromptKnowledgeBase | None = None,
) -> CorrectionResult:
    """Normalize, deduplicate, classify, and reorder a prompt for ANIMA."""

    kb = knowledge_base or PromptKnowledgeBase.empty()
    parsed = parse_prompt(text, profile=profile)
    inspected = inspect_prompt(text, profile=profile, knowledge_base=kb)

    kept: list[tuple[int, TagToken]] = []
    seen: set[str] = set()
    duplicates: list[str] = []
    for index, token in enumerate(inspected.tokens):
        if token.lookup_key in seen:
            duplicates.append(token.normalized)
            continue
        seen.add(token.lookup_key)
        kept.append((index, token))

    kept.sort(key=lambda item: section_sort_key(item[0], item[1].section))
    ordered = [token.text for _, token in kept]
    corrected = render_tags(ordered, parsed.delimiter)
    warnings: list[str] = []
    if inspected.unknown_tags:
        warnings.append(f"unknown tags: {', '.join(inspected.unknown_tags)}")
    if duplicates:
        warnings.append(f"duplicate tags removed: {', '.join(duplicates)}")

    return CorrectionResult(
        text=corrected,
        original_text=text,
        tokens=tuple(token for _, token in kept),
        unknown_tags=inspected.unknown_tags,
        duplicate_tags=tuple(duplicates),
        warnings=tuple(warnings),
        changed=corrected != text,
        report={
            "profile": parsed.profile,
            "delimiter": parsed.delimiter,
            "sections": [token.section.value for _, token in kept],
            "removed_duplicates": duplicates,
        },
    )
