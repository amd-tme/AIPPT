#!/tool/pandora64/bin/uv run
# /// script
# requires-python = ">=3.12"
# dependencies = ["pyyaml>=6.0"]
# ///
"""
Submit a slai-app-platform handoff bundle through the hosted GitHub App.

This script does not clone slai-app-platform, push branches, or create pull
requests with local GitHub credentials. It validates the local handoff bundle,
packages the accepted manifest files as JSON, and posts them to the hosted app.
The hosted app uses a GitHub App installation token to open the PR.
"""

from __future__ import annotations

import argparse
import http.server
import json
import os
import re
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path
from typing import Any

import yaml


DEFAULT_SUBMISSION_URL = "https://slai-app.amd.com/slai-app-submission"
SESSION_COOKIE_NAME = "slai_app_submission_session"
SESSION_CACHE_PATH = Path(os.getenv("SLAI_APP_PLATFORM_CREDENTIALS", "~/.config/slai-app-platform/credentials")).expanduser()
CLI_AUTH_TIMEOUT_SECONDS = 300
REQUIRED_FILES = {"deployment.yaml", "service.yaml", "z-ingress.yaml", "secrets.enc.yaml", "tls-secret.enc.yaml"}
OPTIONAL_FILES = {"networkpolicy.yaml"}
ALLOWED_FILES = REQUIRED_FILES | OPTIONAL_FILES
APP_ID_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")


def print_banner() -> None:
    print("=" * 72)
    print("SLAI APP PLATFORM GITHUB APP SUBMISSION")
    print("=" * 72)
    print("This script will:")
    print("  1. Validate deploy/slai-app-prod/<app_id>/")
    print("  2. Package the accepted handoff manifests as JSON")
    print("  3. Submit them to the hosted SLAI App Submission App")
    print("")
    print("No platform clone, SSH access, git push, or local PR creation is required.")
    print("=" * 72)
    print("")


def normalize_cookie(cookie: str) -> str:
    cookie = cookie.strip()
    if not cookie:
        return ""
    if SESSION_COOKIE_NAME in cookie:
        return cookie
    return f"{SESSION_COOKIE_NAME}={cookie}"


def load_cached_session(submission_url: str) -> str:
    try:
        data = json.loads(SESSION_CACHE_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return ""
    if data.get("submission_url") != submission_url.rstrip("/"):
        return ""
    expires_at = int(data.get("expires_at", 0) or 0)
    if expires_at and expires_at <= int(time.time()) + 60:
        return ""
    return str(data.get("session_token", ""))


def save_cached_session(submission_url: str, session_token: str, expires_in: int) -> None:
    SESSION_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "submission_url": submission_url.rstrip("/"),
        "session_cookie_name": SESSION_COOKIE_NAME,
        "session_token": session_token,
        "expires_at": int(time.time()) + int(expires_in or 0),
    }
    SESSION_CACHE_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    try:
        SESSION_CACHE_PATH.chmod(0o600)
    except OSError:
        pass


def get_current_user(submission_url: str, session_cookie: str) -> dict[str, Any] | None:
    if not session_cookie:
        return None
    request = urllib.request.Request(
        submission_url.rstrip("/") + "/api/me",
        method="GET",
        headers={"Accept": "application/json", "Cookie": normalize_cookie(session_cookie)},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code in {401, 403}:
            return None
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Session check failed with HTTP {exc.code}: {detail}") from exc


class _CliCallbackHandler(http.server.BaseHTTPRequestHandler):
    server: "_CliCallbackServer"

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        params = dict(urllib.parse.parse_qsl(parsed.query))
        if parsed.path != "/callback":
            self.send_error(404)
            return
        if params.get("error"):
            self.server.received_error = params.get("error_description") or params.get("error")
            body = f"Authentication failed: {self.server.received_error}".encode("utf-8")
            self.send_response(400)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.server.received_code = params.get("code")
        self.server.received_state = params.get("state")
        body = b"Authentication complete. You can close this browser tab and return to the terminal."
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


class _CliCallbackServer(http.server.HTTPServer):
    received_code: str | None = None
    received_state: str | None = None
    received_error: str | None = None


def perform_cli_login(submission_url: str, *, open_browser: bool) -> str:
    state = secrets.token_urlsafe(24)
    with _CliCallbackServer(("127.0.0.1", 0), _CliCallbackHandler) as server:
        host, port = server.server_address
        redirect_uri = f"http://{host}:{port}/callback"
        login_params = urllib.parse.urlencode({"redirect_uri": redirect_uri, "state": state})
        login_url = f"{submission_url.rstrip('/')}/auth/cli/login?{login_params}"
        if open_browser:
            print(f"[Auth] Opening browser for GitHub login: {login_url}")
            webbrowser.open(login_url)
        else:
            print(f"[Auth] Browser opening disabled. Visit: {login_url}")
        server.timeout = 1
        deadline = time.time() + CLI_AUTH_TIMEOUT_SECONDS
        while time.time() < deadline and not server.received_code and not server.received_error:
            server.handle_request()
    if server.received_error:
        raise RuntimeError(f"Browser authentication failed: {server.received_error}")
    if not server.received_code:
        raise RuntimeError("Timed out waiting for browser authentication callback.")
    if server.received_state != state:
        raise RuntimeError("CLI authentication state mismatch.")

    request = urllib.request.Request(
        submission_url.rstrip("/") + "/auth/cli/exchange",
        data=json.dumps({"code": server.received_code}).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"CLI session exchange failed with HTTP {exc.code}: {detail}") from exc
    session_token = str(payload.get("session_token", ""))
    if not session_token:
        raise RuntimeError("CLI session exchange did not return a session token.")
    user = payload.get("user") if isinstance(payload.get("user"), dict) else {}
    print(f"[Auth] Browser login succeeded for @{user.get('login', 'unknown')}")
    save_cached_session(submission_url, session_token, int(payload.get("expires_in", 0)))
    return session_token


def ensure_session_cookie(submission_url: str, current_cookie: str, *, open_browser: bool) -> str:
    try:
        user = get_current_user(submission_url, current_cookie)
    except RuntimeError as exc:
        print(f"[Auth] Existing session could not be checked: {exc}")
        user = None
    if user:
        print(f"[Auth] Existing hosted app session is valid for @{user.get('login', 'unknown')}")
        return current_cookie

    cached_cookie = load_cached_session(submission_url)
    user = get_current_user(submission_url, cached_cookie)
    if user:
        print(f"[Auth] Cached hosted app session is valid for @{user.get('login', 'unknown')}")
        return cached_cookie

    if current_cookie or cached_cookie:
        print("[Auth] Existing hosted app session is expired or unauthorized.")
    else:
        print("[Auth] No hosted app session is available.")
    cookie = perform_cli_login(submission_url, open_browser=open_browser)
    user = get_current_user(submission_url, cookie)
    if not user:
        raise RuntimeError("The browser login session could not be verified.")
    print(f"[Auth] New hosted app session is valid for @{user.get('login', 'unknown')}")
    return cookie


def resolve_app_id(handoff_dir: Path, explicit: str | None) -> str:
    app_id = explicit or handoff_dir.name
    if not APP_ID_RE.fullmatch(app_id):
        raise ValueError("app_id must be lowercase kebab-case and start with a letter")
    return app_id


def validate_handoff(handoff_dir: Path) -> None:
    script = Path(__file__).resolve().parent / "main.py"
    proc = subprocess.run([sys.executable, str(script), str(handoff_dir)], text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"platform handoff validator failed with exit code {proc.returncode}")


def package_handoff_files(handoff_dir: Path) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    names = {path.name for path in handoff_dir.iterdir() if path.is_file()}
    missing = REQUIRED_FILES - names
    if missing:
        raise ValueError(f"handoff is missing required file(s): {', '.join(sorted(missing))}")
    unexpected = names - ALLOWED_FILES
    if unexpected:
        raise ValueError(f"handoff has unexpected top-level file(s): {', '.join(sorted(unexpected))}")

    for name in sorted(ALLOWED_FILES):
        path = handoff_dir / name
        if not path.is_file():
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"{path} is not valid UTF-8 text") from exc
        files.append({"path": name, "content": content, "executable": bool(path.stat().st_mode & 0o111)})
    return files


