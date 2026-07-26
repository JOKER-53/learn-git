"""
Manages one isolated Docker container per student.

Each student's terminal runs in its own container (workspace-<reg_no>),
so concurrent students never touch the same shell or the same repo.
All workspace containers share one named volume, but each only ever
writes to its own subfolder: /data/<reg_no>/repo.

Requires the Docker socket to be mounted into this (api) container.
See SECURITY.md for the implications of that before deploying publicly.
"""
import os
import re

import docker
from docker.errors import NotFound, APIError

_client = None


def client():
    global _client
    if _client is None:
        _client = docker.from_env()
    return _client


NETWORK = os.environ.get("DOCKER_NETWORK", "learn-git_net")
WORKSPACE_IMAGE = os.environ.get("WORKSPACE_IMAGE", "learn-git-workspace:latest")
# Absolute HOST path (resolved by the Docker daemon, not by paths inside
# this api container) to the parent directory holding every student's
# folder. Each student's container gets ONLY <STUDENTS_HOST_PATH>/<reg_no>
# bind-mounted at /data -- never the whole tree -- so a student can never
# touch another student's files, even with `rm -rf /*` as root in their
# own container.
STUDENTS_HOST_PATH = os.environ.get("STUDENTS_HOST_PATH")

_SAFE_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def is_safe_reg_no(reg_no: str) -> bool:
    """Registration numbers become container names and URL path segments,
    so we only allow a conservative charset."""
    return bool(reg_no) and bool(_SAFE_RE.match(reg_no)) and len(reg_no) <= 64


def container_name(reg_no: str) -> str:
    return f"workspace-{reg_no.lower()}"


def ensure_workspace(reg_no: str) -> str:
    """Start (or reuse) this student's workspace container. Returns its name.
    Raises docker.errors.APIError / DockerException on failure -- callers
    should catch and log rather than block login on an orchestration hiccup.
    """
    if not STUDENTS_HOST_PATH:
        raise RuntimeError(
            "STUDENTS_HOST_PATH is not set -- required to isolate each "
            "student's container to their own folder. Set it in .env to "
            "an absolute host path, e.g. STUDENTS_HOST_PATH=/home/you/learn-git/students-data"
        )

    name = container_name(reg_no)
    c_client = client()

    try:
        container = c_client.containers.get(name)
        if container.status != "running":
            container.start()
        return name
    except NotFound:
        pass

    student_host_dir = os.path.join(STUDENTS_HOST_PATH, reg_no)
    # Docker creates this directory on the host automatically if it doesn't
    # exist yet, since it's a bind mount source.

    c_client.containers.run(
        WORKSPACE_IMAGE,
        name=name,
        detach=True,
        network=NETWORK,
        environment={"REG_NO": reg_no},
        volumes={student_host_dir: {"bind": "/data", "mode": "rw"}},
        restart_policy={"Name": "unless-stopped"},
        mem_limit="256m",
        nano_cpus=500_000_000,  # 0.5 CPU cap per student workspace
    )
    return name


def workspace_repo_path(reg_no: str) -> str:
    """Path where THIS (api) container can see the student's repo,
    via the same shared students volume mounted at /data."""
    return f"/data/{reg_no}/repo"


def remove_workspace(reg_no: str) -> None:
    """Stop and remove this student's workspace container.
    Does NOT delete their repo files on the students_data volume --
    only the container. Safe to call even if it doesn't exist."""
    name = container_name(reg_no)
    c_client = client()
    try:
        container = c_client.containers.get(name)
        container.remove(force=True)
    except NotFound:
        pass


def restart_workspace(reg_no: str) -> None:
    """Restart this student's workspace container. Used on logout to kill
    any live terminal connection (ttyd) tied to their old session -- any
    tab still open to it will fail to reconnect once nginx re-runs
    auth_request against the now-cleared session cookie.
    Safe to call even if the container doesn't exist (no-op)."""
    name = container_name(reg_no)
    c_client = client()
    try:
        container = c_client.containers.get(name)
        container.restart(timeout=2)
    except NotFound:
        pass
