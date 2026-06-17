from __future__ import annotations

from pathlib import Path

from library.anima_prompt import (
    AnimaDexDB,
    AnimaDexImportClient,
    AnimaDexImportToken,
    AnimaDexTokenStore,
    GeneralTagDB,
    PromptKnowledgeBase,
    correct_prompt,
    inspect_prompt,
)
from library.anima_prompt.animadex import ANIMADEX_DEFAULT_DATA_DIR
from library.anima_prompt.knowledge import parse_category_path


def _kb() -> PromptKnowledgeBase:
    tags = {
        "1girl": ("캐릭터", "인원수"),
        "gotoh hitori": ("캐릭터",),
        "bocchi the rock!": ("작품",),
        "artist name": ("작가",),
        "long hair": ("패션", "헤어스타일"),
    }
    db = GeneralTagDB()
    from library.anima_prompt.models import TagInfo

    db.tags = {
        tag: TagInfo(tag=tag, category_path=path, source="test")
        for tag, path in tags.items()
    }
    return PromptKnowledgeBase(general=db)


def test_animadex_default_data_dir_uses_ignored_models_folder() -> None:
    assert ANIMADEX_DEFAULT_DATA_DIR == Path("models") / "animadex"


def test_parse_description_category_path() -> None:
    assert parse_category_path("[캐릭터 > 작품] desc") == ("캐릭터", "작품")
    assert parse_category_path("desc only") == ()


def test_correct_prompt_orders_anima_sections() -> None:
    result = correct_prompt(
        "long_hair, @artist_name, bocchi the rock!, gotoh hitori, 1girl",
        knowledge_base=_kb(),
    )

    assert result.text == (
        "1girl, gotoh hitori, bocchi the rock!, @artist_name, long hair"
    )
    assert result.changed is True


def test_caption_profile_preserves_newline_delimiter() -> None:
    result = correct_prompt(
        "long hair\nartist name\n1girl",
        profile="caption",
        knowledge_base=_kb(),
    )

    assert result.text == "1girl\n@artist_name\nlong hair"


def test_unknown_and_duplicates_reported() -> None:
    result = correct_prompt("1girl, mystery tag, 1girl", knowledge_base=_kb())

    assert result.text == "1girl, mystery tag"
    assert result.unknown_tags == ("mystery tag",)
    assert result.duplicate_tags == ("1girl",)


def test_general_tag_db_from_csv_and_jsonl(tmp_path: Path) -> None:
    csv_path = tmp_path / "tags.csv"
    csv_path.write_text(
        '1girl,0,10,"[인물 > 인원수] one girl"\n'
        'gotoh hitori,0,5,"[캐릭터] character"\n',
        encoding="utf-8",
    )
    db = GeneralTagDB.from_csv(csv_path)
    assert db.tags["1girl"].category_path == ("인물", "인원수")

    jsonl = tmp_path / "tag_index.jsonl"
    db.write_jsonl(jsonl)
    loaded = GeneralTagDB.from_jsonl(jsonl)
    assert loaded.tags["gotoh hitori"].category_path == ("캐릭터",)


def test_inspect_prompt_keeps_original_order() -> None:
    result = inspect_prompt("long hair, 1girl", knowledge_base=_kb())

    assert [token.text for token in result.tokens] == ["long hair", "1girl"]
    assert [token.section.value for token in result.tokens] == ["general", "count"]


def test_animadex_csv_classifies_character_copyright_artist_and_core_tags(
    tmp_path: Path,
) -> None:
    characters = tmp_path / "characters.csv"
    artists = tmp_path / "artists.csv"
    characters.write_text(
        "character,copyright,trigger,core_tags,count,url\n"
        'hatsune_miku,vocaloid,"hatsune miku, vocaloid",'
        '"1girl, aqua eyes, twintails, detached sleeves",103500,'
        "https://danbooru.donmai.us/posts?tags=hatsune_miku\n",
        encoding="utf-8",
    )
    artists.write_text(
        "artist,trigger,count,url\n"
        "0-den,0-den,52,https://danbooru.donmai.us/posts?tags=0-den\n",
        encoding="utf-8",
    )

    db = AnimaDexDB.from_csvs(characters_csv=characters, artists_csv=artists)
    kb = PromptKnowledgeBase(animadex=db)
    result = correct_prompt(
        "twintails, vocaloid, @0-den, hatsune miku, 1girl",
        knowledge_base=kb,
    )

    assert result.text == "1girl, hatsune miku, vocaloid, @0-den, twintails"
    assert result.unknown_tags == ()
    assert [token.section.value for token in result.tokens] == [
        "count",
        "character",
        "copyright",
        "artist",
        "general",
    ]


def test_animadex_jsonl_index_round_trip(tmp_path: Path) -> None:
    characters = tmp_path / "characters.csv"
    artists = tmp_path / "artists.csv"
    characters.write_text(
        "character,copyright,trigger,core_tags,count,url\n"
        'hatsune_miku,vocaloid,"hatsune miku, vocaloid","1girl",103500,\n',
        encoding="utf-8",
    )
    artists.write_text(
        "artist,trigger,count,url\n0-den,0-den,52,\n",
        encoding="utf-8",
    )

    db = AnimaDexDB.from_csvs(characters_csv=characters, artists_csv=artists)
    character_index, artist_index = db.write_jsonl(tmp_path / "index")
    loaded = AnimaDexDB.from_jsonl(
        character_index=character_index,
        artist_index=artist_index,
    )

    assert "hatsune miku" in loaded.characters
    assert "vocaloid" in loaded.copyrights
    assert "1girl" in loaded.core_tags
    assert "0-den" in loaded.artists


class _FakeResponse:
    def __init__(self, data: bytes):
        self._data = data

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return self._data


def test_animadex_token_store_round_trip(tmp_path: Path) -> None:
    store = AnimaDexTokenStore(tmp_path / "token.json")
    store.save(AnimaDexImportToken(token="secret", site="https://animadex.example"))

    loaded = store.load()

    assert loaded is not None
    assert loaded.token == "secret"
    assert loaded.site == "https://animadex.example"


def test_animadex_import_downloads_csvs_to_import_dir(tmp_path: Path) -> None:
    requests = []
    manifest = (
        b'{"csv":{"characters":"https://r2.example/characters.csv",'
        b'"artists":"https://r2.example/artists.csv"}}'
    )

    def fake_open(request, timeout):
        requests.append((request, timeout))
        if request.full_url == "https://animadex.example/api/export/manifest?full=1":
            return _FakeResponse(manifest)
        if request.full_url == "https://r2.example/characters.csv":
            return _FakeResponse(b"character,copyright,trigger,core_tags,count,url\n")
        if request.full_url == "https://r2.example/artists.csv":
            return _FakeResponse(b"artist,trigger,count,url\n")
        raise AssertionError(request.full_url)

    client = AnimaDexImportClient(
        site="https://animadex.example",
        token="secret",
        opener=fake_open,
    )

    result = client.download_required_csvs(tmp_path / "animadex", full=True)

    assert result.characters_csv == tmp_path / "animadex" / "import" / "characters.csv"
    assert result.artists_csv == tmp_path / "animadex" / "import" / "artists.csv"
    assert result.characters_csv.read_text(encoding="utf-8").startswith("character")
    manifest_request = requests[0][0]
    assert manifest_request.headers["X-export-token"] == "secret"
