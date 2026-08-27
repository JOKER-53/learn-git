"""
Manages one isolated Docker container per student.

Architecture change from bind-mount to named volume:
- Each student gets their own named Docker volume: student-<reg_no>
- Their container mounts that volume at /data exclusively
- No student data ever touches the host/EC2 filesystem
- Git validation runs via docker exec inside the container instead of
  reading host paths directly

Lifecycle: create on login, REMOVE (not just stop) on logout.
This gives every session a clean container start (credits roll, ttyd
is fresh) while the VOLUME persists -- so repo data survives across
sessions even though the container itself is recreated each time.
"""
import os
import re

import docker
from docker.errors import NotFound

_client = None


def client():
    global _client
    if _client is None:
        _client = docker.from_env()
    return _client


NETWORK = os.environ.get("DOCKER_NETWORK", "learn-git_net")
WORKSPACE_IMAGE = os.environ.get("WORKSPACE_IMAGE", "learn-git-workspace:latest")

_SAFE_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def is_safe_reg_no(reg_no: str) -> bool:
    return bool(reg_no) and bool(_SAFE_RE.match(reg_no)) and len(reg_no) <= 64


def container_name(reg_no: str) -> str:
    return f"workspace-{reg_no.lower()}"


def volume_name(reg_no: str) -> str:
    """Each student gets their own named volume -- no host path involved."""
    return f"student-{reg_no.lower()}"


def ensure_volume(reg_no: str) -> str:
    """Create the student's named volume if it doesn't exist yet.
    Idempotent -- safe to call every login."""
    vol_name = volume_name(reg_no)
    c_client = client()
    try:
        c_client.volumes.get(vol_name)
    except NotFound:
        c_client.volumes.create(name=vol_name)
    return vol_name


def ensure_workspace(reg_no: str) -> str:
    """Create (or reuse if already running) this student's workspace
    container. Returns the container name. Container mounts their
    private named volume -- no host paths involved."""
    name = container_name(reg_no)
    c_client = client()

    # If already running, reuse it
    try:
        container = c_client.containers.get(name)
        if container.status == "running":
            return name
        # Exists but not running -- remove and recreate for a clean start
        container.remove(force=True)
    except NotFound:
        pass

    vol = ensure_volume(reg_no)

    c_client.containers.run(
        WORKSPACE_IMAGE,
        name=name,
        detach=True,
        network=NETWORK,
        environment={"REG_NO": reg_no},
        volumes={vol: {"bind": "/data", "mode": "rw"}},
        # No restart_policy -- containers are created on login and removed
        # on logout. The VOLUME persists so repo data is never lost.
        mem_limit="256m",
        nano_cpus=500_000_000,
    )
    return name


def remove_workspace(reg_no: str) -> None:
    """Force-remove the container on logout. The named volume is kept
    so repo data persists for next session."""
    name = container_name(reg_no)
    c_client = client()
    try:
        container = c_client.containers.get(name)
        container.remove(force=True)
    except NotFound:
        pass


def run_git_in_container(reg_no: str, *args) -> tuple:
    """Run a git command inside the student's running container via
    docker exec. Returns (ok: bool, stdout: str).
    This replaces the old host-path approach -- no host filesystem
    access needed for validation."""
    name = container_name(reg_no)
    c_client = client()
    try:
        container = c_client.containers.get(name)
        if container.status != "running":
            return False, "container not running"
        result = container.exec_run(
            ["git", "-C", "/data/repo", *args],
            stdout=True, stderr=False
        )
        return result.exit_code == 0, (result.output or b"").decode(errors="replace").strip()
    except Exception as e:
        return False, str(e)


def workspace_repo_path_in_container(reg_no: str) -> str:
    """Repo path as seen INSIDE the student's container."""
    return "/data/repo"


def workspace_container_exists(reg_no: str) -> bool:
    """True if the student has a running workspace container right now."""
    try:
        c = client().containers.get(container_name(reg_no))
        return c.status == "running"
    except NotFound:
        return False


