#!/bin/bash

#!/bin/bash

# Get database credentials from environment variables or use defaults
DB_ROOT_PASSWORD=${MYSQL_ROOT_PASSWORD:-Autonomy@2026}
DB_NAME=${MYSQL_DATABASE:-autonomy}
DB_USER=${MYSQL_USER:-autonomy_user}
DB_PASSWORD=${MYSQL_PASSWORD:-Autonomy@2026}

# Log the database initialization
echo "Initializing database: $DB_NAME with user: $DB_USER"

# Connect to MySQL and create the database and user
mysql -h db -u root -p"$DB_ROOT_PASSWORD" <<EOF
-- Create database if not exists
CREATE DATABASE IF NOT EXISTS \`$DB_NAME\`;

-- Create user if not exists and grant privileges
CREATE USER IF NOT EXISTS '$DB_USER'@'%' IDENTIFIED BY '$DB_PASSWORD';
GRANT ALL PRIVILEGES ON \`$DB_NAME\`.* TO '$DB_USER'@'%';
FLUSH PRIVILEGES;

-- Use the database
USE \`$DB_NAME\`;

CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NULL,
    email VARCHAR(100) NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    full_name VARCHAR(100) NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_superuser BOOLEAN NOT NULL DEFAULT FALSE,
    roles JSON NULL,
    last_login DATETIME NULL,
    last_password_change DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    failed_login_attempts INT NOT NULL DEFAULT 0,
    locked_until DATETIME NULL,
    mfa_secret VARCHAR(100) NULL,
    mfa_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_users_username (username),
    UNIQUE KEY uq_users_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS groups (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description TEXT NULL,
    logo VARCHAR(255) NULL,
    admin_id INT NOT NULL,
    UNIQUE KEY uq_group_admin (admin_id),
    CONSTRAINT fk_group_admin FOREIGN KEY (admin_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS group_id INT NULL,
    ADD CONSTRAINT fk_user_group FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE;

-- Insert default users if they don't exist
INSERT IGNORE INTO users (username, email, hashed_password, full_name, is_superuser, is_active) VALUES
('systemadmin', 'systemadmin@autonomy.ai', '\$2b\$12\$/FAxQ94QmW1WFdMZd5nKzegYJZkZSi.JUSX/4IvImY3cE2vtleAu6', 'System Admin', TRUE, TRUE);

-- Verify users were created
SELECT id, username, email, is_superuser, is_active FROM users;
EOF
