#!/usr/bin/env python3
"""
Stage A of the description-refinement pipeline: cheap verification pass.

For each photo, sends the (downscaled) image plus its existing catalog record
to a vision model and asks it to AUDIT the record rather than re-describe the
photo: confirm or correct the tags and description, report confidence, and
list any claims it cannot verify. Results feed scripts/triage_photos.py.

Usage:
    export OPENROUTER_API_KEY="your-key-here"

    # Calibration subset
    python scripts/verify_photos.py --calibration data/calibration_set.json \
        --output data/refinement/verification_results.json

    # Explicit LH numbers, one per line
    python scripts/verify_photos.py --lh-file my_photos.txt

    # Full collection
    python scripts/verify_photos.py --all

The results file is written incrementally and keyed by LH number, so an
interrupted run resumes where it left off.

Dependencies:
    pip install requests Pillow
"""

import argparse
import base64
import io
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

import requests
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = REPO_ROOT / "datasette" / "corning_historic_photos.db"
DEFAULT_PHOTOS_DIR = REPO_ROOT / "data" / "photos"
DEFAULT_OUTPUT = REPO_ROOT / "data" / "refinement" / "verification_results.json"

API_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "anthropic/claude-haiku-4.5"
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds
RATE_LIMIT_DELAY = 0.5  # seconds between requests

# Longest image side sent to the model. Image tokens dominate cost and scale
# with pixel count; these are scans of mostly B&W prints, so 1024px preserves
# enough detail for verification at roughly half the cost of full resolution.
DEFAULT_MAX_SIZE = 1024
JPEG_QUALITY = 80

VALID_CATEGORIES = [
    "Disasters & Floods", "Military & War", "Archaeological Artifacts",
    "Glass & Decorative Arts", "Industry & Manufacturing",
    "Sports & Recreation", "Commerce & Business", "Civic Life & Events",
    "Education", "People & Portraits", "Transportation",
    "Domestic & Family Life", "Streetscapes & Architecture",
    "Landscapes & Natural Features",
]

