#!/usr/bin/env bash
docker rm -f pgfleet 2>/dev/null && echo "pgfleet removed" || echo "pgfleet was not running"
