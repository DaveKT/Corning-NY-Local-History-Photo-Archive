#!/usr/bin/env python3
"""
Stage C of the description-refinement pipeline: adjudication of flagged photos.

Takes the review queue produced by scripts/triage_photos.py and re-examines
each flagged photo with a stronger vision model (Claude Sonnet by default) at
higher resolution. The adjudicator sees the baseline record, the first-pass
verifier's findings, and the triage reasons, and issues a final proposed
record with a verdict:

  - auto-resolve : the adjudicator is confident and the change involves no
                   identity claims -> written to corrections_auto.json
  - human review : identity-related changes, low adjudicator confidence, or
                   photos the adjudicator itself marks ambiguous -> written
                   to human_queue.json for the review app

Usage:
    export OPENROUTER_API_KEY="your-key-here"
    python scripts/adjudicate_photos.py \
        --queue data/refinement/review_queue.json

Incremental and resumable, like verify_photos.py.

Dependencies:
    pip install requests Pillow
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import requests

from verify_photos import (API_URL, MAX_RETRIES, RETRY_DELAY,
                           VALID_CATEGORIES, encode_image, load_records,
                           repair_candidates)

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = REPO_ROOT / "datasette" / "corning_historic_photos.db"
DEFAULT_PHOTOS_DIR = REPO_ROOT / "data" / "photos"
DEFAULT_QUEUE = REPO_ROOT / "data" / "refinement" / "review_queue.json"
DEFAULT_OUTPUT = REPO_ROOT / "data" / "refinement" / "adjudication_results.json"
DEFAULT_AUTO = REPO_ROOT / "data" / "refinement" / "corrections_auto.json"
DEFAULT_HUMAN_QUEUE = REPO_ROOT / "data" / "refinement" / "human_queue.json"

DEFAULT_MODEL = "anthropic/claude-sonnet-4.5"
# Higher resolution than the cheap pass: the adjudicator only sees the small
# flagged subset, so the extra tokens are affordable where they matter.
DEFAULT_MAX_SIZE = 1568
RATE_LIMIT_DELAY = 0.5
# Sonnet's modal self-reported confidence is 0.85, and at that level its
# changes are precision edits; identity changes and self-declared ambiguity
# route to humans through separate gates regardless of this threshold.
AUTO_RESOLVE_CONFIDENCE = 0.85

PROMPT_TEMPLATE = """\
You are the senior reviewer for the catalog of the Corning, NY local \
history photo archive. A first-pass automated check flagged this \
photograph's record (ID: {lh}) as possibly wrong. Examine the image \
carefully and issue the final record.

Current record:
- Library subject (human-entered, trustworthy): {subject}
- Library date (human-entered, trustworthy): {date}
- Tags: {tags}
- Description: {description}
- Category: {category}

First-pass findings (from a smaller model — may be right or wrong):
{findings}

Flag reasons from rule-based triage: {reasons}

Your task:
1. Decide what the photograph actually shows. Trust the image over both \
the record and the first-pass findings.
2. Issue final tags (3-5, semicolon-delimited, lowercase), a final \
one-sentence description, and a final category. Change as little as \
possible: keep the existing wording wherever it is accurate. Keep any \
names, places, and dates that come from the library fields or a visible \
caption unless the image contradicts them.
3. Never assert gender, age bracket, ethnicity, or group identity that \
the image does not clearly support; prefer neutral terms ("person", \
"child", "people") where uncertain. Name a sport only if equipment, \
uniforms, or markings identify it.
4. Valid categories:
{categories}
5. Set "needs_human" to true if: the correct reading of the image is \
genuinely ambiguous; the change alters a claim about a person's identity \
(gender, age, ethnicity, group membership, or who they are); or you are \
not confident. Give the reason in "human_reason".