PROMPT_TEMPLATE = """\
You are fact-checking the catalog record of a historical photograph from \
the Corning, NY local history archive (ID: {lh}).

Existing record:
- Library subject (human-entered): {subject}
- Library date (human-entered): {date}
- Tags (machine-generated): {tags}
- Description (machine-generated): {description}
- Category (machine-assigned): {category}

The tags and description were machine-generated from this image and may \
contain factual errors: misidentified objects, activities, settings, or \
people. Your job is to find CONTRADICTIONS between the record and what the \
image actually shows. Your job is NOT to rewrite, improve, or hedge the \
record.

Rules:
0. FIRST, look for any printed or handwritten caption, sign, label, or \
text in or around the photograph and transcribe it into "caption_text" \
(a single valid JSON string — put any notes such as "partially visible" \
inside the string; abbreviate transcriptions longer than ~60 words). A \
caption is authoritative: if the record contradicts \
what a caption says the photo shows (e.g., the caption names a brick and \
tile works but the record says glass works), that is a material error.
1. Report an error ONLY when the image contradicts a claim (record says \
"beach" but the image clearly shows a road) or a claim clearly overreaches \
the visible evidence (record names a specific sport but no equipment, \
uniforms, or markings identify one).
2. Do NOT report style, wording, tone, or completeness issues. Do not \
remove or soften claims that are consistent with the image. If the record \
is factually consistent with the image, report zero errors even if you \
would have worded it differently.
3. Names, places, and dates likely come from the library's subject/date \
fields or a visible caption. Trust them unless the image contradicts them; \
never report them just because you cannot independently verify them.
4. Error types to check especially carefully (these are the known failure \
modes of the original cataloging model):
   - gender or age of people (e.g., "woman" for a girl, misgendered subject)
   - group identity inferred from appearance (e.g., "Native Americans" for \
soldiers in training) — flag unless a caption supports it
   - sport or game identification (e.g., "baseball team" for a basketball \
team)
   - specific objects/settings (beach vs. road, pool vs. fountain, sphere \
vs. globe, promotional poster vs. certificate)
   - the activity depicted
5. Also check that the description captures the photograph's PRIMARY \
subject. If it describes peripheral content and misses the main activity \
or subject (e.g., describes trees when the photo shows men felling a \
tree), report that as an error.
6. Check for garbled, truncated, or nonsensical text in the description \
(e.g., a sentence fragment like "'ed on the Pacific Ocean"). Report it as \
an error.
7. Before reporting an error, re-examine the image and confirm your own \
reading is certain. If your observation could itself be mistaken, use \
"doubts" instead of "errors".
8. Grade each error's severity with this test: would fixing it change \
what a catalog user understands the photograph to DEPICT — the \
one-sentence gist? If the gist stays the same, it is "minor".
   - "material" examples: "baseball team" when the image shows \
basketball; "woman" when the subject is a girl; "beach" when it is a \
road; a group identity the image cannot support; a description of trees \
when the photo shows men felling a tree; garbled or truncated text.
   - "minor" examples: "headset" vs. handset; "partially submerged" vs. \
water surrounding buildings; three stories vs. four; "books on a table" \
vs. a single book in hand; pose angle; foliage or season; counts of \
people or objects.
9. When you report errors, provide corrected text as a MINIMAL edit of the \
existing text: change only the erroneous parts, keep everything else \
verbatim.
10. Use "doubts" only for claims the image gives you active reason to \
suspect but cannot settle. Do not list things that are merely unverifiable \
from the image (exact year, whether a style is "Victorian", etc.).
11. Judge whether the assigned category is appropriate for what the image \
shows. The valid categories are:
{categories}
If the current category is defensible, keep it — suggest a change only \
when the image clearly belongs elsewhere.

Respond with ONLY a JSON object, no other text:
{{
  "caption_text": null or "exact transcription of visible caption/sign text",
  "errors": [
    {{"field": "tags" or "description",
      "severity": "material" or "minor",
      "claim": "the erroneous text from the record",
      "observed": "what the image actually shows"}}
  ],
  "corrected_tags": null, or corrected semicolon-delimited tags if any \
error has field "tags",
  "corrected_description": null, or corrected one-sentence description if \
any error has field "description",
  "category_ok": true|false,
  "suggested_category": null, or one of the valid category names,
  "doubts": ["suspect claim you could not settle", ...],
  "confidence": 0.0-1.0,
  "sensitive_claims": ["gender"|"group_identity"|"named_person"|"sport"|"specific_object"|"location", ...]
}}

"confidence" is your confidence in your own verdict — a clean record \
confirmed with no errors deserves a high value. "sensitive_claims" lists \
which of those claim types appear in the record at all, whether or not \
they are wrong."""


# ---------------------------------------------------------------------------
# Record and image loading
# ---------------------------------------------------------------------------

