DROP TABLE IF EXISTS reservation_item;
DROP TABLE IF EXISTS traveler;
DROP TABLE IF EXISTS reservation;
DROP TABLE IF EXISTS status_code;

CREATE TABLE status_code (
    status_id   int          NOT NULL PRIMARY KEY,
    code        varchar(20)  NOT NULL
);
CREATE TABLE reservation (
    res_id      int           NOT NULL PRIMARY KEY,
    start_date  date          NOT NULL,
    channel     varchar(10)   NOT NULL,
    total_due   numeric(12,2) NOT NULL
);
CREATE TABLE reservation_item (
    item_id     int          NOT NULL PRIMARY KEY,
    res_id      int          NOT NULL,
    status_id   int          NOT NULL,
    updated_at  timestamp(0) NOT NULL
);
CREATE TABLE traveler (
    traveler_id int          NOT NULL PRIMARY KEY,
    res_id      int          NOT NULL,
    age         int          NOT NULL
);
-- Deliberately NO index on reservation_item(res_id) or traveler(res_id):
-- that's the pathology.
