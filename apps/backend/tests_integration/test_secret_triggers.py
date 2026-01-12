import httpx
import pytest

pytestmark = pytest.mark.asyncio


async def test_secret_rotated_trigger(client: httpx.AsyncClient, admin_token: str, uniq: str):
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    pb_payload = {
        "name": f"pb-secret-{uniq}",
        "description": "secret trigger",
        "stored_content": "---\n- name: demo\n  hosts: all\n  gather_facts: false\n  tasks:\n    - name: ping\n      ping:\n",
        "variables": {},
        "inventory_scope": [],
        "repo_path": None,
    }
    pb_resp = await client.post("/api/v1/playbooks/", json=pb_payload, headers=admin_headers)
    pb_resp.raise_for_status()
    pb_id = pb_resp.json()["id"]

    trigger_payload = {
        "playbook_id": pb_id,
        "type": "secret_rotated",
        "enabled": True,
        "filters": {"types": ["password"]},
        "extra_vars": {"source": "secret"},
    }
    trigger_resp = await client.post("/api/v1/playbook-triggers/", json=trigger_payload, headers=admin_headers)
    trigger_resp.raise_for_status()

    secret_payload = {
        "name": f"sec-{uniq}",
        "type": "password",
        "value": "initial",
        "scope": "project",
        "description": None,
        "tags": {"rotation": "yes"},
    }
    secret_resp = await client.post("/api/v1/secrets/", json=secret_payload, headers=admin_headers)
    secret_resp.raise_for_status()
    secret_id = secret_resp.json()["id"]

    host_payload = {
        "name": f"h-{uniq}",
        "hostname": "10.0.0.70",
        "port": 22,
        "username": "root",
        "os_type": "linux",
        "environment": "dev",
        "tags": {"role": "db"},
        "description": None,
        "credential_id": secret_id,
    }
    host_resp = await client.post("/api/v1/hosts/", json=host_payload, headers=admin_headers)
    host_resp.raise_for_status()

    update_resp = await client.put(
        f"/api/v1/secrets/{secret_id}",
        json={"value": "rotated"},
        headers=admin_headers,
    )
    update_resp.raise_for_status()

    runs = await client.get("/api/v1/runs/", headers=admin_headers)
    runs.raise_for_status()
    assert any(r["triggered_by"] == "trigger:secret_rotated" for r in runs.json())
