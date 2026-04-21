# PRD: Library / View-Only Mode

**Date:** 2026-03-04
**Author:** Matt
**Status:** Draft

---

## Summary

Add a "view-only" mode to the web UI that disables all LLM-dependent features while keeping the full browsing, searching, tag filtering, notes editing, and download experience. Activated via a `--view-only` CLI flag or auto-detected when no LLM configuration is available. LLM-dependent UI elements are visible but disabled with explanatory tooltips.

## Motivation

- **What problem does this solve?** Not every deployment has LLM access (no API keys, no gateway, air-gapped environments). Currently the UI shows all LLM features and they silently fail when invoked. Users also want to share the slide library as a read/browse tool without exposing LLM controls.
- **Who benefits?** Users deploying the web UI as a slide library without LLM access, and teams sharing a catalog for browsing/searching.
- **What happens if we don't do this?** Users see buttons that don't work, get confusing error messages, and can't tell which features need LLM access.

## Requirements

### Must Have

- [ ] New `--view-only` CLI flag for the `serve` command
- [ ] Auto-detection: if no `--gateway-config` file exists and no `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` env vars are set, auto-enable view-only mode
- [ ] `--view-only` flag overrides auto-detection (forces view-only even if LLM config exists)
- [ ] New `GET /api/config` endpoint returning `{ "view_only": bool }` (and any other frontend-relevant config)
- [ ] Frontend fetches config on page load and conditionally disables LLM features
- [ ] LLM-dependent UI elements are visible but disabled with tooltip "LLM not configured"
- [ ] LLM API endpoints return 403 `{"error": "LLM features are disabled in view-only mode"}` when view-only is active
- [ ] Upload works in view-only mode but "Generate AI tags" checkbox is disabled
- [ ] All local features work normally: browse decks, view slides, search, tag filter, manual tagging, notes editing, download, CSV export, taxonomy management

### Features by Mode

| Feature | Full Mode | View-Only Mode |
|---------|-----------|----------------|
| Browse decks/slides | Yes | Yes |
| Search by title/tags | Yes | Yes |
| View slide detail | Yes | Yes |
| Edit speaker notes | Yes | Yes |
| Manual tag add/remove | Yes | Yes |
| Download deck | Yes | Yes |
| Export CSV | Yes | Yes |
| Taxonomy management | Yes | Yes |
| Upload deck | Yes | Yes (no AI tags) |
| Generate AI tags on upload | Yes | Disabled |
| Create deck from outline | Yes | Disabled |
| Enhanced mode (LLM) | Yes | Disabled |
| Analyze slide | Yes | Disabled |
| Suggest Notes (AI) | Yes | Disabled |
| Suggest Improvements (AI) | Yes | Disabled |
| Model settings | Yes | Disabled |

### Nice to Have

- [ ] Banner or badge in the nav bar indicating "Library Mode" or "View Only" when active
- [ ] `--no-view-only` flag to force full mode even when auto-detection would trigger view-only

### Out of Scope

- Role-based access control (multi-user permissions)
- Disabling upload entirely
- Per-feature granular enable/disable toggles

---

## Design

### Approach

Add a `view_only` boolean to `app.state` in the app factory. The CLI sets this based on the `--view-only` flag or auto-detection. A new `/api/config` endpoint exposes this to the frontend. The frontend checks `viewOnly` on page load and:

1. Disables LLM action buttons (Analyze, Suggest Notes, Suggest Improvements) with tooltip
2. Disables the Create Deck panel controls with tooltip
3. Disables the "Generate AI tags" checkbox on upload
4. Disables model settings controls
5. All other features work normally

For defense in depth, LLM-dependent API endpoints check `request.app.state.view_only` and return 403 early.

### Auto-Detection Logic

```python
def detect_view_only(gateway_config: str) -> bool:
    """Return True if no LLM access is available."""
    import os
    # Check if gateway config file actually exists
    if gateway_config and os.path.exists(gateway_config):
        return False
    # Check for direct API keys
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY"):
        return False
    return True
```

The `--view-only` flag forces `True` regardless of detection.

### New/Modified Modules

| Module | Change | Description |
|--------|--------|-------------|
| `outline2ppt/cli.py` | Modified | Add `--view-only` flag to `serve` subparser |
| `outline2ppt/web/app.py` | Modified | Add `view_only` param to `create_app()`, auto-detection logic, store in `app.state` |
| `outline2ppt/web/routes.py` | Modified | Add `GET /api/config` endpoint; add 403 guards to LLM endpoints |
| `outline2ppt/web/static/index.html` | Modified | Fetch config on load; conditionally disable LLM UI elements |

### Data Model Changes

No data model changes.

---

## CLI Changes

### Modified Commands

| Command | Change | Details |
|---------|--------|---------|
| `outline2ppt serve` | New flag `--view-only` | Disables LLM features in the web UI |

### Example Usage

```bash
# Explicit view-only mode
python outline2ppt.py serve --port 8000 --view-only

# Auto-detected view-only (no gateway.yaml, no API keys)
python outline2ppt.py serve --port 8000

# Full mode with gateway
python outline2ppt.py serve --port 8000 --gateway-config gateway.yaml
```

---

## UI Changes

### Modified Pages / Views

