import httpx
import pytest

pytestmark = pytest.mark.asyncio


async def test_playbook_templates_crud(client: httpx.AsyncClient, admin_token: str, uniq: str):
    headers = {"Authorization": f"Bearer {admin_token}"}

    payload = {
        "name": f"tpl-{uniq}",
        "description": "demo",
        "vars_schema": {"type": "object", "properties": {"env": {"type": "string"}}},
        "vars_defaults": {"env": "dev"},
    }
    created = await client.post("/api/v1/playbook-templates/", json=payload, headers=headers)
    created.raise_for_status()
    tpl_id = created.json()["id"]

    listing = await client.get("/api/v1/playbook-templates/", headers=headers)
    listing.raise_for_status()
    assert any(t["id"] == tpl_id for t in listing.json())

    updated = await client.put(
        f"/api/v1/playbook-templates/{tpl_id}",
        json={"description": "updated", "vars_defaults": {"env": "prod"}},
        headers=headers,
    )
    updated.raise_for_status()
    assert updated.json()["description"] == "updated"

    deleted = await client.delete(f"/api/v1/playbook-templates/{tpl_id}", headers=headers)
    assert deleted.status_code == 204
