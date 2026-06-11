#!/usr/bin/env bash
docker rm -f fleetdb 2>/dev/null && echo "fleetdb removed" || echo "fleetdb was not running"
