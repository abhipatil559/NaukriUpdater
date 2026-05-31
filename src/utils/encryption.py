"""
Fernet-based encryption for storing Naukri passwords at rest.
The FERNET_KEY is set in the backend .env and never exposed to users.
"""

from cryptography.fernet import Fernet
import os

_key = os.getenv("FERNET_KEY", "")

def get_fernet():
    if not _key:
        raise RuntimeError("FERNET_KEY not set in environment")
    return Fernet(_key.encode())


def encrypt(plaintext: str) -> str:
    """Encrypt a string and return the ciphertext as a UTF-8 string."""
    return get_fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """Decrypt a ciphertext string back to plaintext."""
    return get_fernet().decrypt(ciphertext.encode()).decode()


def generate_key() -> str:
    """Generate a new Fernet key. Run once: python -c 'from src.utils.encryption import generate_key; print(generate_key())'"""
    return Fernet.generate_key().decode()
