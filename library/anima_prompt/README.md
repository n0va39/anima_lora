# ANIMA Prompt Correction Core

Dependency-light prompt/caption correction helpers for ANIMA-style tag order.

This package is designed so it can later be split into a standalone repository.
It does not import ComfyUI, torch, model loading code, or taggers.

Detailed design and workflow documentation:
[`docs/anima_prompt.md`](../../docs/anima_prompt.md)

## MVP Scope

- Danbooru-style comma-separated prompt parsing
- newline-preserving caption parsing
- tag normalization
- local tag DB lookup
- category classification
- ANIMA ordering
- correction report data
- check/fix CLI skeleton

## Ordering

The default ordering is:

```text
quality / meta / year / safety
-> character count / person type
-> character
-> series / copyright
-> artist
-> general tags
-> unknown tags
```

Example:

```text
masterpiece, best quality, newest, safe,
1girl,
hatsune miku,
vocaloid,
@artist_name,
aqua eyes, twintails, detached sleeves
```

## Data Sources

Local data is preferred. Automatic remote downloads are intentionally not part
of the MVP.

Resolution order:

1. CLI argument
2. environment variable
3. workspace-local default filename

Environment variables:

- `ANIMA_PROMPT_TAG_CSV`
- `ANIMA_PROMPT_TAG_INDEX`
- `ANIMADEX_CHARACTERS_CSV`
- `ANIMADEX_ARTISTS_CSV`
- `ANIMADEX_CHARACTER_INDEX`
- `ANIMADEX_ARTIST_INDEX`

## CLI

```powershell
uv run python scripts/anima_prompt.py build-index --tag-csv tags.csv --output tag_index.jsonl
uv run python scripts/anima_prompt.py build-animadex-index --characters-csv characters.csv --artists-csv artists.csv --output-dir data/animadex
uv run python scripts/anima_prompt.py animadex-save-token
uv run python scripts/anima_prompt.py animadex-import --build-index
uv run python scripts/anima_prompt.py check --text "long hair, 1girl" --tag-csv tags.csv
uv run python scripts/anima_prompt.py fix --text "long_hair, @artist, 1girl" --tag-csv tags.csv
```

### AnimaDex

AnimaDex is expected to be the primary source for character and artist data.
This package does not depend on the full AnimaDex Flask/SQLite app. It reads
only local CSV exports:

- `characters.csv`
- `artists.csv`

The official AnimaDex import flow is:

1. Open `animadex.net`.
2. Create a personal export token from Account -> Offline dataset export.
3. Save the token outside the repository:

   ```powershell
   uv run python scripts/anima_prompt.py animadex-save-token
   ```

4. Download the CSV files for local testing:

   ```powershell
   uv run python scripts/anima_prompt.py animadex-import --build-index
   ```

The official site import uses `ANIMADEX_IMPORT_TOKEN`, `/api/export/manifest`,
and the `X-Export-Token` header.

Default local paths:

- Token: `%APPDATA%\anima_prompt\animadex_import_token.json` on Windows, or
  `~/.config/anima_prompt/animadex_import_token.json` on other OSes
- CSV: `data/animadex/import/characters.csv`,
  `data/animadex/import/artists.csv`
- Index: `data/animadex/index/character_index.jsonl`,
  `data/animadex/index/artist_index.jsonl`

`data/animadex/` is ignored by git. Do not commit downloaded CSVs or tokens.

AnimaDex CSV fields used by the prompt core:

- Characters: `character`, `copyright`, `trigger`, `core_tags`, `count`, `url`
- Artists: `artist`, `trigger`, `count`, `url`

`trigger` is used to connect character and copyright text. `core_tags` are used
as known character trait tags, and person tags such as `1girl`, `1boy`,
`1other`, and `no humans` are ordered before character tags.

## API

```python
from library.anima_prompt import correct_prompt, load_knowledge_base

kb = load_knowledge_base(tag_csv="tags.csv")
result = correct_prompt(
    "1girl, gotoh hitori, bocchi the rock!, long hair",
    profile="prompt",
    knowledge_base=kb,
)

print(result.text)
print(result.warnings)
print(result.unknown_tags)
```
