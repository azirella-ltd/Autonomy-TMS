from passlib.context import CryptContext

# Initialize the password context with bcrypt
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# The password we want to test
test_password = "Admin123!"

# The hash we have in the database (from our previous update)
stored_hash = "$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW"

# Test 1: Verify the stored hash
print("Testing stored hash:")
print(f"Stored hash: {stored_hash}")
print(f"Verification result: {pwd_context.verify(test_password, stored_hash)}")

# Test 2: Generate a new hash and verify it
print("\nTesting new hash generation:")
new_hash = pwd_context.hash(test_password)
print(f"New hash: {new_hash}")
print(f"Verification result: {pwd_context.verify(test_password, new_hash)}")

# Test 3: Print the first 10 characters of the hash for comparison
print("\nHash comparison:")
print(f"Stored hash start: {stored_hash[:10]}")
print(f"New hash start:     {new_hash[:10]}")

# Test 4: Check if the stored hash is a valid bcrypt hash
try:
    is_valid = pwd_context.identify(stored_hash) is not None
    print(f"\nIs stored hash a valid bcrypt hash? {is_valid}")
except Exception as e:
    print(f"Error checking hash validity: {e}")
