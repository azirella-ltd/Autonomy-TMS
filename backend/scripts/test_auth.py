import sys
from pathlib import Path
import requests
import json
import pytest

# Add the backend directory to the Python path
sys.path.append(str(Path(__file__).parent.parent))

from app.core.config import settings

def test_login():
    """Test user login and get JWT token."""
    login_url = f"http://localhost:8001{settings.API_V1_STR}/auth/login"
    test_data = {
        "username": "test@example.com",
        "password": "testpassword"
    }
    
    try:
        # Use form data format for OAuth2 password flow
        response = requests.post(login_url, data=test_data)
        response.raise_for_status()
        
        token_data = response.json()
        print("✅ Login successful!")
        print(f"Access token: {token_data.get('access_token')}")
        print(f"Token type: {token_data.get('token_type')}")
        
        return token_data.get('access_token')
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Login failed: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Status code: {e.response.status_code}")
            print(f"Response: {e.response.text}")
        return None

def test_protected_route():
    """Test accessing a protected route with the JWT token."""
    access_token = test_login()
    if not access_token:
        pytest.skip("Auth service not available")

    protected_url = f"http://localhost:8001{settings.API_V1_STR}/users/me"
    headers = {
        "Authorization": f"Bearer {access_token}"
    }

    try:
        response = requests.get(protected_url, headers=headers)
        response.raise_for_status()

        user_data = response.json()
        print("\n✅ Successfully accessed protected route!")
        print("User details:")
        print(json.dumps(user_data, indent=2))

    except requests.exceptions.RequestException as e:
        print(f"\n❌ Failed to access protected route: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Status code: {e.response.status_code}")
            print(f"Response: {e.response.text}")

if __name__ == "__main__":
    print("Testing authentication...\n")
    
    # Test login
    print("1. Testing login...")
    token = test_login()
    
    if token:
        # Test protected route
        print("\n2. Testing protected route...")
        test_protected_route()
