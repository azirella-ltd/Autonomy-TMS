#!/usr/bin/env bash
# Sets up a local .env based on hostname or example template
set -e

HOSTNAME=$(hostname)
HOST_ENV=".env.$HOSTNAME"

if [ -f "$HOST_ENV" ]; then
  cp "$HOST_ENV" .env
  echo "Loaded environment from $HOST_ENV"
elif [ -f ".env.local" ]; then
  cp .env.local .env
  echo "Loaded environment from .env.local"
else
  cp .env.example .env
  echo "Created .env from .env.example"
fi
