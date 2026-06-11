#!/usr/bin/env bash
# Start (or reuse) the FleetDB SQL Server container and load the workload.
set -euo pipefail
cd "$(dirname "$0")/.."

NAME=fleetdb
PASS='Receipts!Pr00f1'
SQLCMD="/opt/mssql-tools18/bin/sqlcmd -C -S localhost -U sa -P $PASS"

if [ -z "$(docker ps -q -f name=^${NAME}$)" ]; then
  docker rm -f $NAME >/dev/null 2>&1 || true
  docker run -d --name $NAME --platform linux/amd64 \
    -e ACCEPT_EULA=Y -e MSSQL_SA_PASSWORD="$PASS" \
    -p 14333:1433 mcr.microsoft.com/mssql/server:2022-latest
fi

echo "waiting for SQL Server…"
up=0
for i in $(seq 1 60); do
  if docker exec $NAME $SQLCMD -Q "SELECT 1" >/dev/null 2>&1; then up=1; break; fi
  sleep 5
done
if [ "$up" != 1 ]; then echo "SQL Server never came up"; exit 1; fi

echo "loading schema + data…"
for f in schema.sql datagen.sql; do
  docker cp examples/fleetdb/$f $NAME:/tmp/$f
  docker exec $NAME $SQLCMD -b -i /tmp/$f
done
echo "FleetDB ready on localhost,14333 (sa / $PASS)"
