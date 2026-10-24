#!/bin/sh
set -e

# Database migrations run only when asked (RUN_MIGRATIONS=1), so a new image never changes the
# database by surprise.
if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
  python manage.py migrate --noinput
fi

exec "$@"
