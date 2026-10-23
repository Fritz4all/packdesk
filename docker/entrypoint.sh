#!/bin/sh
set -e

# Migrations run only when asked, so a new image never changes the
# database by surprise (the previous webshop migrated on every start).
if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
  python manage.py migrate --noinput
fi

exec "$@"
