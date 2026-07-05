# Feature Spec: Image Thumbnails in Datasette Lite

**Status:** Proposed — not yet built
**Created:** 2026-07-05
**Updated:** 2026-07-05 — added Option A (GitHub-hosted thumbnails, preferred, pending library permission)

## Summary

Add an optional table view to the published Datasette Lite instance that
displays each photograph as an inline thumbnail alongside its catalog
record. Browsing the catalog today shows only text and a bare URL; seeing
the image next to its tags, description, and category makes review and
discovery dramatically easier.

This view is **opt-in, not the default**. The default browsing experience
(the `historic_photos` table) is unchanged.

Two designs, sharing the same rendering mechanics. **Option A is
preferred** and depends on the library's permission; Option B is the
fallback requiring no permission.

## Shared mechanics

### Rendering plugin

Datasette Lite can install pure-Python plugins at load time via a URL
parameter. [`datasette-json-html`](https://datasette.io/plugins/datasette-json-html)
renders cells containing a JSON payload as HTML: `{"img_src": ...,
"width": ...}` becomes an `<img>` tag, and adding `"href"` wraps it in a
link.

Lite URL gains: `?install=datasette-json-html` (alongside the existing
`url=` and `metadata=` parameters).

### SQL view

A `photos_with_images` view in `datasette/corning_historic_photos.db`
adds a JSON `photo` column; the base table stays untouched. The view is
an additional entry in the Datasette table list, described in
`datasette/metadata.yml`. It must be recreated if the database is ever
rebuilt from `data/table_join.sql`.

### README

Add a second Datasette Lite link ("browse with image thumbnails")
pointing at the view with `?install=datasette-json-html`. Keep the
existing text-only link as the primary one.

## Option A — GitHub-hosted thumbnails (preferred; requires library permission)

Generate ~300px thumbnails from the local full-resolution copies and
commit them to the repository; serve them the same way Datasette Lite
already loads the database file. Clicking a thumbnail opens the
full-resolution original on the library's site, which remains the
canonical home of the images.

- **Generation.** Pillow script over `data/photos/` → `thumbnails/`
  (JPEG, ~300px longest side, quality ~75). Mostly-monochrome scans come
  out at ~10–25 KB each; all 1,977 total **~30–40 MB**, well within
  comfortable repository size.
- **Serving.** `https://raw.githubusercontent.com/DaveKT/Corning-NY-Local-History-Photo-Archive/master/thumbnails/<filename>`
  — GitHub serves correct image content types from a CDN; bandwidth at
  this scale is a non-issue. No load lands on the library's server for
  browsing.
- **View column.**

  ```sql
  json_object(
    'img_src', 'https://raw.githubusercontent.com/DaveKT/Corning-NY-Local-History-Photo-Archive/master/thumbnails/' || filename,
    'href', url,          -- full resolution, on the library's site
    'width', 200
  ) AS photo
  ```

- **Page weight.** ~15 KB per row means even a 100-row page is ~1.5 MB;
  no page-size guardrail needed.
- **Permission & licensing (prerequisite).** The photographs are the
  property of the Southeast Steuben County Library and the
  Corning-Painted Post Historical Society; thumbnails are derivatives.
  Written permission from the library is required before committing
  them. On inclusion, update README and LICENSE-DATA to record that the
  thumbnails are included with the library's permission and remain under
  the library's rights (not covered by the repository's CC BY 4.0 data
  license).

## Option B — Hotlink the library's images (fallback; no permission needed)

Point `img_src` directly at the existing `url` column:

```sql
json_object('img_src', url, 'width', 200) AS photo
```

- **Bandwidth.** The URLs are full-resolution originals (~270 KB
  average). A 100-row page ≈ 25 MB pulled from the library's server.
  Mitigations: link with `?_size=20` and note the cost in the view
  description.
- **Thumbnail variants.** WordPress typically generates resized variants
  (e.g., `lh-75-0001-300x225.jpg`). If those exist on
  corningnyhistory.com, using them would cut bandwidth ~90%. **Must be
  verified before relying on it** (spot-check variant URLs across all
  three series; fall back to originals for any 404s).
- **Hotlinking courtesy.** Images load in visitors' browsers directly
  from the library's server — the same pattern as browsing the archive
  site, but denser per page. Worth a heads-up to the library if the view
  gets promoted.

## Shared considerations

- **Plugin compatibility.** `datasette-json-html` is pure Python and
  known to work in Datasette Lite, but verify against the current Lite
  version at build time (including the `href` + `img_src` combination).

## Implementation steps

1. Seek the library's permission for repository-hosted thumbnails
   (Option A). If declined or unanswered, proceed with Option B.
2. **Option A:** write the thumbnail-generation script (idempotent,
   documented), generate `thumbnails/`, commit, and update README /
   LICENSE-DATA with the permission language.
   **Option B:** spot-check WordPress thumbnail variant URLs; decide
   originals vs. variants for `img_src`.
3. Create the `photos_with_images` view in
   `datasette/corning_historic_photos.db` (idempotent script or a
   documented one-liner).
4. Add the view description to `datasette/metadata.yml`.
5. Add the thumbnail-browsing link to the README (Datasette section)
   with `?install=datasette-json-html` (Option B also adds `?_size=20`).
6. Verify end to end in Datasette Lite: rendering, click-through to the
   library originals, facets, FTS, page load weight.

## Out of scope

- Making the image view the default table.
- Storing full-resolution images or image blobs in the repository or
  database.
- Any change to the base `historic_photos` table schema.
