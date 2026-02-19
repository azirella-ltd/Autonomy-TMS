#!/bin/bash

# Reset the admin password directly in the database
set -euo pipefail

if [[ -n "${DOCKER_COMPOSE:-}" ]]; then
  compose_cmd="${DOCKER_COMPOSE}"
elif docker compose version >/dev/null 2>&1; then
  compose_cmd="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  compose_cmd="docker-compose"
else
  echo "Docker Compose is required but was not found." >&2
  exit 1
fi

if [[ "${compose_cmd}" == "docker-compose" ]]; then
  export COMPOSE_API_VERSION="${COMPOSE_API_VERSION:-1.44}"
  export DOCKER_API_VERSION="${DOCKER_API_VERSION:-1.44}"
fi

${compose_cmd} exec db mysql -u autonomy_user -p'Autonomy@2025' -e "
  USE autonomy;
  UPDATE users
  SET hashed_password = '\$2b\$12\$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW'
  WHERE username = 'admin';

  SELECT 'Password reset complete' AS message;
"
