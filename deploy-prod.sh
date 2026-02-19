#!/bin/bash
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

# Load environment variables
if [ -f .env.prod ]; then
    export $(grep -v '^#' .env.prod | xargs)
else
    echo "Error: .env.prod file not found!"
    exit 1
fi

# Create necessary directories
mkdir -p config/nginx/ssl

# Generate self-signed SSL certificate (replace with Let's Encrypt in production)
if [ ! -f config/nginx/ssl/cert.pem ] || [ ! -f config/nginx/ssl/key.pem ]; then
    echo "Generating self-signed SSL certificate..."
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout config/nginx/ssl/key.pem \
        -out config/nginx/ssl/cert.pem \
        -subj "/C=US/ST=State/L=City/O=BeerGame/CN=localhost"
    chmod 600 config/nginx/ssl/*.pem
fi

# Build frontend
echo "Building frontend..."
cd frontend
npm install
npm run build
cd ..

# Build and start services
echo "Starting production services..."
${compose_cmd} -f docker-compose.prod.yml up -d --build

# Wait for database to be ready
echo "Waiting for database to be ready..."
${compose_cmd} -f docker-compose.prod.yml exec -T db bash -c 'while ! mysqladmin ping -h localhost --silent; do sleep 2; done'

# Run database migrations
echo "Running database migrations..."
${compose_cmd} -f docker-compose.prod.yml exec -T backend alembic upgrade head

# Restart backend to ensure all services are using the latest database schema
echo "Restarting backend service..."
${compose_cmd} -f docker-compose.prod.yml restart backend

echo ""
echo "Production deployment complete!"
echo "Application should be available at https://localhost (accept the self-signed certificate)"
echo ""
echo "To view logs:"
echo "  ${compose_cmd} -f docker-compose.prod.yml logs -f"
echo ""
echo "To stop the application:"
echo "  ${compose_cmd} -f docker-compose.prod.yml down"
