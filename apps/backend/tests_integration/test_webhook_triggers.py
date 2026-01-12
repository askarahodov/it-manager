import httpx
import pytest

pytestmark = pytest.mark.asyncio


async def test_playbook_webhook_run(client: httpx.AsyncClient, admin_token: str, uniq: str):
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    host_payload = {
        "name": f"web-{uniq}",
        "hostname": "10.0.0.20",
        "port": 22,
        "username": "root",
        "os_type": "linux",
        "environment": "dev",
        "tags": {"env": "dev"},
        "description": None,
        "credential_id": None,
    }
    host_resp = await client.post("/api/v1/hosts/", json=host_payload, headers=admin_headers)
    host_resp.raise_for_status()
    host_id = host_resp.json()["id"]

    pb_payload = {
        "name": f"pb-web-{uniq}",
        "description": "webhook run",
        "stored_content": "---\n- name: demo\n  hosts: all\n  gather_facts: false\n  tasks:\n    - name: ping\n      ping:\n",
        "variables": {},
        "inventory_scope": [],
        "repo_path": None,
    }
    pb_resp = await client.post("/api/v1/playbooks/", json=pb_payload, headers=admin_headers)
    pb_resp.raise_for_status()
    pb_id = pb_resp.json()["id"]

    token_resp = await client.post(f"/api/v1/playbooks/{pb_id}/webhook-token", headers=admin_headers)
    token_resp.raise_for_status()
    token = token_resp.json()["token"]

    bad = await client.post(
        f"/api/v1/playbooks/{pb_id}/webhook?token=bad-token",
        json={"host_ids": [host_id], "group_ids": [], "extra_vars": {"from": "webhook"}, "dry_run": True},
    )
    assert bad.status_code == 403

    run_resp = await client.post(
        f"/api/v1/playbooks/{pb_id}/webhook?token={token}",
        json={"host_ids": [host_id], "group_ids": [], "extra_vars": {"from": "webhook"}, "dry_run": True},
    )
    run_resp.raise_for_status()
    run_data = run_resp.json()
    assert run_data["status"] == "pending"
    assert run_data["triggered_by"] == "webhook"
