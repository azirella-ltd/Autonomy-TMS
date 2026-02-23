"""
Secret Management System
Phase 6 Sprint 5: Production Deployment & Testing

Secure management of API keys, database credentials, and other secrets.
"""

import os
import json
import base64
from typing import Optional, Dict, Any
from pathlib import Path
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2
from pydantic import BaseModel, Field, validator
class SecretConfig(BaseModel):
    """Secret configuration"""
    name: str = Field(..., description="Secret name")
    value: str = Field(..., description="Secret value")
    encrypted: bool = Field(default=False, description="Whether value is encrypted")
    required: bool = Field(default=True, description="Whether secret is required")
    env_var: Optional[str] = Field(None, description="Environment variable name")
class SecretsManager:
    """
    Manages application secrets with encryption and secure storage.

    Supports:
    - Environment variables
    - Encrypted files
    - AWS Secrets Manager (future)
    - Azure Key Vault (future)
    """

    def __init__(self, encryption_key: Optional[str] = None):
        """
        Initialize secrets manager.

        Args:
            encryption_key: Base64-encoded encryption key
        """
        self._encryption_key = encryption_key
        self._cipher = None
        self._secrets_cache: Dict[str, Any] = {}

        if encryption_key:
            self._cipher = Fernet(encryption_key.encode())

    @staticmethod
    def generate_key() -> str:
        """
        Generate a new encryption key.

        Returns:
            Base64-encoded encryption key
        """
        return Fernet.generate_key().decode()

    @staticmethod
    def derive_key_from_password(password: str, salt: Optional[bytes] = None) -> tuple[str, bytes]:
        """
        Derive encryption key from password.

        Args:
            password: Password to derive key from
            salt: Optional salt (generated if not provided)

        Returns:
            Tuple of (base64-encoded key, salt)
        """
        if salt is None:
            salt = os.urandom(16)

        kdf = PBKDF2(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return key.decode(), salt

    def encrypt_value(self, value: str) -> str:
        """
        Encrypt a secret value.

        Args:
            value: Plain text value

        Returns:
            Encrypted value (base64-encoded)

        Raises:
            ValueError: If encryption key not set
        """
        if not self._cipher:
            raise ValueError("Encryption key not set")

        encrypted = self._cipher.encrypt(value.encode())
        return base64.urlsafe_b64encode(encrypted).decode()

    def decrypt_value(self, encrypted_value: str) -> str:
        """
        Decrypt a secret value.

        Args:
            encrypted_value: Encrypted value (base64-encoded)

        Returns:
            Plain text value

        Raises:
            ValueError: If encryption key not set or decryption fails
        """
        if not self._cipher:
            raise ValueError("Encryption key not set")

        try:
            decoded = base64.urlsafe_b64decode(encrypted_value.encode())
            decrypted = self._cipher.decrypt(decoded)
            return decrypted.decode()
        except Exception as e:
            raise ValueError(f"Decryption failed: {e}")

    def get_secret(
        self,
        name: str,
        default: Optional[str] = None,
        required: bool = True
    ) -> Optional[str]:
        """
        Get a secret value.

        Priority:
        1. Environment variable
        2. Cached value
        3. Encrypted file
        4. Default value

        Args:
            name: Secret name
            default: Default value if not found
            required: Raise error if secret not found and no default

        Returns:
            Secret value or None

        Raises:
            ValueError: If secret not found and required=True
        """
        # Check cache first
        if name in self._secrets_cache:
            return self._secrets_cache[name]

        # Check environment variable
        env_value = os.getenv(name)
        if env_value:
            self._secrets_cache[name] = env_value
            return env_value

        # Check encrypted file
        file_value = self._load_from_file(name)
        if file_value:
            self._secrets_cache[name] = file_value
            return file_value

        # Use default or raise error
        if default is not None:
            return default

        if required:
            raise ValueError(f"Required secret not found: {name}")

        return None

    def set_secret(self, name: str, value: str, cache: bool = True):
        """
        Set a secret value in cache.

        Args:
            name: Secret name
            value: Secret value
            cache: Whether to cache the value
        """
        if cache:
            self._secrets_cache[name] = value

    def save_to_file(self, secrets: Dict[str, str], file_path: Path, encrypt: bool = True):
        """
        Save secrets to encrypted file.

        Args:
            secrets: Dictionary of secret name -> value
            file_path: Path to save file
            encrypt: Whether to encrypt values

        Raises:
            ValueError: If encryption enabled but no key set
        """
        if encrypt and not self._cipher:
            raise ValueError("Encryption key required for encrypted storage")

        # Prepare secrets data
        secrets_data = {}
        for name, value in secrets.items():
            if encrypt:
                secrets_data[name] = {
                    "value": self.encrypt_value(value),
                    "encrypted": True
                }
            else:
                secrets_data[name] = {
                    "value": value,
                    "encrypted": False
                }

        # Write to file
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, 'w') as f:
            json.dump(secrets_data, f, indent=2)

        # Set restrictive permissions (owner read/write only)
        os.chmod(file_path, 0o600)

    def load_from_file(self, file_path: Path) -> Dict[str, str]:
        """
        Load secrets from file.

        Args:
            file_path: Path to secrets file

        Returns:
            Dictionary of secret name -> value

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If decryption fails
        """
        if not file_path.exists():
            raise FileNotFoundError(f"Secrets file not found: {file_path}")

        with open(file_path, 'r') as f:
            secrets_data = json.load(f)

        secrets = {}
        for name, data in secrets_data.items():
            value = data["value"]
            encrypted = data.get("encrypted", False)

            if encrypted:
                value = self.decrypt_value(value)

            secrets[name] = value
            self._secrets_cache[name] = value

        return secrets

    def _load_from_file(self, name: str) -> Optional[str]:
        """
        Load a single secret from default secrets file.

        Args:
            name: Secret name

        Returns:
            Secret value or None
        """
        secrets_dir = Path(os.getenv("SECRETS_DIR", "/run/secrets"))
        file_path = secrets_dir / f"{name}.txt"

        if file_path.exists():
            with open(file_path, 'r') as f:
                value = f.read().strip()
                return value

        return None

    def validate_secrets(self, required_secrets: list[str]) -> Dict[str, bool]:
        """
        Validate that all required secrets are available.

        Args:
            required_secrets: List of required secret names

        Returns:
            Dictionary of secret name -> availability status
        """
        results = {}
        for secret_name in required_secrets:
            try:
                value = self.get_secret(secret_name, required=True)
                results[secret_name] = value is not None
            except ValueError:
                results[secret_name] = False

        return results
