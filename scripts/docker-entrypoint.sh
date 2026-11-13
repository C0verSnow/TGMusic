#!/bin/sh
set -eu
stamp=$(python -c 'import hashlib,platform; print(hashlib.sha256(open("/app/requirements.txt","rb").read()+platform.machine().encode()).hexdigest())')
if [ ! -f /state/python-deps/.tgmusic-stamp ] || [ "$(cat /state/python-deps/.tgmusic-stamp)" != "$stamp" ]; then
  python -m pip install --only-binary=:all: --no-compile --no-cache-dir --disable-pip-version-check --no-warn-script-location --quiet --upgrade --target /state/python-deps -r /app/requirements.txt
  printf '%s' "$stamp" > /state/python-deps/.tgmusic-stamp
fi
exec python /app/scripts/docker_session.py "$@"
