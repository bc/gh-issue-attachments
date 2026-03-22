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

## Requirements

- `gh` CLI installed and authenticated
- `GH_USER_SESSION` env var set (run `./setup.sh && source .env` in the plugin directory, or extract manually from browser DevTools → Cookies → github.com → user_session)
- `uv` and `httpx` available (the skill will bootstrap these if needed)

## Workflow

### 1. Determine the repository

```bash
gh repo view --json nameWithOwner --jq .nameWithOwner
```
If that fails, ask the user which repo to use.

### 2. Create the issue

Extract a short title from the user's request:
```bash
gh issue create --title "Lab: $TITLE" --body "Lab notebook created by Claude Code." --json number,url
```
Save the issue number and URL. Print them clearly.

### 3. Bootstrap the upload script

Write the upload script to a temp file so it's available for attaching files. This is the full `gh-attach` tool inlined — it uploads files to GitHub via the undocumented user-attachments API (3-step S3 presigned URL flow):

```bash
cat > /tmp/gh_attach.py << 'PYEOF'
"""gh-attach: upload files to GitHub issues via the user-attachments API."""
import mimetypes, os, re, subprocess, sys
from pathlib import Path

try:
    import httpx
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "httpx", "-q"])
    import httpx

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"

def upload(file_path, owner, repo, session_cookie):
    p = Path(file_path)
    size = p.stat().st_size
    ct = mimetypes.guess_type(str(p))[0] or "application/octet-stream"
    repo_id = int(subprocess.run(
        ["gh", "api", f"repos/{owner}/{repo}", "--jq", ".id"],
        capture_output=True, text=True, check=True
    ).stdout.strip())

    cookies = httpx.Cookies()
    cookies.set("user_session", session_cookie, domain="github.com")
    cookies.set("logged_in", "yes", domain=".github.com")

    with httpx.Client(cookies=cookies, follow_redirects=True, timeout=60) as c:
        # Preflight: get _gh_sess + nonce
        pre = c.get(f"https://github.com/{owner}/{repo}", headers={"User-Agent": UA})
        m = re.search(r'<meta\s+name="fetch-nonce"\s+content="([^"]+)"', pre.text)
        if not m:
            raise RuntimeError("Could not find fetch-nonce")
        nonce = m.group(1)

        hdr = {
            "X-Requested-With": "XMLHttpRequest",
            "GitHub-Verified-Fetch": "true",
            "Accept": "application/json",
            "X-Fetch-Nonce": nonce,
            "Origin": "https://github.com",
            "Referer": f"https://github.com/{owner}/{repo}",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "User-Agent": UA,
        }

        # Step 1: upload policy
        r1 = c.post("https://github.com/upload/policies/assets", files={
            "repository_id": (None, str(repo_id)),
            "name": (None, p.name),
            "size": (None, str(size)),
            "content_type": (None, ct),
        }, headers=hdr)
        if r1.status_code != 201:
            raise RuntimeError(f"Policy failed ({r1.status_code}): {r1.text[:200]}")
        policy = r1.json()

        # Step 2: upload to S3
        fields = [(k, (None, v)) for k, v in policy["form"].items()]
        fields.append(("file", (p.name, p.read_bytes(), ct)))
        r2 = c.post(policy["upload_url"], files=fields)
        if r2.status_code not in (200, 201, 204):
            raise RuntimeError(f"S3 upload failed ({r2.status_code})")

        # Step 3: confirm
        r3 = c.put(
            f"https://github.com{policy['asset_upload_url']}",
            files={"authenticity_token": (None, policy["asset_upload_authenticity_token"])},
            headers=hdr,
        )
        if r3.status_code != 200:
            raise RuntimeError(f"Confirm failed ({r3.status_code})")
        return r3.json()["href"]

if __name__ == "__main__":
    url = upload(sys.argv[1], sys.argv[2], sys.argv[3], os.environ["GH_USER_SESSION"])
    print(url)
PYEOF
```

### 4. Do the work

Now do whatever work the user originally asked for. As you work, **document progress by adding comments to the issue**.

**To attach an image or screenshot:**
```bash
URL=$(python3 /tmp/gh_attach.py /path/to/image.png OWNER REPO)
gh issue comment NUMBER --repo OWNER/REPO --body "![description]($URL)"
```

**To attach a text note or code snippet:**
```bash
gh issue comment NUMBER --repo OWNER/REPO --body "### Step title

Description of what was done.

\`\`\`language
code snippet if relevant
\`\`\`"
```

**To attach any file (ZIP, PDF, etc.):**
```bash
URL=$(python3 /tmp/gh_attach.py /path/to/file.zip OWNER REPO)
gh issue comment NUMBER --repo OWNER/REPO --body "[filename.zip]($URL)"
```

### 5. What to document

- Add a comment when you **start** a significant step
- Attach **screenshots** of visual results (web pages, plots, UI changes)
- Attach **before/after diffs** for code changes
- Note any **errors encountered** and how they were resolved
- Add a **summary comment** when the task is complete

### 6. Close the notebook

When done:

1. Add a final summary comment:
```bash
gh issue comment NUMBER --repo OWNER/REPO --body "## Summary

- what was accomplished
- key findings or changes
- any follow-up items"
```

2. Open the issue in the browser:
```bash
open "https://github.com/OWNER/REPO/issues/NUMBER"
```

3. Tell the user: "Lab notebook is ready at [URL]"
