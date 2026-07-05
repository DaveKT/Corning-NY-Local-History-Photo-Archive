# TODO

Nothing outstanding.

## Resolved

### 1. `datasette/metadata.yml` referenced the wrong table name — resolved 2026-07-05

The table description was keyed `photos`, but the table in
`datasette/corning_historic_photos.db` is named `historic_photos`, so the
description never displayed in the published Datasette instance.
**Fix:** renamed the key to `historic_photos` (and refreshed the description
to mention the verification pipeline and category column).

### 2. `data/corning_photos.sqlite` was missing the `category` table — resolved 2026-07-05

The README stated the classifier output is imported into both databases,
but the working database had no `category` table, which also meant
`data/table_join.sql` could not run against it.
**Fix:** created the `category` table (1,977 rows, from the corrected
post-refinement categories), verified `table_join.sql` joins all 1,977
rows, and updated `scripts/apply_corrections.py` to apply future category
corrections to it.
