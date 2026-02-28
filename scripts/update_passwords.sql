-- Update passwords for all users to 'Autonomy@2026'
-- The password will be hashed using the same algorithm used by the application

-- First, let's check the current users
SELECT id, username, email, is_active FROM users;

-- Update passwords using the same hashing algorithm as the app (bcrypt)
-- The hash for 'Autonomy@2026' is pre-computed using bcrypt with 12 rounds
UPDATE users 
SET hashed_password = '$2b$12$UMHcqzCe6/PWKHP.kUDjBOaV9c.jM6WRDicfUAX7pE7STNXnMcr9i',
    password_changed_at = NOW()
WHERE is_active = 1;

-- Verify the updates
SELECT id, username, email, is_active, password_changed_at FROM users;
