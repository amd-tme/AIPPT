#!/usr/bin/env python3.12
"""Skill-body load: detach, POST log + ranking event, always exit 0."""
import json
import os
import sys
import time
import uuid
import urllib.error
import urllib.request
from urllib.parse import urlparse

if sys.version_info < (3, 12):
    try:
        os.execvp("python3.12", ["python3.12", os.path.abspath(__file__), *sys.argv[1:]])
    except OSError:
        raise SystemExit(0)

_OTEL = "https://collector.slug.amd.com"
_REG = "https://slai-plugins.slai-app.amd.com"
_T = 2
_HDR = {"Content-Type": "application/json"}
_WORKER = "_SLAI_SKILL_HIT_WORKER"
_RES = (
    ("service.name", "app_slai_plugins"),
    ("organization.id", "SLAI"),
    ("finance.cost_center", "VBU_AI"),
    ("project.name", "slai-plugins"),
)


def _amd(url, default):
    candidate = (url or "").strip() or default
    parsed = urlparse(candidate)
    host = (parsed.hostname or "").lower()
    if (
        parsed.scheme == "https"
        and parsed.username is None
        and parsed.password is None
        and host
        and (host == "amd.com" or host.endswith(".amd.com"))
    ):
        return candidate
    return default


def _logs_url(base):
    trimmed = base.rstrip("/")
    for tail in ("/v1/traces", "/v1/metrics", "/v1/logs"):
        if trimmed.endswith(tail):
            trimmed = trimmed[: -len(tail)]
            break
    return trimmed + "/v1/logs"


def _post(url, payload):
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, separators=(",", ":")).encode(),
        method="POST",
        headers=_HDR,
    )
    try:
        urllib.request.urlopen(request, timeout=_T).read()
    except (urllib.error.URLError, TimeoutError, OSError):
        return


def _python():
    if sys.version_info >= (3, 12):
        return sys.executable
    return "python3.12"


def _foreground():
    """True: caller should return 0 now. False: this process does the POSTs."""
    if os.environ.get(_WORKER) == "1":
        return False
    try:
        if hasattr(os, "fork"):
            if os.fork() != 0:
                return True
            os.environ[_WORKER] = "1"
            try:
                os.setsid()
            except OSError:
                pass
            if not os.environ.get("SLAI_OTEL_DEBUG"):
                for fd in (0, 1, 2):
                    try:
                        os.close(fd)
                    except OSError:
                        pass
            return False
        import subprocess

        env = os.environ.copy()
        env[_WORKER] = "1"
        subprocess.Popen(
            [_python(), os.path.abspath(__file__)],
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
    except Exception:
        pass
    return True


def _emit():
    with open(os.path.join(os.path.dirname(__file__), "slai-skill-hit.json"), encoding="utf-8") as handle:
        data = json.load(handle)
    plugin = str(data["pluginName"]).strip()
    version = str(data["pluginVersion"]).strip()
    skill = str(data["skillName"]).strip()
    if not (plugin and version and skill):
        return
    now = str(time.time_ns())
    attrs = [{"key": key, "value": {"stringValue": value}} for key, value in _RES]
    _post(
        _logs_url(_amd(os.getenv("SLAI_OTEL_ENDPOINT", ""), _OTEL)),
        {
            "resourceLogs": [{
                "resource": {"attributes": attrs},
                "scopeLogs": [{
                    "scope": {"name": "app_slai_plugins.skill"},
                    "logRecords": [{
                        "timeUnixNano": now,
                        "severityNumber": 9,
                        "body": {
                            "stringValue": (
                                f"skill.hit plugin={plugin} version={version} skill={skill}"
                            )
                        },
                        "attributes": [
                            {"key": "event.name", "value": {"stringValue": "skill.hit"}}
                        ],
                    }],
                }],
            }]
        },
    )
    _post(
        _amd(os.getenv("SLAI_PLUGINS_ORIGIN", ""), _REG).rstrip("/") + "/api/v1/events",
        {
            "eventId": str(uuid.uuid4()),
            "eventType": "skill_hit",
            "pluginName": plugin,
            "version": version,
        },
    )


def main():
    forked = os.environ.get(_WORKER) != "1" and hasattr(os, "fork")
    if _foreground():
        return 0
    try:
        _emit()
    except Exception:
        pass
    if forked:
        os._exit(0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
