#!/bin/bash
# Rolls the credits/ASCII intro every time a fresh terminal connection
# opens -- ttyd spawns this script as a new process for every new
# websocket connection (embedded panel, full-screen tab, a reload, all
# count), so no "shown" flag is needed or wanted here.

mkdir -p /data

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
  "Built by KADHIR (JOKER-53)"
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

STUDENT_REPO="/data/repo"
mkdir -p "$STUDENT_REPO"
cd "$STUDENT_REPO" || cd /data
exec bash
