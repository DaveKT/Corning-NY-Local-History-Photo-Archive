**Collection Structure**

The dataset is organized into three numbered series (the LHNo prefix): series 75 (1,641 photos, ~83%), series 77 (195 photos), and series 76 (141 photos). There are also two parallel ID columns (`id` and `id.1`) where `id` increments by 2 most of the time while `id.1` increments by 1 -- suggesting the data was merged from two separate source tables. All 1,977 LHNo values are unique with no duplicates, and no duplicate file hashes exist, so each record represents a distinct image.

**Notable Patterns**

The 1972 flood dominates the collection -- 120 photos from that year alone, almost all flood-related. Combined with 1946 flood imagery (21 photos) and smaller sets from 1935, 1901, and 1889, flood documentation accounts for roughly 8% of the entire collection. This tracks with the two major Chemung River floods that devastated Corning (1946 from Hurricane Diane's aftermath and the catastrophic 1972 Agnes flood).

The Isabel Walker Drake Family Photo collection is the single largest subject group at 150+ photos, nearly all dated to circa 1900. The Ellsworth Cowles Collection (130 photos) is archaeologically focused -- its tags reference stone tools, Lamoka variants, and museum documentation, making it a distinctly different category from the rest of the civic/architectural photography.

Railroad references appear in 112 descriptions, church references in 76, and bank references in 46 -- reflecting Corning's identity as a railroad town and regional commercial center. The earliest item is actually not a photograph but an 1842 printed advertisement for Corning Academy, and the collection includes Civil War artifacts (medals, a bayonet, a military discharge document from 1862).

72% of images are stored as grayscale, consistent with a predominantly pre-color-photography collection.

**Anomalies and Data Quality Issues**

Several items stand out:

1. **High missing-data rates.** Subject is null for 1,052 rows (53%) and Date is null for 1,388 rows (70%). This is the most significant data quality concern -- the majority of records lack basic cataloging metadata.

2. **Inconsistent date formatting.** The same approximate date appears as both "c.1900" (81 occurrences) and "c. 1900" (70 occurrences). Decade references appear as both "1920s" and "1920's" (and likewise for the 1940s). One entry uses the compound value "1903 & 1928". These should be normalized.

3. **Inconsistent geographic tags.** "corning ny" appears in 165 records while "corning new york" appears in 111 -- same place, different tag strings. Similarly, "brick building" (112) vs. "brick buildings" (93) are likely meant to be the same tag.

4. **Colorspace/description mismatch.** 342 photos are described in text as "black and white" but stored in RGB colorspace. Conversely, 400 photos stored as grayscale (L) are not described as black and white. The RGB files may simply be scans that preserved three channels despite the source being monochrome, but it introduces inconsistency between the metadata and the description text.

5. **Extreme aspect ratio outlier.** Photo 75-0705 has dimensions of 1386x180 pixels (aspect ratio 7.7:1) -- essentially a thin strip at only 0.25 megapixels. It is by far the smallest file in the collection at 29 KB. This likely represents a panoramic photo or a scanning/cropping artifact.

6. **ID gaps.** There are 51 gaps in the primary `id` column larger than the normal step of 2, implying approximately 91 records were removed or excluded from the export. The largest gaps skip 6 IDs at a time.

7. **Redundant columns.** `LHNo` and `LHNo.1` are identical across all 1,977 rows. One of these columns is unnecessary.