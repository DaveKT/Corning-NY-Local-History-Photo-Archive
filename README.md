# Corning, NY Local History Photo Archive</br>AI-Assisted Cataloging

This project documents an effort to download, catalog, and enrich the [Corning, NY Local History Photo Archive](https://corningnyhistory.com/local-history-photo-archive/) using AI-generated image descriptions. The archive is maintained by the Southeast Steuben County Library and contains 1,977 digitized historical photographs spanning 1842 to 1975.

The goal is to improve the discoverability of these images by generating structured tags, one-sentence descriptions, and thematic category assignments for every photo, supplementing the library's existing (and often sparse) subject/date metadata.

You can directly interact with the enriched data using the [Datasette Lite URL](https://lite.datasette.io/?url=https://raw.githubusercontent.com/DaveKT/Corning-NY-Local-History-Photo-Archive/master/datasette/corning_historic_photos.db&metadata=https://raw.githubusercontent.com/DaveKT/Corning-NY-Local-History-Photo-Archive/master/datasette/metadata.yml#/).

## Background

The Corning Local History Photo Archive is a digitized collection of photographs documenting the history of Corning, NY, and the surrounding Chemung Valley. The collection covers civic life, architecture, floods, industry (particularly Corning Glass Works), schools, families, archaeological artifacts, and more.

Before this project, the archive's catalog had significant gaps: 53% of records lacked any subject keyword and 70% lacked a date. Tags and date formatting were inconsistent across records. This project addresses those gaps by pairing each image with AI-generated descriptive metadata that can be reviewed, corrected, and incorporated into the library's catalog.

## How It Works

The pipeline has four stages, each handled by a standalone Python script.

### 1. Download
[scripts/download_archive.py](scripts/download_archive.py)

Scrapes the archive website and downloads all full-resolution images into a local `photos/` directory. Supports concurrent downloads with configurable thread count and per-request delay. Skips previously downloaded files, making it safe to re-run.

```
python scripts/download_archive.py --output-dir ./photos --workers 4 --delay 0.25
```

### 2. Image Cataloging
[scripts/image_catalog.py](scripts/image_catalog.py)

Scans the downloaded photos and produces a CSV of technical metadata: dimensions, file size, colorspace, and MD5/SHA-256 hashes. This is used for deduplication checks and to identify anomalies (e.g., unusual aspect ratios or unexpectedly small files).

```
python scripts/image_catalog.py ./photos --output data/image_attributes.csv
```

### 3. AI Description
[scripts/process_photos.py](scripts/process_photos.py)

Sends each image to Claude Haiku (via the OpenRouter API) along with any existing catalog metadata for context. The model returns 3-5 descriptive tags and a one-sentence description per image. Results are saved incrementally to a JSON file, making the process resumable if interrupted.

```
export OPENROUTER_API_KEY="your-key-here"
python scripts/process_photos.py
```

The script also merges the AI-generated tags and descriptions back into the master CSV index.

### 4. Category Classification
[scripts/classify_photos.py](scripts/classify_photos.py)

Assigns each photo exactly one of 14 thematic categories (e.g., Disasters & Floods, Industry & Manufacturing, Streetscapes & Architecture) using rule-based keyword matching against the Subject, Tags, and Description fields. A strict priority hierarchy resolves ambiguity when a photo matches more than one category. The classifier is deterministic and uses only standard-library modules.

```
python scripts/classify_photos.py data/corning_photos.sqlite --output data/photo_categories.csv
```

The output CSV is imported into both `data/corning_photos.sqlite` and `datasette/corning_historic_photos.db` as a `category` table. The full category schema, priority rules, edge-case decisions, and distribution are documented in `analysis/category_classification.md`.

## Repository Structure

```
├── scripts/
│   ├── download_archive.py       # Stage 1: download images from archive website
│   ├── image_catalog.py          # Stage 2: extract technical image metadata
│   ├── process_photos.py         # Stage 3: AI-generated tags and descriptions
│   └── classify_photos.py        # Stage 4: rule-based category classification
├── data/
│   ├── local-history-photo-archive-index-20260301.csv   # Original catalog export
│   ├── local-history-photo-archive-index-20260314.csv   # Updated catalog with AI descriptions
│   ├── local-history-photo-archive-index-updated-20260314.xlsx  # Excel version of updated catalog
│   ├── image_attributes_20260314.csv    # Technical metadata per image (dimensions, hashes)
│   ├── image_attributes_20260314.log    # Errors from image cataloging
│   ├── corrected_results.json           # Raw AI-generated tags and descriptions (JSON)
│   ├── corning_photos.sqlite            # SQLite database of catalog data
│   ├── urls.csv                         # Filename-to-URL mapping for all archive images
│   ├── table_join.sql                   # SQL join query to produce the combined dataset
│   └── Duplicates.sql                   # Query for finding duplicate LHNo entries
├── analysis/
│   ├── collection structure.md          # Statistical analysis of the collection
│   ├── Corning_NY_Timeline.md           # Historical timeline derived from photo descriptions
│   ├── Corning_Photo_Descriptions.xlsx  # Photo descriptions in spreadsheet form
│   └── category_classification.md       # Category schema, methodology, and distribution
├── datasette/
│   ├── corning_historic_photos.db       # SQLite database for Datasette publishing
│   └── corning_historic_photos_20260321.csv  # Combined export (metadata + descriptions + URLs)
├── photos/                              # Downloaded images (not committed; see Setup)
├── .gitignore
└── README.md
```

## Data Files

The `data/` directory contains both inputs and outputs of the pipeline:

- **local-history-photo-archive-index-20260301.csv** — The original catalog export from the archive website. Contains LH number, subject keywords, and date fields. Many records have multiple rows (one per subject keyword), so the row count (2,261) exceeds the unique photo count (1,977).
- **local-history-photo-archive-index-20260314.csv** — The same index after AI-generated tags and descriptions have been merged in.
- **corrected_results.json** — The raw AI output: a JSON object keyed by LH number, each containing `tags` (semicolon-delimited) and `description` (one sentence).
- **image_attributes_20260314.csv** — One row per image with filename, dimensions, megapixels, colorspace, file size, and cryptographic hashes (MD5, SHA-256).
- **urls.csv** — Maps each downloaded filename to its source URL on the archive website (1,981 entries).
- **table_join.sql** — SQL query that joins the metadata, photo_description, category, and urls tables to produce the combined dataset used for Datasette publishing.

## Analysis

The `analysis/` directory contains documents produced from the enriched data:

- **collection structure.md** — A statistical profile of the collection: series breakdown, dominant subjects, data quality issues (missing fields, inconsistent formatting, colorspace mismatches), and anomalies.
- **Corning_NY_Timeline.md** — A chronological narrative of Corning's history as documented by the 589 dated photographs in the collection, spanning 1842 to 1975. Covers the Civil War era, railroad development, major floods (1889, 1901, 1935, 1946, 1972), Corning Glass Works, and the archaeological record of the Chemung Valley.
- **category_classification.md** — Documents the 14-category classification schema applied to all 1,977 photos. Covers design goals, the priority hierarchy for resolving multi-category matches, keyword lists, edge-case rules, and the resulting distribution across categories.

## Results

AI descriptions were generated for all 1,977 images. Each record now has:

- **3-5 descriptive tags** based on visible image content (e.g., 'flooded street; brick buildings; 1940s automobiles; downtown; black and white photograph')
- **A one-sentence description** identifying visible text, landmarks, people, dates, and notable features

These supplement (not replace) the library's existing subject and date fields. The AI descriptions are intended as a draft layer for human review.

### Collection Highlights

The collection is organized into three series: 75 (1,641 photos), 76 (141 photos), and 77 (195 photos). Major subjects include:

- **Flood documentation** — 120 photos from the 1972 Hurricane Agnes flood alone, plus earlier floods in 1946, 1935, 1901, and 1889
- **Isabel Walker Drake Family** — 150+ photos of domestic and social life, mostly c. 1900
- **Ellsworth Cowles Collection** — 130 photos of archaeological artifacts from Chemung Valley sites
- **Corning Glass Works** — Industrial documentation from 1906 through the 1972 flood
- **Corning Free Academy** — Class photos, sports teams, and building views spanning the 1840s through 1970s

### Known Data Quality Issues

- 53% of records lack subject keywords; 70% lack dates
- Inconsistent date formatting (`c.1900` vs. `c. 1900`, `1920s` vs. `1920's`)
- Inconsistent geographic tags (`corning ny` vs. `corning new york`)
- 342 photos described as "black and white" but stored in RGB colorspace
- One panoramic outlier (75-0705) at 1386x180 pixels

These are documented in detail in `analysis/collection structure.md`.

### Datasette

The enriched catalog data is [published](https://lite.datasette.io/?url=https://raw.githubusercontent.com/DaveKT/Corning-NY-Local-History-Photo-Archive/master/datasette/corning_historic_photos.db&metadata=https://raw.githubusercontent.com/DaveKT/Corning-NY-Local-History-Photo-Archive/master/datasette/metadata.yml#/) as an interactive [Datasette](https://datasette.io/) instance for browsing and querying. Datasette is an open-source tool that serves SQLite databases as a web interface with built-in search, filtering, and a JSON/CSV API.

The `datasette/` directory contains the publication-ready database (`corning_historic_photos.db`) and a combined CSV export (`corning_historic_photos_20260321.csv`). The database was produced by joining the image metadata, catalog fields (subject, date), AI-generated tags and descriptions, category assignments, and source URLs using the query in `data/table_join.sql`. The resulting dataset provides a single unified view of all 1,977 photographs with their technical attributes, descriptive metadata, thematic category, and direct links to the original images on the archive website. The category column enables filtering and browsing by topic (e.g., Disasters & Floods, Industry & Manufacturing).

## Setup

### Requirements

- Python 3.10+
- Dependencies: `requests`, `beautifulsoup4`, `Pillow`

```
pip install requests beautifulsoup4 Pillow
```

### Downloading the Photos

The `photos/` directory is not included in this repository due to size (~530 MB, 1,978 JPEG files). To download the images locally:

```
python scripts/download_archive.py --output-dir ./photos
```

This takes approximately 15-20 minutes depending on connection speed. The script is idempotent and skips existing files.

### Running the AI Description Pipeline

An [OpenRouter](https://openrouter.ai/) API key is required for `process_photos.py`. The script uses `anthropic/claude-haiku-4.5` by default.

```
export OPENROUTER_API_KEY="your-key-here"
python scripts/process_photos.py
```

The script saves progress every 10 images and resumes from where it left off. Processing all 1,977 images took a few hours and costs approximately $5 in API usage. Changes in model will cause these numbers to vary. I used Haiku as it was the cheapest model with "vision" capabilities at the time.

## License

The photographs in the Corning Local History Photo Archive are the property of the Southeast Steuben County Library. The code and analysis in this repository are provided for educational and digital humanities purposes.

## Acknowledgments

- **Southeast Steuben County Library** (Corning, NY) for digitizing and maintaining the photo archive
- **Corning-Painted Post Historical Society** for the underlying collection
- AI descriptions generated by Claude (Anthropic) via OpenRouter
