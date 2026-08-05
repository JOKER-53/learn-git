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


def reap_idle_workspaces(last_seen_map: dict, idle_hours: float) -> list:
    """Stop (never remove) any running workspace-<reg_no> container whose
    student hasn't been active in `idle_hours`. Their repo data on the
    bind-mounted host folder is completely untouched -- ensure_workspace()
    just starts the container fresh again next time they log in.
    last_seen_map: {reg_no: datetime or None}. Returns the list of
    reg_nos whose container got stopped, for logging."""
    from datetime import datetime as _dt

    c_client = client()
    now = _dt.utcnow()
    stopped = []

    for c in c_client.containers.list(filters={"status": "running"}):
        if not c.name.startswith("workspace-"):
            continue
        reg_no = c.name[len("workspace-"):]
        last_seen = last_seen_map.get(reg_no)
        if last_seen is None:
            continue  # never recorded -- leave it alone rather than guess
        idle_for_hours = (now - last_seen).total_seconds() / 3600
        if idle_for_hours > idle_hours:
            try:
                c.stop(timeout=5)
                stopped.append(reg_no)
            except Exception:
                pass  # best-effort -- next sweep will retry

    return stopped


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


def _container_stats(c) -> dict:
    """One-shot memory + CPU snapshot for a running container. Docker's
    stats(stream=False) call blocks briefly (~1s) to take two samples
    internally, which is how CPU percent gets computed -- fine for an
    admin dashboard refresh, not something to call in a hot path."""
    try:
        s = c.stats(stream=False)
        mem_usage = s.get("memory_stats", {}).get("usage", 0)
        mem_limit = s.get("memory_stats", {}).get("limit", 0)

        cpu_stats = s.get("cpu_stats", {})
        precpu_stats = s.get("precpu_stats", {})
        cpu_delta = (
            cpu_stats.get("cpu_usage", {}).get("total_usage", 0)
            - precpu_stats.get("cpu_usage", {}).get("total_usage", 0)
        )
        system_delta = (
            cpu_stats.get("system_cpu_usage", 0)
            - precpu_stats.get("system_cpu_usage", 0)
        )
        online_cpus = cpu_stats.get("online_cpus") or len(
            cpu_stats.get("cpu_usage", {}).get("percpu_usage") or [1]
        )
        cpu_percent = 0.0
        if system_delta > 0 and cpu_delta > 0:
            cpu_percent = (cpu_delta / system_delta) * online_cpus * 100.0

        return {
            "mem_used_mb": round(mem_usage / (1024 * 1024), 1),
            "mem_limit_mb": round(mem_limit / (1024 * 1024), 1) if mem_limit else None,
            "cpu_percent": round(cpu_percent, 1),
        }
    except Exception:
        return {"mem_used_mb": None, "mem_limit_mb": None, "cpu_percent": None}


def get_metrics() -> dict:
    """Snapshot of every student workspace container's status/resources,
    plus the core services (nginx/webapp/api/git-server), for the admin
    metrics dashboard."""
    c_client = client()

    workspaces = []
    for c in c_client.containers.list(all=True):
        if not c.name.startswith("workspace-"):
            continue
        reg_no = c.name[len("workspace-"):]
        entry = {"reg_no": reg_no, "status": c.status}
        if c.status == "running":
            entry.update(_container_stats(c))
        workspaces.append(entry)

    core_services = {}
    for service in ["nginx", "webapp", "api", "git-server"]:
        containers = c_client.containers.list(
            all=True, filters={"label": f"com.docker.compose.service={service}"}
        )
        if not containers:
            continue
        c = containers[0]
        health = None
        try:
            health = c.attrs.get("State", {}).get("Health", {}).get("Status")
        except Exception:
            pass
        entry = {"status": c.status, "health": health}
        if c.status == "running":
            entry.update(_container_stats(c))
        core_services[service] = entry

    return {"workspaces": workspaces, "core_services": core_services}
    """Locate the git-server container by its compose service label rather
    than a hardcoded name, so this keeps working regardless of the compose
    project name. Returns None if not found (git-server not running)."""
    c_client = client()
    containers = c_client.containers.list(
        filters={"label": "com.docker.compose.service=git-server"}
    )
    return containers[0] if containers else None


def ensure_git_remote(reg_no: str) -> None:
    """Create this student's bare repo on the git-server, if it doesn't
    already exist, so the clone-remote task actually has something to
    clone at git://git-server/<reg_no>/practice.git. Safe to call
    repeatedly -- `git init --bare` on an already-initialized repo is a
    harmless no-op."""
    if not is_safe_reg_no(reg_no):
        raise ValueError(f"unsafe reg_no for git-server path: {reg_no!r}")

    git_server = _find_git_server()
    if git_server is None:
        raise RuntimeError("git-server container not found (is it running?)")

    repo_path = f"/repos/{reg_no}/practice.git"
    exit_code, output = git_server.exec_run(
        ["sh", "-c", f"mkdir -p {repo_path} && git init --bare -q {repo_path}"]
    )
    if exit_code != 0:
        raise RuntimeError(
            f"git init --bare failed for {reg_no}: {output.decode(errors='replace')}"
        )
