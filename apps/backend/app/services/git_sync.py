from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path

from app.core.config import settings


class GitSyncError(RuntimeError):
    pass


def _run_git(args: list[str], *, cwd: Path | None = None) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise GitSyncError(result.stderr.strip() or "git command failed")
    return result.stdout.strip()


def _ensure_repo(repo_dir: Path, repo_url: str) -> None:
    if (repo_dir / ".git").exists():
        return
    if repo_dir.exists():
        raise GitSyncError("repo directory exists but is not a git repo")
    repo_dir.parent.mkdir(parents=True, exist_ok=True)
    _run_git(["clone", repo_url, str(repo_dir)])


def _checkout_ref(repo_dir: Path, repo_ref: str | None) -> None:
    _run_git(["fetch", "--all", "--tags", "--prune"], cwd=repo_dir)
    if not repo_ref:
        return
    try:
        _run_git(["checkout", "--force", repo_ref], cwd=repo_dir)
    except GitSyncError:
        _run_git(["fetch", "--depth", "1", "origin", repo_ref], cwd=repo_dir)
        _run_git(["checkout", "--force", "FETCH_HEAD"], cwd=repo_dir)


def sync_playbook_repo(*, playbook_id: int, repo_url: str, repo_ref: str | None, repo_playbook_path: str) -> dict[str, str]:
    repo_dir = Path(settings.repo_sync_dir) / f"playbook_{playbook_id}"
    _ensure_repo(repo_dir, repo_url)
    _checkout_ref(repo_dir, repo_ref)

    rel_path = repo_playbook_path.lstrip("/").strip()
    if not rel_path:
        raise GitSyncError("repo_playbook_path пустой")
    file_path = repo_dir / rel_path
    if not file_path.exists() or not file_path.is_file():
        raise GitSyncError(f"Файл плейбука не найден: {repo_playbook_path}")

    content = file_path.read_text(encoding="utf-8")
    commit = _run_git(["rev-parse", "HEAD"], cwd=repo_dir)
    synced_at = datetime.utcnow().isoformat()
    return {"content": content, "commit": commit, "synced_at": synced_at}
