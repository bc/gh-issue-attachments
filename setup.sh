#!/usr/bin/env bash
set -euo pipefail

# ── gh-issue-attachments setup ──────────────────────────────────────
# Opens a browser for GitHub login, extracts the user_session cookie,
# and writes it to .env for use with gh-attach.

GREEN='\033[0;32m'
DIM='\033[2m'
BOLD='\033[1m'
RESET='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"

echo -e "${BOLD}gh-issue-attachments setup${RESET}"
echo "=========================="
echo ""

# Check playwright-cli is available
if ! command -v playwright-cli >/dev/null 2>&1; then
    if command -v npx >/dev/null 2>&1; then
        PLAYWRIGHT="npx playwright-cli"
    else
        echo "playwright-cli not found."
        echo "Install it:  npm install -g playwright-cli"
        exit 1
    fi
else
    PLAYWRIGHT="playwright-cli"
fi

echo "Opening GitHub login page in a browser..."
echo -e "${DIM}Log in with your GitHub credentials, then come back here.${RESET}"
echo ""

# Open headed browser with persistent profile so session persists
$PLAYWRIGHT open https://github.com/login --persistent --headed >/dev/null 2>&1 &
PW_PID=$!

# Wait for user to log in
echo -e "Press ${BOLD}Enter${RESET} after you've logged in to GitHub in the browser."
read -r

# Extract the user_session cookie
echo -e "${DIM}Extracting session cookie...${RESET}"
COOKIE=$($PLAYWRIGHT cookie-get user_session 2>/dev/null | grep -o 'user_session=[^ ]*' | cut -d= -f2-)

# Close the browser
$PLAYWRIGHT close >/dev/null 2>&1 || true
wait $PW_PID 2>/dev/null || true

if [ -z "$COOKIE" ]; then
    echo "Failed to extract cookie. Make sure you logged in successfully."
    exit 1
fi

# Write to .env
echo "GH_USER_SESSION=$COOKIE" > "$ENV_FILE"
echo ""
echo -e "${GREEN}✓${RESET} Session cookie saved to ${BOLD}.env${RESET}"
echo ""
echo "Usage:"
echo "  source .env"
echo "  uv run gh-attach screenshot.png --repo owner/repo"
echo ""
echo -e "${DIM}Cookie will expire eventually — re-run this script to refresh.${RESET}"
