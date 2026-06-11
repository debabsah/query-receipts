WITH latest AS (
    SELECT ri.res_id, sc.code,
           ROW_NUMBER() OVER (PARTITION BY ri.res_id
                              ORDER BY ri.updated_at DESC) AS rn
    FROM reservation_item ri
    JOIN status_code sc ON sc.status_id = ri.status_id
), tc AS (
    SELECT t.res_id, COUNT(*) AS traveler_count
    FROM traveler t
    GROUP BY t.res_id
)
SELECT r.res_id,
       r.start_date,
       l.code AS latest_status,
       COALESCE(tc.traveler_count, 0) AS traveler_count
FROM reservation r
LEFT JOIN latest l ON l.res_id = r.res_id AND l.rn = 1
LEFT JOIN tc ON tc.res_id = r.res_id
WHERE r.start_date >= DATE '2025-01-01' AND r.start_date < DATE '2026-01-01'
