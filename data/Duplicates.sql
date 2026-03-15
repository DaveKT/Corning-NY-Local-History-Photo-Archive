SELECT *
FROM photo_description
WHERE LHNo IN (
    SELECT LHNo
    FROM photo_description
    GROUP BY LHNo
    HAVING COUNT(LHNo) > 1
)
ORDER BY LHNo;