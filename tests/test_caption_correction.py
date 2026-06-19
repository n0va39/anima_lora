from __future__ import annotations

from pathlib import Path

from library.captioning.correction import (
    CaptionCorrectionOptions,
    correct_caption,
    load_tag_knowledge_base,
)


def _csv(path: Path) -> Path:
    path.write_text(
        "\n".join(
            [
                "name,category,post_count,description",
                '1girl,0,10,"[인물 > 인원수] count"',
                'solo,0,10,"[인물 > 인원수] count"',
                'hatsune_miku,4,10,"[캐릭터 > vocaloid] character"',
                'vocaloid,3,10,"[작품 > series] copyright"',
                'sincos,1,10,"[작가 > illustrator] artist"',
                'best_quality,5,10,"[메타 > 화질] quality"',
                'long_hair,0,10,"[머리카락 > 머리 길이] general"',
                'copyright_notice,0,10,"[메타 > 정보_요청] misleading description"',
            ]
        ),
        encoding="utf-8",
    )
    return path


def test_correct_caption_orders_known_sections_and_preserves_general_order(tmp_path):
    kb = load_tag_knowledge_base(_csv(tmp_path / "tags.csv"))
    result = correct_caption(
        "long hair, vocaloid, @sincos, hatsune miku, 1girl, best quality",
        kb,
        options=CaptionCorrectionOptions(insert_no_artist=True),
    )

    assert result.text == (
        "best quality, 1girl, hatsune miku, vocaloid, @sincos, long hair"
    )
    assert result.changed
    assert not result.inserted_no_artist


def test_correct_caption_inserts_no_artist_at_artist_position(tmp_path):
    kb = load_tag_knowledge_base(_csv(tmp_path / "tags.csv"))
    result = correct_caption("long hair, vocaloid, hatsune miku, solo", kb)

    assert result.text == "solo, hatsune miku, vocaloid, @no-artist, long hair"
    assert result.inserted_no_artist


def test_artist_validation_keeps_unknown_at_tag_in_general_tail(tmp_path):
    kb = load_tag_knowledge_base(_csv(tmp_path / "tags.csv"))
    result = correct_caption(
        "@trigger-word, hatsune miku, vocaloid, 1girl",
        kb,
        options=CaptionCorrectionOptions(
            insert_no_artist=True,
            validate_artist_tags=True,
        ),
    )

    assert result.text == (
        "1girl, hatsune miku, vocaloid, @no-artist, @trigger-word"
    )


def test_artist_validation_does_not_reclassify_at_prefixed_character(tmp_path):
    kb = load_tag_knowledge_base(_csv(tmp_path / "tags.csv"))
    result = correct_caption(
        "@hatsune miku, vocaloid, 1girl",
        kb,
        options=CaptionCorrectionOptions(
            insert_no_artist=True,
            validate_artist_tags=True,
        ),
    )

    assert result.text == "1girl, vocaloid, @no-artist, @hatsune miku"


def test_numeric_category_wins_over_description_prefix(tmp_path):
    kb = load_tag_knowledge_base(_csv(tmp_path / "tags.csv"))
    result = correct_caption(
        "copyright notice, hatsune miku, vocaloid, 1girl",
        kb,
    )

    assert result.text == (
        "1girl, hatsune miku, vocaloid, @no-artist, copyright notice"
    )