def _find_git_server():
    c_client = client()
    containers = c_client.containers.list(
        filters={"label": "com.docker.compose.service=git-server"}
    )
    return containers[0] if containers else None


def ensure_git_remote(reg_no: str) -> None:
    """Create this student's bare repo on the git-server if not present."""
    if not is_safe_reg_no(reg_no):
        raise ValueError(f"unsafe reg_no: {reg_no!r}")
    git_server = _find_git_server()
    if git_server is None:
        raise RuntimeError("git-server container not found")
    repo_path = f"/repos/{reg_no}/practice.git"
    exit_code, output = git_server.exec_run(
        ["sh", "-c", f"mkdir -p {repo_path} && git init --bare -q {repo_path}"]
    )
    if exit_code != 0:
        raise RuntimeError(f"git init --bare failed: {output.decode(errors='replace')}")


def get_metrics() -> dict:
    """Snapshot of all student workspace containers and core services."""
    c_client = client()

    def _stats(c):
        try:
            s = c.stats(stream=False)
            mem = s.get("memory_stats", {}).get("usage", 0)
            lim = s.get("memory_stats", {}).get("limit", 0)
            cpu = s.get("cpu_stats", {})
            pcpu = s.get("precpu_stats", {})
            cpu_delta = cpu.get("cpu_usage", {}).get("total_usage", 0) - pcpu.get("cpu_usage", {}).get("total_usage", 0)
            sys_delta = cpu.get("system_cpu_usage", 0) - pcpu.get("system_cpu_usage", 0)
            ncpus = cpu.get("online_cpus") or len(cpu.get("cpu_usage", {}).get("percpu_usage") or [1])
            cpu_pct = round((cpu_delta / sys_delta) * ncpus * 100, 1) if sys_delta > 0 and cpu_delta > 0 else 0.0
            return {"mem_used_mb": round(mem/1024/1024, 1), "mem_limit_mb": round(lim/1024/1024, 1) if lim else None, "cpu_percent": cpu_pct}
        except Exception:
            return {"mem_used_mb": None, "mem_limit_mb": None, "cpu_percent": None}

    workspaces = []
    for c in c_client.containers.list(all=True):
        if not c.name.startswith("workspace-"):
            continue
        reg_no = c.name[len("workspace-"):]
        entry = {"reg_no": reg_no, "status": c.status}
        if c.status == "running":
            entry.update(_stats(c))
        workspaces.append(entry)

    core_services = {}
    for service in ["caddy", "webapp", "api", "git-server"]:
        containers = c_client.containers.list(all=True, filters={"label": f"com.docker.compose.service={service}"})
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
            entry.update(_stats(c))
        core_services[service] = entry

    return {"workspaces": workspaces, "core_services": core_services}


def reap_idle_workspaces(last_seen_map: dict, idle_hours: float) -> list:
    """Remove (not just stop) containers idle longer than idle_hours.
    Volume is kept so data persists."""
    from datetime import datetime as _dt
    c_client = client()
    now = _dt.utcnow()
    removed = []
    for c in c_client.containers.list(filters={"status": "running"}):
        if not c.name.startswith("workspace-"):
            continue
        reg_no = c.name[len("workspace-"):]
        last_seen = last_seen_map.get(reg_no)
        if last_seen is None:
            continue
        idle_for = (now - last_seen).total_seconds() / 3600
        if idle_for > idle_hours:
            try:
                c.remove(force=True)
                removed.append(reg_no)
            except Exception:
                pass
    return removed


def reset_workspace_volume(reg_no: str) -> None:
    """Wipe the /data/repo inside the student's named volume."""
    c_client = client()
    name = container_name(reg_no)
    try:
        container = c_client.containers.get(name)
        if container.status == "running":
            container.exec_run(["sh", "-c", "rm -rf /data/repo && mkdir -p /data/repo"])
            return
    except NotFound:
        pass
    
    vol = volume_name(reg_no)
    c_client.containers.run(
        "alpine",
        command=["sh", "-c", "rm -rf /data/repo && mkdir -p /data/repo"],
        remove=True,
        volumes={vol: {"bind": "/data", "mode": "rw"}},
    )
