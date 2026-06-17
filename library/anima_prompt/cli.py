"""CLI for ANIMA prompt/caption inspection and correction."""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

from .animadex import (
    ANIMADEX_DEFAULT_DATA_DIR,
    ANIMADEX_INDEX_DIR_NAME,
    AnimaDexDB,
    AnimaDexImportClient,
    AnimaDexImportError,
    AnimaDexImportToken,
    AnimaDexTokenStore,
    default_token_path,
    resolve_import_token,
)
from .correction import correct_prompt, inspect_prompt
from .knowledge import GeneralTagDB, KnowledgeBaseNotFound, load_knowledge_base


def _load_input(args) -> str:
    if args.text is not None:
        return args.text
    if args.file:
        return Path(args.file).read_text(encoding="utf-8")
    return sys.stdin.read()


def _add_db_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--tag-csv", default=None)
    parser.add_argument("--tag-index", default=None)
    parser.add_argument("--animadex-characters-csv", default=None)
    parser.add_argument("--animadex-artists-csv", default=None)
    parser.add_argument("--animadex-character-index", default=None)
    parser.add_argument("--animadex-artist-index", default=None)


def _load_kb(args):
    return load_knowledge_base(
        tag_csv=args.tag_csv,
        tag_index=args.tag_index,
        animadex_characters_csv=args.animadex_characters_csv,
        animadex_artists_csv=args.animadex_artists_csv,
        animadex_character_index=args.animadex_character_index,
        animadex_artist_index=args.animadex_artist_index,
    )


def cmd_build_index(args) -> int:
    db = GeneralTagDB.from_csv(args.tag_csv)
    db.write_jsonl(args.output)
    print(f"wrote {len(db.tags)} tags to {args.output}")
    return 0


def cmd_build_animadex_index(args) -> int:
    db = AnimaDexDB.from_csvs(
        characters_csv=args.characters_csv,
        artists_csv=args.artists_csv,
    )
    character_path, artist_path = db.write_jsonl(args.output_dir)
    print(f"wrote {len(db.character_records)} characters to {character_path}")
    print(f"wrote {len(db.artist_records)} artists to {artist_path}")
    return 0


def cmd_animadex_save_token(args) -> int:
    token = args.token or getpass.getpass("AnimaDex export token: ")
    token = token.strip()
    if not token:
        print("empty token", file=sys.stderr)
        return 2
    store = AnimaDexTokenStore(
        Path(args.token_file) if args.token_file else default_token_path()
    )
    store.save(AnimaDexImportToken(token=token, site=args.site))
    print(f"token saved to {store.path}")
    return 0


def cmd_animadex_import(args) -> int:
    try:
        import_token = resolve_import_token(
            token=args.token,
            token_file=args.token_file,
        )
        site = args.site or import_token.site
        client = AnimaDexImportClient(site=site, token=import_token.token)
        output_dir = Path(args.output_dir)
        result = client.download_required_csvs(output_dir, full=args.full)
        if args.save_token:
            store = AnimaDexTokenStore(
                Path(args.token_file) if args.token_file else default_token_path()
            )
            store.save(AnimaDexImportToken(token=import_token.token, site=site))
    except AnimaDexImportError as e:
        print(str(e), file=sys.stderr)
        return 2

    print(f"characters: {result.characters_csv}")
    print(f"artists: {result.artists_csv}")
    if args.build_index:
        db = AnimaDexDB.from_csvs(
            characters_csv=result.characters_csv,
            artists_csv=result.artists_csv,
        )
        index_dir = Path(args.index_dir) if args.index_dir else output_dir / ANIMADEX_INDEX_DIR_NAME
        character_path, artist_path = db.write_jsonl(index_dir)
        print(f"character index: {character_path}")
        print(f"artist index: {artist_path}")
    return 0


def cmd_check(args) -> int:
    try:
        kb = _load_kb(args)
    except KnowledgeBaseNotFound as e:
        print(str(e), file=sys.stderr)
        return 2
    text = _load_input(args)
    result = inspect_prompt(text, profile=args.profile, knowledge_base=kb)
    for token in result.tokens:
        path = " > ".join(token.category_path) if token.category_path else "-"
        print(f"{token.text}\t{token.section.value}\t{path}")
    if result.unknown_tags:
        print("unknown:", ", ".join(result.unknown_tags), file=sys.stderr)
        return 1
    return 0


def cmd_fix(args) -> int:
    try:
        kb = _load_kb(args)
    except KnowledgeBaseNotFound as e:
        print(str(e), file=sys.stderr)
        return 2
    text = _load_input(args)
    result = correct_prompt(text, profile=args.profile, knowledge_base=kb)
    if args.in_place:
        if not args.file:
            print("--in-place requires --file", file=sys.stderr)
            return 2
        Path(args.file).write_text(result.text, encoding="utf-8")
    else:
        print(result.text)
    for warning in result.warnings:
        print(warning, file=sys.stderr)
    return 1 if result.unknown_tags and args.fail_on_unknown else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    build = sub.add_parser("build-index", help="Build tag_index.jsonl from CSV")
    build.add_argument("--tag-csv", required=True)
    build.add_argument("--output", required=True)
    build.set_defaults(func=cmd_build_index)

    build_animadex = sub.add_parser(
        "build-animadex-index",
        help="Build character_index.jsonl and artist_index.jsonl from AnimaDex CSVs",
    )
    build_animadex.add_argument("--characters-csv", required=True)
    build_animadex.add_argument("--artists-csv", required=True)
    build_animadex.add_argument("--output-dir", required=True)
    build_animadex.set_defaults(func=cmd_build_animadex_index)

    save_token = sub.add_parser(
        "animadex-save-token",
        help="Save an animadex.net offline export token outside the repository",
    )
    save_token.add_argument("--token", default=None)
    save_token.add_argument("--token-file", default=None)
    save_token.add_argument("--site", default="https://animadex.net")
    save_token.set_defaults(func=cmd_animadex_save_token)

    import_cmd = sub.add_parser(
        "animadex-import",
        help="Download AnimaDex characters.csv and artists.csv with an export token",
    )
    import_cmd.add_argument("--token", default=None)
    import_cmd.add_argument("--token-file", default=None)
    import_cmd.add_argument("--site", default=None)
    import_cmd.add_argument("--output-dir", default=str(ANIMADEX_DEFAULT_DATA_DIR))
    import_cmd.add_argument("--full", action="store_true")
    import_cmd.add_argument("--save-token", action="store_true")
    import_cmd.add_argument("--build-index", action="store_true")
    import_cmd.add_argument("--index-dir", default=None)
    import_cmd.set_defaults(func=cmd_animadex_import)

    for name, func in (("check", cmd_check), ("fix", cmd_fix)):
        p = sub.add_parser(name)
        _add_db_args(p)
        p.add_argument("--profile", choices=("prompt", "caption"), default="prompt")
        p.add_argument("--text", default=None)
        p.add_argument("--file", default=None)
        if name == "fix":
            p.add_argument("--in-place", action="store_true")
            p.add_argument("--fail-on-unknown", action="store_true")
        p.set_defaults(func=func)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
