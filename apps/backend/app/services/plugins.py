from typing import Any

PLUGIN_DEFINITIONS: list[dict[str, Any]] = [
    {
        "id": "local-inventory",
        "type": "inventory",
        "name": "Local Inventory (DB)",
        "description": "Встроенный inventory на базе локальной БД.",
        "config_schema": [],
    },
    {
        "id": "local-secrets",
        "type": "secrets",
        "name": "Local Secrets Vault",
        "description": "Встроенное хранилище секретов (AES-GCM).",
        "config_schema": [],
    },
    {
        "id": "ansible-local",
        "type": "automation",
        "name": "Local Ansible Runner",
        "description": "Локальный Ansible Runner на воркере.",
        "config_schema": [],
    },
]


def list_definitions() -> list[dict[str, Any]]:
    return PLUGIN_DEFINITIONS


def get_definition(definition_id: str) -> dict[str, Any] | None:
    for item in PLUGIN_DEFINITIONS:
        if item["id"] == definition_id:
            return item
    return None


def validate_definition(definition_id: str, plugin_type: str) -> dict[str, Any]:
    definition = get_definition(definition_id)
    if not definition:
        raise ValueError("Неизвестный plugin definition")
    if definition["type"] != plugin_type:
        raise ValueError("Definition не соответствует выбранному типу")
    return definition
