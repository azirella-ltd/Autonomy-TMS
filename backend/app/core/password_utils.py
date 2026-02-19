import re
from datetime import datetime, timedelta
from typing import List, Optional
from passlib.context import CryptContext

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def validate_password_strength(password: str) -> bool:
    """
    Validate password strength.
    - At least 12 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit
    - At least one special character
    - No common patterns (e.g., 'password', '1234')
    """
    if len(password) < 12:
        return False
    
    if not re.search(r'[A-Z]', password):
        return False
        
    if not re.search(r'[a-z]', password):
        return False
        
    if not re.search(r'\d', password):
        return False
        
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        return False
    
    # Check for common patterns
    common_patterns = [
        'password', '123456', 'qwerty', 'admin', 'welcome',
        'letmein', 'monkey', 'dragon', 'baseball', 'football'
    ]
    
    password_lower = password.lower()
    if any(pattern in password_lower for pattern in common_patterns):
        return False
        
    return True

def is_password_breached(password: str) -> bool:
    """
    Check if password has been exposed in data breaches.
    In a real implementation, this would check against haveibeenpwned API.
    """
    # This is a placeholder - in production, integrate with haveibeenpwned API
    return False

def get_password_hash(password: str) -> str:
    """Generate a secure password hash."""
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hash."""
    return pwd_context.verify(plain_password, hashed_password)
