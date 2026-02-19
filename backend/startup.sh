#!/bin/bash

# Enable debugging
set -e

# Set default values if not provided
export MYSQL_SERVER=${MYSQL_SERVER:-db}
export MYSQL_PORT=${MYSQL_PORT:-3306}
export MYSQL_USER=${MYSQL_USER:-autonomy_user}
export MYSQL_PASSWORD=${MYSQL_PASSWORD:-autonomy_password}
export MYSQL_DB=${MYSQL_DB:-autonomy}
export MYSQL_ROOT_PASSWORD=${MYSQL_ROOT_PASSWORD:-19890617}

# Function to check database connection
check_db_connection() {
    echo "Testing database connection to ${MYSQL_SERVER}:${MYSQL_PORT}..."
    if python3 -c "
import pymysql
connection = pymysql.connect(
    host='${MYSQL_SERVER}',
    port=${MYSQL_PORT},
    user='${MYSQL_USER}',
    password='${MYSQL_PASSWORD}',
    database='${MYSQL_DB}',
    ssl=None
)
with connection.cursor() as cursor:
    cursor.execute('SELECT 1')" &>/dev/null; then
        return 0
    else
        return 1
    fi
}

# Wait for database to be ready with retries
MAX_RETRIES=${DB_CONNECTION_RETRIES:-30}
RETRY_DELAY=2

for ((i=1; i<=MAX_RETRIES; i++)); do
    if check_db_connection; then
        echo "✅ Database connection successful!"
        # Start the application
        echo "Starting application..."
        exec uvicorn main:app --host 0.0.0.0 --port 8000 --reload
        exit 0
    else
        if [ $i -eq $MAX_RETRIES ]; then
            echo "❌ Error: Could not connect to database after ${MAX_RETRIES} attempts. Exiting..."
            exit 1
        fi
        echo "⏳ Database not ready yet (attempt ${i}/${MAX_RETRIES}). Retrying in ${RETRY_DELAY} seconds..."
        sleep ${RETRY_DELAY}
    fi
done

echo "❌ Failed to connect to the database after ${MAX_RETRIES} attempts. Exiting..."
exit 1
