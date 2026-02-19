#!/bin/bash
set -e

echo "Waiting for MariaDB to be ready..."
until mysqladmin ping -h "$MYSQL_SERVER" -u root -p"$MYSQL_ROOT_PASSWORD" --silent; do
    echo "Waiting for database connection..."
    sleep 2
done

echo "Creating database and user if they don't exist..."
mysql -h "$MYSQL_SERVER" -u root -p"$MYSQL_ROOT_PASSWORD" <<-EOSQL
    -- Create database if it doesn't exist
    CREATE DATABASE IF NOT EXISTS \`$MYSQL_DB\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
    
    -- Create user if it doesn't exist and set password
    CREATE USER IF NOT EXISTS '$MYSQL_USER'@'%' IDENTIFIED BY '$MYSQL_PASSWORD';
    
    -- Grant all privileges on the database to the user
    GRANT ALL PRIVILEGES ON \`$MYSQL_DB\`.* TO '$MYSQL_USER'@'%';
    
    -- Apply changes
    FLUSH PRIVILEGES;
    
    -- Show grants for the user (for debugging)
    SHOW GRANTS FOR '$MYSQL_USER'@'%';
EOSQL

echo "Database and user have been created/updated successfully!"

# Run any pending migrations
echo "Running database migrations..."
cd /app && alembic upgrade head

echo "Database initialization complete!"
