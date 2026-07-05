#!/usr/bin/env python3
"""
Stage E of the description-refinement pipeline: apply the corrections overlay.

Reads correction entries (produced automatically by adjudicate_photos.py and
by humans via review_app.py) and applies them to the databases:

  - datasette/corning_historic_photos.db  (historic_photos: tags,
    description, category; the FTS index is rebuilt afterwards)
  - data/corning_photos.sqlite            (photo_description: Tags,
    Description — this database has no category table)

Each correction records the value it expects to replace ("old"). If the
database value matches "new" already, the entry is skipped (idempotent
re-runs). If it matches neither "old" nor "new", the entry is reported and
skipped, so a stale overlay can never silently clobber newer data.

Human corrections win over automatic ones when both touch the same field.

Usage:
    python scripts/apply_corrections.py [--dry-run]
"""

import argparse
import json
import sqlite3
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_AUTO = REPO_ROOT / "data" / "refinement" / "corrections_auto.json"
DEFAULT_HUMAN = REPO_ROOT / "data" / "refinement" / "corrections.json"
DATASETTE_DB = REPO_ROOT / "datasette" / "corning_historic_photos.db"
WORKING_DB = REPO_ROOT / "data" / "corning_photos.sqlite"

FIELDS = ("tags", "description", "category")


def load_corrections(auto_path: Path, human_path: Path) -> dict:
    """Merge corrections keyed by (lh, field); human entries win."""
    merged = {}
    for path, source in ((auto_path, "auto"), (human_path, "human")):
        if not path.exists():
            continue
        for c in json.loads(path.read_text()):
            if c.get("field") not in FIELDS:
                print(f"warning: skipping unknown field in {path.name}: {c}")
                continue
            key = (c["lh"], c["field"])
            if key in merged and merged[key]["source"] == "human" \
                    and c.get("source") != "human":
                continue
            merged[key] = c
    return merged


def apply_to_db(db_path: Path, table: str, colmap: dict,
                key_col: str, corrections: dict, dry_run: bool) -> tuple:
    """Apply corrections to one database. Returns (applied, skipped, stale)."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    applied = skipped = stale = 0

    for (lh, field), c in sorted(corrections.items()):
        if field not in colmap:
            continue
        col = colmap[field]
        rows = cur.execute(
            f'SELECT "{col}" FROM {table} WHERE {key_col} = ?', (lh,)
        ).fetchall()
        if not rows:
            print(f"  stale: {lh} not found in {db_path.name}")
            stale += 1
            continue
        current_values = {r[0] for r in rows}
        if current_values == {c["new"]}:
            skipped += 1  # already applied
            continue
        if c["old"] not in current_values:
            print(f"  stale: {lh}.{field} in {db_path.name} is "
                  f"{list(current_values)[0]!r}, expected {c['old']!r}")
            stale += 1
            continue
        if not dry_run:
            cur.execute(
                f'UPDATE {table} SET "{col}" = ? WHERE {key_col} = ?',
                (c["new"], lh))
        applied += 1

    if not dry_run:
        conn.commit()
    conn.close()
    return applied, skipped, stale


def main():
    parser = argparse.ArgumentParser(
        description="Apply the corrections overlay to the databases.")
    parser.add_argument("--auto", default=str(DEFAULT_AUTO))
    parser.add_argument("--human", default=str(DEFAULT_HUMAN))
    parser.add_argument("--datasette-db", default=str(DATASETTE_DB))
    parser.add_argument("--working-db", default=str(WORKING_DB))
    parser.add_argument("--dry-run", action="store_true",
                        help="Report what would change without writing.")
    args = parser.parse_args()

    corrections = load_corrections(Path(args.auto), Path(args.human))
    if not corrections:
        print("No corrections to apply.")
        return
    by_source = {}
    for c in corrections.values():
        by_source[c["source"]] = by_source.get(c["source"], 0) + 1
    print(f"Loaded {len(corrections)} corrections "
          f"({', '.join(f'{v} {k}' for k, v in sorted(by_source.items()))})"
          f"{' [dry run]' if args.dry_run else ''}\n")

    print(f"Datasette DB ({args.datasette_db}):")
    a1, s1, st1 = apply_to_db(
        Path(args.datasette_db), "historic_photos",
        {"tags": "tags", "description": "description",
         "category": "category"},
        "LHNo", corrections, args.dry_run)
    print(f"  applied {a1}, already current {s1}, stale {st1}")

    if not args.dry_run and a1:
        conn = sqlite3.connect(args.datasette_db)
        conn.execute("INSERT INTO historic_photos_fts(historic_photos_fts) "
                     "VALUES('rebuild')")
        conn.commit()
        conn.close()
        print("  FTS index rebuilt")

    print(f"Working DB ({args.working_db}):")
    a2, s2, st2 = apply_to_db(
        Path(args.working_db), "photo_description",
        {"tags": "Tags", "description": "Description"},
        "LHNo", corrections, args.dry_run)
    print(f"  applied {a2}, already current {s2}, stale {st2}")
    print("  (category corrections don't apply here: no category table)")

    print("\nDone." if not args.dry_run
          else "\nDry run complete — nothing written.")


if __name__ == "__main__":
    main()
