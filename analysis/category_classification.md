# Photo Archive Category Classification

## Overview

This document describes the process used to assign a `category` field to each of the 1,977 photographs in the Corning, NY Local History Photo Archive. The category provides a high-level thematic grouping intended for browsing, filtering, and organizing the collection. Each photo is assigned exactly one category.

## Design Goals

The category schema was designed with three constraints in mind:

1. **Granularity.** The number of categories should be large enough that each label conveys distinct meaning, but small enough that photos can be logically grouped together for browsing. The target was 10–15 categories with no single category exceeding ~15% of the collection.
2. **Mutual exclusivity.** Many photos could plausibly belong to more than one category (e.g., a flooded street is both a disaster and a streetscape). A strict priority hierarchy ensures deterministic, single-category assignment even when multiple categories apply.
3. **User-friendliness.** Category names should be self-explanatory and require no domain expertise to interpret.

## Categories

The schema defines 14 categories. They are listed below in priority order — the order used to resolve ambiguity when a photo matches more than one category.

| Priority | Category | Description |
|----------|----------|-------------|
| 1 | Disasters & Floods | Flood damage, fires, train wrecks, structural collapses. The defining event, not the location. |
| 2 | Military & War | Soldiers, uniforms, Civil War and World War documentation, military equipment, memorials to service, firearms. |
| 3 | Archaeological Artifacts | Stone tools, arrowheads, fossils, museum documentation of pre-contact objects. Substantially the Ellsworth Cowles Collection. |
| 4 | Glass & Decorative Arts | Glass blowing, cutting, engraving, and etching; decorative patterns and designs; ceramic vessels; embroidery and textile documentation. |
| 5 | Industry & Manufacturing | Corning Glass Works facilities, factories, smokestacks, machinery, industrial interiors, construction sites, dairies, and other manufacturing. |
| 6 | Sports & Recreation | Baseball, football, country club, athletic teams, sailing ships, balloonists, beauty pageants. |
| 7 | Commerce & Business | Storefronts, banks, hotels, advertisements, markets, retail interiors, commercial signage. |
| 8 | Civic Life & Events | Parades, festivals, ceremonies, dedications, public gatherings, formal dinners, fire department documentation, concert and theater programs. |
| 9 | Education | Schools, class photos, graduation, academy buildings, diplomas, certificates. |
| 10 | People & Portraits | Formal portraits, headshots, group portraits, posed photographs where the subject is the person rather than an event or place. Also covers named individuals identified in the Subject field. |
| 11 | Transportation | Railroads, locomotives, automobiles, airplanes, bicycles, trolleys, horse-drawn vehicles — where the vehicle or mode of transit is the primary subject. |
| 12 | Domestic & Family Life | Family photos, homes, daily life, personal objects (watches, bells, musical instruments), genealogy documents, social gatherings in private settings. |
| 13 | Streetscapes & Architecture | Named streets, buildings, churches, bridges, parks, cemeteries, monuments, infrastructure — the built environment at rest. |
| 14 | Landscapes & Natural Features | Rivers, hills, forests, winter scenes, rural roads, rock formations, historical maps and land surveys. |

## Priority Hierarchy

The priority order resolves conflicts deterministically. A photo is assigned the first matching category from top to bottom. Some examples:

- A photo of a flooded street matches both Disasters & Floods (priority 1) and Streetscapes & Architecture (priority 13). It is assigned **Disasters & Floods**.
- A soldier's portrait matches both Military & War (priority 2) and People & Portraits (priority 10). It is assigned **Military & War**.
- A Corning Glass Works building exterior matches both Industry & Manufacturing (priority 5) and Streetscapes & Architecture (priority 13). It is assigned **Industry & Manufacturing**.
- A school football team matches both Education (priority 9) and Sports & Recreation (priority 6). It is assigned **Sports & Recreation**.
- A storefront on Market Street matches both Commerce & Business (priority 7) and Streetscapes & Architecture (priority 13). It is assigned **Commerce & Business**.
- A family photo in front of a house matches both Domestic & Family Life (priority 12) and Streetscapes & Architecture (priority 13). It is assigned **Domestic & Family Life**.

The general principle is that event-driven and specialized-content categories take precedence over setting-based categories. A photo of a fire on a street is about the fire, not the street.

## Classification Method

Classification was performed using rule-based keyword matching against three fields in the `photo_description` table: `Subject:`, `Tags`, and `Description`. The Tags and Description fields were generated by Claude Haiku via the AI description pipeline documented in the repository README.

For each photo, the classifier concatenates the three text fields and checks for the presence of category-specific keywords. The check proceeds through categories in priority order and assigns the first match. If no keyword matches, a secondary check examines the Subject field for geographic place names (which route to Streetscapes & Architecture) or personal names (which route to People & Portraits).

The classifier is deterministic — the same input always produces the same output. It can be re-run after keyword list adjustments without side effects.

### Keyword Examples by Category

These are representative, not exhaustive. The full keyword lists are in the classification script.

