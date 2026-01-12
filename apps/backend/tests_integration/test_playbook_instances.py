import httpx
import pytest

pytestmark = pytest.mark.asyncio


async def test_playbook_instances_crud(client: httpx.AsyncClient, admin_token: str, uniq: str):
    headers = {"Authorization": f"Bearer {admin_token}"}

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

    tpl_payload = {
        "name": f"tpl-{uniq}",
        "description": "demo",
        "vars_schema": {"type": "object"},
        "vars_defaults": {"env": "dev"},
    }
    tpl = await client.post("/api/v1/playbook-templates/", json=tpl_payload, headers=headers)
    tpl.raise_for_status()
    tpl_id = tpl.json()["id"]

    inst_payload = {
        "name": f"inst-{uniq}",
        "template_id": tpl_id,
        "description": "instance",
        "values": {"env": "prod"},
        "host_ids": [],
        "group_ids": [],
    }
    created = await client.post("/api/v1/playbook-instances/", json=inst_payload, headers=headers)
    created.raise_for_status()
    inst_id = created.json()["id"]

    listing = await client.get("/api/v1/playbook-instances/", headers=headers)
    listing.raise_for_status()
    assert any(i["id"] == inst_id for i in listing.json())

    updated = await client.put(
        f"/api/v1/playbook-instances/{inst_id}",
        json={"description": "updated", "values": {"env": "stage"}},
        headers=headers,
    )
    updated.raise_for_status()
    assert updated.json()["description"] == "updated"

    run_resp = await client.post(
        f"/api/v1/playbook-instances/{inst_id}/run",
        json={"playbook_id": pb_id, "dry_run": True, "extra_vars": {}},
        headers=headers,
    )
    run_resp.raise_for_status()
    assert run_resp.json()["run_id"] > 0

    deleted = await client.delete(f"/api/v1/playbook-instances/{inst_id}", headers=headers)
    assert deleted.status_code == 204
