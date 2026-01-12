import httpx
import pytest

pytestmark = pytest.mark.asyncio


async def test_approval_flow_for_prod_run(client: httpx.AsyncClient, admin_token: str, uniq: str):
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    host_payload = {
        "name": f"prod-{uniq}",
        "hostname": "10.0.0.10",
        "port": 22,
        "username": "root",
        "os_type": "linux",
        "environment": "prod",
        "tags": {"env": "prod"},
        "description": None,
        "credential_id": None,
    }
    host_resp = await client.post("/api/v1/hosts/", json=host_payload, headers=admin_headers)
    host_resp.raise_for_status()
    host_id = host_resp.json()["id"]

    pb_payload = {
        "name": f"pb-{uniq}",
        "description": "prod run",
        "stored_content": "---\n- name: demo\n  hosts: all\n  gather_facts: false\n  tasks:\n    - name: ping\n      ping:\n",
        "variables": {},
        "inventory_scope": [],
        "repo_path": None,
    }
    pb_resp = await client.post("/api/v1/playbooks/", json=pb_payload, headers=admin_headers)
    pb_resp.raise_for_status()
    pb_id = pb_resp.json()["id"]

    run_resp = await client.post(
        f"/api/v1/playbooks/{pb_id}/run",
        json={"host_ids": [host_id], "group_ids": [], "extra_vars": {"env": "prod"}, "dry_run": True},
        headers=admin_headers,
    )
    run_resp.raise_for_status()
    run_data = run_resp.json()
    assert run_data["status"] == "pending"
    assert run_data["approval_status"] == "pending"
    run_id = run_data["id"]

    approvals = await client.get("/api/v1/approvals/", headers=admin_headers)
    approvals.raise_for_status()
    approval = next(item for item in approvals.json() if item["run_id"] == run_id)
    assert approval["run_id"] == run_id
    assert approval["status"] == "pending"

    operator_email = f"op-{uniq}@example.local"
    user_resp = await client.post(
        "/api/v1/users/",
        json={"email": operator_email, "password": "operator123", "role": "operator", "allowed_project_ids": [1]},
        headers=admin_headers,
    )
    user_resp.raise_for_status()

    login = await client.post("/api/v1/auth/login", json={"email": operator_email, "password": "operator123"})
    login.raise_for_status()
    operator_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    decision = await client.post(
        f"/api/v1/approvals/{approval['id']}/decision",
        json={"status": "approved", "reason": "ok"},
        headers=operator_headers,
    )
    assert decision.status_code == 403

    approve = await client.post(
        f"/api/v1/approvals/{approval['id']}/decision",
        json={"status": "approved", "reason": "ok"},
        headers=admin_headers,
    )
    assert approve.status_code == 204

    approvals_after = await client.get("/api/v1/approvals/", headers=admin_headers)
    approvals_after.raise_for_status()
    updated = next(item for item in approvals_after.json() if item["id"] == approval["id"])
    assert updated["status"] == "approved"
    assert updated["decided_at"] is not None

    run_get = await client.get(f"/api/v1/runs/{run_id}", headers=admin_headers)
    run_get.raise_for_status()
    assert run_get.json()["approval_status"] == "approved"
