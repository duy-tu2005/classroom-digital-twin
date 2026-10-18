#!/usr/bin/env sh
set -eu
umask 077
deploy=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project=$(dirname "$deploy")
export HOST_UID=$(id -u) HOST_GID=$(id -g)
cd "$deploy"
if [ ! -f .env ]; then
  echo 'Run python3 deployment/init-env.py --host SERVER_IP first.'
  exit 1
fi
chmod 600 .env
mkdir -p runtime
docker compose up -d --wait --wait-timeout 120 postgres
schema=$(docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "SELECT to_regclass('\''public.tb_schema_settings'\'') IS NOT NULL;"' < /dev/null | tr -d '[:space:]')
if [ "$schema" != t ]; then docker compose --profile init run --rm -T thingsboard-install; fi
docker compose up -d thingsboard-ce
docker compose --profile bootstrap run --rm --build -T bootstrap
cp runtime/.env.local "$project/.env.local"
cp runtime/firmware/secrets.h "$project/firmware/secrets.h"
chmod 600 "$project/.env.local" "$project/firmware/secrets.h"
echo '[classroom] Standalone server ready'

