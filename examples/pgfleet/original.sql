SELECT r.res_id,
       r.start_date,
       (SELECT sc.code
        FROM reservation_item ri
        JOIN status_code sc ON sc.status_id = ri.status_id
        WHERE ri.res_id = r.res_id
        ORDER BY ri.updated_at DESC
        LIMIT 1) AS latest_status,
       (SELECT COUNT(*) FROM traveler t
        WHERE t.res_id = r.res_id) AS traveler_count
FROM reservation r
WHERE EXTRACT(YEAR FROM r.start_date) = 2025
