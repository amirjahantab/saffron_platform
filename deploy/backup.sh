#!/bin/sh
set -eu
umask 077
mkdir -p /backups
target="/backups/jahantab-$(date -u +%Y%m%dT%H%M%SZ).dump"
pg_dump --format=custom --no-owner --no-acl --file="$target.partial"
pg_restore --list "$target.partial" >/dev/null
mv "$target.partial" "$target"
sha256sum "$target" > "$target.sha256"
tar -czf "$target.media.tgz.partial" -C /media .
tar -tzf "$target.media.tgz.partial" >/dev/null
mv "$target.media.tgz.partial" "$target.media.tgz"
sha256sum "$target.media.tgz" > "$target.media.tgz.sha256"
printf 'Verified database archive created: %s\n' "$target"