- **Disasters & Floods:** flood, floodwater, warehouse fire, house fire, building fire, fire fighting, emergency response, trainwreck
- **Military & War:** military uniform, soldier, civil war, world war, naval vessel, battleship, commemorative medal, firearm, adjutant general
- **Archaeological Artifacts:** archaeological, arrowhead, stone tools, projectile point, museum documentation, fossil, trilobite
- **Glass & Decorative Arts:** glass blow, glass cutting, steuben, decorative pattern, cullet, ceramic vessel, embroidery design
- **Industry & Manufacturing:** industrial factory, smokestack, glass works, machinery, construction site, quarry, cheese factory
- **Sports & Recreation:** baseball, football, country club, sailing ship, beauty pageant, monowheel
- **Commerce & Business:** storefront, bank, hotel, advertisement, merchant, retail, showroom
- **Civic Life & Events:** parade, festival, ceremony, dedication, procession, formal gathering, concert program
- **Education:** school, academy, class picture, graduation, diploma, certificate
- **People & Portraits:** portrait photograph, group portrait, formal attire, headshot, men in suits, stereoscopic
- **Transportation:** locomotive, railroad, automobile, airplane, trolley, horse-drawn carriage, bicycle
- **Domestic & Family Life:** family portrait, porch, parlor, picnic, pocket watch, hand bell, genealogy
- **Streetscapes & Architecture:** downtown street, church building, gothic architecture, cemetery, victorian building, unpaved road
- **Landscapes & Natural Features:** rural landscape, river, forest, hillside, farmland, historical map, land survey

### Named-Subject Heuristic

For records where the Subject field contains what appears to be a personal name (two or more capitalized words with no geographic or institutional keywords), the classifier assigns People & Portraits. This captures the many portrait records in the archive that have a person's name as the subject but no portrait-related keywords in the tags.

## Edge Case Decisions

Several recurring ambiguities were resolved with explicit rules:

- **Construction photos** route to Industry & Manufacturing when tagged with construction-site keywords, or to Streetscapes & Architecture when the Subject field indicates a named building or location under construction.
- **Miscellaneous personal objects** (pocket watches, bells, drums, parasols, preserved fruit jars) route to Domestic & Family Life, treating them as household artifacts rather than industrial or archaeological specimens.
- **Firearms** route to Military & War, given the archive's Civil War and WWI context.
- **Glass jars, ceramic vessels, and decorative wooden objects** route to Glass & Decorative Arts.
- **Historical maps and land surveys** route to Landscapes & Natural Features.
- **Firefighting photos** route to Disasters & Floods when depicting an active fire or fire response. Fire department organizational records (e.g., membership lists, equipment inventories outside of an emergency) route to Civic Life & Events.
- **Sailing ships and maritime photos** route to Sports & Recreation, as they appear to document leisure or travel rather than commercial shipping.

## Distribution

| Category | Count | % of Collection |
|----------|------:|----------------:|
| Disasters & Floods | 266 | 13.5% |
| Industry & Manufacturing | 246 | 12.4% |
| Streetscapes & Architecture | 199 | 10.1% |
| Commerce & Business | 175 | 8.9% |
| People & Portraits | 163 | 8.2% |
| Transportation | 141 | 7.1% |
| Civic Life & Events | 133 | 6.7% |
| Archaeological Artifacts | 133 | 6.7% |
| Military & War | 124 | 6.3% |
| Domestic & Family Life | 100 | 5.1% |
| Landscapes & Natural Features | 79 | 4.0% |
| Education | 75 | 3.8% |
| Glass & Decorative Arts | 72 | 3.6% |
| Sports & Recreation | 71 | 3.6% |
| **Total** | **1,977** | **100%** |

No photos remain uncategorized. The largest category (Disasters & Floods) represents 13.5% of the collection, and the smallest (Sports & Recreation) represents 3.6%. The distribution reflects the archive's historical emphasis on flood documentation, industrial heritage, and civic infrastructure.

## Limitations

- The classification relies entirely on text metadata (Subject, Tags, Description). Tags and Descriptions were AI-generated by Claude Haiku and may contain inaccuracies, which would propagate into category assignments.
- Keyword matching is literal and does not account for semantic similarity. A photo described in unusual language may be misclassified if none of the expected keywords appear.
- The priority hierarchy embeds editorial judgment about what a photo is "primarily about." Reasonable people may disagree on specific assignments, particularly for photos that straddle two categories.
- The 53% of records with no Subject field rely entirely on AI-generated Tags and Descriptions for classification, which may be less reliable than human-assigned subject metadata.
- Some categories (particularly Domestic & Family Life and Civic Life & Events) serve as catch-alls for photos that do not fit neatly elsewhere. Spot-checking these categories is recommended.

## Output

The classification output is a CSV file (`photo_categories.csv`) with two columns: `LHNo` (the archive photo identifier) and `Category` (one of the 14 values listed above). The file contains one row per photo, sorted by LHNo.
