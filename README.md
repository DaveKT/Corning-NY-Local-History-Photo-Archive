# Corning, NY Local History Photo Archive — AI-Assisted Cataloging

This project documents an effort to download, catalog, and enrich the [Corning, NY Local History Photo Archive](https://corningnyhistory.com/local-history-photo-archive/) using AI-generated image descriptions. The archive is maintained by the Southeast Steuben County Library and contains 1,977 digitized historical photographs spanning 1842 to 1975.

The goal is to improve the discoverability of these images by generating structured tags and one-sentence descriptions for every photo, supplementing the library's existing (and often sparse) subject/date metadata.

## Background

The Corning Local History Photo Archive is a digitized collection of photographs documenting the history of Corning, NY, and the surrounding Chemung Valley. The collection covers civic life, architecture, floods, industry (particularly Corning Glass Works), schools, families, archaeological artifacts, and more.

Before this project, the archive's catalog had significant gaps: 53% of records lacked any subject keyword and 70% lacked a date. Tags and date formatting were inconsistent across records. This project addresses those gaps by pairing each image with AI-generated descriptive metadata that can be reviewed, corrected, and incorporated into the library's catalog.

## How It Works

The pipeline has three stages, each handled by a standalone Python script.

### 1. Download (`scripts/download_archive.py`)

Scrapes the archive website and downloads all full-resolution images into a local `photos/` directory. Supports concurrent downloads with configurable thread count and per-request delay. Skips previously downloaded files, making it safe to re-run.

```
python scripts/download_archive.py --output-dir ./photos --workers 4 --delay 0.25
```

### 2. Image Cataloging (`scripts/image_catalog.py`)

Scans the downloaded photos and produces a CSV of technical metadata: dimensions, file size, colorspace, and MD5/SHA-256 hashes. This is used for deduplication checks and to identify anomalies (e.g., unusual aspect ratios or unexpectedly small files).

```
python scripts/image_catalog.py ./photos --output data/image_attributes.csv
```

### 3. AI Description (`scripts/process_photos.py`)

Sends each image to Claude Haiku (via the OpenRouter API) along with any existing catalog metadata for context. The model returns 3-5 descriptive tags and a one-sentence description per image. Results are saved incrementally to a JSON file, making the process resumable if interrupted.

```
export OPENROUTER_API_KEY="your-key-here"
python scripts/process_photos.py
```

The script also merges the AI-generated tags and descriptions back into the master CSV index.

## Repository Structure

```
├── scripts/
│   ├── download_archive.py       # Stage 1: download images from archive website
│   ├── image_catalog.py          # Stage 2: extract technical image metadata
│   └── process_photos.py         # Stage 3: AI-generated tags and descriptions
├── data/
│   ├── local-history-photo-archive-index-20260301.csv   # Original catalog export
│   ├── local-history-photo-archive-index-20260314.csv   # Updated catalog with AI descriptions
│   ├── local-history-photo-archive-index-updated-20260314.xlsx  # Excel version of updated catalog
│   ├── image_attributes_20260314.csv    # Technical metadata per image (dimensions, hashes)
│   ├── image_attributes_20260314.log    # Errors from image cataloging
│   ├── corrected_results.json           # Raw AI-generated tags and descriptions (JSON)
│   ├── corning_photos.sqlite            # SQLite database of catalog data
│   └── Duplicates.sql                   # Query for finding duplicate LHNo entries
├── analysis/
│   ├── collection structure.md          # Statistical analysis of the collection
│   ├── Corning_NY_Timeline.md           # Historical timeline derived from photo descriptions
│   └── Corning_Photo_Descriptions.xlsx  # Photo descriptions in spreadsheet form
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

## Analysis

The `analysis/` directory contains documents produced from the enriched data:

- **collection structure.md** — A statistical profile of the collection: series breakdown, dominant subjects, data quality issues (missing fields, inconsistent formatting, colorspace mismatches), and anomalies.
- **Corning_NY_Timeline.md** — A chronological narrative of Corning's history as documented by the 589 dated photographs in the collection, spanning 1842 to 1975. Covers the Civil War era, railroad development, major floods (1889, 1901, 1935, 1946, 1972), Corning Glass Works, and the archaeological record of the Chemung Valley.

## Results

AI descriptions were generated for all 1,977 images. Each record now has:

- **3-5 descriptive tags** based on visible image content (e.g., `flooded street; brick buildings; 1940s automobiles; downtown; black and white photograph`)
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
