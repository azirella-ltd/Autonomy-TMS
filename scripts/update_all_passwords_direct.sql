-- Update all users' passwords to 'Autonomy@2025' with bcrypt hash
UPDATE users 
SET hashed_password = '$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW';

-- Verify the update
SELECT username, email, LEFT(hashed_password, 10) as password_hash_preview 
FROM users;
