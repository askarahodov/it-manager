from app.core.security import create_access_token, verify_token


def test_jwt_roundtrip():
    token = create_access_token("user@example.local", extra={"role": "admin"})
    payload = verify_token(token)
    assert payload["sub"] == "user@example.local"
    assert payload["role"] == "admin"

