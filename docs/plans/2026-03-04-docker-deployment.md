# PRD: Docker Deployment

**Date:** 2026-03-04
**Author:** Matt
**Status:** Draft

---

## Summary

Create a `Dockerfile` and `docker-compose.yml` for containerized deployment of AIPPT. Supports two profiles: a default view-only mode for shared team browsing, and a full mode with LLM gateway access. View-only mode is configurable via the `AIPPT_VIEW_ONLY` environment variable in addition to the existing `--view-only` CLI flag. Volumes are mapped from `dirs.yaml` conventions for persistent data.

## Motivation

- **What problem does this solve?** Deploying the web UI on a shared team server currently requires cloning the repo, setting up a venv, and managing the process manually. A Docker container makes deployment a single `docker compose up`.
- **Who benefits?** Teams that want a shared slide library server, especially in view-only mode for browsing analyzed content.
- **What happens if we don't do this?** Each deployment requires manual Python environment setup, which creates friction for team sharing.

## Requirements

### Must Have

- [ ] `Dockerfile` using `python:3.11-slim` base image
- [ ] Install dependencies from `requirements.txt` (no venv needed in container)
- [ ] Build Sphinx docs during image build (if docs PRD is implemented)
- [ ] Expose port 8000
- [ ] `AIPPT_VIEW_ONLY` environment variable support (truthy = view-only mode)
- [ ] CLI `--view-only` flag continues to work (env var is additive)
- [ ] `docker-compose.yml` with two profiles:
  - Default profile: view-only, maps data volumes
  - `full` profile: adds `gateway.yaml` mount and API key env vars
- [ ] Volume mounts for persistent data: `uploads/`, `images/`, `slides.db`, `models.yaml`
- [ ] `.dockerignore` excluding venv, .git, backups, __pycache__, etc.
- [ ] Container runs as non-root user

### Nice to Have

- [ ] Health check endpoint (`/api/config` works as a lightweight health check)
- [ ] `AIPPT_PORT` env var to override the default port
- [ ] `AIPPT_DB_PATH` env var to override the database path

### Out of Scope

- Multi-container orchestration (separate DB, reverse proxy)
- Kubernetes manifests
- CI/CD pipeline for building/pushing images
- TLS/HTTPS (use a reverse proxy for that)

---

## Design

### Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY aippt/ aippt/
COPY aippt.py .
COPY pyproject.toml .
COPY dirs.yaml .

# Build Sphinx docs (if docs/ exists)
COPY docs/ docs/
RUN if [ -f docs/Makefile ]; then \
      pip install --no-cache-dir sphinx sphinx-rtd-theme && \
      make -C docs html; \
    fi

# Create non-root user and data directories
RUN useradd -m appuser && \
    mkdir -p uploads images backups && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

ENTRYPOINT ["python", "aippt.py", "serve", "--port", "8000"]
```

### docker-compose.yml

```yaml
services:
  aippt:
    build: .
    ports:
      - "${AIPPT_PORT:-8000}:8000"
    volumes:
      - ./uploads:/app/uploads
      - ./images:/app/images
      - ./slides.db:/app/slides.db
      - ./models.yaml:/app/models.yaml:ro
    environment:
      - AIPPT_VIEW_ONLY=1
    profiles: ["", "default"]

  aippt-full:
    build: .
    ports:
      - "${AIPPT_PORT:-8000}:8000"
    volumes:
      - ./uploads:/app/uploads
      - ./images:/app/images
      - ./slides.db:/app/slides.db
      - ./models.yaml:/app/models.yaml:ro
      - ./gateway.yaml:/app/gateway.yaml:ro
    environment:
      - AIPPT_VIEW_ONLY=0
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY:-}
      - OPENAI_API_KEY=${OPENAI_API_KEY:-}
      - AMD_LLM_KEY=${AMD_LLM_KEY:-}
    profiles: ["full"]
```

### Environment Variable Support

Add `AIPPT_VIEW_ONLY` env var check to the view-only detection logic in `app.py`:

```python
def detect_view_only(gateway_config: str) -> bool:
    # Check env var first (explicit override)
    env_val = os.environ.get("AIPPT_VIEW_ONLY", "").lower()
    if env_val in ("1", "true", "yes"):
        return True
    if env_val in ("0", "false", "no"):
        return False
    # Existing auto-detection logic...
