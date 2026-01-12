import httpx
import pytest

pytestmark = pytest.mark.asyncio


async def test_secret_create_reveal_and_bind_to_host(client: httpx.AsyncClient, admin_token: str, uniq: str):
    headers = {"Authorization": f"Bearer {admin_token}"}

    # create secret
    secret_payload = {
        "name": f"sec-{uniq}",
        "type": "password",
        "scope": "global",
        "description": "integration",
        "tags": {"env": "test"},
        "value": "passw0rd!",
        "passphrase": None,
    }
    resp = await client.post("/api/v1/secrets/", json=secret_payload, headers=headers)
    resp.raise_for_status()
    secret = resp.json()
    assert secret["name"] == secret_payload["name"]
    assert "value" not in secret

    secret_id = secret["id"]

    # reveal (admin)
    resp = await client.post(f"/api/v1/secrets/{secret_id}/reveal", headers=headers)
    resp.raise_for_status()
    assert resp.json()["value"] == "passw0rd!"

    # create host bound to secret
    host_payload = {
        "name": f"h-{uniq}",
        "hostname": "127.0.0.1",
        "port": 22,
        "username": "root",
        "os_type": "linux",
        "environment": "test",
        "tags": {"env": "test"},
        "description": "integration host",
        "credential_id": secret_id,
    }
    resp = await client.post("/api/v1/hosts/", json=host_payload, headers=headers)
    resp.raise_for_status()
    host = resp.json()
    assert host["credential_id"] == secret_id
    assert host["username"] == "root"

    # get host by id
    resp = await client.get(f"/api/v1/hosts/{host['id']}", headers=headers)
    resp.raise_for_status()
    fetched = resp.json()
    assert fetched["id"] == host["id"]
    assert fetched["name"] == host["name"]

    # update username should work
    resp = await client.put(f"/api/v1/hosts/{host['id']}", json={"username": "admin"}, headers=headers)
    resp.raise_for_status()
    assert resp.json()["username"] == "admin"

    # delete secret should fail (bound)
    resp = await client.delete(f"/api/v1/secrets/{secret_id}", headers=headers)
    assert resp.status_code == 400

    # delete host then delete secret should pass
    resp = await client.delete(f"/api/v1/hosts/{host['id']}", headers=headers)
    assert resp.status_code == 204

    resp = await client.delete(f"/api/v1/secrets/{secret_id}", headers=headers)
    assert resp.status_code == 204
