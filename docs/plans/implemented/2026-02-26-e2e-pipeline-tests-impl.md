# E2E Pipeline Tests Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add end-to-end tests that exercise the full Outline2PPT pipeline — from markdown outline to AI-analyzed slide deck — using real LLM API calls and PowerShell image export.

**Architecture:** A single pytest module (`tests/test_e2e_pipeline.py`) with `@pytest.mark.e2e` marker. Tests use real `models.yaml` and `gateway.yaml` from the project root, make actual API calls via the AMD gateway, and call `pwsh.exe` from WSL for image export. Three test outlines live in `tests/e2e_outlines/`. A bug fix in `cmd_export_images` enables cross-platform PowerShell detection.

**Tech Stack:** Python 3.10+, pytest, python-pptx, PowerShell 7 (via WSL), AMD LLM Gateway

---

## Progress Tracker

| Task | Status | Notes |
|------|--------|-------|
| 1. Fix PowerShell detection in `cmd_export_images` | | |
| 2. Create test outline files | | |
| 3. Add pytest `e2e` marker | | |
| 4. Write E2E test fixtures and skip logic | | |
| 5. Write pipeline tests: create + export-images + catalog | | |
| 6. Write pipeline tests: analyze (all 4 modes) | | |
| 7. Write capability analysis logic | | |
| 8. Run full E2E suite and verify | | |

---

### Task 1: Fix PowerShell detection in `cmd_export_images`

**Files:**
- Modify: `outline2ppt/cli.py:575-607`
- Test: `tests/test_cli.py` (add test for PowerShell detection)

**Step 1: Write the failing test**

Add to the bottom of `tests/test_cli.py`:

```python
class TestExportImagesCommand:
    def test_find_powershell_prefers_pwsh_exe(self, monkeypatch):
        """Test that _find_powershell() finds pwsh.exe first."""
        from outline2ppt.cli import _find_powershell
        import shutil

        # Mock shutil.which to return pwsh.exe
        def mock_which(cmd):
            if cmd == "pwsh.exe":
                return "/mnt/c/Program Files/PowerShell/7/pwsh.exe"
            return None

        monkeypatch.setattr(shutil, "which", mock_which)
        result = _find_powershell()
        assert result == "/mnt/c/Program Files/PowerShell/7/pwsh.exe"

    def test_find_powershell_falls_back_to_powershell(self, monkeypatch):
        """Test fallback to 'powershell' when pwsh.exe not available."""
        from outline2ppt.cli import _find_powershell
        import shutil

        def mock_which(cmd):
            if cmd == "powershell":
                return "/usr/bin/powershell"
            return None

        monkeypatch.setattr(shutil, "which", mock_which)
        result = _find_powershell()
        assert result == "/usr/bin/powershell"

    def test_find_powershell_returns_none_when_unavailable(self, monkeypatch):
        """Test that None is returned when no PowerShell is found."""
        from outline2ppt.cli import _find_powershell
        import shutil

        monkeypatch.setattr(shutil, "which", lambda cmd: None)
        result = _find_powershell()
        assert result is None
```

**Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/test_cli.py::TestExportImagesCommand -v`
Expected: FAIL — `_find_powershell` not defined

**Step 3: Write the implementation**

At the top of `cmd_export_images` in `outline2ppt/cli.py`, add the helper function. Place it just above `cmd_export_images` (around line 574):

```python
def _find_powershell():
    """Find available PowerShell executable, preferring pwsh.exe (PowerShell 7).

    Search order: pwsh.exe, pwsh, powershell.exe, powershell
    Returns the full path or None if not found.
    """
    import shutil
    for ps_cmd in ("pwsh.exe", "pwsh", "powershell.exe", "powershell"):
        path = shutil.which(ps_cmd)
        if path:
            return path
    return None
```

Then modify `cmd_export_images` to use it. Replace the hardcoded `"powershell"` in the `cmd` list (line 598):

```python
def cmd_export_images(args):
    """Export slides to PNG images using PowerPoint COM automation."""
    import subprocess

    if not os.path.exists(args.deck):
        logger.error(f"File not found: {args.deck}")
        return 1

    # Find PowerShell executable
    ps_exe = _find_powershell()
    if not ps_exe:
        logger.error("PowerShell not found. Install PowerShell 7 (pwsh) or run from Windows.")
        return 1

    # Locate the PowerShell script relative to this file
    script_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
    ps_script = os.path.join(script_dir, "Export-SlidesToImages.ps1")

    if not os.path.exists(ps_script):
        logger.error(f"PowerShell script not found: {ps_script}")
        logger.info("Expected at: scripts/Export-SlidesToImages.ps1")
        return 1

    out_dir = args.out_dir
    if not out_dir:
        deck_name = os.path.splitext(os.path.basename(args.deck))[0]
        out_dir = os.path.join("images", deck_name)

    cmd = [
        ps_exe, "-ExecutionPolicy", "Bypass", "-File", ps_script,
        "-PptxPath", os.path.abspath(args.deck),
        "-OutDir", os.path.abspath(out_dir),
        "-Width", str(args.width),
        "-Height", str(args.height),
    ]

    logger.info(f"Exporting slides from {args.deck} to {out_dir}")
    result = subprocess.run(cmd, capture_output=False)
    return result.returncode