```

Priority: `--view-only` flag > `AIPPT_VIEW_ONLY` env var > auto-detection.

### Volume Mapping (from dirs.yaml)

| dirs.yaml key | Container path | Volume mount | Notes |
|---------------|----------------|--------------|-------|
| `uploads` | `/app/uploads/` | Read-write | Uploaded .pptx files |
| `images` | `/app/images/` | Read-write | Slide PNG exports |
| `db` | `/app/slides.db` | Read-write | SQLite database |
| (config) | `/app/models.yaml` | Read-only | Model configuration |
| (config) | `/app/gateway.yaml` | Read-only (full only) | LLM gateway config |

### New/Modified Modules

| Module | Change | Description |
|--------|--------|-------------|
| `Dockerfile` | New | Container build definition |
| `docker-compose.yml` | New | Service definitions with profiles |
| `.dockerignore` | New | Exclude venv, .git, backups, etc. |
| `aippt/web/app.py` | Modified | Add `AIPPT_VIEW_ONLY` env var to detection |
| `aippt/cli.py` | Modified | Document env var in serve help text |

### Data Model Changes

No data model changes.

---

## CLI Changes

### Modified Commands

| Command | Change | Details |
|---------|--------|---------|
| `aippt serve` | New env var | `AIPPT_VIEW_ONLY` env var support for view-only mode |

### Example Usage

```bash
# Build the image
docker compose build

# Run in view-only mode (default)
docker compose up -d

# Run in full mode with LLM access
docker compose --profile full up -d

# Run directly with docker
docker run -p 8000:8000 \
  -v ./slides.db:/app/slides.db \
  -v ./images:/app/images \
  -v ./uploads:/app/uploads \
  -e AIPPT_VIEW_ONLY=1 \
  aippt

# Override port
AIPPT_PORT=9000 docker compose up -d
```

---

## UI Changes

No UI changes.

---

## Testing

### Unit Tests

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `tests/test_view_only.py` | `test_env_var_view_only` | `AIPPT_VIEW_ONLY=1` forces view-only |
| `tests/test_view_only.py` | `test_env_var_overrides_detection` | Env var takes effect when set |
| `tests/test_view_only.py` | `test_flag_overrides_env_var` | `--view-only` flag takes precedence |

### Manual Testing

1. `docker compose build` -- image builds successfully
2. `docker compose up` -- container starts, web UI accessible at localhost:8000
3. Verify view-only mode active (Library Mode badge, AI buttons disabled)
4. Upload a deck via the import workflow (pre-populate slides.db and images/ on host)
5. `docker compose --profile full up` -- verify full mode with gateway
6. Stop and restart -- verify data persists via volumes

---

## Changelog Entry

```markdown
### Added
- `Dockerfile` for containerized deployment
- `docker-compose.yml` with view-only (default) and full profiles
- `.dockerignore` for efficient image builds
- `AIPPT_VIEW_ONLY` environment variable for container-friendly view-only configuration
```

---

## Implementation Tasks

| # | Task | Files | Depends On |
|---|------|-------|------------|
| 1 | Create `.dockerignore` | `.dockerignore` | -- |
| 2 | Create `Dockerfile` | `Dockerfile` | -- |
| 3 | Add `AIPPT_VIEW_ONLY` env var support | `aippt/web/app.py` | -- |
| 4 | Add env var tests | `tests/test_view_only.py` | 3 |
| 5 | Create `docker-compose.yml` with profiles | `docker-compose.yml` | 2 |
| 6 | Update serve help text to document env var | `aippt/cli.py` | 3 |
| 7 | Test docker build and run | -- | 2, 5 |
| 8 | Update CLAUDE.md with Docker usage | `CLAUDE.md` | 5 |
| 9 | Update CHANGELOG.md | `CHANGELOG.md` | all |

---

## Risks & Open Questions

- **Risk:** SQLite doesn't handle concurrent writes well — multiple containers sharing one DB could cause locks — **Mitigation:** View-only mode is read-heavy. Single container is the expected deployment. Document the limitation.
- **Risk:** Large images/ directories make the Docker build context slow — **Mitigation:** `.dockerignore` excludes `images/`, `uploads/`, and `slides.db`. They're mounted as volumes, not baked into the image.
- **Question:** Should the Dockerfile include LibreOffice for `export-images` support? — **Recommendation:** No. Image export requires PowerPoint (Windows only) or LibreOffice, which bloats the image significantly. Import pre-exported images via volumes instead.
- **Question:** Should we publish to Docker Hub or GitHub Container Registry? — **Recommendation:** Out of scope for now. Local `docker compose build` is sufficient.

---

## References

- View-only mode: `docs/plans/2026-03-04-library-view-only-mode.md`
- dirs.yaml: `dirs.yaml` (volume mapping source)
- App factory: `aippt/web/app.py` (detect_view_only function)
- CLI serve: `aippt/cli.py` (cmd_serve)
