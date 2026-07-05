# TL;DR

*The essentials of this project. Full details in the [README](README.md).*

## What & Why

The [Corning, NY Local History Photo Archive](https://corningnyhistory.com/local-history-photo-archive/) is a collection of 1,977 digitized historical photographs (1842–1975) maintained by the Southeast Steuben County Library, covering floods, Corning Glass Works, schools, families, and civic life in the Chemung Valley. Before this project, 53% of its catalog records had no subject keywords and 70% had no date. This project used AI to give every photo descriptive tags, a one-sentence description, and one of 14 thematic categories — then verified and corrected that AI-generated layer. Browse the enriched catalog in [Datasette Lite](https://lite.datasette.io/?url=https://raw.githubusercontent.com/DaveKT/Corning-NY-Local-History-Photo-Archive/master/datasette/corning_historic_photos.db&metadata=https://raw.githubusercontent.com/DaveKT/Corning-NY-Local-History-Photo-Archive/master/datasette/metadata.yml#/).

## How It Works

**Cataloging** (four scripts): download all images from the archive website → extract technical metadata (dimensions, hashes) → send each photo to Claude Haiku for tags and a description → assign one of 14 categories by rule-based keyword matching.

**Refinement** (five stages): the original AI descriptions contained errors — wrong sports, misread objects, occasional gender/identity mistakes (GitHub issues #1–#32). A second pipeline fixed them: Claude Haiku fact-checks every record (transcribing photo captions as ground truth) → free rule-based triage flags suspect records → Claude Sonnet re-examines flagged photos at high resolution → a local web app routes identity-sensitive or ambiguous cases to a human → corrections are applied as an auditable overlay (old value, new value, source, timestamp per change). The pipeline was calibrated against the known errors before the full run: 100% recall, ~6% of clean photos needing human eyes.

## Results

- All 1,977 photos have reviewed tags, descriptions, and categories.
- The full refinement run: 557 records auto-confirmed, 1,420 adjudicated by Sonnet, 283 human-reviewed. **2,437 field corrections** applied across 1,313 photos.
- All 32 reported catalog errors fixed in the published data; every issue closed.
- Published as an interactive Datasette instance with full-text search and a combined CSV export.

## Cost

- Original AI cataloging (Claude Haiku, all 1,977 photos): **~$5**
- Refinement pipeline (verification, adjudication, calibration): **~$27**
- **Total: ~$32** in model usage — plus one human review session of 283 photos.
