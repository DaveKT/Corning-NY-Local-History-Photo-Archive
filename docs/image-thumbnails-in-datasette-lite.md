# Feature Spec: Image Thumbnails in Datasette Lite

**Status:** Proposed — not yet built
**Created:** 2026-07-05

## Summary

Add an optional table view to the published Datasette Lite instance that
displays each photograph as an inline thumbnail alongside its catalog
record. Browsing the catalog today shows only text and a bare URL; seeing
the image next to its tags, description, and category makes review and
discovery dramatically easier.

This view is **opt-in, not the default**. The default browsing experience
(the `historic_photos` table) is unchanged.

## Design

### 1. Rendering plugin

Datasette Lite can install pure-Python plugins at load time via a URL
parameter. [`datasette-json-html`](https://datasette.io/plugins/datasette-json-html)
renders cells containing a JSON payload of the form
`{"img_src": "<url>", "width": 200}` as an `<img>` tag.

Lite URL gains: `?install=datasette-json-html` (alongside the existing
`url=` and `metadata=` parameters).

### 2. SQL view (in `datasette/corning_historic_photos.db`)

```sql
CREATE VIEW photos_with_images AS
SELECT
  LHNo,
  json_object('img_src', url, 'width', 200) AS photo,
  subject,
  date,
  tags,
  description,
  category,
  url
FROM historic_photos;
```

The base table stays untouched; the view is an additional entry in the
Datasette table list. Add a description for it in `datasette/metadata.yml`
noting the bandwidth implications.

### 3. README

Add a second Datasette Lite link ("browse with image thumbnails") pointing
at the view with `?install=datasette-json-html` and a constrained page
size (see below). Keep the existing text-only link as the primary one.

## Considerations

- **Bandwidth.** The `url` column points at full-resolution originals
  (~270 KB average). A 100-row page ≈ 25 MB pulled from the library's
  server. Mitigations: link with `?_size=20`, and note the cost in the
  view description.
- **Thumbnail variants.** WordPress typically generates resized variants
  (e.g., `lh-75-0001-300x225.jpg`). If those exist on
  corningnyhistory.com, switching `img_src` to a variant URL would cut
  bandwidth ~90%. **Must be verified before relying on it** (spot-check a
  sample of variant URLs across all three series; fall back to originals
  for any 404s).
- **Hotlinking courtesy.** Images load in visitors' browsers directly
  from the library's server. Same pattern as browsing the archive site,
  but denser per page. Worth a heads-up to the library if the view gets
  promoted; consider `loading="lazy"` if the plugin supports attribute
  passthrough (it does not today — page size is the lever).
- **Plugin compatibility.** `datasette-json-html` is pure Python and
  known to work in Datasette Lite, but verify against the current Lite
  version at build time.

## Implementation steps

1. Spot-check WordPress thumbnail variant URLs; decide originals vs.
   variants for `img_src`.
2. Create the `photos_with_images` view in
   `datasette/corning_historic_photos.db` (idempotent script or a
   documented one-liner; the view must be recreated if the database is
   ever rebuilt from `table_join.sql`).
3. Add the view description to `datasette/metadata.yml`.
4. Add the thumbnail-browsing link to the README (Datasette section),
   with `?install=datasette-json-html` and `?_size=20`.
5. Verify end to end in Datasette Lite: rendering, facets, FTS, page
   load weight.

## Out of scope

- Making the image view the default table.
- Storing image blobs or generated thumbnails in the repository or
  database.
- Any change to the base `historic_photos` table schema.
