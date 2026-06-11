#!/usr/bin/env bash
# Start (or reuse) the pgfleet Postgres container and load the workload.
set -euo pipefail
cd "$(dirname "$0")/.."

NAME=pgfleet

if [ -z "$(docker ps -q -f name=^${NAME}$)" ]; then
  docker rm -f $NAME >/dev/null 2>&1 || true
  docker run -d --name $NAME -e POSTGRES_PASSWORD=receipts \
    -p 15432:5432 postgres:16
fi

echo "waiting for Postgres…"
up=0
for i in $(seq 1 30); do
  if docker exec $NAME pg_isready -U postgres >/dev/null 2>&1; then up=1; break; fi
  sleep 2
done
if [ "$up" != 1 ]; then echo "Postgres never came up"; exit 1; fi

echo "loading schema + data…"
docker exec $NAME psql -U postgres -q \
  -c "DROP DATABASE IF EXISTS fleetdb WITH (FORCE);" \
  -c "CREATE DATABASE fleetdb;"
for f in schema.sql datagen.sql; do
  docker cp examples/pgfleet/$f $NAME:/tmp/$f
  docker exec $NAME psql -U postgres -d fleetdb -q -v ON_ERROR_STOP=1 -f /tmp/$f
done
echo "pgfleet ready on localhost:15432 (postgres / receipts, db fleetdb)"