def extract_image(files: list[dict[str, Any]]) -> str:
    deployment = next((item for item in files if item["path"] == "deployment.yaml"), None)
    if not deployment:
        return ""
    try:
        parsed = yaml.safe_load(str(deployment["content"])) or {}
        return str(parsed["spec"]["template"]["spec"]["containers"][0].get("image") or "")
    except Exception:
        return ""


def submit_payload(submission_url: str, session_cookie: str, payload: dict[str, Any]) -> dict[str, Any]:
    url = submission_url.rstrip("/") + "/api/submissions"
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Cookie": normalize_cookie(session_cookie),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Submission failed with HTTP {exc.code}: {detail}") from exc


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("handoff_dir", type=Path, help="Path to deploy/slai-app-prod/<app_id>")
    parser.add_argument("--app-id", help="Override app_id; defaults to handoff directory name")
    parser.add_argument("--submission-url", default=os.getenv("SLAI_APP_SUBMISSION_URL", DEFAULT_SUBMISSION_URL))
    parser.add_argument("--session-cookie", default=os.getenv("SLAI_APP_SUBMISSION_SESSION_COOKIE", ""))
    parser.add_argument("--title", default="")
    parser.add_argument("--description", default="")
    parser.add_argument("--dry-run", action="store_true", help="Validate and package only; do not authenticate or submit")
    parser.add_argument("--no-browser", action="store_true", help="Print login URL instead of opening a browser")
    parser.add_argument("--skip-validator", action="store_true", help="Skip local skills/slai-app-creator/scripts/main.py validation")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    print_banner()
    handoff_dir = args.handoff_dir.resolve()
    if not handoff_dir.is_dir():
        raise SystemExit(f"handoff directory not found: {handoff_dir}")
    app_id = resolve_app_id(handoff_dir, args.app_id)
    if not args.skip_validator:
        validate_handoff(handoff_dir)
    files = package_handoff_files(handoff_dir)
    image = extract_image(files)
    payload = {
        "app_id": app_id,
        "title": args.title or f"Add {app_id} app-platform manifests",
        "description": args.description or f"Submitted handoff for {app_id}. Image: {image or 'unknown'}",
        "files": files,
    }

    print(f"[Package] App: {app_id}")
    print(f"[Package] Files: {', '.join(item['path'] for item in files)}")
    if image:
        print(f"[Package] Image: {image}")
    print(f"[Submit] Endpoint: {args.submission_url.rstrip('/')}/api/submissions")

    if args.dry_run:
        print("[Dry run] Payload is valid locally; no submission was sent.")
        return 0

    session_cookie = ensure_session_cookie(
        args.submission_url,
        args.session_cookie,
        open_browser=not args.no_browser,
    )
    result = submit_payload(args.submission_url, session_cookie, payload)
    print("")
    print("===SUBMISSION_RESULT===")
    print(f"type: app-platform")
    print(f"status: {result.get('status')}")
    print(f"submission_id: {result.get('id')}")
    print(f"app_id: {result.get('app_id')}")
    print(f"branch: {result.get('branch')}")
    print(f"pr_number: {result.get('pr_number')}")
    print(f"pr_url: {result.get('pr_url')}")
    print("===END_SUBMISSION_RESULT===")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
