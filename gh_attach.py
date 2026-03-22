"""
gh-attach: Upload files to GitHub issues via the undocumented
user-attachments API.

GitHub's web UI uploads files through a 3-step flow:
  1. POST /upload/policies/assets  -> get presigned URL + form fields
  2. POST to storage backend       -> upload the file binary
  3. PUT  /upload/{type}/{id}      -> confirm upload, get final URL

Media files (images, videos) go to an S3 user-asset bucket and render
inline. Other files (ZIP, PDF, etc.) go to a repository-file bucket
and appear as download links.

Auth requires a browser session cookie (user_session), not an API token.
"""

from __future__ import annotations

import argparse
import mimetypes
import os
import re
import subprocess
import sys
from pathlib import Path

import httpx
from rich.console import Console

console = Console(stderr=True)

UPLOAD_POLICIES_URL = "https://github.com/upload/policies/assets"

BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)


def get_repo_id(owner: str, repo: str) -> int:
    """Get the numeric repository ID via gh CLI."""
    result = subprocess.run(
        ["gh", "api", f"repos/{owner}/{repo}", "--jq", ".id"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        console.print(f"[red]Failed to get repo ID: {result.stderr.strip()}[/red]")
        sys.exit(1)
    return int(result.stdout.strip())


def get_session_cookie() -> str:
    """Read the GitHub user_session cookie from env."""
    cookie = os.environ.get("GH_USER_SESSION", "")
    if not cookie:
        console.print(
            "[yellow]GH_USER_SESSION not set.[/yellow]\n"
            "Export your GitHub user_session cookie:\n"
            "  export GH_USER_SESSION='<value from browser DevTools>'\n"
            "  (Application -> Cookies -> github.com -> user_session)"
        )
        sys.exit(1)
    return cookie


def upload(
    file_path: Path,
    repo_id: int,
    session_cookie: str,
    owner: str,
    repo: str,
) -> str:
    """Upload a file through GitHub's 3-step protocol.

    Returns the final user-attachments URL.
    """
    file_size = file_path.stat().st_size
    content_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
    file_name = file_path.name

    cookies = httpx.Cookies()
    cookies.set("user_session", session_cookie, domain="github.com")
    cookies.set("logged_in", "yes", domain=".github.com")

    with httpx.Client(cookies=cookies, follow_redirects=True, timeout=60) as client:
        # -- Preflight: establish _gh_sess cookie + extract nonce ----
        console.print("[dim]Preflight: establishing session...[/dim]")
        preflight = client.get(
            f"https://github.com/{owner}/{repo}",
            headers={"User-Agent": BROWSER_UA},
        )
        if preflight.status_code != 200:
            console.print(f"[red]Preflight failed ({preflight.status_code})[/red]")
            sys.exit(1)

        nonce_match = re.search(
            r'<meta\s+name="fetch-nonce"\s+content="([^"]+)"',
            preflight.text,
        )
        if not nonce_match:
            console.print("[red]Could not find fetch-nonce in page[/red]")
            sys.exit(1)
        nonce = nonce_match.group(1)
        console.print(f"  [green]OK[/green] session established")

        # Sec-Fetch-* headers are required -- GitHub uses them for
        # CSRF validation alongside the session cookie and nonce.
        gh_headers = {
            "X-Requested-With": "XMLHttpRequest",
            "GitHub-Verified-Fetch": "true",
            "Accept": "application/json",
            "X-Fetch-Nonce": nonce,
            "Origin": "https://github.com",
            "Referer": f"https://github.com/{owner}/{repo}",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "User-Agent": BROWSER_UA,
        }

        # -- Step 1: get upload policy --------------------------------
        console.print(
            f"[cyan]Step 1/3[/cyan] upload policy for "
            f"[bold]{file_name}[/bold] ({file_size:,} bytes, {content_type})"
        )
        policy_resp = client.post(
            UPLOAD_POLICIES_URL,
            files={
                "repository_id": (None, str(repo_id)),
                "name": (None, file_name),
                "size": (None, str(file_size)),
                "content_type": (None, content_type),
            },
            headers=gh_headers,
        )
        if policy_resp.status_code != 201:
            console.print(f"[red]Upload policy failed ({policy_resp.status_code})[/red]")
            try:
                console.print(policy_resp.json())
            except Exception:
                console.print(policy_resp.text[:500])
            sys.exit(1)

        policy = policy_resp.json()
        upload_url = policy["upload_url"]
        form_fields = policy["form"]
        confirm_path = policy["asset_upload_url"]
        asset_upload_token = policy["asset_upload_authenticity_token"]

        console.print(f"  [green]OK[/green] asset {policy['asset']['id']}")

        # -- Step 2: upload to storage backend ------------------------
        console.print("[cyan]Step 2/3[/cyan] uploading file...")
        s3_files: list[tuple[str, tuple]] = [
            (k, (None, v)) for k, v in form_fields.items()
        ]
        s3_files.append(("file", (file_name, file_path.read_bytes(), content_type)))

        s3_resp = client.post(upload_url, files=s3_files)
        if s3_resp.status_code not in (200, 201, 204):
            console.print(f"[red]Upload failed ({s3_resp.status_code})[/red]")
            console.print(s3_resp.text[:500])
            sys.exit(1)
        console.print(f"  [green]OK[/green] uploaded ({s3_resp.status_code})")

        # -- Step 3: confirm ------------------------------------------
        console.print("[cyan]Step 3/3[/cyan] confirming...")
        confirm_resp = client.put(
            f"https://github.com{confirm_path}",
            files={"authenticity_token": (None, asset_upload_token)},
            headers=gh_headers,
        )
        if confirm_resp.status_code != 200:
            console.print(f"[red]Confirm failed ({confirm_resp.status_code})[/red]")
            try:
                console.print(confirm_resp.json())
            except Exception:
                console.print(confirm_resp.text[:500])
            sys.exit(1)

        final_url = confirm_resp.json()["href"]
        console.print(f"  [green]OK[/green] {final_url}")
        return final_url


def main():
    parser = argparse.ArgumentParser(
        prog="gh-attach",
        description="Upload files to GitHub issues and get markdown-ready URLs.",
    )
    parser.add_argument("file", type=Path, help="File to upload")
    parser.add_argument("--repo", required=True, help="owner/repo")
    parser.add_argument("--cookie", help="user_session cookie (or set GH_USER_SESSION)")
    parser.add_argument("--issue", type=int, help="Add as comment on this issue")
    parser.add_argument("--issue-body", type=int, help="Append to this issue's body")
    parser.add_argument("--alt", default="", help="Alt text / caption")
    parser.add_argument("--quiet", action="store_true", help="Only print the URL to stdout")

    args = parser.parse_args()

    if not args.file.exists():
        console.print(f"[red]Not found: {args.file}[/red]")
        sys.exit(1)

    session_cookie = args.cookie or os.environ.get("GH_USER_SESSION", "")
    if not session_cookie:
        get_session_cookie()  # prints instructions and exits

    parts = args.repo.split("/")
    if len(parts) != 2:
        console.print("[red]--repo must be owner/name[/red]")
        sys.exit(1)
    owner, repo = parts

    repo_id = get_repo_id(owner, repo)
    if not args.quiet:
        console.print(f"[dim]{owner}/{repo} (ID: {repo_id})[/dim]\n")

    url = upload(args.file, repo_id, session_cookie, owner, repo)

    # Print URL to stdout for piping
    print(url)

    # Determine markdown based on content type
    ct = mimetypes.guess_type(str(args.file))[0] or ""
    alt = args.alt or args.file.stem
    if ct.startswith("image/"):
        md = f"![{alt}]({url})"
    elif ct.startswith("video/"):
        md = f"<video src=\"{url}\" controls>{alt}</video>"
    else:
        md = f"[{alt}]({url})"

    if args.issue:
        if not args.quiet:
            console.print(f"\n[cyan]Commenting on #{args.issue}...[/cyan]")
        r = subprocess.run(
            ["gh", "issue", "comment", str(args.issue),
             "--repo", f"{owner}/{repo}", "--body", md],
            capture_output=True, text=True,
        )
        if r.returncode == 0:
            console.print(f"[green]OK[/green] comment added to #{args.issue}")
        else:
            console.print(f"[red]Failed: {r.stderr.strip()}[/red]")

    if args.issue_body:
        if not args.quiet:
            console.print(f"\n[cyan]Appending to #{args.issue_body} body...[/cyan]")
        r = subprocess.run(
            ["gh", "issue", "view", str(args.issue_body),
             "--repo", f"{owner}/{repo}", "--json", "body", "--jq", ".body"],
            capture_output=True, text=True,
        )
        if r.returncode != 0:
            console.print(f"[red]Failed to read issue: {r.stderr.strip()}[/red]")
            sys.exit(1)
        new_body = f"{r.stdout.rstrip()}\n\n{md}"
        r = subprocess.run(
            ["gh", "issue", "edit", str(args.issue_body),
             "--repo", f"{owner}/{repo}", "--body", new_body],
            capture_output=True, text=True,
        )
        if r.returncode == 0:
            console.print(f"[green]OK[/green] image appended to #{args.issue_body}")
        else:
            console.print(f"[red]Failed: {r.stderr.strip()}[/red]")


if __name__ == "__main__":
    main()
