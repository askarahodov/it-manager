import base64
import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings


def _derive_key() -> bytes:
    return hashlib.sha256(settings.master_key.encode("utf-8")).digest()


def encrypt_value(plaintext: str) -> str:
    key = _derive_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.b64encode(nonce + ciphertext).decode("utf-8")


def decrypt_value(token: str) -> str:
    key = _derive_key()
    aesgcm = AESGCM(key)
    decoded = base64.b64decode(token.encode("utf-8"))
    nonce = decoded[:12]
    ciphertext = decoded[12:]
    return aesgcm.decrypt(nonce, ciphertext, None).decode("utf-8")
