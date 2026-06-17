"""Local tag database loading for ANIMA prompt correction."""

from __future__ import annotations

import csv
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .animadex import AnimaDexDB, GENDER_TAGS
from .models import TagInfo
from .normalize import lookup_key

TAG_CSV_ENV = "ANIMA_PROMPT_TAG_CSV"
TAG_INDEX_ENV = "ANIMA_PROMPT_TAG_INDEX"
ANIMADEX_CHARACTERS_ENV = "ANIMADEX_CHARACTERS_CSV"
ANIMADEX_ARTISTS_ENV = "ANIMADEX_ARTISTS_CSV"
ANIMADEX_CHARACTER_INDEX_ENV = "ANIMADEX_CHARACTER_INDEX"
ANIMADEX_ARTIST_INDEX_ENV = "ANIMADEX_ARTIST_INDEX"

DEFAULT_TAG_CSV_NAME = "KR_danbooru_tags_with_description v3_modified.csv"
DEFAULT_TAG_INDEX_NAME = "tag_index.jsonl"
DEFAULT_CHARACTER_INDEX_NAME = "character_index.jsonl"
DEFAULT_ARTIST_INDEX_NAME = "artist_index.jsonl"
DEFAULT_ANIMADEX_IMPORT_DIR = Path("data") / "animadex" / "import"
DEFAULT_ANIMADEX_INDEX_DIR = Path("data") / "animadex" / "index"

_CATEGORY_RE = re.compile(r"^\s*\[([^\]]+)\]")


class KnowledgeBaseNotFound(FileNotFoundError):
    """Raised when no local tag data source could be resolved."""


def parse_category_path(description: str) -> tuple[str, ...]:
    match = _CATEGORY_RE.match(description or "")
    if not match:
        return ()
    return tuple(part.strip() for part in match.group(1).split(">") if part.strip())


def _parse_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value).replace(",", "").strip())
    except ValueError:
        return None


