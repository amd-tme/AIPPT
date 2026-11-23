#!/usr/bin/env python3
"""Submit and merge a deployment bundle through the hosted GitHub App (stdlib only)."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import base64
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
import uuid

SERVICE = "https://slai-app-submission.slai-app.amd.com"
COOKIE = "slai_app_submission_session"
REQUIRED = {"deployment.yaml", "service.yaml", "z-ingress.yaml", "secrets.enc.yaml", "networkpolicy.yaml"}
ALLOWED = REQUIRED | {"service-cimd.yaml", "z-ingress-cimd.yaml", "auth-policy.json", "cli-auth-policy.yaml", "tls-secret.enc.yaml", "image-policy.yaml", "image-release.json", "image-release.bundle.jsonl"}
ALLOWED.add('tls-policy.json')
CREATOR_PROTOCOL = 'per-app-tls-v1'


class ClientError(Exception):
    pass


class TransportError(ClientError):
    """Request outcome may be unknown; retry mutations only with idempotency."""


class HttpError(ClientError):
    def __init__(self, status):
        self.status = status
        message = ('Update your slai-app-creator plugin and restart your agent client; the platform requires per-app TLS deployment.' if status == 426 else
                   "Hosted service denied the request (HTTP 403); a platform maintainer should verify App permissions and branch protection."
                   if status == 403 else f"Hosted service returned HTTP {status}; response details omitted to protect credentials.")
        super().__init__(message)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Client:
    def __init__(self):
        self.token = None
        self.opener = urllib.request.build_opener(NoRedirect())

    def request(self, method, path, payload=None, *, idempotency_key=None):
        if not path.startswith(("/api/", "/auth/")) or "?" in path or "#" in path or ".." in path:
            raise ClientError("Invalid service request path")
        headers = {"Accept": "application/json"}
        if idempotency_key is not None:
            if not re.fullmatch(r"[A-Za-z0-9._:-]{16,128}", idempotency_key):
                raise ClientError("Invalid idempotency key")
            headers["Idempotency-Key"] = idempotency_key
        if self.token:
            headers["Cookie"] = f"{COOKIE}={self.token}"
        data = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload).encode()
        req = urllib.request.Request(SERVICE + path, data=data, headers=headers, method=method)
        try:
            with self.opener.open(req, timeout=20) as response:
                raw = response.read(2 * 1024 * 1024 + 1)
                if len(raw) > 2 * 1024 * 1024:
                    raise ClientError("Hosted response exceeds supported size")
                result = json.loads(raw)
            if not isinstance(result, dict):
                raise ClientError("Unexpected hosted service response")
            return result
        except urllib.error.HTTPError as exc:
            raise HttpError(exc.code) from None
        except (TimeoutError,):
            raise TransportError("Hosted request timed out; a submitted operation may still be processing.") from None
        except urllib.error.URLError as exc:
            message = "Hosted request timed out; outcome may be unknown." if isinstance(exc.reason, TimeoutError) else "Hosted connection failed; outcome may be unknown."
            raise TransportError(message) from None
        except OSError:
            raise TransportError("Hosted connection failed; outcome may be unknown.") from None
        except ValueError:
            raise ClientError("Hosted response was not valid JSON; inspect submission state before retrying.") from None


def bundle(directory, app_id, title=None, description=None):
    root = Path(directory)
    if root.is_symlink() or not root.is_dir():
        raise ClientError("Bundle must be a regular directory")
    if not re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", app_id):
        raise ClientError("App ID must be lowercase kebab-case")
    if not all(hasattr(os, flag) for flag in ("O_NOFOLLOW", "O_DIRECTORY", "O_NONBLOCK")) or os.open not in os.supports_dir_fd:
        raise ClientError("Secure bundle reads require a supported POSIX host; use Linux, WSL, or macOS.")
    files = []
    total = 0
    directory_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        names = set()
        with os.scandir(directory_fd) as entries:
            for entry in entries:
                if len(names) >= 100:
                    raise ClientError("Bundle exceeds 100 entries")
                names.add(entry.name)
        if any(name not in ALLOWED and not re.fullmatch(r'[a-z0-9][a-z0-9-]*(?:\.enc)?\.ya?ml', name) for name in names):
            raise ClientError("Unsupported bundle file")
        if REQUIRED - names:
            raise ClientError("Missing required bundle manifests")
        for name in sorted(names):
            try:
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
            except FileNotFoundError:
                if name in REQUIRED:
                    raise ClientError(f"Missing required manifest: {name}") from None
                continue
            except OSError:
                raise ClientError(f"Cannot securely open manifest: {name}") from None
            with os.fdopen(fd, "rb") as source:
                info = os.fstat(source.fileno())
                if not stat.S_ISREG(info.st_mode):
                    raise ClientError(f"Manifest must be a regular file: {name}")
                if info.st_size > 1024 * 1024:
                    raise ClientError(f"Manifest is too large: {name}")
                raw = source.read(1024 * 1024 + 1)
                if len(raw) > 1024 * 1024:
                    raise ClientError(f"Manifest is too large: {name}")
            content = raw.decode("utf-8")
            total += len(raw)
            if total > 5 * 1024 * 1024:
                raise ClientError("Bundle exceeds 5 MiB")
            files.append({"path": name, "content": content, "executable": False})
    finally:
        os.close(directory_fd)
    if total > 5 * 1024 * 1024:
        raise ClientError("Bundle exceeds 5 MiB")
    evidence_spec = importlib.util.spec_from_file_location('image_release_evidence', Path(__file__).with_name('image_release_evidence.py'))
    evidence = importlib.util.module_from_spec(evidence_spec)
    evidence_spec.loader.exec_module(evidence)
    legacy = json.loads((Path(__file__).resolve().parents[1] / 'assets/tls-cutover.json').read_text())['legacy_apps']
    # Existing legacy apps can have reviewed image baselines without local
    # receipts. Defer that decision to hosted validation; never trust a caller
    # environment variable as image authorization. Partial evidence still fails.
    errors = evidence.evidence_errors([item['path'] for item in files], require_for_additional=app_id not in legacy)
    if errors:
        raise ClientError('Bundle rejected before upload: ' + ' '.join(errors))
    add_managed_tls_policy(files, app_id)
    try:
        checked = subprocess.run(
            [sys.executable, "-E", str(Path(__file__).with_name("secret_upload_validation.py"))],
            input=json.dumps({'app_id': app_id, 'files': files}).encode(), capture_output=True, timeout=10,
            env={key: value for key, value in os.environ.items() if not key.upper().startswith("PYTHON")})
        if checked.returncode or len(checked.stdout) > 1024 or json.loads(checked.stdout) != {"valid": True}:
            raise ClientError("Bundle rejected before upload: invalid YAML, Secret, TLS binding, or Keycloak SSO egress. Preserve tls-policy.json and the platform-managed exact-host TLS Secret; wildcard TLS is retired except for the LocalAI load-balancer apps. Reconcile the local bundle with the current platform manifest before resubmitting.")
    except (OSError, ValueError, subprocess.TimeoutExpired):
        raise ClientError("Bundle Secret validation failed before upload") from None
    return {"app_id": app_id, "title": title, "description": description, "files": files, 'creator_protocol': CREATOR_PROTOCOL}


def add_managed_tls_policy(files, app_id):
    legacy = json.loads((Path(__file__).resolve().parents[1] / 'assets/tls-cutover.json').read_text())['legacy_apps']
    if any(f['path'] == 'tls-policy.json' for f in files) or app_id in legacy:
        return
    ingress = next(f['content'] for f in files if f['path'] == 'z-ingress.yaml')
    try:
        result = subprocess.run([sys.executable, '-E', str(Path(__file__).with_name('manifest_yaml.py'))],
            input=ingress.encode(), capture_output=True, timeout=10,
            env={k: v for k, v in os.environ.items() if not k.upper().startswith('PYTHON')})
        parsed = json.loads(result.stdout) if len(result.stdout) <= 2 * 1024 * 1024 else {}
        if result.returncode or not parsed.get('ok'):
            raise ValueError('invalid ingress')
        doc = parsed['document']
        if doc.get('kind') != 'Ingress':
            raise ValueError('invalid ingress')
        policy = {'version': 1, 'mode': 'platform-managed', 'ingress': doc['metadata']['name']}
        from per_app_tls_inventory import target_from_policy
        target_from_policy(app_id, policy)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, subprocess.TimeoutExpired):
        raise ClientError('Cannot prepare platform-managed TLS enrollment; update z-ingress.yaml using the current slai-app-creator template.') from None
    files.append({'path': 'tls-policy.json', 'content': json.dumps(policy, indent=2) + '\n', 'executable': False})


def cache_path():
    return Path.home() / ".slai-app-submission" / "session.json"


def _open_session_cache_directory(path, create=False):
    """Keep traversal and later cache I/O pinned to verified POSIX directories."""
    if (not all(hasattr(os, flag) for flag in ('O_DIRECTORY', 'O_NOFOLLOW', 'O_NONBLOCK'))
            or any(function not in os.supports_dir_fd for function in (os.open, os.mkdir, os.stat, os.unlink, os.rename))
            or os.stat not in os.supports_follow_symlinks):
        raise ClientError('Secure session caching requires descriptor-relative POSIX filesystem support')
    path = Path(path)
    if path.name in ('', '.', '..') or '..' in path.parts:
        raise ClientError('Invalid session cache path')
    parent = Path(os.path.abspath(path.parent))
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    uid = os.geteuid()

    def verify(fd, final=False):
        info = os.fstat(fd)
        if not stat.S_ISDIR(info.st_mode):
            raise ClientError('Session cache ancestors must be real directories')
        if final:
            if info.st_uid != uid or stat.S_IMODE(info.st_mode) != 0o700:
                raise ClientError('Session cache directory must be owned by you with mode 0700')
        else:
            root_sticky = info.st_uid == 0 and bool(info.st_mode & stat.S_ISVTX)
            if info.st_uid not in (0, uid) or (info.st_mode & 0o022 and not root_sticky):
                raise ClientError('Session cache ancestors must have trusted ownership and write permissions')

    directory_fd = os.open(os.path.sep, flags)
    try:
        verify(directory_fd)
        for part in parent.parts[1:]:
            try:
                child = os.open(part, flags, dir_fd=directory_fd)
            except FileNotFoundError:
                if not create:
                    raise
                try:
                    os.mkdir(part, mode=0o700, dir_fd=directory_fd)
                except FileExistsError:
                    pass
                child = os.open(part, flags, dir_fd=directory_fd)
            os.close(directory_fd)
            directory_fd = child
            verify(directory_fd)
        verify(directory_fd, final=True)
        return directory_fd
    except BaseException:
        os.close(directory_fd)
        raise


def load_session(path, refresh=False):
    if os.name == "nt":
        return None
    path = Path(path)
    try:
        directory_fd = _open_session_cache_directory(path)
        try:
            fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
            with os.fdopen(fd, "rb") as source:
                info = os.fstat(source.fileno())
                if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_nlink != 1
                        or info.st_mode & 0o077 or info.st_size > 16384):
                    return None
                raw = source.read(16385)
                if len(raw) > 16384:
                    return None
                data = json.loads(raw)
        finally:
            os.close(directory_fd)
        if not isinstance(data, dict) or data.get("service") != SERVICE or data.get("refresh_expires_at" if refresh else "expires_at", 0) <= time.time() + 30:
            return None
        token = data.get("refresh_token" if refresh else "token", "")
        return token if re.fullmatch(r"[A-Za-z0-9_.-]+", token) else None
    except (OSError, ValueError, TypeError, ClientError):
        return None


def save_session(path, token, expires_in, refresh_token=None, refresh_expires_in=0):
    # POSIX mode bits do not secure Windows ACLs: use an in-memory session there.
    if os.name == "nt":
        return
    path = Path(path)
    directory_fd = _open_session_cache_directory(path, create=True)
    temporary = None
    fd = None
    try:
        try:
            existing = os.stat(path.name, dir_fd=directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            existing = None
        if existing is not None and (not stat.S_ISREG(existing.st_mode) or existing.st_uid != os.geteuid()
                                     or existing.st_nlink != 1 or existing.st_mode & 0o077):
            raise ClientError('Existing session cache must be a private, owned regular file with one link')
        for _ in range(16):
            candidate = 'session-' + secrets.token_hex(16) + '.tmp'
            try:
                fd = os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=directory_fd)
                temporary = candidate
                break
            except FileExistsError:
                pass
        if fd is None:
            raise ClientError('Cannot create a private session cache file')
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as stream:
            fd = None
            json.dump({"service": SERVICE, "token": token, "expires_at": time.time() + expires_in, "refresh_token": refresh_token, "refresh_expires_at": time.time() + refresh_expires_in}, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path.name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
    finally:
        try:
            if fd is not None:
                os.close(fd)
            if temporary is not None:
                try:
                    os.unlink(temporary, dir_fd=directory_fd)
                except FileNotFoundError:
                    pass
        finally:
            os.close(directory_fd)


def browser_login(client, timeout):
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    pairing = client.request("POST", "/auth/cli/pair", {"challenge": challenge})
    code = pairing.get("code", "")
    path = pairing.get("verification_path", "")
    expected = "/auth/cli/authorize?" + urllib.parse.urlencode({"code": code})
    if not isinstance(code, str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", code) or path != expected:
        raise ClientError("Hosted service returned an invalid pairing")
    url = SERVICE + path
    print("Open this hosted login URL in your browser (on any machine):\n" + url, flush=True)
    webbrowser.open(url)
    deadline = time.monotonic() + min(timeout, 300)
    while time.monotonic() < deadline:
        result = client.request("POST", "/auth/cli/poll", {"code": code, "verifier": verifier})
        if result.get("status") == "complete":
            break
        if result.get("status") != "pending":
            raise ClientError("Unexpected pairing status")
        time.sleep(2)
    else:
        raise ClientError("Hosted browser login timed out; restart login to obtain a new pairing.")
    token = result.get("session_token", "")
    if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", token):
        raise ClientError("Hosted service returned an invalid session")
    client.token = token
    save_session(cache_path(), token, min(int(result.get("expires_in", 0)), 8 * 3600), result.get("refresh_token"), min(int(result.get("refresh_expires_in", 0)), 180 * 86400))


def authenticate(client, no_browser, timeout):
    client.token = load_session(cache_path())
    if client.token:
        try:
            client.request("GET", "/api/me")
            return
        except HttpError as exc:
            if exc.status != 401:
                raise
            client.token = None
    refresh_token = load_session(cache_path(), refresh=True)
    if refresh_token:
        try:
            result = client.request('POST', '/auth/refresh', {'refresh_token': refresh_token})
            token = result.get('session_token', '')
            if not re.fullmatch(r'[A-Za-z0-9_.-]+', token):
                raise ClientError('Invalid renewed session')
            save_session(cache_path(), token, min(int(result.get('expires_in', 0)), 8 * 3600), result.get('refresh_token'), min(int(result.get('refresh_expires_in', 0)), 180 * 86400))
            client.token = token
            return
        except HttpError as exc:
            if exc.status != 401: raise
    if no_browser:
        raise ClientError("No valid hosted session; rerun without --no-browser for browser login. Git/gh credentials are not used.")
    browser_login(client, timeout)


def safe_reason(value, client):
    """Display bounded server guidance without terminal controls or session material."""
    text = str(value)
    token = getattr(client, "token", None)
    if token:
        text = text.replace(token, "[REDACTED]")
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
    text = re.sub(r"(?i)(bearer\s+)[\w.\-+/=]+", r"\1[REDACTED]", text)
    text = re.sub(r"(?i)((?:password|token|secret|api[_-]?key)\s*[:=]\s*)\S+", r"\1[REDACTED]", text)
    return " ".join("".join(c if c.isprintable() else " " for c in text).split())[:500]


def wait_for_merge(client, submission_id, timeout, interval):
    path = "/api/submissions/" + submission_id
    deadline = time.monotonic() + timeout
    last_reason = None
    while True:
        record = client.request("GET", path)
        status = record.get("status")
        if status == "merged":
            return
        if status == "errored":
            state = client.request("GET", path + "/status")
            processing = state.get("processing", {})
            if not isinstance(processing, dict) or processing.get("retryable") is not True:
                raise ClientError(f"Submission stopped with status {status}; inspect status before retrying.")
        elif status in {"validation_failed", "changes_requested", "closed", "failed"}:
            raise ClientError(f"Submission stopped with status {status}; inspect the submission or PR before retrying.")
        if status == "pr_opened":
            gate = client.request("GET", path + "/merge")
            reason = safe_reason(gate.get("reason", ""), client)
            if reason and reason != last_reason:
                print("Merge: " + reason, flush=True)
                last_reason = reason
            if gate.get("merged"):
                return
            if gate.get("mergeable"):
                sha = gate.get("head_sha", "")
                if not isinstance(sha, str) or not re.fullmatch(r"[a-fA-F0-9]{40}", sha):
                    raise ClientError("Hosted merge readiness response omitted a valid head SHA")
                try:
                    result = client.request("POST", path + "/merge", {"head_sha": sha})
                    if result.get("merged"):
                        return
                except HttpError as exc:
                    if exc.status != 409:
                        raise
        if time.monotonic() >= deadline:
            raise ClientError(f"Merge gates are still pending. Resume with --submission-id {submission_id}.")
        time.sleep(min(interval, max(0, deadline - time.monotonic())))


def show_logs(client, submission_id):
    result = client.request("GET", "/api/submissions/" + submission_id + "/logs")
    # Terminal controls and unbounded workflow output must not reach the console.
    def clean(value, limit):
        text = "".join(c for c in str(value) if c in "\n\t" or c.isprintable())
        if client.token:
            text = text.replace(client.token, "[REDACTED]")
        text = re.sub(r"(?i)(\bbearer[ \t]+)[^\s]+", r"\1[REDACTED]", text)
        text = re.sub(
            r"(?im)(\b[A-Z0-9_]*(?:TOKEN|PASSWORD|SECRET|API_KEY|PRIVATE_KEY)[A-Z0-9_]*[ \t]*[:=][ \t]*)(?:\"[^\"\r\n]*\"|'[^'\r\n]*'|[^\s]+)",
            r"\1[REDACTED]", text)
        return text[:limit]
    print("Deployment status: " + clean(result.get("status", "unknown"), 80))
    if result.get("conclusion"):
        print("Conclusion: " + clean(result["conclusion"], 80))
    states = {'queued', 'pending', 'in_progress', 'completed', 'success', 'failure', 'cancelled', 'skipped', 'unknown'}
    for index, job in enumerate(result.get("jobs", [])[:50], start=1):
        state = job.get("status", "unknown")
        conclusion = job.get("conclusion", "unknown")
        print(f"Job {index}: {state if state in states else 'unknown'}; conclusion: {conclusion if conclusion in states else 'unknown'}")
    print("Raw workflow logs omitted; inspect the workflow in GitHub for detailed diagnostics.")


def submit_once(client, payload, key):
    """One bounded retry, with identical body and owner-scoped idempotency key."""
    for attempt in range(2):
        try:
            return client.request("POST", "/api/submissions", payload, idempotency_key=key)
        except TransportError:
            if attempt:
                raise
        except HttpError as exc:
            if exc.status not in {502, 503, 504} or attempt:
                raise
        print("Submission outcome uncertain; retrying once with the same idempotency key.", file=sys.stderr)


def show_status(client, submission_id, as_json=False):
    result = client.request("GET", "/api/submissions/" + submission_id + "/status")
    if result.get("schema_version") != 1:
        raise ClientError("Unsupported hosted status schema")
    # Only bounded public status fields are printed; raw diagnostics never are.
    allowed_states = {"received", "queued", "processing", "validating", "pr_opened", "merged",
                      "validation_failed", "changes_requested", "closed", "errored", "failed",
                      "pending", "running", "in_progress", "completed", "success", "failure",
                      "cancelled", "skipped", "unknown", "ready", "blocked", "not_started",
                      "validation", "github", "done", "retry", "leased", "waiting", "open", "closed", "working", "recovery_required", "requires_recovery", "finished", "reconciliation"}
    summary = {"schema_version": 1, "submission_id": submission_id}
    for stage in ("submission", "processing", "pr", "checks", "merge", "rollout"):
        value = result.get(stage, {})
        fields = {}
        if isinstance(value, dict):
            for name in ("status", "phase", "conclusion", "state"):
                if name in value:
                    fields[name] = value[name] if isinstance(value[name], str) and value[name] in allowed_states else "unknown"
            for name in ("attempt", "number", "run_id"):
                if type(value.get(name)) is int and 0 <= value[name] < 10**18:
                    fields[name] = value[name]
            for name in ("retryable", "mergeable", "merged"):
                if type(value.get(name)) is bool:
                    fields[name] = value[name]
        if stage == "processing" and isinstance(value, dict):
            codes = {"validation_rejected", "upstream_timeout", "upstream_unavailable", "authorization_rejected", "recovery_required", "attempt_limit"}
            code = value.get("error_code")
            if code is not None:
                fields["error_code"] = code if isinstance(code, str) and code in codes else "unknown"
        if stage == "checks" and isinstance(value, list):
            fields = {"total": min(len(value), 100)}
            for state in ("queued", "pending", "in_progress", "completed", "success", "failure"):
                fields[state] = sum(1 for item in value[:100] if isinstance(item, dict) and (item.get("status") == state or item.get("conclusion") == state))
        if stage == "rollout" and isinstance(value, dict):
            jobs = value.get("jobs", [])
            if isinstance(jobs, list):
                fields["jobs"] = [{name: item.get(name) if isinstance(item.get(name), str) and item.get(name) in allowed_states else "unknown" for name in ("status", "conclusion")} for item in jobs[:50] if isinstance(item, dict)]
        summary[stage] = fields
    if as_json:
        print(json.dumps(summary, indent=2))
    else:
        print("Submission: " + submission_id)
        for stage, fields in summary.items():
            if isinstance(fields, dict):
                print(stage.capitalize() + ": " + (", ".join(f"{k}={v}" for k, v in fields.items()) or "unknown"))
        if summary["processing"].get("retryable") is False and summary["submission"].get("status") == "errored":
            print("Next: ask the platform agent to inspect this exact submission; preserve its ID and do not repost or bypass the hosted flow.")
            return summary
        print("Next: " + ("check --status or --logs for rollout; merge is complete." if summary["submission"].get("status") == "merged" else "resume with --submission-id to continue merge; use --logs for deployment details."))
    return summary


def prepare_replacement(client, submission_id, payload):
    """Explicitly replace only a failed validation record that created no PR."""
    record = client.request('GET', '/api/submissions/' + submission_id)
    if record.get('status') != 'validation_failed' or record.get('pr_number') or record.get('pr_url') or record.get('branch'):
        raise ClientError('Replacement requires a validation_failed submission with no branch or PR')
    if record.get('app_id') != payload['app_id']:
        raise ClientError('Replacement must target the same application')
    payload['description'] = (payload.get('description') or '') + '\n\nExplicit replacement for validation-only submission ' + submission_id + '; no PR existed.'
    return payload


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, epilog="Examples: submit_app.py ./handoff/my-app --dry-run; submit_app.py ./handoff/my-app; submit_app.py --submission-id <id>")
    parser.add_argument("bundle", nargs="?", help="Directory containing the app deployment manifests")
    parser.add_argument("--app-id", help="Defaults to the bundle directory name")
    parser.add_argument("--title")
    parser.add_argument("--description")
    parser.add_argument("--replace-failed-submission", help="Explicit replacement for owned validation_failed record with no PR")
    parser.add_argument("--submission-id", help="Resume an existing submission and request merge when its gates pass")
    parser.add_argument("--status", action="store_true", help="Read unified submission and rollout status without mutation")
    parser.add_argument("--json", action="store_true", help="Machine-readable output for --status")
    parser.add_argument("--idempotency-key", help="Reuse this key and identical bundle after an uncertain submission outcome")
    parser.add_argument("--logs", action="store_true", help="Read deployment logs for --submission-id without creating or merging")
    parser.add_argument("--dry-run", action="store_true", help="Inspect selected filenames locally; no authentication or network")
    parser.add_argument("--no-browser", action="store_true", help="Require a valid cached hosted session")
    parser.add_argument("--timeout", type=int, default=600, help="Maximum merge polling seconds (0-3600)")
    parser.add_argument("--login-timeout", type=int, default=300, help="Maximum browser login seconds (1-300)")
    parser.add_argument("--poll-interval", type=int, default=5, help="Seconds between checks (1-60)")
    args = parser.parse_args(argv)
    if args.status and (not args.submission_id or args.logs):
        parser.error("--status requires --submission-id and cannot combine with --logs")
    if args.json and not args.status:
        parser.error("--json requires --status")
    if args.idempotency_key and (not args.bundle or not re.fullmatch(r"[A-Za-z0-9._:-]{16,128}", args.idempotency_key)):
        parser.error("--idempotency-key requires a bundle and 16-128 supported ASCII characters")
    if args.logs and not args.submission_id:
        parser.error("--logs requires --submission-id")
    if bool(args.bundle) == bool(args.submission_id):
        parser.error("provide a bundle directory or --submission-id")
    if not 0 <= args.timeout <= 3600 or not 1 <= args.login_timeout <= 300 or not 1 <= args.poll_interval <= 60:
        parser.error("timeouts or polling interval outside supported range")
    if args.submission_id and not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", args.submission_id):
        parser.error("invalid submission ID")
    if args.replace_failed_submission and (not args.bundle or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', args.replace_failed_submission)):
        parser.error('replacement requires bundle and valid failed ID')
    submission_id = args.submission_id
    key = args.idempotency_key or (str(uuid.uuid4()) if args.bundle else None)
    try:
        payload = bundle(args.bundle, args.app_id or Path(args.bundle).name, args.title, args.description) if args.bundle else None
        if args.dry_run:
            print(json.dumps({"service": SERVICE, "app_id": payload["app_id"] if payload else None,
                              "files": [f["path"] for f in payload["files"]] if payload else [],
                              "submission_id": submission_id, "action": "status" if args.status else "logs" if args.logs else ("submit and merge" if payload else "resume and merge")}, indent=2))
            return 0
        client = Client()
        authenticate(client, args.no_browser, args.login_timeout)
        if args.status:
            show_status(client, submission_id, args.json)
            return 0
        if args.logs:
            show_logs(client, submission_id)
            return 0
        if payload:
            if args.replace_failed_submission:
                payload = prepare_replacement(client, args.replace_failed_submission, payload)
            print("Idempotency key: " + key, flush=True)
            record = submit_once(client, payload, key)
            submission_id = record.get("id", "")
            if not isinstance(submission_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", submission_id):
                raise ClientError("Hosted service returned an invalid submission ID")
            print("Submission: " + submission_id, flush=True)
        wait_for_merge(client, submission_id, args.timeout, args.poll_interval)
        print(f"Submission {submission_id} merged. Deployment runs separately in the platform workflow.")
        print(f"Deployment logs: submit_app.py --submission-id {submission_id} --logs")
        return 0
    except (ClientError, OSError, UnicodeError, ValueError) as exc:
        message = str(exc) if isinstance(exc, ClientError) else "Local file or session processing failed."
        print("Error: " + message, file=sys.stderr)
        if key and not submission_id:
            print("Retry the identical bundle with --idempotency-key " + key + "; do not generate another key for an uncertain outcome.", file=sys.stderr)
        if submission_id:
            print("Resume: submit_app.py --submission-id " + submission_id, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
