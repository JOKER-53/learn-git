# Learn Git

A hands-on, browser/terminal-based platform to learn Git by actually using it — not by reading about it.

Clone this repo, run `docker compose up`, and start completing real Git tasks in a real terminal. Your progress is saved automatically, even after you shut the environment down.

## How it works

1. **Clone & run**
   ```bash
   git clone <this-repo-url>
   cd learn-git
   docker compose up
   ```

2. **Pick a task** — e.g. "Create a new branch named `dev`" — from the platform UI.

3. **Do it in your terminal** — a real Git environment is provided. No simulations.

4. **Get validated** — the platform checks your actual repo state and marks the task complete.

5. **Progress persists** — your task progress and workspace state are stored in Docker volumes, so `docker compose down` never wipes your work.

## Task tracks

- **Beginner** — init, add, commit, status, log
- **Intermediate** — branching, merging, .gitignore, diff, stash
- **Advanced** — rebase, cherry-pick, reflog, bisect
- **Expert** — remote workflows: clone, push, pull, fetch, resolving conflicts, recovering from force-push

## Architecture (early plan)

- `webapp` — task list & progress UI
- `api` — task engine, validation, progress tracking
- `db` — stores user progress (persisted via Docker volume)
- `git-server` — bare git server for remote-operation tasks
- `workspace` — the student's real terminal/Git environment

## Status

🚧 Early scaffolding — architecture and task engine in progress.

## License

TBD