Respond with ONLY a JSON object, no other text:
{{
  "final_tags": "...",
  "final_description": "...",
  "final_category": "one of the valid categories",
  "rationale": "one or two sentences on what you changed and why, or why the record was fine",
  "confidence": 0.0-1.0,
  "needs_human": true|false,
  "human_reason": null or "why a human should look"
}}"""


def format_findings(entry: dict) -> str:
    lines = []
    for e in entry.get("material_errors", []) + entry.get("minor_errors", []):
        lines.append(f"- [{e.get('severity', 'material')}] record says "
                     f"\"{e.get('claim', '')}\" but first pass observed: "
                     f"{e.get('observed', '')}")
    if entry.get("proposed_tags") != entry.get("baseline_tags"):
        lines.append(f"- proposed tags: {entry.get('proposed_tags')}")
    if entry.get("proposed_description") != entry.get("baseline_description"):
        lines.append(f"- proposed description: "
                     f"{entry.get('proposed_description')}")
    if entry.get("proposed_category") != entry.get("baseline_category"):
        lines.append(f"- proposed category: {entry.get('proposed_category')}")
    for d in entry.get("doubts", []):
        lines.append(f"- doubt: {d}")
    return "\n".join(lines) if lines else "(none — flagged by rules only)"


def parse_response(content: str) -> dict | None:
    content = content.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", content, re.DOTALL)
    if fence:
        content = fence.group(1)
    parsed = None
    for candidate in repair_candidates(content):
        try:
            parsed = json.loads(candidate)
            break
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}", candidate, re.DOTALL)
            if m:
                try:
                    parsed = json.loads(m.group(0))
                    break
                except json.JSONDecodeError:
                    pass
    if parsed is None:
        return None
    if not isinstance(parsed, dict) or "final_description" not in parsed:
        return None
    category = parsed.get("final_category")
    if category not in VALID_CATEGORIES:
        category = None
    return {
        "final_tags": parsed.get("final_tags") or None,
        "final_description": parsed.get("final_description") or None,
        "final_category": category,
        "rationale": parsed.get("rationale") or "",
        "confidence": float(parsed.get("confidence", 0.0)),
        "needs_human": bool(parsed.get("needs_human", False)),
        "human_reason": parsed.get("human_reason") or None,
    }


def adjudicate_photo(api_key: str, record: dict, entry: dict,
                     image_path: Path, model: str, max_size: int) -> dict:
    img_b64 = encode_image(image_path, max_size)
    prompt = PROMPT_TEMPLATE.format(
        lh=record["LHNo"],
        subject=record.get("subject") or "(none)",
        date=record.get("date") or "(none)",
        tags=record.get("tags") or "(none)",
        description=record.get("description") or "(none)",
        category=record.get("category") or "(none)",
        findings=format_findings(entry),
        reasons=", ".join(entry.get("reasons", [])),
        categories="\n".join(f"   - {c}" for c in VALID_CATEGORIES),
    )
    payload = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url",
                 "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
            ],
        }],
        "max_tokens": 1200,
        "temperature": 0.1,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://local-history-archive",
        "X-Title": "Corning NY Photo Archive Adjudication",
    }

    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.post(API_URL, json=payload, headers=headers,
                                 timeout=120)
            if resp.status_code == 429:
                wait = RETRY_DELAY * (attempt + 1)
                print(f"  rate limited, waiting {wait}s...", flush=True)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            parsed = parse_response(content)
            if parsed is None:
                last_error = f"unparseable response: {content[:200]}"
                continue
            parsed["model"] = model
            return parsed
        except requests.exceptions.RequestException as exc:
            body = ""
            if getattr(exc, "response", None) is not None:
                body = f" | body: {exc.response.text[:200]}"
            last_error = f"{exc}{body}"
            print(f"  error (attempt {attempt + 1}/{MAX_RETRIES}): "
                  f"{last_error}", flush=True)
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
    return {"error": last_error or "unknown error", "model": model}


# Vocabulary that makes a *change* identity-sensitive. A record merely
# containing these words is fine; a correction that adds, removes, or swaps
# them must be reviewed by a human.
IDENTITY_TERMS = [
    "woman", "women", "man", "men", "girl", "boy", "girls", "boys",
    "lady", "ladies", "gentleman", "gentlemen", "female", "male",
    "child", "children", "native american", "indian", "african american",
    "asian", "chinese", "japanese", "italian", "irish", "immigrant",
]


def identity_terms(text: str) -> set:
    words = f" {(text or '').lower().replace(';', ' ').replace(',', ' ')} "
    return {t for t in IDENTITY_TERMS if f" {t} " in words or f" {t}s " in words}


def route(entry: dict, record: dict, verdict: dict) -> tuple[str, list[dict]]:
    """Decide auto-resolve vs. human review; build correction entries.

    Returns (route, corrections) where route is 'auto', 'human', or
    'confirmed' (no change needed).
    """
    changes = []
    for field, final_key in (("tags", "final_tags"),
                             ("description", "final_description"),
                             ("category", "final_category")):
        old = record.get(field)
        new = verdict.get(final_key)
        if new and new != old:
            changes.append({"lh": record["LHNo"], "field": field,
                            "old": old, "new": new})

    if not changes:
        return "confirmed", []

    identity_change = any(
        c["field"] in ("tags", "description")
        and identity_terms(c["old"]) != identity_terms(c["new"])
        for c in changes)
    if (verdict.get("needs_human") or identity_change
            or verdict.get("confidence", 0.0) < AUTO_RESOLVE_CONFIDENCE):
        return "human", changes
    return "auto", changes


def main():
    parser = argparse.ArgumentParser(
        description="Adjudicate triage-flagged photos with a stronger model.")
    parser.add_argument("--queue", default=str(DEFAULT_QUEUE))
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--photos-dir", default=str(DEFAULT_PHOTOS_DIR))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--auto-out", default=str(DEFAULT_AUTO))
    parser.add_argument("--human-queue", default=str(DEFAULT_HUMAN_QUEUE))
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--max-size", type=int, default=DEFAULT_MAX_SIZE)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--force-human", default=None,
                        help="JSON file mapping LH number -> reason. These "
                             "photos always route to the human queue (e.g. "
                             "photos with open GitHub issues), regardless "
                             "of model verdicts.")
    args = parser.parse_args()

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        sys.exit("Error: set the OPENROUTER_API_KEY environment variable.")

    records = load_records(Path(args.db))
    queue = json.loads(Path(args.queue).read_text())
    photos_dir = Path(args.photos_dir)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    results = {}
    if output_path.exists():
        results = json.loads(output_path.read_text())

    todo = [lh for lh in sorted(queue)
            if lh not in results or "error" in results[lh]]
    if args.limit:
        todo = todo[: args.limit]
    print(f"Queue: {len(queue)} | already adjudicated: "
          f"{len(queue) - len(todo)} | to process: {len(todo)}")

    for i, lh in enumerate(todo, 1):
        record = records[lh]
        print(f"[{i}/{len(todo)}] {lh} ...", end=" ", flush=True)
        verdict = adjudicate_photo(api_key, record, queue[lh],
                                   photos_dir / record["filename"],
                                   args.model, args.max_size)
        results[lh] = verdict
        if "error" in verdict:
            print(f"ERROR ({verdict['error'][:80]})")
        else:
            print(f"conf {verdict['confidence']:.2f}"
                  f"{' -> human' if verdict['needs_human'] else ''}")
        if i % 10 == 0 or i == len(todo):
            output_path.write_text(json.dumps(results, indent=2))
        time.sleep(RATE_LIMIT_DELAY)

    force_human = {}
    if args.force_human:
        force_human = json.loads(Path(args.force_human).read_text())

    # Route every adjudicated photo.
    auto_corrections = []
    human_queue = {}
    confirmed = 0
    for lh, verdict in results.items():
        if lh not in queue or lh not in records:
            continue
        if "error" in verdict:
            human_queue[lh] = {**queue[lh], "adjudication": None,
                               "human_reason": "adjudicator error"}
            continue
        destination, changes = route(queue[lh], records[lh], verdict)
        if lh in force_human:
            human_queue[lh] = {
                **queue[lh],
                "adjudication": verdict,
                "proposed_changes": changes,
                "human_reason": force_human[lh],
            }
            continue
        if destination == "confirmed":
            confirmed += 1
        elif destination == "auto":
            for c in changes:
                auto_corrections.append({**c, "source": "sonnet",
                                         "rationale": verdict["rationale"],
                                         "confidence": verdict["confidence"]})
        else:
            human_queue[lh] = {
                **queue[lh],
                "adjudication": verdict,
                "proposed_changes": changes,
                "human_reason": (verdict.get("human_reason")
                                 or "identity-sensitive change or low "
                                    "adjudicator confidence"),
            }

    Path(args.auto_out).write_text(json.dumps(auto_corrections, indent=2))
    Path(args.human_queue).write_text(json.dumps(human_queue, indent=2))

    print(f"\nAdjudicated {len(results)} photos: {confirmed} record upheld, "
          f"{len(auto_corrections)} auto corrections, "
          f"{len(human_queue)} for human review.")
    print(f"Auto corrections: {args.auto_out}")
    print(f"Human queue     : {args.human_queue}")


if __name__ == "__main__":
    main()
