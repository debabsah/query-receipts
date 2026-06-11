USE FleetDB;
SET NOCOUNT ON;
INSERT dbo.STATUS_CODE (STATUS_ID, CODE) VALUES
 (1,'HELD'),(2,'CONFIRMED'),(3,'PAID'),(4,'CANCELLED'),(5,'COMPLETE');

INSERT dbo.RESERVATION (RES_ID, START_DATE, CHANNEL, TOTAL_DUE)
SELECT value,
       DATEADD(DAY, value % 1095, '2024-01-01'),
       CASE value % 3 WHEN 0 THEN 'WEB' WHEN 1 THEN 'AGENT' ELSE 'API' END,
       CAST(50 + (value % 900) AS DECIMAL(12,2))
FROM GENERATE_SERIES(1, 200000);

INSERT dbo.RESERVATION_ITEM (ITEM_ID, RES_ID, STATUS_ID, UPDATED_AT)
SELECT s.value,
       ((s.value - 1) / 3) + 1,
       1 + (s.value % 5),
       DATEADD(SECOND, s.value % 3,
               DATEADD(MINUTE, ((s.value - 1) / 3) % 525600, '2024-01-01'))
FROM GENERATE_SERIES(1, 600000) s;
-- UPDATED_AT: per RES_ID the 3 items differ by seconds -> unique latest.

INSERT dbo.TRAVELER (TRAVELER_ID, RES_ID, AGE)
SELECT s.value, ((s.value - 1) / 2) + 1, 18 + (s.value % 60)
FROM GENERATE_SERIES(1, 400000) s;
GO
