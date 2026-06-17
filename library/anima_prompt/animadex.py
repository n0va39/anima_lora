"""Lightweight AnimaDex CSV loading for prompt correction.

The full AnimaDex app owns account login, export tokens, SQLite storage, and
thumbnail import. This module intentionally reads only local ``characters.csv``
and ``artists.csv`` exports so the prompt core can stay dependency-light.
"""

from __future__ import annotations

import csv
import json
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .normalize import lookup_key, normalize_tag

ANIMADEX_IMPORT_TOKEN_ENV = "ANIMADEX_IMPORT_TOKEN"
ANIMADEX_IMPORT_TOKEN_FILE_ENV = "ANIMADEX_IMPORT_TOKEN_FILE"
ANIMADEX_DEFAULT_SITE = "https://animadex.net"
ANIMADEX_MANIFEST_PATH = "/api/export/manifest"
ANIMADEX_EXPORT_TOKEN_HEADER = "X-Export-Token"
ANIMADEX_IMPORT_USER_AGENT = "animadex-import/1"
ANIMADEX_DEFAULT_DATA_DIR = Path("models") / "animadex"
ANIMADEX_IMPORT_DIR_NAME = "import"
ANIMADEX_INDEX_DIR_NAME = "index"

GENDER_TAGS = frozenset({"1boy", "1girl", "1other", "no humans"})


class AnimaDexImportError(RuntimeError):
    """Raised when AnimaDex export import cannot complete."""


def default_token_path() -> Path:
    configured = os.environ.get(ANIMADEX_IMPORT_TOKEN_FILE_ENV)
    if configured:
        return Path(configured)
    if os.name == "nt":
        root = os.environ.get("APPDATA")
        if root:
            return Path(root) / "anima_prompt" / "animadex_import_token.json"
    return Path.home() / ".config" / "anima_prompt" / "animadex_import_token.json"


@dataclass(frozen=True)
class AnimaDexImportToken:
    token: str
    site: str = ANIMADEX_DEFAULT_SITE

    def to_json(self) -> dict[str, str]:
        return {"token": self.token, "site": self.site}

    @classmethod
    def from_json(cls, data: dict[str, object]) -> "AnimaDexImportToken":
        token = str(data.get("token") or "").strip()
        if not token:
            raise AnimaDexImportError("Stored AnimaDex token file is missing token.")
        site = str(data.get("site") or ANIMADEX_DEFAULT_SITE).strip()
        return cls(token=token, site=site)


@dataclass
class AnimaDexTokenStore:
    path: Path

    @classmethod
    def default(cls) -> "AnimaDexTokenStore":
        return cls(default_token_path())

    def load(self) -> AnimaDexImportToken | None:
        if not self.path.is_file():
            return None
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            raise AnimaDexImportError(f"Could not read AnimaDex token file: {e}") from e
        if not isinstance(data, dict):
            raise AnimaDexImportError("Stored AnimaDex token file is not a JSON object.")
        return AnimaDexImportToken.from_json(data)

    def save(self, token: AnimaDexImportToken) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(token.to_json(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        try:
            self.path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass


@dataclass(frozen=True)
class AnimaDexImportResult:
    characters_csv: Path
    artists_csv: Path
    manifest: dict[str, object]


def resolve_import_token(
    *,
    token: str | None = None,
    token_file: str | os.PathLike | None = None,
) -> AnimaDexImportToken:
    if token:
        return AnimaDexImportToken(token=token.strip())
    env_token = os.environ.get(ANIMADEX_IMPORT_TOKEN_ENV)
    if env_token:
        return AnimaDexImportToken(token=env_token.strip())
    store = AnimaDexTokenStore(Path(token_file)) if token_file else AnimaDexTokenStore.default()
    stored = store.load()
    if stored is None:
        raise AnimaDexImportError(
            "No AnimaDex export token. Pass --token, set "
            f"{ANIMADEX_IMPORT_TOKEN_ENV}, or run animadex-save-token."
        )
    return stored


@dataclass
class AnimaDexImportClient:
    site: str = ANIMADEX_DEFAULT_SITE
    token: str = ""
    timeout: float = 60.0
    opener: object = urlopen

    def fetch_manifest(self, *, full: bool = False) -> dict[str, object]:
        query = f"?{urlencode({'full': '1'})}" if full else ""
        url = self.site.rstrip("/") + ANIMADEX_MANIFEST_PATH + query
        request = Request(
            url,
            headers={
                ANIMADEX_EXPORT_TOKEN_HEADER: self.token,
                "User-Agent": ANIMADEX_IMPORT_USER_AGENT,
            },
            method="GET",
        )
        data = self._open_bytes(request)
        try:
            manifest = json.loads(data.decode("utf-8"))
        except json.JSONDecodeError as e:
            raise AnimaDexImportError(f"AnimaDex manifest was not JSON: {e}") from e
        if not isinstance(manifest, dict):
            raise AnimaDexImportError("AnimaDex manifest was not a JSON object.")
        return manifest

    def download_required_csvs(
        self,
        data_dir: str | os.PathLike = ANIMADEX_DEFAULT_DATA_DIR,
        *,
        full: bool = False,
    ) -> AnimaDexImportResult:
        manifest = self.fetch_manifest(full=full)
        csv_manifest = manifest.get("csv")
        if not isinstance(csv_manifest, dict):
            raise AnimaDexImportError("AnimaDex manifest is missing csv entries.")

        characters_url = str(csv_manifest.get("characters") or "")
        artists_url = str(csv_manifest.get("artists") or "")
        if not characters_url or not artists_url:
            raise AnimaDexImportError(
                "AnimaDex manifest must include csv.characters and csv.artists."
            )

        import_dir = Path(data_dir) / ANIMADEX_IMPORT_DIR_NAME
        import_dir.mkdir(parents=True, exist_ok=True)
        characters_path = import_dir / "characters.csv"
        artists_path = import_dir / "artists.csv"
        characters_path.write_bytes(self._download_url(characters_url))
        artists_path.write_bytes(self._download_url(artists_url))
        return AnimaDexImportResult(
            characters_csv=characters_path,
            artists_csv=artists_path,
            manifest=manifest,
        )

    def _open_bytes(self, request: Request) -> bytes:
        try:
            with self.opener(request, timeout=self.timeout) as response:
                return response.read()
        except HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            raise AnimaDexImportError(f"AnimaDex HTTP {e.code}: {detail}") from e
        except URLError as e:
            raise AnimaDexImportError(f"Could not reach AnimaDex: {e.reason}") from e

    def _download_url(self, url: str) -> bytes:
        request = Request(
            url,
            headers={"User-Agent": ANIMADEX_IMPORT_USER_AGENT},
            method="GET",
        )
        return self._open_bytes(request)


def _parse_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value).replace(",", "").strip())
    except ValueError:
        return None


