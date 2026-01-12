import httpx
import pytest

pytestmark = pytest.mark.asyncio


async def test_groups_and_playbook_run_lifecycle(client: httpx.AsyncClient, admin_token: str, uniq: str):
    headers = {"Authorization": f"Bearer {admin_token}"}

    # create host
    host_payload = {
        "name": f"h-{uniq}",
        "hostname": "127.0.0.1",
        "port": 22,
        "username": "root",
        "os_type": "linux",
        "environment": "dev",
        "tags": {"env": "dev"},
        "description": None,
        "credential_id": None,
    }
    host_resp = await client.post("/api/v1/hosts/", json=host_payload, headers=headers)
    host_resp.raise_for_status()
    host_id = host_resp.json()["id"]

    # create dynamic group matching env=dev
    group_payload = {
        "name": f"g-{uniq}",
        "type": "dynamic",
        "description": "dyn",
        "rule": {"op": "and", "rules": [{"field": "environment", "op": "eq", "value": "dev"}]},
        "host_ids": [],
    }
    group_resp = await client.post("/api/v1/groups/", json=group_payload, headers=headers)
    group_resp.raise_for_status()
    group_id = group_resp.json()["id"]

    # recompute and check hosts in group
    rr = await client.post(f"/api/v1/groups/{group_id}/recompute-dynamic", headers=headers)
    assert rr.status_code == 204
    hosts = await client.get(f"/api/v1/groups/{group_id}/hosts", headers=headers)
    hosts.raise_for_status()
    assert any(h["id"] == host_id for h in hosts.json())

    # create playbook
    pb_payload = {
        "name": f"pb-{uniq}",
        "description": "demo",
        "stored_content": "---\n- name: demo\n  hosts: all\n  gather_facts: false\n  tasks:\n    - name: ping\n      ping:\n",
        "variables": {},
        "inventory_scope": [],
        "repo_path": None,
    }
    pb = await client.post("/api/v1/playbooks/", json=pb_payload, headers=headers)
    pb.raise_for_status()
    pb_id = pb.json()["id"]

    # create run (group target)
    run_req = {"host_ids": [], "group_ids": [group_id], "extra_vars": {}, "dry_run": True}
    run_resp = await client.post(f"/api/v1/playbooks/{pb_id}/run", json=run_req, headers=headers)
    run_resp.raise_for_status()
    run_id = run_resp.json()["id"]
    assert run_resp.json()["status"] == "pending"

    # claim (simulate worker)
    claim = await client.post(f"/api/v1/runs/{run_id}/claim", headers=headers)
    claim.raise_for_status()
    assert claim.json()["run"]["status"] == "running"
    assert claim.json()["playbook"]["id"] == pb_id

    # append log and set status
    al = await client.post(f"/api/v1/runs/{run_id}/append-log", json={"chunk": "hello\n"}, headers=headers)
    assert al.status_code == 204
    st = await client.post(f"/api/v1/runs/{run_id}/set-status", json={"status": "success"}, headers=headers)
    assert st.status_code == 204

    # fetch run and verify logs are present
    run_get = await client.get(f"/api/v1/runs/{run_id}", headers=headers)
    run_get.raise_for_status()
    assert "hello" in run_get.json()["logs"]

    # host should have last run fields updated
    host_get = await client.get(f"/api/v1/hosts/{host_id}", headers=headers)
    host_get.raise_for_status()
    assert host_get.json()["last_run_id"] == run_id
    assert host_get.json()["last_run_status"] == "success"


async def test_runs_stream_implicit_project_selection(client: httpx.AsyncClient, admin_token: str, uniq: str):
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    p1 = await client.post("/api/v1/projects/", json={"name": f"p1-{uniq}"}, headers=admin_headers)
    p1.raise_for_status()
    project_id = p1.json()["id"]

    user_email = f"viewer-{uniq}@example.local"
    created = await client.post(
        "/api/v1/users/",
        json={"email": user_email, "password": "viewer123", "role": "viewer", "allowed_project_ids": [project_id]},
        headers=admin_headers,
    )
    created.raise_for_status()

    login = await client.post("/api/v1/auth/login", json={"email": user_email, "password": "viewer123"})
    login.raise_for_status()
    user_token = login.json()["access_token"]

    pb_payload = {
        "name": f"pb-{uniq}",
        "description": "demo",
        "stored_content": "---\n- name: demo\n  hosts: all\n  gather_facts: false\n  tasks:\n    - name: ping\n      ping:\n",
        "variables": {},
        "inventory_scope": [],
        "repo_path": None,
    }
    pb = await client.post("/api/v1/playbooks/", json=pb_payload, headers={**admin_headers, "X-Project-Id": str(project_id)})
    pb.raise_for_status()
    pb_id = pb.json()["id"]

    run_req = {"host_ids": [], "group_ids": [], "extra_vars": {}, "dry_run": True}
    run_resp = await client.post(
        f"/api/v1/playbooks/{pb_id}/run",
        json=run_req,
        headers={**admin_headers, "X-Project-Id": str(project_id)},
    )
    run_resp.raise_for_status()
    run_id = run_resp.json()["id"]

    claim = await client.post(f"/api/v1/runs/{run_id}/claim", headers={**admin_headers, "X-Project-Id": str(project_id)})
    claim.raise_for_status()

    al = await client.post(
        f"/api/v1/runs/{run_id}/append-log",
        json={"chunk": "hello-stream\n"},
        headers={**admin_headers, "X-Project-Id": str(project_id)},
    )
    assert al.status_code == 204

    # Без project_id: backend должен выбрать доступный проект по allowed_project_ids.
    async with client.stream("GET", f"/api/v1/runs/{run_id}/stream?token={user_token}") as resp:
        assert resp.status_code == 200
        text = await resp.aread()
        assert b"hello-stream" in text
