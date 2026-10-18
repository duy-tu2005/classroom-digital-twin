#!/usr/bin/env sh
set -eu
umask 077
deploy=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project=$(dirname "$deploy")
export HOST_UID=$(id -u) HOST_GID=$(id -g)
cd "$deploy"
test -f .env || { echo 'Missing private deployment/.env'; exit 1; }
chmod 600 .env
mkdir -p runtime
docker compose -f docker-compose.bootstrap.yml run --rm --build -T bootstrap
cp runtime/.env.local "$project/.env.local"
cp runtime/firmware/secrets.h "$project/firmware/secrets.h"
chmod 600 "$project/.env.local" "$project/firmware/secrets.h"
echo '[classroom] Deployed classroom to the existing AWS ThingsBoard'

