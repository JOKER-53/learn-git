import workspace_manager

def run_git(reg_no, *args):
    """Run git inside the student's running container via docker exec."""
    return workspace_manager.run_git_in_container(reg_no, *args)

def check_repo_exists(reg_no, _args):
    ok, _ = run_git(reg_no, "rev-parse", "--git-dir")
    return ok

def check_has_commit(reg_no, _args):
    ok, out = run_git(reg_no, "log", "--oneline")
    return ok and len(out) > 0

def check_branch_exists(reg_no, args):
    ok, out = run_git(reg_no, "branch", "--list", args["branch"])
    return ok and args["branch"] in out

def check_current_branch_is(reg_no, args):
    ok, out = run_git(reg_no, "rev-parse", "--abbrev-ref", "HEAD")
    return ok and out == args["branch"]

def check_branch_merged_into(reg_no, args):
    ok, out = run_git(reg_no, "branch", "--merged", args["into"])
    branches = [b.strip().lstrip("* ").strip() for b in out.splitlines()]
    return ok and args["branch"] in branches

def check_stash_not_empty(reg_no, _args):
    ok, out = run_git(reg_no, "stash", "list")
    return ok and len(out) > 0

def check_has_remote(reg_no, args):
    ok, out = run_git(reg_no, "remote")
    return ok and args["remote"] in out.splitlines()

def check_rebase_onto(reg_no, args):
    branch, onto = args["branch"], args["onto"]
    ok, _ = run_git(reg_no, "rev-parse", "--verify", branch)
    if not ok:
        return False
    ok, _ = run_git(reg_no, "merge-base", "--is-ancestor", onto, branch)
    if not ok:
        return False
    ok, ahead = run_git(reg_no, "rev-list", "--count", f"{onto}..{branch}")
    if not ok or not ahead.isdigit() or int(ahead) < 1:
        return False
    ok, merges = run_git(reg_no, "log", "--merges", "--oneline", f"{onto}..{branch}")
    return ok and merges.strip() == ""

def check_cherry_picked(reg_no, args):
    source, target = args["source"], args["target"]
    ok, base = run_git(reg_no, "merge-base", source, target)
    if not ok or not base:
        return False
    ok, source_log = run_git(reg_no, "log", "--format=%H %s", f"{base}..{source}")
    if not ok:
        return False
    source_commits = {}
    for line in source_log.splitlines():
        h, _, msg = line.partition(" ")
        source_commits[msg] = h
    ok, target_log = run_git(reg_no, "log", "--format=%H %s", f"{base}..{target}")
    if not ok:
        return False
    for line in target_log.splitlines():
        h, _, msg = line.partition(" ")
        if msg in source_commits and h != source_commits[msg]:
            return True
    return False

def check_in_sync_with_remote(reg_no, args):
    branch = args.get("branch", "main")
    remote = args.get("remote", "origin")
    ok1, local = run_git(reg_no, "rev-parse", branch)
    ok2, remote_sha = run_git(reg_no, "rev-parse", f"{remote}/{branch}")
    return ok1 and ok2 and local and local == remote_sha

def check_tag_exists(reg_no, args):
    ok, out = run_git(reg_no, "tag", "--list", args["tag"])
    return ok and args["tag"] in out.splitlines()

def check_branch_deleted(reg_no, args):
    ok, out = run_git(reg_no, "branch", "--list", args["branch"])
    return ok and args["branch"] not in out

def check_conflict_resolved(reg_no, _args):
    ok, unmerged = run_git(reg_no, "diff", "--name-only", "--diff-filter=U")
    if not ok or unmerged.strip():
        return False
    ok, merge_commit = run_git(reg_no, "log", "--merges", "-1", "--oneline")
    return ok and merge_commit.strip() != ""

def check_manual_review(reg_no, _args):
    return False

VALIDATORS = {
    "repo_exists": check_repo_exists,
    "has_commit": check_has_commit,
    "branch_exists": check_branch_exists,
    "current_branch_is": check_current_branch_is,
    "branch_merged_into": check_branch_merged_into,
    "stash_not_empty": check_stash_not_empty,
    "has_remote": check_has_remote,
    "rebase_onto": check_rebase_onto,
    "cherry_picked": check_cherry_picked,
    "in_sync_with_remote": check_in_sync_with_remote,
    "tag_exists": check_tag_exists,
    "branch_deleted": check_branch_deleted,
    "conflict_resolved": check_conflict_resolved,
    "manual_review": check_manual_review,
}
