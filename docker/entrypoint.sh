#!/bin/sh
set -e

# Started as root: make sure the data folder belongs to PackDesk's own user (a folder created on the
# server usually belongs to someone else), then continue as that user.
if [ "$(id -u)" = "0" ]; then
  mkdir -p "${DATA_ROOT:-/data}"
  if [ "$(stat -c %U "${DATA_ROOT:-/data}")" != "app" ]; then
    chown -R app:app "${DATA_ROOT:-/data}"
  fi
  HOME=/app exec setpriv --reuid=app --regid=app --init-groups "$0" "$@"
fi

# A new (empty) database gets its tables right away. Changes of a new version are only applied
# with RUN_MIGRATIONS=1, or with the "Update database" button in the browser after a backup, so an
# update never changes the database by surprise.
python manage.py setup_database

# Reminders that are due go out from here, so an installation needs no separate scheduler. Only for the real
# server: a development server (RUN_TASKS=0) or a one-off command must not send anything.
case "${1:-}" in
  gunicorn)
    if [ "${RUN_TASKS:-1}" = "1" ]; then
      ( while :; do sleep 3600; python manage.py cmdb_warranty_mails >/dev/null 2>&1 || true; done ) &
    fi
    ;;
esac

exec "$@"
