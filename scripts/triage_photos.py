#!/usr/bin/env python3
"""
Stage B of the description-refinement pipeline: deterministic triage.

Reads the verification results produced by scripts/verify_photos.py, applies
rule-based flagging (no API calls, no cost), and splits photos into:

  - auto-confirm : verifier agreed with the record at high confidence
  - flagged      : proposed change, low confidence, unverifiable claims,
                   category flip, or uncorroborated sensitive vocabulary

Outputs a CSV report (all photos, one row each, with flag reasons) and a
JSON review queue (flagged photos only) for the adjudication/review stages.

With --calibration, also scores the pipeline against the known-bad photos
from the GitHub issues and the known-good control sample:

    python scripts/triage_photos.py \
        --results data/refinement/verification_results.json \
        --calibration data/calibration_set.json

Uses only the standard library plus the classifier in classify_photos.py.
"""

import argparse
import csv
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from classify_photos import classify  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = REPO_ROOT / "datasette" / "corning_historic_photos.db"
DEFAULT_RESULTS = REPO_ROOT / "data" / "refinement" / "verification_results.json"
DEFAULT_REPORT = REPO_ROOT / "data" / "refinement" / "triage_report.csv"
DEFAULT_QUEUE = REPO_ROOT / "data" / "refinement" / "review_queue.json"

CONFIDENCE_THRESHOLD = 0.85

# ---------------------------------------------------------------------------
# Sensitive-vocabulary lexicons, derived from the error classes documented in
# GitHub issues #1-#32. A term appearing in the machine-generated text without
# support from the human-entered Subject field is treated as suspect.
# ---------------------------------------------------------------------------

SPORT_TERMS = [
    "baseball", "basketball", "football", "tennis", "golf", "track team",
    "swimming", "hockey", "lacrosse", "soccer",
]

GROUP_IDENTITY_TERMS = [
    "native american", "indian", "african american", "black man", "black woman",
    "asian", "chinese", "japanese", "italian", "irish", "immigrant",
]

RISKY_OBJECT_TERMS = [
    "beach", "swimming pool", "pool;", "sphere", "poster", "schoolhouse",
    "religious procession", "pacific ocean",
]

# Gendered vocabulary is too common to flag on its own (it appears in most
# people photos). Instead its presence marks a record as identity-sensitive:
# if the record is flagged for any other reason, it must be routed to a human
# rather than auto-resolved by the adjudicator model.
GENDER_TERMS = [
    "woman", "women", "man;", "man ", "men;", "men ", "girl", "boy",
    "lady", "ladies", "gentleman", "gentlemen", "female", "male",
]


def load_records(db_path: Path) -> dict:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT LHNo, filename, subject, date, tags, description, category "
        "FROM historic_photos"
    ).fetchall()
    conn.close()
    return {r["LHNo"]: dict(r) for r in rows}


def contains_term(text: str, terms: list[str]) -> list[str]:
    text = f" {text.lower()} "
    return [t for t in terms if t in text]


# Signal kinds used by ensemble gating. "Precise" signals fire from either
# run alone; the noisier ones must agree across both runs to flag.
PRECISE_SIGNALS = {"tags_error", "category_change", "verifier_error"}


def signal_kinds(record: dict, result: dict) -> set:
    """Reduce one verification result to its set of signal kinds."""
    if "error" in result:
        return {"verifier_error"}
    kinds = set()
    if not result.get("description_ok", True):
        kinds.add("description_error")
    if not result.get("tags_ok", True):
        kinds.add("tags_error")
    if (not result.get("category_ok", True)
            and result.get("suggested_category")
            and result["suggested_category"] != record.get("category")):
        kinds.add("category_change")
    if result.get("confidence", 0.0) < CONFIDENCE_THRESHOLD:
        kinds.add("low_confidence")
    if result.get("doubts"):
        kinds.add("doubts")
    return kinds


