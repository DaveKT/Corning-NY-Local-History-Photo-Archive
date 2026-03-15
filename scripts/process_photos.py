#!/usr/bin/env python3
"""
Process historical photos from Corning, NY local history archive.
Uses OpenRouter API with Claude Haiku to generate tags and descriptions.

Usage:
    export OPENROUTER_API_KEY="your-key-here"
    python3 process_photos.py

The script:
- Reads each image file individually from photos/
- Sends it to Claude Haiku via OpenRouter for analysis
- Saves results to corrected_results.json (incremental, resumable)
- Handles rate limits and errors with retries
"""

import os
import sys
import json
import glob
import base64
import time
import csv
import re
import requests
from pathlib import Path

# --- Configuration ---
PHOTOS_DIR = "photos"
RESULTS_FILE = "corrected_results.json"
CSV_FILE = "local-history-photo-archive-index-20260314.csv"
MODEL = "anthropic/claude-haiku-4.5"
API_URL = "https://openrouter.ai/api/v1/chat/completions"
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds
RATE_LIMIT_DELAY = 1  # seconds between requests

# --- Load existing metadata from CSV for context ---
def load_csv_metadata(csv_path):
    """Load subject and date info from CSV keyed by LH number."""
    metadata = {}
    if not os.path.exists(csv_path):
        return metadata
    with open(csv_path, 'r') as f:
        reader = csv.reader(f)
        header = next(reader)
        for row in reader:
            lh = row[0].strip()
            if lh not in metadata:
                metadata[lh] = {"subjects": [], "date": ""}
            if len(row) > 1 and row[1].strip():
                metadata[lh]["subjects"].append(row[1].strip())
            if len(row) > 2 and row[2].strip():
                metadata[lh]["date"] = row[2].strip()
    return metadata


def load_existing_results(results_path):
    """Load previously saved results for resume capability."""
    if os.path.exists(results_path):
        with open(results_path, 'r') as f:
            return json.load(f)
    return {}


def save_results(results, results_path):
    """Save results to JSON file."""
    with open(results_path, 'w') as f:
        json.dump(results, f, indent=2)


def get_photo_list(photos_dir):
    """Get sorted list of (lh_number, filepath) tuples."""
    photos = sorted(glob.glob(os.path.join(photos_dir, "lh-*.jpg")))
    result = []
    for p in photos:
        base = os.path.basename(p)
        lh = base.replace("lh-", "").replace(".jpg", "")
        result.append((lh, p))
    return result


