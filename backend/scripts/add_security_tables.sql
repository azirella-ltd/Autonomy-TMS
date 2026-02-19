-- Align the users table with application expectations
ALTER TABLE users
    MODIFY COLUMN username VARCHAR(50) NULL,
    MODIFY COLUMN hashed_password VARCHAR(255) NOT NULL,
    ADD COLUMN IF NOT EXISTS roles JSON NULL AFTER is_superuser,
    ADD COLUMN IF NOT EXISTS last_login DATETIME NULL AFTER roles,
    ADD COLUMN IF NOT EXISTS last_password_change DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP AFTER last_login,
    ADD COLUMN IF NOT EXISTS failed_login_attempts INT NOT NULL DEFAULT 0 AFTER last_password_change,
    ADD COLUMN IF NOT EXISTS locked_until DATETIME NULL AFTER failed_login_attempts,
    ADD COLUMN IF NOT EXISTS mfa_secret VARCHAR(100) NULL AFTER locked_until,
    ADD COLUMN IF NOT EXISTS mfa_enabled BOOLEAN NOT NULL DEFAULT FALSE AFTER mfa_secret,
    ADD COLUMN IF NOT EXISTS group_id INT NULL AFTER mfa_enabled,
    ADD COLUMN IF NOT EXISTS created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ADD COLUMN IF NOT EXISTS updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP;

ALTER TABLE users
    DROP COLUMN IF EXISTS is_locked,
    DROP COLUMN IF EXISTS lockout_until;

-- Create password_history table
CREATE TABLE IF NOT EXISTS password_history (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    hashed_password VARCHAR(100) NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Create password_reset_tokens table
CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    token VARCHAR(100) NOT NULL,
    expires_at DATETIME NOT NULL,
    is_used BOOLEAN NOT NULL DEFAULT FALSE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE KEY (token)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Update the alembic_version table to mark this migration as applied
-- This is a workaround since we're not using alembic for this migration
-- Replace '1234abcd5678' with the actual revision ID you want to use
-- If the table doesn't exist, this will be skipped
INSERT IGNORE INTO alembic_version (version_num) VALUES ('1234abcd5678');
