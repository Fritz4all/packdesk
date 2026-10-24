#!/bin/sh
set -e

# A new (empty) database gets its tables right away. Changes of a new version are only applied
# with RUN_MIGRATIONS=1, or with the "Update database" button in the browser after a backup, so an
# update never changes the database by surprise.
python manage.py setup_database

exec "$@"
