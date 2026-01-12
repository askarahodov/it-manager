from fastapi import APIRouter

from app.api.v1.endpoints import audit, approvals, auth, groups, hosts, notifications, playbook_instances, playbook_templates, playbook_triggers, playbooks, projects, runs, secrets, users

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
api_router.include_router(projects.router, prefix="/projects", tags=["Projects"])
api_router.include_router(hosts.router, prefix="/hosts", tags=["Hosts"])
api_router.include_router(groups.router, prefix="/groups", tags=["Groups"])
api_router.include_router(playbooks.router, prefix="/playbooks", tags=["Playbooks"])
api_router.include_router(playbook_templates.router, prefix="/playbook-templates", tags=["PlaybookTemplates"])
api_router.include_router(playbook_triggers.router, prefix="/playbook-triggers", tags=["PlaybookTriggers"])
api_router.include_router(playbook_instances.router, prefix="/playbook-instances", tags=["PlaybookInstances"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["Notifications"])
api_router.include_router(runs.router, prefix="/runs", tags=["Runs"])
api_router.include_router(approvals.router, prefix="/approvals", tags=["Approvals"])
api_router.include_router(secrets.router, prefix="/secrets", tags=["Secrets"])
api_router.include_router(audit.router, prefix="/audit", tags=["Audit"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
