import httpx
import pytest

pytestmark = pytest.mark.asyncio


async def test_auth_me(client: httpx.AsyncClient, admin_token: str):
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {admin_token}"})
    resp.raise_for_status()
    data = resp.json()
    assert data["email"] == "admin@it.local"
    assert data["role"] == "admin"


async def test_users_crud_admin(client: httpx.AsyncClient, admin_token: str, uniq: str):
    headers = {"Authorization": f"Bearer {admin_token}"}

    email = f"user-{uniq}@example.local"
    created = await client.post(
        "/api/v1/users/",
        json={"email": email, "password": "passw0rd!", "role": "user"},
        headers=headers,
    )
    created.raise_for_status()
    user_id = created.json()["id"]

    login = await client.post("/api/v1/auth/login", json={"email": email, "password": "passw0rd!"})
    login.raise_for_status()
    user_token = login.json()["access_token"]

    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {user_token}"})
    me.raise_for_status()
    assert me.json()["role"] == "user"

    # Projects scoping: пользователь видит/использует только разрешённые проекты.
    p1 = await client.post("/api/v1/projects/", json={"name": f"p1-{uniq}"}, headers=headers)
    p1.raise_for_status()
    p2 = await client.post("/api/v1/projects/", json={"name": f"p2-{uniq}"}, headers=headers)
    p2.raise_for_status()

    upd_scope = await client.put(
        f"/api/v1/users/{user_id}",
        json={"allowed_project_ids": [p1.json()["id"]]},
        headers=headers,
    )
    upd_scope.raise_for_status()

    # Создаём хост в p1, чтобы проверить implicit project selection для пользователя.
    created_host = await client.post(
        "/api/v1/hosts/",
        json={
            "name": f"h1-{uniq}",
            "hostname": "ssh-demo",
            "port": 22,
            "username": "demo",
            "environment": "dev",
            "os_type": "linux",
            "check_method": "tcp",
        },
        headers={**headers, "X-Project-Id": str(p1.json()["id"])},
    )
    created_host.raise_for_status()
    host_id = created_host.json()["id"]

    visible = await client.get("/api/v1/projects/", headers={"Authorization": f"Bearer {user_token}"})
    visible.raise_for_status()
    ids = {p["id"] for p in visible.json()}
    assert p1.json()["id"] in ids
    assert p2.json()["id"] not in ids

    # Без явного выбора проекта запросы в доменные сущности используют первый доступный проект.
    implicit_hosts = await client.get("/api/v1/hosts/", headers={"Authorization": f"Bearer {user_token}"})
    implicit_hosts.raise_for_status()
    assert any(h["id"] == host_id for h in implicit_hosts.json())

    ok_hosts = await client.get(
        "/api/v1/hosts/",
        headers={"Authorization": f"Bearer {user_token}", "X-Project-Id": str(p1.json()["id"])},
    )
    ok_hosts.raise_for_status()

    upd = await client.put(f"/api/v1/users/{user_id}", json={"role": "admin"}, headers=headers)
    upd.raise_for_status()
    assert upd.json()["role"] == "admin"

    deleted = await client.delete(f"/api/v1/users/{user_id}", headers=headers)
    assert deleted.status_code == 204