# Global secrets manager instance
_secrets_manager: Optional[SecretsManager] = None
def get_secrets_manager() -> SecretsManager:
    """
    Get global secrets manager instance.

    Returns:
        SecretsManager instance
    """
    global _secrets_manager

    if _secrets_manager is None:
        # Get encryption key from environment
        encryption_key = os.getenv("SECRETS_ENCRYPTION_KEY")
        _secrets_manager = SecretsManager(encryption_key)

    return _secrets_manager
# Required secrets for the application
REQUIRED_SECRETS = [
    "SECRET_KEY",              # FastAPI secret key
    "MARIADB_PASSWORD",        # Database password
]
def validate_environment_secrets() -> bool:
    """
    Validate that all required secrets are available.

    Returns:
        True if all secrets available, False otherwise
    """
    manager = get_secrets_manager()
    results = manager.validate_secrets(REQUIRED_SECRETS)

    missing = [name for name, available in results.items() if not available]

    if missing:
        print(f"Missing required secrets: {', '.join(missing)}")
        return False

    return True
def get_secret(name: str, default: Optional[str] = None, required: bool = False) -> Optional[str]:
    """
    Convenience function to get a secret.

    Args:
        name: Secret name
        default: Default value
        required: Whether secret is required

    Returns:
        Secret value or None
    """
    manager = get_secrets_manager()
    return manager.get_secret(name, default=default, required=required)