@dataclass
class GeneralTagDB:
    tags: dict[str, TagInfo] = field(default_factory=dict)

    @classmethod
    def from_csv(cls, path: str | os.PathLike) -> "GeneralTagDB":
        tags: dict[str, TagInfo] = {}
        with Path(path).open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            for row in reader:
                if not row or len(row) < 1:
                    continue
                raw_tag = row[0].strip()
                if not raw_tag or raw_tag.lower() == "tag":
                    continue
                count = _parse_int(row[2] if len(row) > 2 else None)
                desc = row[3] if len(row) > 3 else ""
                key = lookup_key(raw_tag)
                tags[key] = TagInfo(
                    tag=key,
                    category_path=parse_category_path(desc),
                    post_count=count,
                    source="general",
                )
        return cls(tags)

    @classmethod
    def from_jsonl(cls, path: str | os.PathLike) -> "GeneralTagDB":
        tags: dict[str, TagInfo] = {}
        with Path(path).open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                key = lookup_key(str(data.get("tag") or ""))
                if not key:
                    continue
                tags[key] = TagInfo(
                    tag=key,
                    category_path=tuple(data.get("category_path") or ()),
                    post_count=data.get("post_count"),
                    source=str(data.get("source") or "general"),
                )
        return cls(tags)

    def write_jsonl(self, path: str | os.PathLike) -> None:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8", newline="\n") as f:
            for key in sorted(self.tags):
                info = self.tags[key]
                f.write(
                    json.dumps(
                        {
                            "tag": info.tag,
                            "category_path": list(info.category_path),
                            "post_count": info.post_count,
                            "source": info.source,
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                    + "\n"
                )


@dataclass
class PromptKnowledgeBase:
    general: GeneralTagDB = field(default_factory=GeneralTagDB)
    animadex: AnimaDexDB = field(default_factory=AnimaDexDB)

    @classmethod
    def empty(cls) -> "PromptKnowledgeBase":
        return cls()

    def lookup(self, tag: str) -> TagInfo | None:
        key = lookup_key(tag)
        info = self.general.tags.get(key)
        if key in self.animadex.characters:
            return TagInfo(
                tag=key,
                category_path=("캐릭터",),
                post_count=info.post_count if info else None,
                source="animadex",
            )
        if key in self.animadex.copyrights:
            return TagInfo(
                tag=key,
                category_path=("작품",),
                post_count=info.post_count if info else None,
                source="animadex",
            )
        if key in self.animadex.artists:
            return TagInfo(
                tag=key,
                category_path=("작가",),
                post_count=info.post_count if info else None,
                source="animadex",
            )
        if key in self.animadex.core_tags:
            category_path = ("인물", "인원수") if key in GENDER_TAGS else ("일반",)
            return TagInfo(
                tag=key,
                category_path=category_path,
                post_count=info.post_count if info else None,
                source="animadex_core",
            )
        return info


def _candidate_paths(
    explicit: str | os.PathLike | None,
    env_name: str,
    default_name: str | os.PathLike,
    *,
    extra_defaults: Iterable[str | os.PathLike] = (),
) -> list[Path]:
    paths: list[Path] = []
    if explicit:
        paths.append(Path(explicit))
    env = os.environ.get(env_name)
    if env:
        paths.append(Path(env))
    cwd = Path.cwd()
    for base in (cwd, *cwd.parents):
        paths.append(base / default_name)
        for default in extra_defaults:
            paths.append(base / default)
    return paths


def _first_file(paths: Iterable[Path]) -> Path | None:
    seen: set[Path] = set()
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        if path.is_file():
            return path
    return None


def load_knowledge_base(
    *,
    tag_csv: str | os.PathLike | None = None,
    tag_index: str | os.PathLike | None = None,
    animadex_characters_csv: str | os.PathLike | None = None,
    animadex_artists_csv: str | os.PathLike | None = None,
    animadex_character_index: str | os.PathLike | None = None,
    animadex_artist_index: str | os.PathLike | None = None,
    allow_missing: bool = False,
) -> PromptKnowledgeBase:
    """Load local prompt knowledge from CSV/JSONL sources.

    Resolution priority is explicit argument, environment variable, then a
    workspace-local default filename. Missing data raises a clear error unless
    ``allow_missing`` is set.
    """

    index_path = _first_file(
        _candidate_paths(tag_index, TAG_INDEX_ENV, DEFAULT_TAG_INDEX_NAME)
    )
    csv_path = _first_file(_candidate_paths(tag_csv, TAG_CSV_ENV, DEFAULT_TAG_CSV_NAME))

    if index_path:
        general = GeneralTagDB.from_jsonl(index_path)
    elif csv_path:
        general = GeneralTagDB.from_csv(csv_path)
    elif allow_missing:
        general = GeneralTagDB()
    else:
        raise KnowledgeBaseNotFound(
            "No tag DB found. Pass --tag-csv/--tag-index or set "
            f"{TAG_CSV_ENV}/{TAG_INDEX_ENV}."
        )

    character_index_path = _first_file(
        _candidate_paths(
            animadex_character_index,
            ANIMADEX_CHARACTER_INDEX_ENV,
            DEFAULT_CHARACTER_INDEX_NAME,
            extra_defaults=(DEFAULT_ANIMADEX_INDEX_DIR / DEFAULT_CHARACTER_INDEX_NAME,),
        )
    )
    artist_index_path = _first_file(
        _candidate_paths(
            animadex_artist_index,
            ANIMADEX_ARTIST_INDEX_ENV,
            DEFAULT_ARTIST_INDEX_NAME,
            extra_defaults=(DEFAULT_ANIMADEX_INDEX_DIR / DEFAULT_ARTIST_INDEX_NAME,),
        )
    )
    char_csv_path = _first_file(
        _candidate_paths(
            animadex_characters_csv,
            ANIMADEX_CHARACTERS_ENV,
            "characters.csv",
            extra_defaults=(DEFAULT_ANIMADEX_IMPORT_DIR / "characters.csv",),
        )
    )
    artist_csv_path = _first_file(
        _candidate_paths(
            animadex_artists_csv,
            ANIMADEX_ARTISTS_ENV,
            "artists.csv",
            extra_defaults=(DEFAULT_ANIMADEX_IMPORT_DIR / "artists.csv",),
        )
    )
    if character_index_path or artist_index_path:
        animadex = AnimaDexDB.from_jsonl(
            character_index=character_index_path,
            artist_index=artist_index_path,
        )
    else:
        animadex = AnimaDexDB.from_csvs(
            characters_csv=char_csv_path,
            artists_csv=artist_csv_path,
        )
    return PromptKnowledgeBase(general=general, animadex=animadex)