| Page | Change | Details |
|------|--------|---------|
| Deck list | Create Deck panel | All controls disabled with tooltip when view-only |
| Deck list | Upload controls | "Generate AI tags" checkbox disabled with tooltip |
| Slide detail modal | AI action buttons | Analyze, Suggest Notes, Suggest Improvements disabled with tooltip |
| Settings | Model defaults | Dropdowns and save buttons disabled with tooltip |
| Settings | Available Models table | Still shown (informational) |
| Nav bar | Mode indicator | Optional badge showing "Library Mode" |

### New API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/config` | Returns `{"view_only": true/false}` |

### Modified API Endpoints (403 guard)

| Method | Path | Guard |
|--------|------|-------|
| POST | `/api/slides/{id}/analyze` | Returns 403 if view-only |
| POST | `/api/slides/{id}/notes` | Returns 403 if view-only |
| POST | `/api/slides/{id}/improvements` | Returns 403 if view-only |
| POST | `/api/decks/create` | Returns 403 if view-only |

### Wireframe (View-Only indicator)

```
Outline2PPT  [Library Mode]     Decks  |  Search  |  Settings  |  Export CSV
```

---

## Testing

### Unit Tests

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `tests/test_web.py` | `TestViewOnlyMode` | Config endpoint, 403 guards, auto-detection |

### Test Cases

| Test | Description |
|------|-------------|
| `test_config_endpoint_full_mode` | `/api/config` returns `{"view_only": false}` when LLM configured |
| `test_config_endpoint_view_only` | `/api/config` returns `{"view_only": true}` when `--view-only` |
| `test_analyze_blocked_view_only` | `/api/slides/{id}/analyze` returns 403 in view-only |
| `test_notes_blocked_view_only` | `/api/slides/{id}/notes` returns 403 in view-only |
| `test_improvements_blocked_view_only` | `/api/slides/{id}/improvements` returns 403 in view-only |
| `test_create_blocked_view_only` | `/api/decks/create` returns 403 in view-only |
| `test_upload_works_view_only` | `/api/decks/upload` works in view-only (tags disabled) |
| `test_search_works_view_only` | `/api/search` works normally in view-only |
| `test_auto_detect_no_config` | Auto-detects view-only when no gateway.yaml and no env vars |
| `test_auto_detect_with_gateway` | Does not auto-detect when gateway.yaml exists |
| `test_flag_overrides_detection` | `--view-only` forces view-only even with gateway present |

### Manual Testing

1. Start server with `--view-only` -- confirm AI buttons are grayed out with tooltip
2. Click a disabled AI button -- confirm nothing happens (no request, no error)
3. Upload a deck -- confirm it works; "Generate AI tags" checkbox is disabled
4. Browse, search, edit notes, download -- confirm all work normally
5. Start server without gateway or API keys -- confirm auto-detection activates view-only
6. Start server with valid gateway.yaml -- confirm full mode active

---

## Changelog Entry

```markdown
### Added
- Library / view-only mode for the web UI (`--view-only` flag or auto-detected)
- New `/api/config` endpoint exposing frontend configuration
- LLM-dependent features are visibly disabled with tooltips when no LLM access is configured

### Changed
- LLM API endpoints return 403 in view-only mode instead of failing with cryptic errors
```

---

## Implementation Tasks

| # | Task | Files | Depends On |
|---|------|-------|------------|
| 1 | Add `--view-only` CLI flag | `outline2ppt/cli.py` | -- |
| 2 | Add `view_only` param + auto-detection to `create_app()` | `outline2ppt/web/app.py` | -- |
| 3 | Wire CLI flag to app factory | `outline2ppt/cli.py` | 1, 2 |
| 4 | Add `GET /api/config` endpoint | `outline2ppt/web/routes.py` | 2 |
| 5 | Add 403 guards to LLM endpoints | `outline2ppt/web/routes.py` | 2 |
| 6 | Frontend: fetch config, disable LLM UI elements | `outline2ppt/web/static/index.html` | 4 |
| 7 | Add unit/integration tests | `tests/test_web.py` | 4, 5 |
| 8 | Update changelog | `CHANGELOG.md` | all |

---

## Risks & Open Questions

- **Risk:** Auto-detection could produce false positives if gateway.yaml exists but is misconfigured -- **Mitigation:** Auto-detection only checks file existence, not validity. The `--view-only` flag provides an explicit override.
- **Risk:** New env vars for LLM providers (e.g., Google) won't be checked by auto-detection -- **Mitigation:** Start with the two primary keys (Anthropic, OpenAI). Add others as providers are supported. The `--view-only` flag is always available as a fallback.
- **Question:** Should the `POST /api/decks/upload` endpoint itself block `generate_tags=True` in view-only, or just trust the frontend? -- **Recommendation:** Both. Frontend disables the checkbox; backend ignores `generate_tags=True` in view-only mode (belt and suspenders).

---

## References

- App factory: `outline2ppt/web/app.py:13-31`
- CLI serve command: `outline2ppt/cli.py:1244-1248`
- CLI serve handler: `outline2ppt/cli.py:722-732`
- LLM endpoints: `outline2ppt/web/routes.py:376-408` (analyze), `411-443` (notes), `529-561` (improvements), `662-794` (create)
- Upload endpoint: `outline2ppt/web/routes.py:606-659`
- AI action buttons: `outline2ppt/web/static/index.html:554-558`
- Create deck panel: `outline2ppt/web/static/index.html:366-410`
- Settings view: `outline2ppt/web/static/index.html:473-534`
