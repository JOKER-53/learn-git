#!/bin/bash
# Rolls a one-time credits/ASCII intro, then drops into a normal shell.
# Runs once per container start (flag file lives in the ephemeral container fs,
# not the persisted volume, so it re-plays on every fresh container --
# change FLAG to live under /workspace-data if you want it to show only once ever).

FLAG="/tmp/.credits_shown"

if [ ! -f "$FLAG" ]; then
  GREEN='\033[0;32m'
  CYAN='\033[0;36m'
  YELLOW='\033[1;33m'
  BOLD='\033[1m'
  RESET='\033[0m'

  clear

  ART='
      _                          _ _
     | |                        (_) |
     | | ___  __ _ _ __ _ __ ___ _| |_
     | |/ _ \/ _` | `__| `_ ` _ \ | __|
     | |  __/ (_| | |  | | | | | | |_
     |_|\___|\__,_|_|  |_| |_| |_|_|\__|

        practical git, one task at a time
'

  # scroll the ASCII art in line by line
  while IFS= read -r line; do
    echo -e "${GREEN}${line}${RESET}"
    sleep 0.03
  done <<< "$ART"

  sleep 0.3

  CREDITS=(
    ""
    "learn-git — an interactive Git training workstation"
    ""
    "Built by KADHIR (KADHIRAVANEG)"
    "B.E. Computer Science (Cybersecurity)"
    "Sri Shakthi Institute of Engineering and Technology"
    ""
    "Stack: Flask · SQLite · Docker · ttyd · nginx"
    ""
    "Your progress is saved automatically."
    "docker compose down will NOT erase your work."
    ""
    "Type freely below. Good luck. 🐙"
    ""
  )

  for line in "${CREDITS[@]}"; do
    echo -e "${CYAN}${line}${RESET}"
    sleep 0.12
  done

  echo -e "${YELLOW}${BOLD}――――――――――――――――――――――――――――――――――――――――――――${RESET}"
  sleep 0.4

  touch "$FLAG"
fi

cd /workspace-data/repo || cd /workspace-data
exec bash
