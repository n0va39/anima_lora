"""Prompt inspection and correction."""

from __future__ import annotations

from .knowledge import PromptKnowledgeBase
from .models import CorrectionResult, TagToken
from .normalize import lookup_key, normalize_tag, render_artist_tag
from .ordering import classify_tag, section_sort_key
from .parser import parse_prompt, render_tags

NO_ARTIST_TAG = "@no-artist"


def _render_token(raw: str, section_name: str) -> str:
    if section_name == "artist":
        return render_artist_tag(raw)
    return normalize_tag(raw)


def _tag_key_set(tags) -> set[str]:
    return {lookup_key(str(tag)) for tag in tags or () if str(tag).strip()}


def _classify_with_artist_options(
    normalized: str,
    *,
    info,
    kb: PromptKnowledgeBase,
    validate_artist_tags: bool,
    artist_overrides: set[str],
    artist_exclusions: set[str],
):
    key = lookup_key(normalized)
    is_no_artist = key == lookup_key(NO_ARTIST_TAG)
    if is_no_artist:
        return classify_tag(NO_ARTIST_TAG, info)
    if key in artist_exclusions:
        return classify_tag(normalized.lstrip("@"), None)
    if key in artist_overrides:
        return classify_tag(f"@{key}", info)
    if normalized.strip().startswith("@"):
        if not validate_artist_tags:
            return classify_tag(normalized, info)
        if key in kb.animadex.artists:
            return classify_tag(normalized, info)
        return classify_tag(normalized.lstrip("@"), None)
    return classify_tag(normalized, info)


def _no_artist_token() -> TagToken:
    key = lookup_key(NO_ARTIST_TAG)
    return TagToken(
        raw=NO_ARTIST_TAG,
        normalized=NO_ARTIST_TAG,
        lookup_key=key,
        text=NO_ARTIST_TAG,
        known=True,
        section=classify_tag(NO_ARTIST_TAG),
        source="manual",
    )


def inspect_prompt(
    text: str,
    *,
    profile: str = "prompt",
    knowledge_base: PromptKnowledgeBase | None = None,
    validate_artist_tags: bool = False,
    artist_overrides=(),
    artist_exclusions=(),
) -> CorrectionResult:
    """Parse and classify a prompt without reordering it."""

    kb = knowledge_base or PromptKnowledgeBase.empty()
    override_keys = _tag_key_set(artist_overrides)
    exclusion_keys = _tag_key_set(artist_exclusions)
    parsed = parse_prompt(text, profile=profile)
    tokens: list[TagToken] = []
    unknown: list[str] = []
    seen: set[str] = set()
    duplicates: list[str] = []

    for raw in parsed.tokens:
        normalized = normalize_tag(raw)
        key = lookup_key(normalized)
        info = kb.lookup(normalized)
        manual_known = key == lookup_key(NO_ARTIST_TAG) or key in override_keys
        section = _classify_with_artist_options(
            normalized,
            info=info,
            kb=kb,
            validate_artist_tags=validate_artist_tags,
            artist_overrides=override_keys,
            artist_exclusions=exclusion_keys,
        )
        dedupe_key = key
        if dedupe_key in seen:
            duplicates.append(normalized)
        else:
            seen.add(dedupe_key)
        if info is None and not manual_known:
            unknown.append(normalized)
        tokens.append(
            TagToken(
                raw=raw,
                normalized=normalized,
                lookup_key=key,
                text=_render_token(normalized, section.value),
                known=info is not None or manual_known,
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
    validate_artist_tags: bool = False,
    insert_no_artist: bool = False,
    artist_overrides=(),
    artist_exclusions=(),
) -> CorrectionResult:
    """Normalize, deduplicate, classify, and reorder a prompt for ANIMA."""

    kb = knowledge_base or PromptKnowledgeBase.empty()
    parsed = parse_prompt(text, profile=profile)
    inspected = inspect_prompt(
        text,
        profile=profile,
        knowledge_base=kb,
        validate_artist_tags=validate_artist_tags,
        artist_overrides=artist_overrides,
        artist_exclusions=artist_exclusions,
    )

    kept: list[tuple[int, TagToken]] = []
    seen: set[str] = set()
    duplicates: list[str] = []
    for index, token in enumerate(inspected.tokens):
        if token.lookup_key in seen:
            duplicates.append(token.normalized)
            continue
        seen.add(token.lookup_key)
        kept.append((index, token))

    if insert_no_artist and not any(
        token.section.value == "artist" for _, token in kept
    ):
        no_artist = _no_artist_token()
        if no_artist.lookup_key not in seen:
            kept.append((len(inspected.tokens), no_artist))

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