```

**Step 4: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/test_cli.py::TestExportImagesCommand -v`
Expected: All 3 tests PASS

Run: `venv/bin/python -m pytest tests/ -v --tb=short`
Expected: All existing tests still pass (no regressions)

**Step 5: Commit**

```bash
git add outline2ppt/cli.py tests/test_cli.py
git commit -m "fix: detect pwsh.exe/powershell cross-platform in export-images"
```

---

### Task 2: Create test outline files

**Files:**
- Create: `tests/e2e_outlines/tech_overview.md`
- Create: `tests/e2e_outlines/mini_presentation.md`
- Create: `tests/e2e_outlines/generic_info.md`

**Step 1: Create the directory**

Run: `mkdir -p tests/e2e_outlines`

**Step 2: Create `tech_overview.md`** (3 slides)

```markdown
# Cloud-Native Architecture Overview
- Microservices architecture pattern
- Container orchestration with Kubernetes
- Service mesh for inter-service communication
- API gateway for external traffic management

# Security Considerations
- Zero trust network architecture
- mTLS between all services
- Secret management with HashiCorp Vault
- Role-based access control (RBAC) for cluster resources
- Regular vulnerability scanning of container images

# Performance and Scalability
- Horizontal pod autoscaling based on CPU and memory
- Database connection pooling strategies
- CDN integration for static assets
- Caching layers: Redis for session data, Varnish for HTTP
```

**Step 3: Create `mini_presentation.md`** (5 slides)

```markdown
# Cloud Migration Strategy
- Enterprise cloud migration roadmap
- Presented by the Infrastructure Team
- Q1 2026 Planning Cycle

# Agenda
- Current state assessment
- Migration approach and timeline
- Cost analysis and projections
- Risk mitigation strategies
- Next steps and action items

# Migration Approach
- Lift-and-shift for stateless web applications
- Re-platform databases to managed services (RDS, Cloud SQL)
- Re-architect monolithic backend into microservices
- Phased rollout: dev environments first, then staging, then production
- Automated infrastructure provisioning with Terraform

# Cost Analysis
- Current on-premises costs: $2.4M annually
- Projected cloud costs year 1: $1.8M (includes migration overhead)
- Projected cloud costs year 2: $1.2M (steady state)
- Break-even point: 14 months after migration start
- Key cost drivers: compute (45%), storage (25%), networking (15%), support (15%)

# Summary and Next Steps
- Cloud migration reduces TCO by 50% within 2 years
- Phase 1 begins March 2026 with dev environment migration
- Team leads to submit application inventory by end of February
- Weekly migration standup begins next Monday
- Questions and discussion
```

**Step 4: Create `generic_info.md`** (4 slides)

```markdown
# Q3 Project Status Update
- Project Lighthouse: Quarterly Review
- Reporting Period: July through September 2025
- Prepared for the Executive Steering Committee

# Project Milestones
- Milestone 1: Requirements gathering (Complete)
- Milestone 2: Design and prototyping (Complete)
- Milestone 3: Core development (85% complete, on track)
- Milestone 4: User acceptance testing (Scheduled for October)
- Milestone 5: Production launch (Target: November 15)
- Overall project health: Green

# Team Highlights
- Development team expanded from 8 to 12 members
- Customer satisfaction score: 4.6 out of 5.0
- Sprint velocity improved 20% over Q2
- Zero critical production incidents in Q3
- Two team members completed AWS Solutions Architect certification
- Successful knowledge transfer sessions with offshore team

# Next Steps and Risks
- Complete remaining 15% of core development by October 5
- Begin UAT preparation: test plans, data seeding, user training
- Risk: third-party API vendor delayed SDK update (mitigation: parallel development with mock API)
- Risk: key developer on planned leave in November (mitigation: cross-training completed)
- Budget utilization: 72% of annual allocation spent, on target
- Next review: October 30
```

**Step 5: Verify files**

Run: `ls -la tests/e2e_outlines/`
Expected: 3 markdown files

Run: `grep -c "^# " tests/e2e_outlines/tech_overview.md`
Expected: `3`

Run: `grep -c "^# " tests/e2e_outlines/mini_presentation.md`
Expected: `5`

Run: `grep -c "^# " tests/e2e_outlines/generic_info.md`
Expected: `4`

**Step 6: Commit**

```bash
git add tests/e2e_outlines/
git commit -m "test: add E2E test outline files (3 decks, 12 slides total)"
```

---

### Task 3: Add pytest `e2e` marker

**Files:**
- Modify: `pyproject.toml`

**Step 1: Add the marker configuration**

Append to `pyproject.toml`:

```toml
[tool.pytest.ini_options]
markers = [
    "e2e: end-to-end tests requiring API keys and optional PowerPoint",
]
```

**Step 2: Verify marker is recognized**

Run: `venv/bin/python -m pytest --markers | grep e2e`
Expected: Shows the `e2e` marker description

**Step 3: Verify existing tests still pass**

Run: `venv/bin/python -m pytest tests/ -v --tb=short -m "not e2e"`
Expected: All existing tests pass, no warnings about unknown markers

**Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add pytest e2e marker for end-to-end tests"
```

---

### Task 4: Write E2E test fixtures and skip logic

**Files:**
- Create: `tests/test_e2e_pipeline.py`

This task creates the file with all fixtures and helper infrastructure. Tests come in Tasks 5-7.

**Step 1: Create the test file with fixtures**

```python
"""End-to-end pipeline tests: outline → deck → images → catalog → AI analysis.

These tests make REAL LLM API calls and optionally invoke PowerShell for image export.
They validate the full user workflow, not individual modules.

Run with:
    AMD_LLM_KEY=<key> python -m pytest tests/test_e2e_pipeline.py -m e2e -v -s

Requirements:
    - AMD_LLM_KEY environment variable set (for LLM calls via gateway)
    - models.yaml and gateway.yaml in project root (real config, not test fixtures)
    - Optional: pwsh.exe accessible from WSL (for image export step)
    - Optional: Microsoft PowerPoint installed on Windows side (for image export)
"""

import os
import re
import shutil
import textwrap
from pathlib import Path

import pytest
from pptx import Presentation

# ---------------------------------------------------------------------------
# Skip logic
# ---------------------------------------------------------------------------

SKIP_NO_KEY = not os.environ.get("AMD_LLM_KEY")
SKIP_KEY_REASON = "AMD_LLM_KEY environment variable not set"

PROJECT_ROOT = Path(__file__).parent.parent
OUTLINES_DIR = Path(__file__).parent / "e2e_outlines"
MODELS_YAML = PROJECT_ROOT / "models.yaml"
GATEWAY_YAML = PROJECT_ROOT / "gateway.yaml"

# Check PowerShell availability
def _pwsh_available():
    """Check if any PowerShell executable is accessible."""
    from outline2ppt.cli import _find_powershell
    return _find_powershell() is not None

HAS_PWSH = _pwsh_available() if not SKIP_NO_KEY else False
SKIP_NO_PWSH_REASON = "PowerShell (pwsh.exe) not available from this environment"

