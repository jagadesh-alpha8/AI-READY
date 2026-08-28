#!/bin/sh
set -e

# Only the web process runs migrations/collectstatic on boot -- the celery
# service (`command: celery ...`) shares this same image but must not race
# the web container's migrate on every deploy.
if [ "$1" = "gunicorn" ]; then
  python manage.py migrate --noinput
  python manage.py collectstatic --noinput
fi

exec "$@"
