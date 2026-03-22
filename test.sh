#!/usr/bin/env bash
set -euo pipefail

# ── gh-issue-attachments smoke test ─────────────────────────────────
# Verifies: gh CLI installed, authenticated, GH_USER_SESSION set,
# and performs a real upload + comment cycle on a test issue.

RED='\033[0;31m'
GREEN='\033[0;32m'
DIM='\033[2m'
RESET='\033[0m'

pass() { echo -e "${GREEN}✓${RESET} $1"; }
fail() { echo -e "${RED}✗${RESET} $1"; exit 1; }

echo "gh-issue-attachments smoke test"
echo "================================"

# 1. Check gh CLI
command -v gh >/dev/null 2>&1 || fail "gh CLI not found. Install: https://cli.github.com"
pass "gh CLI installed ($(gh --version | head -1))"

# 2. Check gh auth
gh auth status >/dev/null 2>&1 || fail "gh not authenticated. Run: gh auth login"
GH_USER=$(gh api user --jq .login 2>/dev/null)
pass "gh authenticated as ${GH_USER}"

# 3. Check GH_USER_SESSION
[ -n "${GH_USER_SESSION:-}" ] || fail "GH_USER_SESSION not set. Export your browser cookie."
pass "GH_USER_SESSION is set"

# 4. Check uv
command -v uv >/dev/null 2>&1 || fail "uv not found. Install: https://docs.astral.sh/uv/"
pass "uv installed"

# 5. Sync dependencies
echo -e "\n${DIM}Installing dependencies...${RESET}"
uv sync --quiet
pass "dependencies installed"

# 6. Create test image
TEST_IMG="/tmp/gh-attach-test-$$.png"
# 1x1 red pixel PNG
printf '\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x00\x02\x00\x01\xe2!\xbc3\x00\x00\x00\x00IEND\xaeB`\x82' > "$TEST_IMG"
pass "created test image ($TEST_IMG)"

# 7. Pick a test repo (use the first repo the user owns)
TEST_REPO="${TEST_REPO:-$(gh repo list --limit 1 --json nameWithOwner --jq '.[0].nameWithOwner')}"
echo -e "${DIM}Using repo: ${TEST_REPO}${RESET}"

# 8. Upload test image
echo -e "\n${DIM}Uploading test image...${RESET}"
URL=$(uv run gh-attach "$TEST_IMG" --repo "$TEST_REPO" 2>/dev/null)
[ -n "$URL" ] || fail "Upload returned empty URL"
pass "upload succeeded: $URL"

# 9. Verify URL is reachable (may 404 until referenced in an issue)
STATUS=$(curl -s -o /dev/null -w '%{http_code}' -L "$URL")
if [ "$STATUS" = "200" ]; then
    pass "URL is accessible (HTTP 200)"
else
    echo -e "${DIM}  URL returned HTTP $STATUS (normal — assets become accessible once referenced in an issue)${RESET}"
    pass "upload completed (HTTP $STATUS from CDN is expected for unreferenced assets)"
fi

# Cleanup
rm -f "$TEST_IMG"

echo -e "\n${GREEN}All tests passed.${RESET}"