def _field(row: dict[str, str], name: str) -> str:
    lowered = {str(k).strip().lower(): v for k, v in row.items()}
    value = lowered.get(name)
    return str(value).strip() if value else ""


def parse_core_tags(value: str) -> tuple[str, ...]:
    return tuple(
        normalize_tag(part)
        for part in value.split(",")
        if normalize_tag(part)
    )


def split_trigger(trigger: str) -> tuple[str, str]:
    """Split an AnimaDex character trigger into character and copyright text."""

    parts = [normalize_tag(part) for part in trigger.split(",", 1)]
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[1].strip()


@dataclass(frozen=True)
class AnimaDexCharacter:
    character: str
    copyright: str
    trigger: str
    core_tags: tuple[str, ...] = ()
    count: int | None = None
    url: str = ""
    trigger_character: str = ""
    trigger_copyright: str = ""

    @property
    def person_tags(self) -> tuple[str, ...]:
        return tuple(tag for tag in self.core_tags if tag in GENDER_TAGS)

    @property
    def trait_tags(self) -> tuple[str, ...]:
        return tuple(tag for tag in self.core_tags if tag not in GENDER_TAGS)


@dataclass(frozen=True)
class AnimaDexArtist:
    artist: str
    trigger: str
    count: int | None = None
    url: str = ""


def parse_character_row(row: dict[str, str]) -> AnimaDexCharacter | None:
    character = lookup_key(_field(row, "character"))
    copyright_tag = lookup_key(_field(row, "copyright"))
    trigger = _field(row, "trigger")
    trigger_character, trigger_copyright = split_trigger(trigger)
    core_tags = parse_core_tags(_field(row, "core_tags"))

    if not character and not trigger_character:
        return None

    return AnimaDexCharacter(
        character=character,
        copyright=copyright_tag,
        trigger=normalize_tag(trigger),
        core_tags=core_tags,
        count=_parse_int(_field(row, "count")),
        url=_field(row, "url"),
        trigger_character=trigger_character,
        trigger_copyright=trigger_copyright,
    )


def parse_artist_row(row: dict[str, str]) -> AnimaDexArtist | None:
    artist = lookup_key(_field(row, "artist"))
    trigger = normalize_tag(_field(row, "trigger") or artist)
    if not artist and not trigger:
        return None
    return AnimaDexArtist(
        artist=artist,
        trigger=trigger,
        count=_parse_int(_field(row, "count")),
        url=_field(row, "url"),
    )


