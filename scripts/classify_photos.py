#!/usr/bin/env python3
"""
Classify photos in the Corning, NY Local History Photo Archive into categories.

Reads from a SQLite database containing the photo_description table and produces
a CSV file with LHNo and Category columns. Classification is rule-based using
keyword matching against Subject, Tags, and Description fields, with a strict
priority hierarchy to ensure each photo receives exactly one category.

Usage:
    python classify_photos.py <database_path> [--output <output_path>]

Example:
    python classify_photos.py corning_photos.sqlite --output photo_categories.csv
"""

import argparse
import csv
import sqlite3
import sys
from collections import Counter


# ---------------------------------------------------------------------------
# Category definitions in priority order.
# Each entry: (category_name, combined_keywords, subject_keywords)
#
# combined_keywords are matched against the concatenation of Subject, Tags,
# and Description (all lowercased). subject_keywords are matched only against
# the Subject field.
# ---------------------------------------------------------------------------

CATEGORIES = [
    (
        "Disasters & Floods",
        [
            "flood", "floodwater", "flood damage", "flooded", "hurricane agnes",
            "trainwreck", "train wreck", "derail", "fire damage", "burning building",
            "collapsed", "structural damage", "warehouse fire", "house fire",
            "building fire", "church fire", "fire truck", "fire hose",
            "emergency response", "fire fighting", "firefighting",
        ],
        ["flood", "trainwreck"],
    ),
    (
        "Military & War",
        [
            "military uniform", "soldier", "civil war", "world war", "army",
            "navy", "naval vessel", "battleship", "sailor uniform", "camp brough",
            "war memorial", "war monument", "military portrait", "military personnel",
            "veterans", "armory", "four minute men", "state police",
            "military commission", "military decoration", "military officer",
            "commemorative medal", "adjutant general", "firearm", "revolver",
            "antique firearm", "rifle mechanism", "rifle;", "bullet mold",
        ],
        ["civil war", "armory", "camp brough", "four minute men", "bullet mold"],
    ),
    (
        "Archaeological Artifacts",
        [
            "archaeological", "arrowhead", "stone tool", "stone tools",
            "projectile point", "museum documentation", "lithic", "chipped stone",
            "flaked stone", "bone tool", "pottery shard", "ceramic fragment",
            "artifact collection", "pre-contact", "native american artifact",
            "fossil", "trilobite",
        ],
        ["ellsworth cowles"],
    ),
    (
        "Glass & Decorative Arts",
        [
            "glass blow", "glass cut", "glass cutting", "glass etching",
            "glass pattern", "glassware design", "steuben", "decorative design",
            "decorative pattern", "floral motif", "geometric pattern", "ornamental",
            "cullet", "glass engraver", "glass product", "glass art",
            "glass artwork", "glass object", "embroidery design", "needlework",
            "textile documentation", "ceramic vessel", "decorative pottery",
            "glass jar", "wooden object; geometric design",
        ],
        [
            "corning glass works engraver", "corning glass works glass blower",
            "corning glass works pattern", "cullet", "eggington",
        ],
    ),
    (
        "Industry & Manufacturing",
        [
            "industrial factory", "industrial facility", "manufacturing",
            "factory floor", "smokestack", "industrial building",
            "industrial landscape", "glass works", "machinery",
            "industrial interior", "fibre box", "incinerator", "pump house",
            "creamery", "dairy product", "glass center", "quarry",
            "excavation site", "telephone equipment", "pharmacy interior",
            "cheese factory", "drainage pipe", "industrial infrastructure",
            "industrial equipment", "construction site", "construction;",
            "construction work", "stone masonry", "scaffolding", "crane;",
        ],
        [
            "corning glass works", "corning glass center", "city incinerator",
            "city pump house", "corning fibre box", "bowers creamery",
            "deluxe dairy", "dann's dairy", "corning leader", "mrs. bebout",
            "construction",
        ],
    ),
    (
        "Sports & Recreation",
        [
            "baseball", "football", "basketball", "tennis", "swimming",
            "country club", "golf", "athletic", "balloonist", "monowheel",
            "bicycle race", "sporting event", "sailing ship", "maritime",
            "beauty pageant",
        ],
        ["baseball", "football", "country club", "balloonist", "bicycles"],
    ),
    (
        "Commerce & Business",
        [
            "storefront", "store front", "market", "bank ", "hotel",
            "advertisement", "merchant", "clothing store", "drug store",
            "grocery", "commercial", "business district", "food-mart", "inn,",
            "carlton hotel", "baron steuben", "bonady", "retail", "showroom",
            "reward poster",
        ],
        [
            "first national bank", "food-mart", "bonady", "carlton hotel",
            "baron steuben", "crystal city clothing", "crystal city lodge",
            "alley's inn", "advertisement", "conservatory of music",
        ],
    ),
    (
        "Civic Life & Events",
        [
            "parade", "festival", "ceremony", "celebration", "dedication",
            "public gathering", "large crowd", "civic event",
            "fireman convention", "convention", "circus", "fair ",
            "fourth of july", "memorial day", "eisenhower", "procession",
            "formal gathering", "formal dinner", "formal event", "banquet",
            "concert program", "theater program", "historical marker",
            "fire department", "firefighter names", "group gathering",
            "indoor gathering", "formal suit", "uniformed officials",
        ],
        [
            "eisenhower", "fireman", "circus", "activit", "fire department",
            "flint glass workers monument", "erwin museum", "joseph costa",
        ],
    ),
    (
        "Education",
        [
            "school", "academy", "class picture", "class photo", "graduation",
            "classroom", "education", "students", "elmira college",
            "board of education", "diploma", "certificate",
        ],
        [
            "corning free academy", "school", "class picture",
            "board of education", "elmira college", "carder school",
        ],
    ),
    # People & Portraits is handled specially (see classify function).
    (
        "People & Portraits",
        [
            "portrait photograph", "formal portrait", "headshot", "portrait;",
            "group portrait", "formal attire", "posed photograph",
            "men in suits", "man at desk", "office interior", "stereoscopic",
            "three men", "two men",
        ],
        [],
    ),
    (
        "Transportation",
        [
            "locomotive", "railroad", "railway", "train ", "freight car",
            "railroad track", "depot", "automobile", "airplane", "biplane",
            "trolley", "streetcar", "horse-drawn carriage", "horse-drawn wagon",
            "wagon", "steam engine", "aviation", "bicycle",
        ],
        [
            "railroad", "erie railroad", "delaware, lackawanna",
            "elmira-corning", "automobile", "airplane", "airplanes",
        ],
    ),
    (
        "Domestic & Family Life",
        [
            "family portrait", "family photo", "home interior",
            "residential interior", "domestic", "porch", "parlor",
            "living room", "dining room", "garden party", "picnic",
            "children playing", "drake family", "corning homes", "drake home",
            "family tree", "genealogy", "pocket watch", "timepiece",
            "alarm clock", "musical instrument", "drum;", "hand bell",
            "wooden box", "umbrella", "parasol", "bottle;", "preserved fruit",
            "canning",
        ],
        [
            "isabel walker drake", "drake home", "corning homes",
            "dickinson house", "crooker farm", "brewer place",
        ],
    ),
    (
        "Streetscapes & Architecture",
        [
            "downtown street", "residential street", "street scene",
            "main street", "brick building", "church building", "church;",
            "stone church", "presbyterian church", "methodist church",
            "congregational church", "episcopal church", "bridge", "viaduct",
            "park", "historic building", "historic architecture",
            "victorian architecture", "brick architecture",
            "institutional building", "courthouse", "city hall", "monument",
            "statue", "clock tower", "public square", "neoclassical building",
            "stone building", "stone tower", "gothic architecture", "cemetery",
            "chapel", "convent", "columned facade", "historic mansion",
            "arsenal", "unpaved road", "tree-lined street",
            "residential neighborhood", "village street", "wooden houses",
            "victorian building", "water street", "architectural detail",
            "wooden structure", "birdhouse",
        ],
        [
            "street", "bridge", "viaduct", "park", "church", "square",
            "courthouse", "city hall", "clocktower", "monument",
            "denison park", "couthouse park", "centerway", "city club",
        ],
    ),
    (
        "Landscapes & Natural Features",
        [
            "rural landscape", "river", "forest", "winter landscape",
            "hillside", "mountain", "valley", "creek", "waterfront", "snow",
            "landscape", "farmland", "rural road", "chimney narrows",
            "rock formation", "covered bridge", "scenic", "nature", "rural",
            "historical map", "land survey", "township", "historical letter",
            "election dispute", "man; hat; outdoor",
        ],
        [
            "chemung river", "chimney narrows", "bill smith creek",
            "cohocton river", "covered bridge",
        ],
    ),
]

