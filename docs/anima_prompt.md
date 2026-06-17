# ANIMA Prompt Correction Core

`library/anima_prompt/` is a dependency-light prompt and caption correction
core for ANIMA-style tag ordering.

The package is written as plain Python so it can be reused by CLI tools, GUI
tools, and future ComfyUI nodes without importing ComfyUI, torch, model loading
code, or taggers.

## Goals

- Parse Danbooru-style comma-separated prompts.
- Preserve newline-separated caption files when using the `caption` profile.
- Normalize tag spelling for lookup and duplicate detection.
- Load local tag knowledge from CSV or JSONL indexes.
- Use AnimaDex character and artist exports as the main character database.
- Classify tags into ANIMA ordering sections.
- Reorder captions so person count/type tags come before character tags.
- Produce a correction result with warnings, unknown tags, duplicates, and token
  metadata.

## Non-Goals

- No model loading.
- No tagger integration.
- No natural-language-to-tag conversion.
- No fuzzy matching in the MVP.
- No full AnimaDex Flask/SQLite dependency.
- No committed downloaded database files or tokens.

## Ordering Profile

The default ANIMA ordering is:

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

Important rules:

- `1girl`, `1boy`, `1other`, `no humans`, and similar person tags are ordered
  before character tags.
- Character tags are ordered before series/copyright tags.
- Series/copyright tags are ordered before artist tags.
- Artist tags are rendered with ANIMA's `@artist_name` style.
- General visual tags stay after the identity tags.

## Data Sources

The knowledge base can combine two sources:

1. General Danbooru-style tag CSV or JSONL index.
2. AnimaDex `characters.csv` and `artists.csv`, or their generated JSONL
   indexes.

Resolution priority:

1. CLI argument.
2. Environment variable.
3. Workspace-local default path.

Environment variables:

- `ANIMA_PROMPT_TAG_CSV`
- `ANIMA_PROMPT_TAG_INDEX`
- `ANIMADEX_CHARACTERS_CSV`
- `ANIMADEX_ARTISTS_CSV`
- `ANIMADEX_CHARACTER_INDEX`
- `ANIMADEX_ARTIST_INDEX`
- `ANIMADEX_IMPORT_TOKEN`
- `ANIMADEX_IMPORT_TOKEN_FILE`

## AnimaDex Import

AnimaDex data is expected to come from the official offline export flow:

1. Open `animadex.net`.
2. Create an offline dataset export token from the account page.
3. Save the token outside the repository.
4. Download `characters.csv` and `artists.csv` into the local ignored
   `models/` directory.
5. Build JSONL indexes for faster repeated tests.

Default paths:

- Token on Windows:
  `%APPDATA%\anima_prompt\animadex_import_token.json`
- Token on other OSes:
  `~/.config/anima_prompt/animadex_import_token.json`
- CSV:
  `models/animadex/import/characters.csv`
  `models/animadex/import/artists.csv`
- Index:
  `models/animadex/index/character_index.jsonl`
  `models/animadex/index/artist_index.jsonl`

`models/animadex/` is ignored by git. Do not commit export tokens or downloaded
CSV files.

The import command follows the public AnimaDex export contract:

- Manifest endpoint: `/api/export/manifest`
- Token header: `X-Export-Token`
- Token environment variable: `ANIMADEX_IMPORT_TOKEN`

## CLI

Build a general tag index:

```powershell
uv run python scripts/anima_prompt.py build-index `
  --tag-csv tags.csv `
  --output tag_index.jsonl
```

Save an AnimaDex export token:

```powershell
uv run python scripts/anima_prompt.py animadex-save-token
```

Download AnimaDex CSVs and build indexes:

```powershell
uv run python scripts/anima_prompt.py animadex-import --build-index
```

Build AnimaDex indexes from existing local CSVs:

```powershell
uv run python scripts/anima_prompt.py build-animadex-index `
  --characters-csv models/animadex/import/characters.csv `
  --artists-csv models/animadex/import/artists.csv `
  --output-dir models/animadex/index
```

Inspect a prompt:

```powershell
uv run python scripts/anima_prompt.py check `
  --text "long hair, 1girl"
```

Fix a prompt:

```powershell
uv run python scripts/anima_prompt.py fix `
  --text "long_hair, @artist_name, hatsune_miku, vocaloid, 1girl"
```

Fix a newline-separated caption file in place:

```powershell
uv run python scripts/anima_prompt.py fix `
  --profile caption `
  --file image.txt `
  --in-place
```

## Python API

```python
from library.anima_prompt import correct_prompt, load_knowledge_base

kb = load_knowledge_base(
    tag_index="tag_index.jsonl",
    animadex_character_index="models/animadex/index/character_index.jsonl",
    animadex_artist_index="models/animadex/index/artist_index.jsonl",
)

result = correct_prompt(
    "long hair, @artist_name, vocaloid, hatsune miku, 1girl",
    profile="prompt",
    knowledge_base=kb,
)

print(result.text)
print(result.warnings)
print(result.unknown_tags)
```

## Module Layout

- `parser.py`: prompt/caption tokenization and rendering.
- `normalize.py`: tag normalization, lookup keys, artist rendering.
- `models.py`: immutable result and token data models.
- `knowledge.py`: local DB discovery and merged knowledge base lookup.
- `animadex.py`: lightweight AnimaDex CSV import, token storage, and JSONL
  index helpers.
- `ordering.py`: ANIMA section classification and stable ordering.
- `correction.py`: inspect/fix orchestration.
- `cli.py`: command-line entry points.

## Validation

Run the focused test suite:

```powershell
uv run python -m pytest tests\test_anima_prompt.py -q
```

Run lint:

```powershell
uv run python -m ruff check library\anima_prompt scripts\anima_prompt.py tests\test_anima_prompt.py
```

Run syntax checks:

```powershell
uv run python -m py_compile `
  library\anima_prompt\__init__.py `
  library\anima_prompt\animadex.py `
  library\anima_prompt\knowledge.py `
  library\anima_prompt\cli.py `
  tests\test_anima_prompt.py
```

## Future Work

- Alias override support.
- Order profile configuration.
- Conflict reports for character/series mismatch.
- Optional fuzzy matching.
- Batch caption directory fix command.
- GUI integration.
- ComfyUI prompt-corrector node using the same core.
