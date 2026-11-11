"""The runtime image must not inherit file modes from the build checkout.

COPY keeps each file's mode from the build context, so a checkout made under a
restrictive umask (e.g. 077) yields 0600 files that the Deployment's non-root user
(65534) cannot read: the container then fails at startup reading aippt.py. The
runtime stage therefore normalises every path it copies into /app with
`chmod -R a+rX` after the last such COPY.
"""
import shlex
from pathlib import Path

DOCKERFILE = Path(__file__).resolve().parent.parent / "Dockerfile"


def _instructions(text: str) -> list[tuple[str, list[str]]]:
    lines, buf = [], ""
    for raw in text.splitlines():
        line = raw.strip()
        if not buf and (not line or line.startswith("#")):
            continue
        if line.endswith("\\"):
            buf += line[:-1] + " "
            continue
        buf += line
        words = shlex.split(buf, comments=False)
        lines.append((words[0].upper(), words[1:]))
        buf = ""
    return lines


def _runtime_stage() -> list[tuple[str, list[str]]]:
    instructions = _instructions(DOCKERFILE.read_text())
    last_from = max(i for i, (op, _) in enumerate(instructions) if op == "FROM")
    return instructions[last_from + 1:]


def _app_paths(args: list[str]) -> list[str]:
    """Relative paths under WORKDIR /app that a COPY creates."""
    plain = [a for a in args if not a.startswith("--")]
    *sources, dest = plain
    if dest.startswith("/") and not dest.startswith("/app/"):
        return []
    dest = dest.removeprefix("/app/").rstrip("/") or "."
    if dest in (".", "./"):
        return [Path(s.rstrip("/")).name for s in sources]
    return [dest]


def test_runtime_copies_are_world_readable_after_copy():
    stage = _runtime_stage()
    copied: dict[str, int] = {}
    for index, (op, args) in enumerate(stage):
        if op == "COPY" and not any(a.startswith("--chmod") for a in args):
            for path in _app_paths(args):
                copied[path] = index

    normalised: dict[str, int] = {}
    for index, (op, args) in enumerate(stage):
        if op == "RUN" and args[:3] == ["chmod", "-R", "a+rX"]:
            for path in args[3:]:
                normalised[path.removeprefix("/app/").rstrip("/")] = index

    missing = sorted(p for p in copied if p not in normalised)
    assert not missing, f"COPY into /app without a later `chmod -R a+rX`: {missing}"
    early = sorted(p for p, at in copied.items() if normalised[p] < at)
    assert not early, f"`chmod -R a+rX` runs before these are copied: {early}"