@dataclass
class AnimaDexDB:
    characters: set[str] = field(default_factory=set)
    copyrights: set[str] = field(default_factory=set)
    artists: set[str] = field(default_factory=set)
    core_tags: set[str] = field(default_factory=set)
    character_to_copyright: dict[str, str] = field(default_factory=dict)
    character_core_tags: dict[str, tuple[str, ...]] = field(default_factory=dict)
    character_records: dict[str, AnimaDexCharacter] = field(default_factory=dict)
    artist_records: dict[str, AnimaDexArtist] = field(default_factory=dict)

    @classmethod
    def from_csvs(
        cls,
        *,
        characters_csv: str | Path | None = None,
        artists_csv: str | Path | None = None,
    ) -> "AnimaDexDB":
        db = cls()
        if characters_csv and Path(characters_csv).is_file():
            db.add_characters(read_characters_csv(characters_csv))
        if artists_csv and Path(artists_csv).is_file():
            db.add_artists(read_artists_csv(artists_csv))
        return db

    @classmethod
    def from_jsonl(
        cls,
        *,
        character_index: str | Path | None = None,
        artist_index: str | Path | None = None,
    ) -> "AnimaDexDB":
        db = cls()
        if character_index and Path(character_index).is_file():
            records = []
            with Path(character_index).open("r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        data = json.loads(line)
                        records.append(
                            AnimaDexCharacter(
                                character=str(data.get("character") or ""),
                                copyright=str(data.get("copyright") or ""),
                                trigger=str(data.get("trigger") or ""),
                                core_tags=tuple(data.get("core_tags") or ()),
                                count=data.get("count"),
                                url=str(data.get("url") or ""),
                                trigger_character=str(
                                    data.get("trigger_character") or ""
                                ),
                                trigger_copyright=str(
                                    data.get("trigger_copyright") or ""
                                ),
                            )
                        )
            db.add_characters(records)
        if artist_index and Path(artist_index).is_file():
            records = []
            with Path(artist_index).open("r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        data = json.loads(line)
                        records.append(
                            AnimaDexArtist(
                                artist=str(data.get("artist") or ""),
                                trigger=str(data.get("trigger") or ""),
                                count=data.get("count"),
                                url=str(data.get("url") or ""),
                            )
                        )
            db.add_artists(records)
        return db

    def add_characters(self, records: Iterable[AnimaDexCharacter]) -> None:
        for record in records:
            names = {
                lookup_key(record.character),
                lookup_key(record.trigger_character),
            }
            names.discard("")
            self.characters.update(names)

            copyrights = {
                lookup_key(record.copyright),
                lookup_key(record.trigger_copyright),
            }
            copyrights.discard("")
            self.copyrights.update(copyrights)

            self.core_tags.update(record.core_tags)
            canonical = lookup_key(record.trigger_character or record.character)
            if canonical:
                self.character_records[canonical] = record
                self.character_core_tags[canonical] = record.core_tags
                copyright_tag = lookup_key(
                    record.trigger_copyright or record.copyright
                )
                if copyright_tag:
                    self.character_to_copyright[canonical] = copyright_tag

    def add_artists(self, records: Iterable[AnimaDexArtist]) -> None:
        for record in records:
            names = {lookup_key(record.artist), lookup_key(record.trigger)}
            names.discard("")
            self.artists.update(names)
            canonical = lookup_key(record.trigger or record.artist)
            if canonical:
                self.artist_records[canonical] = record

    def write_jsonl(self, output_dir: str | Path) -> tuple[Path, Path]:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        character_path = out / "character_index.jsonl"
        artist_path = out / "artist_index.jsonl"
        write_character_index(character_path, self.character_records.values())
        write_artist_index(artist_path, self.artist_records.values())
        return character_path, artist_path


def read_characters_csv(path: str | Path) -> list[AnimaDexCharacter]:
    records: list[AnimaDexCharacter] = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            record = parse_character_row(row)
            if record is not None:
                records.append(record)
    return records


def read_artists_csv(path: str | Path) -> list[AnimaDexArtist]:
    records: list[AnimaDexArtist] = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            record = parse_artist_row(row)
            if record is not None:
                records.append(record)
    return records


def write_character_index(
    path: str | Path,
    records: Iterable[AnimaDexCharacter],
) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="\n") as f:
        for record in sorted(records, key=lambda item: item.character):
            f.write(
                json.dumps(
                    {
                        "character": record.character,
                        "copyright": record.copyright,
                        "trigger": record.trigger,
                        "trigger_character": record.trigger_character,
                        "trigger_copyright": record.trigger_copyright,
                        "core_tags": list(record.core_tags),
                        "count": record.count,
                        "url": record.url,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
                + "\n"
            )


def write_artist_index(
    path: str | Path,
    records: Iterable[AnimaDexArtist],
) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="\n") as f:
        for record in sorted(records, key=lambda item: item.artist):
            f.write(
                json.dumps(
                    {
                        "artist": record.artist,
                        "trigger": record.trigger,
                        "count": record.count,
                        "url": record.url,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
                + "\n"
            )
