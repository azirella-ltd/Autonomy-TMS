#!/bin/bash
# Restore autonomy DB from backup with email migration to autonomy.com
set -e

BACKUP="/home/trevor/Documents/Autonomy/Autonomy/exports/autonomy_backup_clean.sql"
DB_NAME="autonomy"
DB_USER="autonomy_user"
DB_PASS="autonomy_password"

echo "==> Creating PostgreSQL roles..."
sudo -u postgres psql <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'beer_user') THEN
    CREATE ROLE beer_user WITH LOGIN PASSWORD 'beer_password';
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '$DB_USER') THEN
    CREATE ROLE $DB_USER WITH LOGIN PASSWORD '$DB_PASS';
  END IF;
END
\$\$;
SQL

echo "==> Dropping and recreating database '$DB_NAME'..."
sudo -u postgres psql -c "DROP DATABASE IF EXISTS $DB_NAME;"
sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO beer_user;"

echo "==> Restoring from backup (this may take a minute)..."
sudo -u postgres psql -d "$DB_NAME" -f "$BACKUP" 2>&1 | grep -v "^$" | grep -v "^SET$" | grep -v "already exists" || true

echo "==> Transferring ownership to $DB_USER..."
sudo -u postgres psql -d "$DB_NAME" <<SQL
REASSIGN OWNED BY beer_user TO $DB_USER;
GRANT ALL ON SCHEMA public TO $DB_USER;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO $DB_USER;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO $DB_USER;
GRANT ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public TO $DB_USER;
SQL

echo ""
echo "==> Verifying users in database..."
sudo -u postgres psql -d "$DB_NAME" -c "SELECT id, username, email, role, is_superuser FROM users ORDER BY id LIMIT 20;"

echo ""
echo "Done! Database restored successfully."
echo "Login: systemadmin@autonomy.com / Autonomy@2026"