# Subject-field place names that fall back to Streetscapes & Architecture
# when no other category matches.
FALLBACK_LOCATION_SUBJECTS = [
    "caton", "addison", "avoca", "branchport", "painted post",
    "corning, new york", "northside", "south corning",
]

# Words in the Subject field that indicate the subject is a place or thing,
# not a person. Used by the named-subject heuristic for People & Portraits.
NON_PERSON_SUBJECT_WORDS = [
    "n.y.", "corning", "painted post", "street", "bridge", "park", "church",
    "railroad", "river", "road", "hotel", "bank", "school", "academy",
    "flood", "fire", "baseball", "football", "glass", "construction",
    "collection", "drake family",
]


def classify(lhno: str, subject: str | None, tags: str | None,
             description: str | None) -> str:
    """Assign a single category to a photo based on its metadata fields.

    Args:
        lhno: The archive photo identifier (e.g., '75-0001').
        subject: The Subject field value, or None.
        tags: The Tags field value, or None.
        description: The Description field value, or None.

    Returns:
        One of the 14 category names, or 'Uncategorized' if no rule matched.
    """
    subj = (subject or "").lower()
    t = (tags or "").lower()
    d = (description or "").lower()
    combined = f"{subj} | {t} | {d}"

    # Special handling for Subject = "Fires" (exact match).
    if subj.strip() == "fires" or subj.strip().startswith("fires"):
        return "Disasters & Floods"

    for category_name, combined_kw, subject_kw in CATEGORIES:

        # Standard keyword check against combined text.
        if any(kw in combined for kw in combined_kw):
            # People & Portraits also needs the named-subject heuristic,
            # but keyword match alone is sufficient to assign it.
            return category_name

        # Subject-only keyword check.
        if any(kw in subj for kw in subject_kw):
            return category_name

        # Named-subject heuristic for People & Portraits.
        if category_name == "People & Portraits" and subject:
            if not any(pw in subj for pw in NON_PERSON_SUBJECT_WORDS):
                words = subject.strip().split()
                skip = {"and", "of", "the", "Mrs.", "Rev.", "Sr."}
                if len(words) >= 2 and all(
                    w[0].isupper() for w in words if w not in skip
                ):
                    return "People & Portraits"

    # Fallback: geographic subject names -> Streetscapes & Architecture.
    if any(kw in subj for kw in FALLBACK_LOCATION_SUBJECTS):
        return "Streetscapes & Architecture"

    return "Uncategorized"


