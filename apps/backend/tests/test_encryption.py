from app.services.encryption import decrypt_value, encrypt_value


def test_encrypt_decrypt_roundtrip():
    plaintext = "super-secret-value"
    token = encrypt_value(plaintext)
    assert token != plaintext
    assert decrypt_value(token) == plaintext

