# gh-issue-attachments

Upload images, videos, and files to GitHub issues from the command line.

GitHub has no public API for attaching files to issues. This tool reverse-engineers the browser's upload protocol — a 3-step flow through S3 presigned URLs — so you can do it programmatically.

## How it works

```mermaid
sequenceDiagram
    participant C as gh-attach
    participant G as github.com
    participant S as AWS S3

    C->>G: GET /owner/repo (preflight)
    G-->>C: _gh_sess cookie + fetch-nonce

    C->>G: POST /upload/policies/assets
    Note right of C: repo_id, filename, size, content_type
    G-->>C: 201: S3 presigned URL + form fields + asset ID

    C->>S: POST file + signed form fields
    S-->>C: 204 No Content

    C->>G: PUT /upload/assets/{id}
    Note right of C: authenticity_token
    G-->>C: 200: final href URL

    Note over C: https://github.com/user-attachments/assets/{uuid}
```

**Supported:** PNG, JPG, GIF, SVG, MP4, MOV, ZIP, PDF, and anything else GitHub's web UI accepts.

## Install

```bash
# Prerequisites
gh auth status          # must be authenticated
brew install uv         # or: curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone and install
git clone https://github.com/bc/gh-issue-attachments.git
cd gh-issue-attachments
uv sync

# Set your GitHub session cookie (required for uploads)
# Get it from: Browser DevTools → Application → Cookies → github.com → user_session
export GH_USER_SESSION='your_cookie_value'
```

## Usage

```bash
# Upload a file and get the URL
uv run gh-attach screenshot.png --repo owner/repo

# Upload and comment on an issue
uv run gh-attach diagram.png --repo owner/repo --issue 42

# Upload and append to an issue body
uv run gh-attach photo.jpg --repo owner/repo --issue-body 42 --alt "Photo of setup"

# Pipe the URL to other commands
URL=$(uv run gh-attach result.mp4 --repo owner/repo --quiet)
gh issue comment 42 --repo owner/repo --body "## Results
<video src=\"$URL\" controls></video>"
```

## Test

```bash
export GH_USER_SESSION='your_cookie_value'
./test.sh
```

The test checks `gh` is installed and authenticated, verifies your session cookie, uploads a 1-pixel test image, and confirms the returned URL is accessible.

## Claude Code Plugin

This repo includes a Claude Code skill called **lab-notebook** that documents your work session as a GitHub issue with inline attachments.

### Install the plugin

```
/plugin install https://github.com/bc/gh-issue-attachments
```

### Use it

Either invoke it directly:

```
/lab-notebook debug the flaky auth test in CI
```

Or just mention it inline:

> use the lab-notebook skill to debug the flaky auth test in CI

> fix the pagination bug and track it with a lab notebook

> create a lab notebook issue and investigate why the deploy is slow

Claude will:
1. Create a GitHub issue titled "Lab: debug the flaky auth test in CI"
2. Work on the task, attaching screenshots and notes as issue comments along the way
3. Add a summary comment when done
4. Open the issue in your browser as a complete record

## Authentication

The upload endpoint requires a browser session cookie, not a GitHub API token. The `gh` CLI's OAuth token (`gho_...`) authenticates against `api.github.com`, but the upload flow lives on `github.com` and requires web session auth.

**Required headers for CSRF:** `Sec-Fetch-Site: same-origin`, `Sec-Fetch-Mode: cors`, `Sec-Fetch-Dest: empty`, plus a `fetch-nonce` extracted from the page HTML.

Session cookies expire periodically — you'll need to refresh yours from the browser when uploads start failing with 422.

## License

MIT