def load_records(db_path: Path) -> dict:
    """Load baseline catalog records keyed by LH number."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT LHNo, filename, subject, date, tags, description, category "
        "FROM historic_photos"
    ).fetchall()
    conn.close()
    return {r["LHNo"]: dict(r) for r in rows}


def encode_image(path: Path, max_size: int) -> str:
    """Downscale an image and return it base64-encoded as JPEG."""
    with Image.open(path) as img:
        img = img.convert("RGB")
        img.thumbnail((max_size, max_size), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=JPEG_QUALITY)
    return base64.standard_b64encode(buf.getvalue()).decode("utf-8")


# ---------------------------------------------------------------------------
# API call and response parsing
# ---------------------------------------------------------------------------

def build_payload(record: dict, img_b64: str, model: str) -> dict:
    prompt = PROMPT_TEMPLATE.format(
        lh=record["LHNo"],
        subject=record.get("subject") or "(none)",
        date=record.get("date") or "(none)",
        tags=record.get("tags") or "(none)",
        description=record.get("description") or "(none)",
        category=record.get("category") or "(none)",
        categories="\n".join(f"   - {c}" for c in VALID_CATEGORIES),
    )
    return {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"},
                    },
                ],
            }
        ],
        "max_tokens": 1000,
        "temperature": 0.1,
    }


def repair_candidates(content: str) -> tuple[str, ...]:
    """The raw response plus repaired variants of known invalid-JSON quirks.

    Two failure modes seen in production: a parenthesized annotation after a
    string value ('"CORNING" (visible on drum),'), and unescaped double
    quotes inside a string value (quoted caption or document text).
    """
    # Annotation after string value -> merged into the string.
    annotated = re.sub(r'"((?:[^"\\]|\\.)*)"\s*\(([^()\n]*)\)\s*(,|\n|\})',
                       lambda m: json.dumps(f"{m.group(1)} ({m.group(2)})")
                       + m.group(3), content)

    # Unescaped quotes inside single-line string values -> escaped.
    lines = []
    for line in content.split("\n"):
        m = re.match(r'^(\s*"[a-z_]+"\s*:\s*")(.*)("\s*,?\s*)$', line)
        if m and '"' in m.group(2):
            inner = m.group(2).replace('\\"', '"').replace('"', '\\"')
            line = m.group(1) + inner + m.group(3)
        lines.append(line)
    quoted = "\n".join(lines)

    return content, annotated, quoted


def parse_response(content: str) -> dict | None:
    """Extract the JSON verdict from the model response."""
    content = content.strip()
    # Strip markdown code fences if present.
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
    if not isinstance(parsed, dict):
        return None
    # Normalize expected fields. description_ok/tags_ok are derived from the
    # enumerated error list: a correction without a named error is treated as
    # a stylistic rewrite and ignored.
    errors = []
    for e in parsed.get("errors") or []:
        if isinstance(e, dict) and e.get("field") in ("tags", "description"):
            e["severity"] = ("minor" if e.get("severity") == "minor"
                             else "material")
            errors.append(e)
    # Only material errors invalidate a field; minor quibbles are recorded
    # but do not trigger corrections.
    tags_bad = any(e["field"] == "tags" and e["severity"] == "material"
                   for e in errors)
    desc_bad = any(e["field"] == "description" and e["severity"] == "material"
                   for e in errors)
    suggested = parsed.get("suggested_category")
    if suggested not in VALID_CATEGORIES:
        suggested = None
    return {
        "caption_text": parsed.get("caption_text") or None,
        "errors": errors,
        "description_ok": not desc_bad,
        "corrected_description": (parsed.get("corrected_description") or None)
                                 if desc_bad else None,
        "tags_ok": not tags_bad,
        "corrected_tags": (parsed.get("corrected_tags") or None)
                          if tags_bad else None,
        "category_ok": bool(parsed.get("category_ok", True)) or suggested is None,
        "suggested_category": suggested,
        "confidence": float(parsed.get("confidence", 0.0)),
        "doubts": list(parsed.get("doubts") or []),
        "sensitive_claims": list(parsed.get("sensitive_claims") or []),
    }


def verify_photo(api_key: str, record: dict, image_path: Path,
                 model: str, max_size: int) -> dict:
    """Run one verification call. Returns a result dict (may carry 'error')."""
    img_b64 = encode_image(image_path, max_size)
    payload = build_payload(record, img_b64, model)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://local-history-archive",
        "X-Title": "Corning NY Photo Archive Verification",
    }

    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.post(API_URL, json=payload, headers=headers,
                                 timeout=90)
            if resp.status_code == 429:
                wait = RETRY_DELAY * (attempt + 1)
                print(f"  rate limited, waiting {wait}s...", flush=True)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            parsed = parse_response(content)
            if parsed is None:
                last_error = f"unparseable response: {content[:200]}"
                continue
            parsed["model"] = model
            parsed["raw"] = content
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


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def select_lh_numbers(args, records: dict) -> list[str]:
    if args.calibration:
        cal = json.loads(Path(args.calibration).read_text())
        return sorted(set(cal["known_bad"]) | set(cal["known_good"]))
    if args.lh_file:
        lines = Path(args.lh_file).read_text().splitlines()
        return [ln.strip() for ln in lines if ln.strip()]
    if args.all:
        return sorted(records)
    return []


def main():
    parser = argparse.ArgumentParser(
        description="Verification pass over photo catalog records.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--calibration",
                       help="Calibration set JSON; verifies its photos.")
    group.add_argument("--lh-file",
                       help="File with one LH number per line.")
    group.add_argument("--all", action="store_true",
                       help="Verify the entire collection.")
    parser.add_argument("--db", default=str(DEFAULT_DB),
                        help=f"Baseline database (default: {DEFAULT_DB}).")
    parser.add_argument("--photos-dir", default=str(DEFAULT_PHOTOS_DIR),
                        help=f"Image folder (default: {DEFAULT_PHOTOS_DIR}).")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT),
                        help=f"Results JSON (default: {DEFAULT_OUTPUT}).")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--max-size", type=int, default=DEFAULT_MAX_SIZE,
                        help="Longest image side sent to the model.")
    parser.add_argument("--limit", type=int, default=None,
                        help="Stop after N photos (for testing).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Prepare images and prompts but make no API "
                             "calls; prints token estimates.")
    args = parser.parse_args()

    records = load_records(Path(args.db))
    lh_numbers = select_lh_numbers(args, records)
    photos_dir = Path(args.photos_dir)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    missing = [lh for lh in lh_numbers if lh not in records]
    if missing:
        sys.exit(f"Error: LH numbers not in database: {missing}")

    results = {}
    if output_path.exists():
        results = json.loads(output_path.read_text())

    todo = [lh for lh in lh_numbers if lh not in results
            or "error" in results[lh]]
    if args.limit:
        todo = todo[: args.limit]

    print(f"Selected: {len(lh_numbers)} | already done: "
          f"{len(lh_numbers) - len(todo)} | to process: {len(todo)}")

    if args.dry_run:
        total_b64 = 0
        total_px = 0
        for lh in todo:
            image_path = photos_dir / records[lh]["filename"]
            b64 = encode_image(image_path, args.max_size)
            total_b64 += len(b64)
            with Image.open(image_path) as img:
                img.thumbnail((args.max_size, args.max_size))
                total_px += img.width * img.height
        # Anthropic vision tokens are roughly pixels / 750.
        est_img_tokens = int(total_px / 750)
        print(f"Dry run OK. {len(todo)} images prepared; "
              f"~{total_b64 / 1e6:.1f} MB base64 payload; estimated image "
              f"tokens ~{est_img_tokens / 1000:.0f}k "
              f"(plus ~450 prompt tokens each).")
        return

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        sys.exit("Error: set the OPENROUTER_API_KEY environment variable.")

    changed = confirmed = errors = 0
    for i, lh in enumerate(todo, 1):
        record = records[lh]
        image_path = photos_dir / record["filename"]
        print(f"[{i}/{len(todo)}] {lh} ...", end=" ", flush=True)

        result = verify_photo(api_key, record, image_path,
                              args.model, args.max_size)
        results[lh] = result

        if "error" in result:
            errors += 1
            print(f"ERROR ({result['error'][:80]})")
        elif (result["description_ok"] and result["tags_ok"]
              and result.get("category_ok", True)):
            confirmed += 1
            print(f"confirmed (conf {result['confidence']:.2f})")
        else:
            changed += 1
            print(f"CORRECTION proposed (conf {result['confidence']:.2f})")

        if i % 10 == 0 or i == len(todo):
            output_path.write_text(json.dumps(results, indent=2))

        time.sleep(RATE_LIMIT_DELAY)

    output_path.write_text(json.dumps(results, indent=2))
    print(f"\nDone. {confirmed} confirmed, {changed} corrections proposed, "
          f"{errors} errors.")
    print(f"Results: {output_path}")


if __name__ == "__main__":
    main()
