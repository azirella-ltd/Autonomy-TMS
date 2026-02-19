#!/bin/bash
set -e

# Log function
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1"
}

# Wait for MariaDB to be ready
MAX_RETRIES=60
COUNTER=0

log "Waiting for MariaDB to be ready..."
until mysql -h localhost -u root -p"$MARIADB_ROOT_PASSWORD" -e "SELECT 1" >/dev/null 2>&1; do
    COUNTER=$((COUNTER + 1))
    if [ $COUNTER -ge $MAX_RETRIES ]; then
        log "Error: MariaDB is not available after $MAX_RETRIES attempts"
        exit 1
    fi
    log "⏳ Database not ready yet (attempt $COUNTER/$MAX_RETRIES). Retrying in 2 seconds..."
    sleep 2
done

log "✅ MariaDB is ready. Initializing database..."

# Create database and user if they don't exist
mysql -h localhost -u root -p"$MARIADB_ROOT_PASSWORD" -e "
    -- Create database if it doesn't exist
    CREATE DATABASE IF NOT EXISTS \`$MARIADB_DATABASE\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
    
    -- Create user if it doesn't exist
    CREATE USER IF NOT EXISTS '$MARIADB_USER'@'%' IDENTIFIED BY '$MARIADB_PASSWORD';
    
    -- Grant privileges
    GRANT ALL PRIVILEGES ON \`$MARIADB_DATABASE\`.* TO '$MARIADB_USER'@'%';
    
    -- Apply changes
    FLUSH PRIVILEGES;
"

log "✅ Database and user created successfully"

# The init_db.sql file will be executed automatically by the MariaDB
# entrypoint after this script completes, so we no longer import it here
# to avoid running the schema twice and causing duplicate key errors.

# Run migrations if alembic is available
if command -v alembic &> /dev/null; then
    log "Running database migrations..."
    # Set the database URL for alembic
    export DATABASE_URL="mysql+pymysql://$MARIADB_USER:$MARIADB_PASSWORD@localhost:3306/$MARIADB_DATABASE"
    cd /app && alembic upgrade head
    log "✅ Database migrations completed"
fi

log "✅ Database setup is complete!"
