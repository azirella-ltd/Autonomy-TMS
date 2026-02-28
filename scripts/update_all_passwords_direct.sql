-- Update all users' passwords to 'Autonomy@2026' with bcrypt hash
UPDATE users 
SET hashed_password = '$2b$12$UMHcqzCe6/PWKHP.kUDjBOaV9c.jM6WRDicfUAX7pE7STNXnMcr9i';

-- Verify the update
SELECT username, email, LEFT(hashed_password, 10) as password_hash_preview 
FROM users;
