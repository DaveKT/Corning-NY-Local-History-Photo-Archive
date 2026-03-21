SELECT
	metadata.LHNo,
	metadata.filename,
	metadata.extension,
	metadata.size_bytes,
	metadata.size_human,
	metadata.width_px,
	metadata.height_px,
	metadata.megapixels,
	metadata.md5,
	metadata.sha256,
	photo_description."Subject:" AS Subject,
	photo_description.Date,
	photo_description.Tags,
	photo_description.Description,
	urls.url
FROM
	metadata,
	photo_description,
	urls
WHERE
	metadata.LHNo = photo_description.LHNo
	AND metadata.filename = urls.filename
ORDER BY
	metadata.LHNo