def triage_one(record: dict, result: dict, result2: dict | None = None) -> dict:
    """Apply flag rules to one photo. Returns a triage row.

    When result2 (an independent second verification run) is provided,
    ensemble gating applies: noisy signals (description errors, low
    confidence, doubts) must appear in BOTH runs to flag; precise signals
    (tags errors, category changes) flag from either run; lexicon rules
    always flag.
    """
    baseline_text = f"{record.get('tags') or ''}; {record.get('description') or ''}"
    subject = (record.get("subject") or "").lower()

    reasons = []

    if "error" in result:
        reasons.append("verifier_error")
        proposed_tags = record.get("tags")
        proposed_desc = record.get("description")
        confidence = 0.0
        sensitive = []
        doubts = []
        material_errors = []
        minor_errors = []
        suggested_category = None
    else:
        proposed_tags = (result.get("corrected_tags") or record.get("tags")
                         if not result.get("tags_ok") else record.get("tags"))
        proposed_desc = (result.get("corrected_description")
                         or record.get("description")
                         if not result.get("description_ok")
                         else record.get("description"))
        confidence = result.get("confidence", 0.0)
        sensitive = result.get("sensitive_claims", [])
        doubts = result.get("doubts", [])
        all_errors = result.get("errors", [])
        material_errors = [e for e in all_errors
                           if e.get("severity") != "minor"]
        minor_errors = [e for e in all_errors if e.get("severity") == "minor"]
        suggested_category = (result.get("suggested_category")
                              if not result.get("category_ok", True) else None)

        if not result.get("description_ok"):
            reasons.append("description_error")
        if not result.get("tags_ok"):
            reasons.append("tags_error")
        if suggested_category and suggested_category != record.get("category"):
            reasons.append(f"category_change({record.get('category')} -> "
                           f"{suggested_category})")
        if confidence < CONFIDENCE_THRESHOLD:
            reasons.append(f"low_confidence({confidence:.2f})")
        if doubts:
            reasons.append(f"doubts({len(doubts)})")

    # Category flip: re-run the deterministic classifier on the proposed text.
    new_category = classify(record["LHNo"], record.get("subject"),
                            proposed_tags, proposed_desc)
    if new_category != record.get("category"):
        reasons.append(f"category_flip({record.get('category')} -> {new_category})")
    if suggested_category:
        new_category = suggested_category

    # Uncorroborated sensitive vocabulary in the baseline machine text.
    # Group-identity and risky-object terms flag unconditionally: these are
    # exactly the error classes where the verifier itself has been shown to
    # confirm bad records at high confidence.
    for label, terms in (("group_identity", GROUP_IDENTITY_TERMS),
                         ("risky_object", RISKY_OBJECT_TERMS)):
        hits = contains_term(baseline_text, terms)
        uncorroborated = [t for t in hits if t not in subject]
        if uncorroborated:
            reasons.append(f"lexicon_{label}({','.join(uncorroborated)})")
    # Sport terms are common in legitimate records; they flag only when the
    # verifier did not explicitly confirm both fields at high confidence.
    sport_hits = [t for t in contains_term(baseline_text, SPORT_TERMS)
                  if t not in subject]
    if sport_hits and "error" not in result:
        confirmed = (result.get("description_ok")
                     and result.get("tags_ok")
                     and confidence >= CONFIDENCE_THRESHOLD)
        if not confirmed:
            reasons.append(f"lexicon_sport({','.join(sport_hits)})")

    # Identity-sensitive routing: gendered language or identity claim types.
    identity_sensitive = bool(
        contains_term(f"{baseline_text} {proposed_tags or ''} {proposed_desc or ''}",
                      GENDER_TERMS)
        or {"gender", "group_identity", "named_person"} & set(sensitive)
    )

    # Ensemble gate: with a second run, noisy model signals need agreement.
    lexicon_flag = any(r.startswith("lexicon_") for r in reasons)
    if result2 is None:
        model_flag = bool(signal_kinds(record, result))
    else:
        kinds1 = signal_kinds(record, result)
        kinds2 = signal_kinds(record, result2)
        model_flag = bool((kinds1 & kinds2)
                          or ((kinds1 | kinds2) & PRECISE_SIGNALS))
        if not model_flag and (kinds1 or kinds2):
            reasons.append("ensemble_unconfirmed")

    return {
        "LHNo": record["LHNo"],
        "flagged": model_flag or lexicon_flag,
        "reasons": reasons,
        "identity_sensitive": identity_sensitive,
        "confidence": confidence,
        "baseline_tags": record.get("tags"),
        "baseline_description": record.get("description"),
        "baseline_category": record.get("category"),
        "proposed_tags": proposed_tags,
        "proposed_description": proposed_desc,
        "proposed_category": new_category,
        "material_errors": material_errors,
        "minor_errors": minor_errors,
        "doubts": doubts,
        "sensitive_claims": sensitive,
        "subject": record.get("subject"),
        "date": record.get("date"),
        "filename": record.get("filename"),
    }


