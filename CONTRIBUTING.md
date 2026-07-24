# Contributing to learn-git

Thanks for considering a contribution — this project is meant to grow as a community teaching tool.

## Getting set up

```bash
git clone <this-repo-url>
cd learn-git
cp .env.example .env      # fill in a real SECRET_KEY at minimum
docker compose up --build
```

- Dashboard: http://localhost:8080
- Terminal: http://localhost:7681
- API: http://localhost:5000

## Project structure

```
learn-git/
├── api/          # Flask backend — auth, task validation, progress, admin
├── webapp/       # Static frontend — login, dashboard, admin pages
├── workspace/    # Student's terminal environment (Alpine + git + ttyd)
├── git-server/   # Bare git daemon for remote-operation tasks
├── tasks/        # tasks.json — the task tree (beginner → expert)
└── docker-compose.yml
```

## Adding a new task

1. Add an entry to `tasks/tasks.json` with a unique `id`, `tier`, `order`, `title`, `description`, `check` (validator name), optional `check_args`, and `prereq`.
2. If it needs a new kind of validation, add a function to `VALIDATORS` in `api/app.py`. Keep validators pure — they inspect repo state, they don't mutate it.
3. Restart the api service: `docker compose up --build api`.

## Code style

- Python: keep it simple and readable — this is a teaching tool, not a framework. Favor explicit code over cleverness.
- Frontend: plain HTML/CSS/JS on purpose (no build step, no bundler) — keep it that way unless there's a strong reason to add tooling.
- Commit messages: short, imperative ("Add rebase validator", not "Added" or "Adding").

## Submitting changes

1. Fork the repo and create a branch: `git checkout -b feature/my-change`.
2. Make your changes, test locally with `docker compose up --build`.
3. Open a pull request using the provided template.
4. Describe what you changed and why — screenshots help for UI changes.

## Reporting bugs

Use the bug report template when opening an issue. Include your OS, Docker version, and the exact command that failed.

## Security issues

Do not open a public issue for security vulnerabilities — see [SECURITY.md](./SECURITY.md).
