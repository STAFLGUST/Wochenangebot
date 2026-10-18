#!/bin/sh
# Exercise real production PHP image and Apache, not the built-in test server.
set -eu
REPO=$(cd "$(dirname "$0")/../.." && pwd)
T=$(mktemp -d)
NAME="wa-db-http-$$"
trap 'docker rm -f "$NAME" >/dev/null 2>&1 || true; rm -rf "$T"' EXIT
mkdir -p "$T/.sqlite"
printf 'Require all denied\n' > "$T/.sqlite/.htaccess"
printf 'private-database-content' > "$T/.sqlite/store.sqlite"
printf 'private-journal-content' > "$T/.sqlite/store.sqlite-journal"
docker run --rm php:8.3-apache php -r 'exit(in_array("sqlite", PDO::getAvailableDrivers(), true) ? 0 : 1);'
docker run -d --name "$NAME" -p 127.0.0.1:18887:80 -v "$REPO/app:/var/www/html:ro" -v "$T:/var/www/html/data:ro" php:8.3-apache >/dev/null
n=0
until curl -fsS http://127.0.0.1:18887/ >/dev/null; do
  n=$((n+1)); [ "$n" -lt 30 ] || exit 1; sleep 1
done
for path in data/.sqlite/store.sqlite data/.sqlite/store.sqlite-journal; do
  code=$(curl -sS -o "$T/response" -w '%{http_code}' "http://127.0.0.1:18887/$path")
  [ "$code" = 403 ] || [ "$code" = 404 ]
  ! grep -q private- "$T/response"
done
echo "PASS SQLite available; database and journal denied by Apache"
