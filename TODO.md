# TODO

Issues noticed during a repository review (2026-07-04). Documented only — no changes made yet.

## 1. `datasette/metadata.yml` references the wrong table name

`datasette/metadata.yml` defines a table description under `databases.corning_historic_photos.tables.photos`, but the actual table in `datasette/corning_historic_photos.db` is named `historic_photos`. As a result, the table description likely never displays in the published Datasette instance.

**Fix:** Rename the `photos:` key to `historic_photos:` in `datasette/metadata.yml`.

## 2. `data/corning_photos.sqlite` is missing the `category` table

The README (Stage 4, Category Classification) states the classifier output CSV "is imported into both `data/corning_photos.sqlite` and `datasette/corning_historic_photos.db` as a `category` table." However, `data/corning_photos.sqlite` only contains `metadata`, `photo_description`, and `urls` — no `category` table. This also means `data/table_join.sql`, which joins against `category`, cannot run against that database as-is.

**Fix:** Either import the category assignments into `data/corning_photos.sqlite` (re-run `scripts/classify_photos.py` and import the resulting CSV), or correct the README to reflect where the category table actually lives.