# Deck definitions: (name, outline_file, expected_slide_count)
DECK_SPECS = [
    ("tech_overview", "tech_overview.md", 3),
    ("mini_presentation", "mini_presentation.md", 5),
    ("generic_info", "generic_info.md", 4),
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def e2e_workspace(tmp_path_factory):
    """Create a workspace directory with subdirs for the entire E2E module.

    Structure:
        workspace/
            outlines/       -- copies of test outlines
            decks/          -- generated PPTX files
            images/         -- exported slide images (per deck)
            exports/        -- feedback and analysis exports
            slides.db       -- shared catalog database
    """
    workspace = tmp_path_factory.mktemp("e2e")
    for subdir in ("outlines", "decks", "images", "exports"):
        (workspace / subdir).mkdir()

    # Copy outline files into workspace
    for _, outline_file, _ in DECK_SPECS:
        src = OUTLINES_DIR / outline_file
        dst = workspace / "outlines" / outline_file
        shutil.copy2(str(src), str(dst))

    return workspace


@pytest.fixture(scope="module")
def db_path(e2e_workspace):
    """Path to the shared E2E database."""
    return str(e2e_workspace / "slides.db")


@pytest.fixture(scope="module")
def real_models_yaml(e2e_workspace, monkeypatch_module):
    """Point config to the real models.yaml in the project root.

    Unlike unit tests (which patch to tmp_path), E2E tests use the actual
    models.yaml so we validate the real configuration.
    """
    import outline2ppt.config as cfg_module
    monkeypatch_module.setattr(cfg_module, "DEFAULT_CONFIG_PATH", str(MODELS_YAML))
    return str(MODELS_YAML)


@pytest.fixture(scope="module")
def monkeypatch_module():
    """Module-scoped monkeypatch (pytest's monkeypatch is function-scoped)."""
    from _pytest.monkeypatch import MonkeyPatch
    mp = MonkeyPatch()
    yield mp
    mp.undo()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_default_template():
    """Get the path to the default python-pptx template."""
    import pptx
    return os.path.join(os.path.dirname(pptx.__file__), "templates", "default.pptx")


def _create_placeholder_images(images_dir, slide_count):
    """Create minimal valid PNG files as placeholders when PowerShell is unavailable.

    These are 1x1 pixel white PNGs — enough for the LLM vision API to process
    (it will see a blank slide, which is fine for testing the pipeline).
    """
    import struct
    import zlib

    def _minimal_png():
        """Generate a minimal valid 100x75 white PNG (small but not degenerate)."""
        width, height = 100, 75
        # IHDR
        ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
        ihdr = b"IHDR" + ihdr_data
        ihdr_chunk = struct.pack(">I", len(ihdr_data)) + ihdr + struct.pack(">I", zlib.crc32(ihdr) & 0xFFFFFFFF)
        # IDAT — white pixels (RGB)
        raw_data = b""
        for _ in range(height):
            raw_data += b"\x00" + b"\xff" * (width * 3)
        compressed = zlib.compress(raw_data)
        idat = b"IDAT" + compressed
        idat_chunk = struct.pack(">I", len(compressed)) + idat + struct.pack(">I", zlib.crc32(idat) & 0xFFFFFFFF)
        # IEND
        iend = b"IEND"
        iend_chunk = struct.pack(">I", 0) + iend + struct.pack(">I", zlib.crc32(iend) & 0xFFFFFFFF)
        return b"\x89PNG\r\n\x1a\n" + ihdr_chunk + idat_chunk + iend_chunk

    os.makedirs(images_dir, exist_ok=True)
    png_data = _minimal_png()
    for i in range(1, slide_count + 1):
        with open(os.path.join(images_dir, f"Slide{i}.PNG"), "wb") as f:
            f.write(png_data)


def _count_h1_headers(md_path):
    """Count H1 (# ) headers in a markdown file."""
    with open(md_path, encoding="utf-8") as f:
        return sum(1 for line in f if line.startswith("# "))


# ---------------------------------------------------------------------------
# Capability matrix for feedback-to-code analysis
# ---------------------------------------------------------------------------

CAPABILITY_MATRIX = {
    "font": {"level": "full", "description": "Font size, family, style changes", "api": "paragraph.font.size = Pt(N)"},
    "color": {"level": "partial", "description": "Individual color changes (no theme swap)", "api": "font.color.rgb = RGBColor(...)"},
    "text": {"level": "full", "description": "Text content changes", "api": "shape.text_frame.text = '...'"},
    "bold": {"level": "full", "description": "Bold/italic/underline", "api": "run.font.bold = True"},
    "bullet": {"level": "full", "description": "Bullet level and formatting", "api": "paragraph.level = N"},
    "notes": {"level": "full", "description": "Speaker notes", "api": "slide.notes_slide.notes_text_frame.text"},
    "position": {"level": "full", "description": "Shape position and size", "api": "shape.left = Inches(N)"},
    "shape": {"level": "full", "description": "Add/remove shapes", "api": "slide.shapes.add_textbox(...)"},
    "background": {"level": "full", "description": "Slide background color", "api": "slide.background.fill.solid()"},
    "table": {"level": "full", "description": "Table cell text and formatting", "api": "table.cell(r,c).text = '...'"},
    "layout": {"level": "partial", "description": "Layout selection (template-dependent)", "api": "slide_layouts[N]"},
    "image": {"level": "partial", "description": "Image add/replace (not edit)", "api": "slide.shapes.add_picture(...)"},
    "split": {"level": "partial", "description": "Slide splitting/reordering (XML)", "api": "XML manipulation"},
    "diagram": {"level": "none", "description": "SmartArt / complex diagrams", "api": "Not supported"},
    "animation": {"level": "none", "description": "Animations and transitions", "api": "Not supported"},
    "chart": {"level": "limited", "description": "Chart data (limited styling)", "api": "chart.series[0].values = [...]"},
    "whitespace": {"level": "full", "description": "Margin and spacing adjustments", "api": "text_frame.margin_left = Inches(N)"},
}

# Keywords that map feedback text to capability categories
CAPABILITY_KEYWORDS = {
    "font": ["font", "text size", "pt ", "point", "typeface", "serif", "sans-serif"],
    "color": ["color", "colour", "palette", "contrast", "rgb", "hex"],
    "text": ["text", "wording", "label", "title", "heading", "content", "rewrite", "rephrase"],
    "bold": ["bold", "italic", "underline", "emphasis", "weight"],
    "bullet": ["bullet", "indent", "list", "numbering", "hierarchy"],
    "notes": ["notes", "speaker", "talking point"],
    "position": ["position", "align", "center", "margin", "spacing", "move", "resize", "placement"],
    "shape": ["shape", "textbox", "box", "rectangle", "callout", "add a "],
    "background": ["background"],
    "table": ["table", "cell", "row", "column", "grid"],
    "layout": ["layout", "template", "slide design"],
    "image": ["image", "picture", "photo", "icon", "logo", "graphic", "visual"],
    "split": ["split", "divide", "separate", "two slides", "multiple slides", "break up"],
    "diagram": ["diagram", "smartart", "flowchart", "org chart", "process flow"],
    "animation": ["animation", "transition", "fade", "appear", "motion"],
    "chart": ["chart", "graph", "pie", "bar chart", "line chart", "data visualization"],
    "whitespace": ["whitespace", "white space", "spacing", "breathing room", "clutter", "dense", "crowded"],
}


def classify_feedback_item(text):
    """Classify a single feedback bullet point against the capability matrix.

    Returns: (category, level) or ("unknown", "unknown") if no match.
    """
    text_lower = text.lower()
    for category, keywords in CAPABILITY_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text_lower:
                return category, CAPABILITY_MATRIX[category]["level"]
    return "unknown", "unknown"


def analyze_improvements_feedback(improvements_text):
    """Parse improvements markdown and classify each bullet point.

    Returns a list of dicts:
        [{"section": "Visual Design", "item": "...", "category": "font", "level": "full"}, ...]
    """
    results = []
    current_section = "General"

    for line in improvements_text.split("\n"):
        line = line.strip()
        # Detect section headers
        if line.startswith("## "):
            current_section = line[3:].strip()
            continue
        # Detect bullet points
        if line.startswith("- ") or line.startswith("* ") or re.match(r"^\d+\.", line):
            item_text = re.sub(r"^[-*]\s*|\d+\.\s*", "", line).strip()
            if item_text:
                category, level = classify_feedback_item(item_text)
                results.append({
                    "section": current_section,
                    "item": item_text,
                    "category": category,
                    "level": level,
                })

    return results
```

**Step 2: Verify the file loads without errors**

Run: `venv/bin/python -c "import tests.test_e2e_pipeline; print('OK')"`
Expected: `OK` (or import from the test file successfully)

Actually, verify with pytest collection:

Run: `venv/bin/python -m pytest tests/test_e2e_pipeline.py --collect-only`
Expected: `no tests ran` (no test functions yet, but no import errors)

**Step 3: Commit**

```bash
git add tests/test_e2e_pipeline.py
git commit -m "test: E2E pipeline test fixtures and capability analysis helpers"
```

---

### Task 5: Write pipeline tests — create + export-images + catalog

**Files:**
- Modify: `tests/test_e2e_pipeline.py`

**Step 1: Add the pipeline test for deck creation, image export, and cataloging**

Append to `tests/test_e2e_pipeline.py`:

```python
# ---------------------------------------------------------------------------
# Pipeline tests
# ---------------------------------------------------------------------------

@pytest.mark.e2e
@pytest.mark.skipif(SKIP_NO_KEY, reason=SKIP_KEY_REASON)
class TestE2EPipeline:
    """Full pipeline test: outline → deck → images → catalog → analyze → export.

    Uses module-scoped fixtures so state (database, files) persists across
    test methods within this class. Methods are ordered and must run sequentially.
    """

    # Store results across test methods (module-level state)
    _deck_paths = {}       # deck_name → pptx path
    _image_dirs = {}       # deck_name → images directory
    _feedback_results = {} # deck_name → {position: feedback_text}
    _improvements_results = {}  # deck_name → {position: improvements_text}

    # -- Step 1: Create decks from outlines ----------------------------------

    @pytest.mark.parametrize("deck_name, outline_file, expected_slides", DECK_SPECS)
    def test_01_create_deck(self, deck_name, outline_file, expected_slides,
                            e2e_workspace, real_models_yaml):
        """Create a PPTX deck from a markdown outline (no LLM enhancement)."""
        from outline2ppt.cli import build_parser, cmd_create

        outline_path = str(e2e_workspace / "outlines" / outline_file)
        output_path = str(e2e_workspace / "decks" / f"{deck_name}.pptx")
        template_path = _get_default_template()

        # Verify outline has expected slide count
        assert _count_h1_headers(outline_path) == expected_slides, \
            f"{outline_file} should have {expected_slides} H1 headers"

        # Build args and run create
        parser = build_parser()
        args = parser.parse_args([
            "create", outline_path, template_path, output_path,
        ])
        result = cmd_create(args)
        assert result == 0, f"cmd_create failed for {deck_name}"

        # Verify output
        assert os.path.exists(output_path), f"Output PPTX not created: {output_path}"
        prs = Presentation(output_path)
        assert len(prs.slides) == expected_slides, \
            f"Expected {expected_slides} slides, got {len(prs.slides)}"

        # Store for later tests
        TestE2EPipeline._deck_paths[deck_name] = output_path
        print(f"  Created {deck_name}: {len(prs.slides)} slides → {output_path}")

    # -- Step 2: Export images -----------------------------------------------

    @pytest.mark.parametrize("deck_name, _, expected_slides", DECK_SPECS)
    def test_02_export_images(self, deck_name, _, expected_slides,
                              e2e_workspace, real_models_yaml):
        """Export slide images via PowerShell, or create placeholders."""
        deck_path = TestE2EPipeline._deck_paths.get(deck_name)
        assert deck_path, f"Deck not created yet: {deck_name} (run test_01 first)"

        images_dir = str(e2e_workspace / "images" / deck_name)

        if HAS_PWSH:
            # Real PowerShell export
            from outline2ppt.cli import build_parser, cmd_export_images
            parser = build_parser()
            args = parser.parse_args([
                "export-images", deck_path, images_dir,
                "--width", "1920", "--height", "1080",
            ])
            result = cmd_export_images(args)
            if result != 0:
                print(f"  PowerShell export failed (rc={result}), falling back to placeholders")
                _create_placeholder_images(images_dir, expected_slides)
        else:
            print(f"  PowerShell not available, creating placeholder images")
            _create_placeholder_images(images_dir, expected_slides)

        # Verify images exist
        for i in range(1, expected_slides + 1):
            found = False
            for ext in (".PNG", ".png", ".jpg", ".jpeg"):
                if os.path.exists(os.path.join(images_dir, f"Slide{i}{ext}")):
                    found = True
                    break
            assert found, f"No image found for Slide{i} in {images_dir}"

        TestE2EPipeline._image_dirs[deck_name] = images_dir
        print(f"  Images for {deck_name}: {images_dir} ({expected_slides} slides)")

    # -- Step 3: Catalog decks -----------------------------------------------

    @pytest.mark.parametrize("deck_name, _, expected_slides", DECK_SPECS)
    def test_03_catalog_deck(self, deck_name, _, expected_slides,
                             e2e_workspace, db_path, real_models_yaml):
        """Catalog each deck into the SQLite database."""
        from outline2ppt.catalog import catalog_deck, get_db

        deck_path = TestE2EPipeline._deck_paths[deck_name]
        images_dir = TestE2EPipeline._image_dirs[deck_name]

        deck_id = catalog_deck(deck_path, db_path=db_path, images_dir=images_dir)
        assert deck_id > 0, f"catalog_deck returned invalid id: {deck_id}"

        # Verify slide count in DB
        conn = get_db(db_path)
        slides = conn.execute(
            "SELECT COUNT(*) as cnt FROM slides WHERE deck_id = ?", (deck_id,)
        ).fetchone()
        conn.close()
        assert slides["cnt"] == expected_slides, \
            f"Expected {expected_slides} slides in DB for {deck_name}, got {slides['cnt']}"

        print(f"  Cataloged {deck_name}: deck_id={deck_id}, {expected_slides} slides")
```

**Step 2: Run the creation and cataloging tests (no LLM calls yet)**

Run: `AMD_LLM_KEY=$AMD_LLM_KEY venv/bin/python -m pytest tests/test_e2e_pipeline.py::TestE2EPipeline::test_01_create_deck -v -s -m e2e`
Expected: 3 parametrized tests PASS, PPTX files created

Run: `AMD_LLM_KEY=$AMD_LLM_KEY venv/bin/python -m pytest tests/test_e2e_pipeline.py::TestE2EPipeline::test_02_export_images -v -s -m e2e`
Expected: 3 tests PASS (with PowerShell or placeholder fallback)

Run: `AMD_LLM_KEY=$AMD_LLM_KEY venv/bin/python -m pytest tests/test_e2e_pipeline.py::TestE2EPipeline::test_03_catalog_deck -v -s -m e2e`
Expected: 3 tests PASS, slides in DB

**Step 3: Commit**

```bash
git add tests/test_e2e_pipeline.py
git commit -m "test: E2E pipeline steps 1-3 (create, export-images, catalog)"
```

---

### Task 6: Write pipeline tests — analyze (all 4 modes)

**Files:**
- Modify: `tests/test_e2e_pipeline.py`

**Step 1: Add analysis tests to `TestE2EPipeline` class**

Append inside the `TestE2EPipeline` class:

```python
    # -- Step 4: Generate tags (real LLM) ------------------------------------

    @pytest.mark.parametrize("deck_name, _, expected_slides", DECK_SPECS)
    def test_04_analyze_tags(self, deck_name, _, expected_slides,
                             e2e_workspace, db_path, real_models_yaml):
        """Generate AI tags for each slide via real LLM call."""
        from outline2ppt.catalog import get_db, get_slide_tags

        deck_path = TestE2EPipeline._deck_paths[deck_name]
        images_dir = TestE2EPipeline._image_dirs[deck_name]

        # Run analyze via the CLI function
        from outline2ppt.cli import build_parser, cmd_analyze
        parser = build_parser()
        args = parser.parse_args([
            "analyze", deck_path,
            "--mode", "tags",
            "--images-dir", images_dir,
            "--db", db_path,
            "--gateway-config", str(GATEWAY_YAML),
        ])
        result = cmd_analyze(args)
        assert result == 0, f"cmd_analyze --mode tags failed for {deck_name}"

        # Verify tags were added
        conn = get_db(db_path)
        deck_row = conn.execute(
            "SELECT id FROM decks WHERE file_path = ?",
            (os.path.abspath(deck_path),)
        ).fetchone()
        slides = conn.execute(
            "SELECT id, position, title FROM slides WHERE deck_id = ? ORDER BY position",
            (deck_row["id"],)
        ).fetchall()
        conn.close()

        for slide in slides:
            tags = get_slide_tags(slide["id"], db_path)
            assert len(tags) >= 1, \
                f"Slide {slide['position']} ({slide['title']}) has no tags"
            print(f"  {deck_name} slide {slide['position']}: tags={tags}")

    # -- Step 5: Generate feedback (real LLM) --------------------------------

    @pytest.mark.parametrize("deck_name, _, expected_slides", DECK_SPECS)
    def test_05_analyze_feedback(self, deck_name, _, expected_slides,
                                 e2e_workspace, db_path, real_models_yaml, capsys):
        """Generate AI feedback for each slide via real LLM call."""
        deck_path = TestE2EPipeline._deck_paths[deck_name]
        images_dir = TestE2EPipeline._image_dirs[deck_name]

        from outline2ppt.cli import build_parser, cmd_analyze
        parser = build_parser()
        args = parser.parse_args([
            "analyze", deck_path,
            "--mode", "feedback",
            "--images-dir", images_dir,
            "--db", db_path,
            "--gateway-config", str(GATEWAY_YAML),
        ])
        result = cmd_analyze(args)
        assert result == 0, f"cmd_analyze --mode feedback failed for {deck_name}"

        # Capture printed feedback
        captured = capsys.readouterr()
        assert len(captured.out) > 100, \
            f"Feedback output too short for {deck_name}: {len(captured.out)} chars"

        # Store for export in step 8
        TestE2EPipeline._feedback_results[deck_name] = captured.out
        print(f"  {deck_name} feedback: {len(captured.out)} chars captured")

    # -- Step 6: Generate notes (real LLM) -----------------------------------

    @pytest.mark.parametrize("deck_name, _, expected_slides", DECK_SPECS)
    def test_06_analyze_notes(self, deck_name, _, expected_slides,
                              e2e_workspace, db_path, real_models_yaml):
        """Generate AI speaker notes and save to PPTX."""
        deck_path = TestE2EPipeline._deck_paths[deck_name]
        images_dir = TestE2EPipeline._image_dirs[deck_name]

        from outline2ppt.cli import build_parser, cmd_analyze
        parser = build_parser()
        args = parser.parse_args([
            "analyze", deck_path,
            "--mode", "notes",
            "--images-dir", images_dir,
            "--db", db_path,
            "--gateway-config", str(GATEWAY_YAML),
        ])
        result = cmd_analyze(args)
        assert result == 0, f"cmd_analyze --mode notes failed for {deck_name}"

        # Verify notes were written to the PPTX
        prs = Presentation(deck_path)
        notes_found = 0
        for i, slide in enumerate(prs.slides, 1):
            if slide.has_notes_slide:
                notes_text = slide.notes_slide.notes_text_frame.text.strip()
                if notes_text:
                    notes_found += 1
                    # Print first 80 chars of notes
                    preview = notes_text[:80].replace("\n", " ")
                    print(f"  {deck_name} slide {i} notes: {preview}...")

        assert notes_found >= 1, \
            f"No speaker notes found in {deck_name} PPTX after notes generation"
        print(f"  {deck_name}: {notes_found}/{len(prs.slides)} slides have notes")

    # -- Step 7: Generate improvements (real LLM) ----------------------------

    @pytest.mark.parametrize("deck_name, _, expected_slides", DECK_SPECS)
    def test_07_analyze_improvements(self, deck_name, _, expected_slides,
                                     e2e_workspace, db_path, real_models_yaml,
                                     capsys):
        """Generate structured improvement suggestions via real LLM call."""
        deck_path = TestE2EPipeline._deck_paths[deck_name]
        images_dir = TestE2EPipeline._image_dirs[deck_name]

        from outline2ppt.cli import build_parser, cmd_analyze
        parser = build_parser()
        args = parser.parse_args([
            "analyze", deck_path,
            "--mode", "improvements",
            "--images-dir", images_dir,
            "--db", db_path,
            "--gateway-config", str(GATEWAY_YAML),
        ])
        result = cmd_analyze(args)
        assert result == 0, f"cmd_analyze --mode improvements failed for {deck_name}"

        # Capture printed improvements
        captured = capsys.readouterr()
        assert len(captured.out) > 200, \
            f"Improvements output too short for {deck_name}: {len(captured.out)} chars"

        # Verify expected sections are present in the output
        output_lower = captured.out.lower()
        for section in ["visual design", "technical accuracy", "flow", "split"]:
            assert section in output_lower, \
                f"Missing '{section}' section in improvements for {deck_name}"

        TestE2EPipeline._improvements_results[deck_name] = captured.out
        print(f"  {deck_name} improvements: {len(captured.out)} chars captured")
```

**Step 2: Run the analysis tests (these make real LLM calls — slow)**

Run: `AMD_LLM_KEY=$AMD_LLM_KEY venv/bin/python -m pytest tests/test_e2e_pipeline.py::TestE2EPipeline::test_04_analyze_tags -v -s -m e2e --timeout=300`
Expected: 3 tests PASS (may take 30-60s total for 12 slides)

Run each subsequent test class similarly. Or run all at once:

Run: `AMD_LLM_KEY=$AMD_LLM_KEY venv/bin/python -m pytest tests/test_e2e_pipeline.py -v -s -m e2e --timeout=600`
Expected: All tests through step 7 PASS

**Step 3: Commit**

```bash
git add tests/test_e2e_pipeline.py
git commit -m "test: E2E pipeline steps 4-7 (tags, feedback, notes, improvements)"
```

---

### Task 7: Write capability analysis logic and export

**Files:**
- Modify: `tests/test_e2e_pipeline.py`

**Step 1: Add export and capability analysis tests**

Append inside the `TestE2EPipeline` class:

```python
    # -- Step 8: Export feedback to markdown ----------------------------------

    def test_08_export_feedback(self, e2e_workspace, real_models_yaml):
        """Export collected feedback results to markdown files."""
        exports_dir = e2e_workspace / "exports"

        for deck_name, feedback_text in TestE2EPipeline._feedback_results.items():
            output_path = exports_dir / f"{deck_name}-feedback.md"
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(f"# Feedback: {deck_name}\n\n")
                f.write(f"Generated by E2E pipeline test\n\n")
                f.write(feedback_text)

            assert os.path.exists(output_path)
            assert os.path.getsize(output_path) > 100
            print(f"  Exported feedback: {output_path}")

        assert len(TestE2EPipeline._feedback_results) == len(DECK_SPECS), \
            "Not all decks have feedback results"

    # -- Step 9: Capability analysis -----------------------------------------

    def test_09_capability_analysis(self, e2e_workspace, real_models_yaml):
        """Classify improvement feedback against python-pptx capability matrix."""
        exports_dir = e2e_workspace / "exports"

        for deck_name, improvements_text in TestE2EPipeline._improvements_results.items():
            classified = analyze_improvements_feedback(improvements_text)
            assert len(classified) > 0, \
                f"No feedback items parsed from improvements for {deck_name}"

            # Count by level
            counts = {"full": 0, "partial": 0, "limited": 0, "none": 0, "unknown": 0}
            for item in classified:
                counts[item["level"]] = counts.get(item["level"], 0) + 1

            total = len(classified)
            actionable = counts["full"] + counts["partial"] + counts["limited"]

            # Write analysis report
            output_path = exports_dir / f"{deck_name}-capability-analysis.md"
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(f"# Capability Analysis: {deck_name}\n\n")
                f.write(f"Total feedback items: {total}\n")
                f.write(f"Actionable (full/partial/limited): {actionable} ({actionable*100//total if total else 0}%)\n")
                f.write(f"Not actionable: {counts['none']}\n")
                f.write(f"Unclassified: {counts['unknown']}\n\n")

                f.write("## Detailed Classification\n\n")
                current_section = None
                for item in classified:
                    if item["section"] != current_section:
                        current_section = item["section"]
                        f.write(f"\n### {current_section}\n\n")

                    level_emoji = {"full": "YES", "partial": "PARTIAL", "limited": "LIMITED",
                                   "none": "NO", "unknown": "?"}
                    f.write(f"- [{level_emoji[item['level']]}] {item['item']}\n")
                    f.write(f"  Category: {item['category']}")
                    if item["category"] in CAPABILITY_MATRIX:
                        f.write(f" — {CAPABILITY_MATRIX[item['category']]['description']}")
                        f.write(f" — API: `{CAPABILITY_MATRIX[item['category']]['api']}`")
                    f.write("\n")

                f.write("\n## python-pptx Capability Reference\n\n")
                f.write("| Category | Support | API |\n")
                f.write("|----------|---------|-----|\n")
                for cat, info in CAPABILITY_MATRIX.items():
                    f.write(f"| {cat} | {info['level']} | `{info['api']}` |\n")

            assert os.path.exists(output_path)
            print(f"  {deck_name}: {actionable}/{total} items actionable via python-pptx")
            print(f"    Full: {counts['full']}, Partial: {counts['partial']}, "
                  f"None: {counts['none']}, Unknown: {counts['unknown']}")
            print(f"  Report: {output_path}")

    # -- Step 10: Print summary and export locations -------------------------

    def test_10_summary(self, e2e_workspace, real_models_yaml):
        """Print a summary of all E2E test artifacts."""
        print("\n" + "=" * 70)
        print("E2E PIPELINE TEST SUMMARY")
        print("=" * 70)

        print(f"\nWorkspace: {e2e_workspace}")
        print(f"Database: {e2e_workspace / 'slides.db'}")

        print("\nDecks created:")
        for name, path in TestE2EPipeline._deck_paths.items():
            prs = Presentation(path)
            print(f"  {name}: {len(prs.slides)} slides → {path}")

        print("\nImage directories:")
        for name, path in TestE2EPipeline._image_dirs.items():
            count = len([f for f in os.listdir(path) if f.endswith((".png", ".PNG", ".jpg"))])
            print(f"  {name}: {count} images → {path}")

        print("\nExport files:")
        exports_dir = e2e_workspace / "exports"
        for f in sorted(exports_dir.iterdir()):
            size = f.stat().st_size
            print(f"  {f.name}: {size:,} bytes")

        print("\n" + "=" * 70)
```

**Step 2: Run the full E2E suite**

Run: `AMD_LLM_KEY=$AMD_LLM_KEY venv/bin/python -m pytest tests/test_e2e_pipeline.py -v -s -m e2e --timeout=600`
Expected: All tests PASS. Summary printed at end shows all artifacts.

**Step 3: Commit**

```bash
git add tests/test_e2e_pipeline.py
git commit -m "test: E2E pipeline steps 8-10 (export, capability analysis, summary)"
```

---

### Task 8: Run full E2E suite and verify

**Files:** None (verification only)

**Step 1: Run existing tests to verify no regressions**

Run: `venv/bin/python -m pytest tests/ -v --tb=short -m "not e2e" --ignore=tests/test_gateway_live.py`
Expected: All existing tests pass (the `autouse` fixture for `patch_default_config_path` should NOT interfere with E2E tests since E2E overrides it with `real_models_yaml`)

**Step 2: Run the full E2E suite**

Run: `AMD_LLM_KEY=$AMD_LLM_KEY venv/bin/python -m pytest tests/test_e2e_pipeline.py -v -s -m e2e --timeout=600`
Expected: All tests PASS

**Step 3: Review the exported artifacts**

Check the workspace path printed in the summary. Review:
- `exports/*-feedback.md` — readable, contains per-slide feedback
- `exports/*-capability-analysis.md` — categories make sense, percentages reasonable

**Step 4: Commit all remaining changes and update progress tracker**

```bash
git add -A
git commit -m "test: complete E2E pipeline test suite with capability analysis"
```

---

## Notes for the Implementer

1. **The `autouse` fixture in `conftest.py` patches `DEFAULT_CONFIG_PATH`** to `tmp_path`. The E2E tests need the real `models.yaml`, so `real_models_yaml` fixture re-patches it. This must be module-scoped to persist across the ordered test methods.

2. **Test ordering matters.** The tests within `TestE2EPipeline` are numbered (`test_01_`, `test_02_`, etc.) and share class-level state. Pytest runs them in declaration order within a class. If a parametrized test fails for one deck, subsequent tests for that deck will also fail (they depend on `_deck_paths` being populated).

3. **The `capsys` fixture** captures stdout/stderr. The analyze commands print their results to stdout, so we capture them and store them for the export step. Note: `capsys` is function-scoped in pytest, which is fine since each `test_0N_` method is a separate function.

4. **PowerShell fallback.** If `pwsh.exe` isn't available or fails, placeholder images are created. The LLM will see minimal white PNGs, which is fine for testing the pipeline (the feedback will be generic but the pipeline still exercises all code paths).

5. **Module-scoped `tmp_path_factory`** creates a single workspace shared across all tests in the module. This avoids recreating decks and databases for each test method.