def main():
    parser = argparse.ArgumentParser(
        description="Classify Corning photo archive into categories."
    )
    parser.add_argument("database", help="Path to the SQLite database.")
    parser.add_argument(
        "--output", "-o", default="photo_categories.csv",
        help="Output CSV path (default: photo_categories.csv).",
    )
    args = parser.parse_args()

    conn = sqlite3.connect(args.database)
    cur = conn.cursor()
    cur.execute(
        'SELECT LHNo, "Subject:", Tags, Description FROM photo_description'
    )
    rows = cur.fetchall()
    conn.close()

    results = []
    for lhno, subject, tags, desc in rows:
        cat = classify(lhno, subject, tags, desc)
        results.append((lhno, cat))

    results.sort(key=lambda x: x[0])

    with open(args.output, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["LHNo", "Category"])
        for lhno, cat in results:
            writer.writerow([lhno, cat])

    # Print summary to stderr.
    dist = Counter(cat for _, cat in results)
    total = sum(dist.values())
    print(f"Classified {total} photos into {len(dist)} categories:\n",
          file=sys.stderr)
    for cat, count in dist.most_common():
        print(f"  {count:5d}  ({count / total * 100:4.1f}%)  {cat}",
              file=sys.stderr)

    uncat = [lhno for lhno, cat in results if cat == "Uncategorized"]
    if uncat:
        print(f"\nUncategorized ({len(uncat)}): {uncat}", file=sys.stderr)

    print(f"\nOutput written to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
