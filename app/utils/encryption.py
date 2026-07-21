import os
import logging
from cryptography.fernet import Fernet, InvalidToken
from typing import Optional

logger = logging.getLogger(__name__)

_fernet = None

def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        key_str = os.getenv("ENCRYPTION_KEY")
        if not key_str:
            logger.critical("No ENCRYPTION_KEY found in environment variables!")
            raise ValueError("ENCRYPTION_KEY environment variable is required but not set.")
            
        try:
            _fernet = Fernet(key_str.encode())
        except Exception as e:
            logger.critical(f"Invalid ENCRYPTION_KEY in environment: {e}")
            raise ValueError(f"ENCRYPTION_KEY is structurally invalid: {e}")
            
    return _fernet

def encrypt(plaintext: Optional[str]) -> Optional[str]:
    """Encrypt a plaintext string. Returns None if input is None or empty."""
    if not plaintext:
        return plaintext
    f = _get_fernet()
    return f.encrypt(plaintext.encode('utf-8')).decode('utf-8')

def decrypt(ciphertext: Optional[str]) -> Optional[str]:
    """Decrypt a ciphertext string. Returns None if input is None or empty."""
    if not ciphertext:
        return ciphertext
    try:
        f = _get_fernet()
        return f.decrypt(ciphertext.encode('utf-8')).decode('utf-8')
    except InvalidToken as e:
        logger.warning(f"Decryption failed (possibly legacy plaintext): {e}. Falling back to original string.")
        return ciphertext
