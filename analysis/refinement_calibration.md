# Description-Refinement Pipeline: Calibration Report

**Date:** 2026-07-04

This document records the calibration of the AI-description refinement
pipeline (scripts/verify_photos.py → triage_photos.py →
adjudicate_photos.py → review_app.py → apply_corrections.py) against a
ground-truth set before running it over the full collection.

## Calibration set

`data/calibration_set.json`:

- **72 known-bad photos** — every photo referenced by GitHub issues #1–#32
  (confirmed catalog errors: wrong sports, misidentified objects and
  settings, gender/identity errors, wrong categories).
- **70 known-good controls** — random sample (seed 42) of photos with no
  reported errors. Note: "known-good" means *unreviewed*, not verified
  clean; some genuinely contain minor inaccuracies.

## Verifier prompt iterations (Stage A, Claude Haiku, 1024px, ~$0.45/run)

| Run | Prompt change | Recall (known-bad flagged) | False-flag rate (controls) |
|-----|---------------|---------------------------:|---------------------------:|
| 1 | "Audit and correct the record" | 100% | 100% — useless; model rewrote everything for style/caution |
| 2 | Contradiction-only fact-checking; corrections require an enumerated error | 83% | 87% — stopped rewriting, but pedantic errors flagged and category-only errors missed |
| 3 | + material/minor severity, category audit, primary-subject and garbled-text checks | 97% | 79% |
| 4 | + severity "gist test" with concrete examples | 93% | 64% |
| 5 | + caption transcription (captions are authoritative) | **100%** | **64%** |

Two-run ensemble (runs 4+5, noisy signals require agreement): 99% recall,
57% false flags. Rejected: the extra Haiku pass roughly cancels out the
Sonnet savings, and the disagreement gate drops the hardest true positive
(75-0375, a felled tree that reads as a dirt road).

**Key lessons**

1. Asking a model to "audit and improve" makes it rewrite everything.
   Asking it to enumerate *contradictions between image and record*, with
   corrections only for enumerated errors, is what makes verification
   meaningful.
2. Category errors are invisible to text verification — the category must
   be audited explicitly against the schema.
3. Captions on the photograph are ground truth and must be transcribed
   and compared (this caught 75-1623, a "glass works" that the caption
   identifies as a brick, terra cotta & tile works).
4. Severity needs an operational test ("would the fix change the
   one-sentence gist?") with concrete examples, or everything is graded
   material.

## Triage (Stage B, free)

Flags fire on: material description/tags errors, category change proposed
by the verifier, category flip from re-running the deterministic
classifier on corrected text, low confidence (<0.85), doubts, and
unconditional lexicon rules for group-identity and risky-object terms.
Gendered language marks a record identity-sensitive without flagging it.

## Adjudication (Stage C, Claude Sonnet, 1568px, ~$0.013/photo measured)

Funnel on the calibration set (111 flagged photos):

- 6 records upheld, 30 photos auto-corrected (58 field changes),
  75 routed to human review.
- **All 72 issue photos route to human** via `--force-human
  data/refinement/issue_overrides.json` — archival knowledge (e.g., issue
  #21: those "schoolhouses" may just be buildings) can contradict what a
  model sees, so open-issue photos are never auto-resolved.
- Only **4 of 70 controls (5.7%)** reached the human queue after the
  identity gate was made diff-based (a change must alter identity terms,
  not merely touch a record containing them) and the auto-resolve
  threshold set to Sonnet's modal confidence (0.85). Identity changes and
  Sonnet-declared ambiguity route to humans regardless of confidence.

## Full-collection run (2026-07-05): projection vs. actual

| Metric | Projected | Actual |
|--------|----------:|-------:|
| Flagged at triage | 60–65% | 72% (1,420 of 1,977) |
| Stage A cost (Haiku) | ~$4 | ~$5 |
| Stage C cost (Sonnet) | ~$20–25 | ~$18 (1,310 new calls, ~$0.013 each) |
| Human queue | ~180 photos | 283 photos (72 issue + 211 others) |
| Total model cost | ~$25–30 | **~$27** (incl. ~$4 calibration) |

The human queue overshot the control-based projection (11% of non-issue
photos vs. 5.7% in the controls) — the collection proved error-richer than
the random control sample suggested, which also pushed the flag rate up.

Final outcomes: 98 flagged records upheld by the adjudicator, 1,039 photos
auto-corrected, 283 human-reviewed in the app (200 proposals accepted, 75
edited before saving, 8 originals kept). In total **2,437 field
corrections** (1,221 descriptions, 767 tags, 449 categories) were applied
across 1,313 photos, and all 32 GitHub issues were resolved in the
published data and closed.

## Production notes

Two robustness problems surfaced during the full run, both now handled:

1. **Token limits.** Photos containing long printed documents or captions
   produced responses that hit the output cap mid-JSON. `max_tokens` was
   raised (600 → 1000 for the verifier, 700 → 1200 for the adjudicator).
2. **Invalid JSON quirks.** Two recurring patterns are repaired by the
   shared parser (`repair_candidates` in verify_photos.py): a
   parenthesized annotation after a string value
   (`"CORNING" (visible on drum),`) and unescaped double quotes inside a
   string value (quoted document text). After both fixes, the full run
   completed with zero unparsed responses.

## Correction flow

Corrections are an overlay, never in-place edits: `corrections_auto.json`
(Sonnet) and `corrections.json` (human, written by the review app), applied
by `apply_corrections.py`, which verifies the expected old value before
writing, skips already-applied entries, rebuilds the FTS index, and reports
stale entries instead of overwriting newer data.