def score_calibration(rows: dict, calibration_path: Path) -> None:
    """Print recall on known-bad photos and flag rate on known-good ones."""
    cal = json.loads(calibration_path.read_text())
    known_bad = set(cal["known_bad"])
    known_good = set(cal["known_good"])

    scored_bad = [lh for lh in known_bad if lh in rows]
    scored_good = [lh for lh in known_good if lh in rows]

    caught = [lh for lh in scored_bad if rows[lh]["flagged"]]
    missed = [lh for lh in scored_bad if not rows[lh]["flagged"]]
    false_flags = [lh for lh in scored_good if rows[lh]["flagged"]]

    print("\n=== Calibration score ===")
    print(f"Known-bad photos scored : {len(scored_bad)}")
    print(f"  caught (flagged)      : {len(caught)} "
          f"({len(caught) / len(scored_bad) * 100:.0f}% recall)"
          if scored_bad else "  (none)")
    if missed:
        print(f"  MISSED                : {len(missed)}")
        for lh in sorted(missed):
            issues = cal["known_bad"][lh]
            refs = ", ".join(f"#{i['issue']}" for i in issues)
            print(f"    {lh}  ({refs}) conf={rows[lh]['confidence']:.2f}")
    print(f"Known-good photos scored: {len(scored_good)}")
    print(f"  false flags           : {len(false_flags)} "
          f"({len(false_flags) / len(scored_good) * 100:.0f}%)"
          if scored_good else "  (none)")
    if false_flags:
        for lh in sorted(false_flags):
            print(f"    {lh}  reasons: {', '.join(rows[lh]['reasons'])}")


def main():
    parser = argparse.ArgumentParser(
        description="Triage verification results into auto-confirm vs. "
                    "flagged-for-review.")
    parser.add_argument("--results", default=str(DEFAULT_RESULTS),
                        help="verification_results.json from verify_photos.py")
    parser.add_argument("--results2", default=None,
                        help="Second independent verification run; enables "
                             "ensemble gating of noisy signals.")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--report", default=str(DEFAULT_REPORT),
                        help="CSV report over all verified photos.")
    parser.add_argument("--queue", default=str(DEFAULT_QUEUE),
                        help="JSON review queue of flagged photos.")
    parser.add_argument("--calibration", default=None,
                        help="Calibration set JSON; prints recall metrics.")
    args = parser.parse_args()

    records = load_records(Path(args.db))
    results = json.loads(Path(args.results).read_text())
    results2 = (json.loads(Path(args.results2).read_text())
                if args.results2 else None)

    rows = {}
    for lh, result in results.items():
        if lh not in records:
            print(f"warning: {lh} not in database, skipping", file=sys.stderr)
            continue
        second = results2.get(lh) if results2 else None
        rows[lh] = triage_one(records[lh], result, second)

    flagged = {lh: r for lh, r in rows.items() if r["flagged"]}

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["LHNo", "flagged", "reasons", "identity_sensitive", "confidence",
              "baseline_category", "proposed_category", "baseline_tags",
              "proposed_tags", "baseline_description", "proposed_description",
              "subject", "date", "filename"]
    with open(report_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for lh in sorted(rows):
            row = dict(rows[lh])
            row["reasons"] = "; ".join(row["reasons"])
            writer.writerow(row)

    queue_path = Path(args.queue)
    queue_path.write_text(json.dumps(
        {lh: flagged[lh] for lh in sorted(flagged)}, indent=2))

    n = len(rows)
    print(f"Triaged {n} photos: {n - len(flagged)} auto-confirm, "
          f"{len(flagged)} flagged ({len(flagged) / n * 100:.0f}%)."
          if n else "No photos triaged.")
    print(f"Report: {report_path}")
    print(f"Queue : {queue_path}")

    if args.calibration:
        score_calibration(rows, Path(args.calibration))


if __name__ == "__main__":
    main()