def encode_image(filepath):
    """Read and base64-encode an image file."""
    with open(filepath, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8")


def analyze_image(api_key, filepath, lh_number, metadata_context):
    """Send a single image to the API and get tags + description."""

    img_b64 = encode_image(filepath)

    # Build context string from metadata
    context_parts = []
    if metadata_context.get("subjects"):
        context_parts.append(f"Existing subject keywords: {', '.join(metadata_context['subjects'])}")
    if metadata_context.get("date"):
        context_parts.append(f"Date: {metadata_context['date']}")
    context_str = "\n".join(context_parts) if context_parts else "No existing metadata."

    prompt = f"""Analyze this historical photograph from the Corning, NY local history archive (ID: {lh_number}).

{context_str}

Provide exactly two things:
1. TAGS: 3-5 semicolon-delimited lowercase descriptive tags based on what is VISIBLE in the image (e.g., "flooded street; brick buildings; 1940s automobiles; downtown; black and white photograph")
2. DESCRIPTION: One sentence describing what the image shows. Include any visible text, captions, place names, person names, dates, or identifiable landmarks. If specifics cannot be identified, give a general description.

Respond in exactly this format (no other text):
TAGS: tag1; tag2; tag3; tag4
DESCRIPTION: Your one sentence description here."""

    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{img_b64}"
                        }
                    }
                ]
            }
        ],
        "max_tokens": 300,
        "temperature": 0.1
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://local-history-archive",
        "X-Title": "Corning NY Photo Archive Processing"
    }

    for attempt in range(MAX_RETRIES):
        try:
            response = requests.post(API_URL, json=payload, headers=headers, timeout=60)

            if response.status_code == 429:
                wait = RETRY_DELAY * (attempt + 1)
                print(f"  Rate limited, waiting {wait}s...")
                time.sleep(wait)
                continue

            if response.status_code >= 400:
                print(f"\n  HTTP {response.status_code} response body: {response.text[:500]}")
            response.raise_for_status()
            data = response.json()

            content = data["choices"][0]["message"]["content"].strip()
            return parse_response(content)

        except requests.exceptions.RequestException as e:
            # Print response body if available for debugging
            if hasattr(e, 'response') and e.response is not None:
                print(f"  Error (attempt {attempt+1}/{MAX_RETRIES}): {e}")
                print(f"  Response body: {e.response.text[:500]}")
            else:
                print(f"  Error (attempt {attempt+1}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
            else:
                return None

    return None


def parse_response(content):
    """Parse the TAGS/DESCRIPTION response format."""
    tags = ""
    description = ""

    for line in content.split("\n"):
        line = line.strip()
        if line.upper().startswith("TAGS:"):
            tags = line[5:].strip()
        elif line.upper().startswith("DESCRIPTION:"):
            description = line[12:].strip()

    # Fallback: if parsing failed, try to extract from unstructured response
    if not tags or not description:
        lines = [l.strip() for l in content.split("\n") if l.strip()]
        if len(lines) >= 2:
            tags = lines[0].replace("TAGS:", "").strip()
            description = lines[1].replace("DESCRIPTION:", "").strip()
        elif len(lines) == 1:
            description = lines[0]
            tags = "historical photograph; corning ny"

    return {"tags": tags, "description": description}


def update_csv(results, csv_path):
    """Update the CSV file with new tags and descriptions."""
    # Read existing CSV
    with open(csv_path, 'r') as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = list(reader)

    # Ensure header has Tags and Description columns
    while len(header) < 5:
        header.append("")
    if not header[3]:
        header[3] = "Tags"
    if not header[4]:
        header[4] = "Description"

    # Track LH numbers in CSV
    csv_lh_numbers = set()
    for row in rows:
        csv_lh_numbers.add(row[0].strip())

    # Update existing rows
    updated = 0
    for row in rows:
        lh = row[0].strip()
        if lh in results:
            while len(row) < 5:
                row.append("")
            row[3] = results[lh]["tags"]
            row[4] = results[lh]["description"]
            updated += 1

    # Add new rows for photos not in CSV
    new_rows = 0
    for lh in sorted(results.keys()):
        if lh not in csv_lh_numbers:
            rows.append([lh, "", "", results[lh]["tags"], results[lh]["description"]])
            csv_lh_numbers.add(lh)
            new_rows += 1

    # Write updated CSV
    with open(csv_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)

    return updated, new_rows


def main():
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("Error: Set OPENROUTER_API_KEY environment variable")
        print("  export OPENROUTER_API_KEY='your-key-here'")
        sys.exit(1)

    # Load data
    metadata = load_csv_metadata(CSV_FILE)
    results = load_existing_results(RESULTS_FILE)
    photos = get_photo_list(PHOTOS_DIR)

    print(f"Total photos: {len(photos)}")
    print(f"Already processed: {len(results)}")

    # Filter to unprocessed photos
    to_process = [(lh, fp) for lh, fp in photos if lh not in results]
    print(f"Remaining: {len(to_process)}")

    if not to_process:
        print("All photos already processed!")
        print("Updating CSV...")
        updated, new_rows = update_csv(results, CSV_FILE)
        print(f"Updated {updated} existing rows, added {new_rows} new rows")
        return

    # Process each image
    start_time = time.time()
    for i, (lh, filepath) in enumerate(to_process):
        meta = metadata.get(lh, {"subjects": [], "date": ""})

        print(f"[{i+1}/{len(to_process)}] Processing {lh}...", end=" ", flush=True)

        result = analyze_image(api_key, filepath, lh, meta)

        if result:
            results[lh] = result
            print(f"OK - {result['tags'][:60]}...")
        else:
            print("FAILED - skipped")
            results[lh] = {
                "tags": "historical photograph; corning ny",
                "description": f"Historical photograph from the Corning, NY local history archive (LH {lh})."
            }

        # Save progress every 10 images
        if (i + 1) % 10 == 0:
            save_results(results, RESULTS_FILE)
            elapsed = time.time() - start_time
            rate = (i + 1) / elapsed
            remaining = (len(to_process) - i - 1) / rate
            print(f"  --- Saved progress. {i+1}/{len(to_process)} done. "
                  f"~{remaining/60:.0f} min remaining ---")

        # Rate limiting
        time.sleep(RATE_LIMIT_DELAY)

    # Final save
    save_results(results, RESULTS_FILE)
    print(f"\nAll {len(to_process)} photos processed!")

    # Update CSV
    print("Updating CSV...")
    updated, new_rows = update_csv(results, CSV_FILE)
    print(f"Updated {updated} existing rows, added {new_rows} new rows")
    print("Done!")


if __name__ == "__main__":
    main()
