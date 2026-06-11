INSERT INTO status_code (status_id, code) VALUES
 (1,'HELD'),(2,'CONFIRMED'),(3,'PAID'),(4,'CANCELLED'),(5,'COMPLETE');

INSERT INTO reservation (res_id, start_date, channel, total_due)
SELECT g,
       DATE '2024-01-01' + (g % 1095),
       CASE g % 3 WHEN 0 THEN 'WEB' WHEN 1 THEN 'AGENT' ELSE 'API' END,
       (50 + (g % 900))::numeric(12,2)
FROM generate_series(1, 10000) g;

INSERT INTO reservation_item (item_id, res_id, status_id, updated_at)
SELECT g,
       ((g - 1) / 3) + 1,
       1 + (g % 5),
       TIMESTAMP '2024-01-01'
         + (((g - 1) / 3) % 525600) * interval '1 minute'
         + (g % 3) * interval '1 second'
FROM generate_series(1, 30000) g;
-- updated_at: per res_id the 3 items differ by seconds -> unique latest.

INSERT INTO traveler (traveler_id, res_id, age)
SELECT g, ((g - 1) / 2) + 1, 18 + (g % 60)
FROM generate_series(1, 20000) g;

ANALYZE;
