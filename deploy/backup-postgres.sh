#!/bin/sh
set -eu
umask 077
backup_parent=${1:?Provide a private backup directory}
backup_target="$backup_parent/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$backup_parent"
mkdir "$backup_target"
# Stop writers for a consistent database/upload snapshot, then always bring them back.
trap 'docker compose start app ai sources >/dev/null' EXIT HUP INT TERM
docker compose stop app ai sources
docker compose exec -T db pg_dump -U surveyor -d surveyor -Fc > "$backup_target/database.dump"
docker compose run --rm --no-deps -T --entrypoint tar app -C /app/data -czf - uploads > "$backup_target/uploads.tar.gz"
printf '%s\n' "Backup created: $backup_target"
