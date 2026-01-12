import httpx
import pytest

pytestmark = pytest.mark.asyncio


async def test_host_created_trigger_creates_run(client: httpx.AsyncClient, admin_token: str, uniq: str):
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    pb_payload = {
        "name": f"pb-trigger-{uniq}",
        "description": "trigger",
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
        "type": "host_created",
        "enabled": True,
        "filters": {"environments": ["prod"]},
        "extra_vars": {"source": "trigger"},
    }
    trigger_resp = await client.post("/api/v1/playbook-triggers/", json=trigger_payload, headers=admin_headers)
    trigger_resp.raise_for_status()

    host_payload = {
        "name": f"h-{uniq}",
        "hostname": "10.0.0.50",
        "port": 22,
        "username": "root",
        "os_type": "linux",
        "environment": "prod",
        "tags": {"role": "db"},
        "description": None,
        "credential_id": None,
    }
    host_resp = await client.post("/api/v1/hosts/", json=host_payload, headers=admin_headers)
    host_resp.raise_for_status()

    runs = await client.get("/api/v1/runs/", headers=admin_headers)
    runs.raise_for_status()
    assert any(r["triggered_by"] == "trigger:host_created" for r in runs.json())


async def test_host_tags_changed_trigger(client: httpx.AsyncClient, admin_token: str, uniq: str):
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    pb_payload = {
        "name": f"pb-tags-{uniq}",
        "description": "trigger",
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
        "type": "host_tags_changed",
        "enabled": True,
        "filters": {"tags": {"role": "web"}},
        "extra_vars": {"from": "tags"},
    }
    trigger_resp = await client.post("/api/v1/playbook-triggers/", json=trigger_payload, headers=admin_headers)
    trigger_resp.raise_for_status()

    host_payload = {
        "name": f"ht-{uniq}",
        "hostname": "10.0.0.60",
        "port": 22,
        "username": "root",
        "os_type": "linux",
        "environment": "dev",
        "tags": {"role": "db"},
        "description": None,
        "credential_id": None,
    }
    host_resp = await client.post("/api/v1/hosts/", json=host_payload, headers=admin_headers)
    host_resp.raise_for_status()
    host_id = host_resp.json()["id"]

    update = await client.put(
        f"/api/v1/hosts/{host_id}",
        json={"tags": {"role": "web"}},
        headers=admin_headers,
    )
    update.raise_for_status()

    runs = await client.get("/api/v1/runs/", headers=admin_headers)
    runs.raise_for_status()
    assert any(r["triggered_by"] == "trigger:host_tags_changed" for r in runs.json())
