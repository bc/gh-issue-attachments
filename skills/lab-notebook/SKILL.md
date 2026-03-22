---
name: lab-notebook
description: "Create a GitHub issue as a lab notebook, attach screenshots and files as you work, then open the issue when done. Trigger when the user says 'lab notebook', 'lab-notebook', or asks to track/document work in a GitHub issue with attachments."
allowed-tools: Bash, Read, Write, Glob, Grep, Agent
user-invocable: true
---

# Lab Notebook

Create a GitHub issue to document your work session. As you complete tasks, attach screenshots, code snippets, and files as comments on the issue. When finished, open the issue in the browser as a complete record.

This skill activates when:
- The user invokes `/lab-notebook <topic>` directly
- The user mentions "lab notebook" or "lab-notebook" inline (e.g. "use the lab-notebook skill to fix XYZ")

## Setup

This skill requires:
- `gh` CLI installed and authenticated (`gh auth status`)
- `GH_USER_SESSION` environment variable set (run `./setup.sh && source .env` in the plugin directory)
- `uv` installed (for the upload tool)
- The `gh-issue-attachments` tool synced (`cd <plugin-dir> && uv sync`)

## Workflow

Follow these steps exactly:

### 1. Determine the repository

Check if the current directory is a git repo with a GitHub remote:
```bash
gh repo view --json nameWithOwner --jq .nameWithOwner
```
If that fails, ask the user which repo to use.

### 2. Create the issue

Extract a short title from the user's request. Create the issue:
```bash
gh issue create --title "Lab: $TITLE" --body "Lab notebook created by Claude Code." --json number,url
```

Save the issue number and URL. Print them clearly:
```
Lab notebook created: #NUMBER
URL: https://github.com/owner/repo/issues/NUMBER
```

### 3. Work on the user's task

Now do whatever work the user originally asked for. As you work, **document progress by adding comments to the issue**. Attach relevant artifacts:

**To attach an image or screenshot:**
Find the plugin installation directory by looking for `gh_attach.py`:
```bash
PLUGIN_DIR=$(dirname "$(find ~/.claude -name gh_attach.py -path '*/gh-issue-attachments/*' 2>/dev/null | head -1)")
```

Then upload and comment:
```bash
URL=$(cd "$PLUGIN_DIR" && GH_USER_SESSION="$GH_USER_SESSION" uv run gh-attach /path/to/image.png --repo owner/repo 2>/dev/null)
gh issue comment NUMBER --repo owner/repo --body "![description]($URL)"
```

**To attach a text note or code snippet:**
```bash
gh issue comment NUMBER --repo owner/repo --body "### Step title

Description of what was done.

\`\`\`language
code snippet if relevant
\`\`\`"
```

**To attach any file (ZIP, PDF, etc.):**
```bash
URL=$(cd "$PLUGIN_DIR" && GH_USER_SESSION="$GH_USER_SESSION" uv run gh-attach /path/to/file.zip --repo owner/repo 2>/dev/null)
gh issue comment NUMBER --repo owner/repo --body "[filename.zip]($URL)"
```

### 4. Guidelines for what to document

- Add a comment when you **start** a significant step
- Attach **screenshots** of visual results (web pages, plots, UI changes)
- Attach **before/after diffs** for code changes
- Note any **errors encountered** and how they were resolved
- Add a **summary comment** when the task is complete

### 5. Close the notebook

When the work is done:

1. Add a final summary comment:
```bash
gh issue comment NUMBER --repo owner/repo --body "## Summary

- what was accomplished
- key findings or changes
- any follow-up items"
```

2. Open the issue in the browser:
```bash
open "https://github.com/owner/repo/issues/NUMBER"
```

3. Tell the user: "Lab notebook is ready at [URL]"
