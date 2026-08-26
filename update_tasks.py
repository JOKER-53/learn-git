import json
with open('tasks/tasks.json', 'r') as f:
    tasks = json.load(f)
new_tasks = [
    {"id": "amend-commit", "tier": "intermediate", "order": 6.5, "title": "Amend the last commit", "description": "Forgot to include a file or made a typo in your last commit message? Instead of creating a new commit, you can amend the previous one. Make a new commit, then change a file, stage it, and use `--amend` to add it to that same commit.", "hint": "Stage a file with `git add`, then run `git commit --amend --no-edit` to combine it with the last commit.", "check": "amend_commit", "prereq": "merge-dev"},
    {"id": "stash-pop", "tier": "intermediate", "order": 7.1, "title": "Retrieve stashed changes", "description": "Now that you have safely stashed your changes in the previous task, you can retrieve them. This pulls the changes out of the stash and applies them back to your working directory, simultaneously removing them from the stash list.", "hint": "Run `git stash pop`. Check `git status` to see your changes are back.", "check": "stash_popped", "prereq": "stash-changes"},
    {"id": "clean-tree", "tier": "beginner", "order": 3.8, "title": "Clean untracked files", "description": "Sometimes you create temporary files that you don't want to track or ignore. Git can clean these up for you automatically. Create a dummy file (e.g., `touch junk.txt`) and use Git to wipe your working directory clean of all untracked files.", "hint": "Run `git clean -f` to force Git to remove untracked files.", "check": "clean_working_tree", "prereq": "ignore-files"},
    {"id": "reset-hard", "tier": "advanced", "order": 11.8, "title": "Hard reset to a previous commit", "description": "If you want to completely throw away recent commits and all uncommitted changes, returning your project exactly to a previous state, you use a hard reset. Be careful: this permanently deletes uncommitted work. Reset your branch back by one commit.", "hint": "Run `git reset --hard HEAD~1` to move the current branch back by exactly one commit and force the working directory to match it.", "check": "reset_hard", "prereq": "revert-commit"}
]
tasks.extend(new_tasks)
tasks.sort(key=lambda x: x["order"])
with open('tasks/tasks.json', 'w') as f:
    json.dump(tasks, f, indent=2)
