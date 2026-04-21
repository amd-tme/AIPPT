# Ingest Command Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add an `ingest` CLI subcommand that automates export-images → catalog → optional tagging in one invocation.

**Architecture:** A new `cmd_ingest()` function in `cli.py` that orchestrates calls to existing internal functions (`cmd_export_images`, `catalog_deck`, `cmd_analyze`). No new modules — pure orchestration. The function constructs `argparse.Namespace` objects to pass to existing commands.

**Tech Stack:** Python, argparse, existing cli.py functions

**PRD:** `docs/plans/2026-02-26-prd-ingest-command.md`

---

### Task 1: Add `ingest` subparser to `build_parser()`

**Files:**
- Modify: `outline2ppt/cli.py:963` (insert before `export-images` parser)
- Test: `tests/test_cli.py`

**Step 1: Write the failing test**

Add to `tests/test_cli.py` — import `cmd_ingest` in the import block and add a new test class:

```python
# Update import at top of file (line 8-12):
from outline2ppt.cli import (
    build_parser,
    cmd_reverse,
    cmd_ingest,
    _extract_slide_text,
)

# Add after TestBuildParser class:

class TestIngestParser:
    """Tests for the ingest subcommand argument parsing."""

    def test_ingest_subcommand_exists(self):
        parser = build_parser()
        args = parser.parse_args(['ingest', 'deck.pptx'])
        assert args.command == 'ingest'
        assert args.deck == 'deck.pptx'

    def test_ingest_defaults(self):
        parser = build_parser()
        args = parser.parse_args(['ingest', 'deck.pptx'])
        assert args.db == 'slides.db'
        assert args.images_dir is None
        assert args.tags is False
        assert args.taxonomy is None
        assert args.model is None
        assert args.width == 1920
        assert args.height == 1080

    def test_ingest_all_flags(self):
        parser = build_parser()
        args = parser.parse_args([
            'ingest', 'deck.pptx',
            '--images-dir', 'img/',
            '--db', 'test.db',
            '--tags',
            '--taxonomy', 'tags.csv',
            '--model', 'gpt-4o',
            '--gateway-config', 'gw.yaml',
            '--width', '2560',
            '--height', '1440',
        ])
        assert args.tags is True
        assert args.taxonomy == 'tags.csv'
        assert args.model == 'gpt-4o'
        assert args.gateway_config == 'gw.yaml'
        assert args.images_dir == 'img/'
        assert args.db == 'test.db'
        assert args.width == 2560
        assert args.height == 1440

    def test_taxonomy_flag_without_tags_flag(self):
        """--taxonomy doesn't implicitly enable --tags."""
        parser = build_parser()
        args = parser.parse_args(['ingest', 'deck.pptx', '--taxonomy', 'tags.csv'])
        assert args.tags is False
```

**Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/test_cli.py::TestIngestParser -v`
Expected: ImportError for `cmd_ingest` or argument parsing errors.

**Step 3: Add the subparser and stub `cmd_ingest`**

In `outline2ppt/cli.py`, add the subparser. Insert before the `# export-images` block (line 963):

```python
    # ingest
    p_ingest = sub.add_parser("ingest", help="Ingest a deck: export images, catalog, and optionally tag")
    p_ingest.add_argument("deck", help="PowerPoint file to ingest")
    p_ingest.add_argument("--images-dir", default=None,
                          help="Output directory for slide images (default: images/<deck-name>/)")
    p_ingest.add_argument("--db", default="slides.db", help="Database file path")
    p_ingest.add_argument("--tags", action="store_true", help="Generate AI tags after cataloging")
    p_ingest.add_argument("--taxonomy", help="CSV file for taxonomy-constrained tagging")
    p_ingest.add_argument("--model", default=None, help="Model to use for tag generation")
    p_ingest.add_argument("--gateway-config", default="gateway.yaml", help="Gateway YAML config path")
    p_ingest.add_argument("--api-key", default=None, help="API key for LLM provider")
    p_ingest.add_argument("--width", type=int, default=1920, help="Image export width (default: 1920)")
    p_ingest.add_argument("--height", type=int, default=1080, help="Image export height (default: 1080)")
```

Add the stub function before `cmd_export_images` (around line 700):

```python
def cmd_ingest(args):
    """Ingest a deck: export images, catalog, and optionally tag."""
    pass
```

Add `"ingest": cmd_ingest,` to the `commands` dict in `main()` (after the `"export-images"` entry, around line 1014).

**Step 4: Run test to verify it passes**

Run: `venv/bin/python -m pytest tests/test_cli.py::TestIngestParser -v`
Expected: All 4 tests PASS.

**Step 5: Commit**

```bash
git add outline2ppt/cli.py tests/test_cli.py
git commit -m "feat: add ingest subparser and stub cmd_ingest"
```

---

### Task 2: Implement `cmd_ingest()` — image export + catalog

**Files:**
- Modify: `outline2ppt/cli.py` — `cmd_ingest()` function
- Test: `tests/test_cli.py`

**Step 1: Write the failing tests**

Add to `TestIngestCommand` class in `tests/test_cli.py`:

```python
class TestIngestCommand:
    """Tests for cmd_ingest orchestration logic."""

    def test_file_not_found(self, tmp_path):
        parser = build_parser()
        args = parser.parse_args(['ingest', str(tmp_path / 'missing.pptx')])
        result = cmd_ingest(args)
        assert result == 1

    @patch('outline2ppt.cli.cmd_export_images')
    def test_export_images_failure_stops_pipeline(self, mock_export, tmp_path):
        deck = tmp_path / 'test.pptx'
        deck.touch()
        mock_export.return_value = 1

        parser = build_parser()
        args = parser.parse_args(['ingest', str(deck)])
        result = cmd_ingest(args)

        assert result == 1
        mock_export.assert_called_once()

    @patch('outline2ppt.cli.catalog_deck')
    @patch('outline2ppt.cli.cmd_export_images')
    def test_export_then_catalog(self, mock_export, mock_catalog, tmp_path):
        deck = tmp_path / 'test.pptx'
        deck.touch()
        mock_export.return_value = 0
        mock_catalog.return_value = 42

        parser = build_parser()
        args = parser.parse_args(['ingest', str(deck), '--db', str(tmp_path / 'test.db')])
        result = cmd_ingest(args)

        assert result == 0
        mock_export.assert_called_once()
        mock_catalog.assert_called_once()
        # Verify catalog was called with correct db_path
        _, kwargs = mock_catalog.call_args
        assert kwargs['db_path'] == str(tmp_path / 'test.db')

    @patch('outline2ppt.cli.catalog_deck')
    @patch('outline2ppt.cli.cmd_export_images')
    def test_default_images_dir(self, mock_export, mock_catalog, tmp_path):
        deck = tmp_path / 'my-deck.pptx'
        deck.touch()
        mock_export.return_value = 0
        mock_catalog.return_value = 1

        parser = build_parser()
        args = parser.parse_args(['ingest', str(deck)])
        result = cmd_ingest(args)

        assert result == 0
        # Verify export was called with auto-derived images dir
        export_args = mock_export.call_args[0][0]
        assert 'my-deck' in export_args.out_dir

    @patch('outline2ppt.cli.catalog_deck')
    @patch('outline2ppt.cli.cmd_export_images')
    def test_no_tags_by_default(self, mock_export, mock_catalog, tmp_path):
        """Without --tags, cmd_analyze is not called."""
        deck = tmp_path / 'test.pptx'
        deck.touch()
        mock_export.return_value = 0
        mock_catalog.return_value = 1

        parser = build_parser()
        args = parser.parse_args(['ingest', str(deck)])

        with patch('outline2ppt.cli.cmd_analyze') as mock_analyze:
            result = cmd_ingest(args)
            mock_analyze.assert_not_called()

        assert result == 0
```

**Step 2: Run tests to verify they fail**

Run: `venv/bin/python -m pytest tests/test_cli.py::TestIngestCommand -v`
Expected: Failures — `cmd_ingest` returns None (stub).

**Step 3: Implement `cmd_ingest` — export + catalog steps**

Replace the `cmd_ingest` stub in `cli.py`:

```python
def cmd_ingest(args):
    """Ingest a deck: export images, catalog, and optionally tag."""
    import argparse
    from outline2ppt.catalog import catalog_deck

    if not os.path.exists(args.deck):
        logger.error(f"File not found: {args.deck}")
        return 1

    # Derive images directory from deck filename if not specified
    images_dir = args.images_dir
    if not images_dir:
        deck_name = os.path.splitext(os.path.basename(args.deck))[0]
        images_dir = os.path.join("images", deck_name)

    # --- Step 1: Export images ---
    print(f"\n[1/{'3' if args.tags else '2'}] Exporting slide images...")
    export_args = argparse.Namespace(
        deck=args.deck,
        out_dir=images_dir,
        width=args.width,
        height=args.height,
    )
    rc = cmd_export_images(export_args)
    if rc != 0:
        logger.error("Image export failed. Is PowerShell and PowerPoint available?")
        return 1
    print(f"  Images exported to: {images_dir}")

    # --- Step 2: Catalog ---
    step = "2" if not args.tags else "2/3"
    print(f"\n[{step}] Cataloging deck...")
    deck_id = catalog_deck(args.deck, db_path=args.db, images_dir=images_dir)
    print(f"  Cataloged as deck_id={deck_id}")

    # --- Step 3: Tags (optional) ---
    tag_count = 0
    if args.tags:
        print(f"\n[3/3] Generating tags...")
        analyze_args = argparse.Namespace(
            deck=args.deck,
            mode="tags",
            images_dir=images_dir,
            db=args.db,
            model=args.model,
            taxonomy=args.taxonomy,
            gateway_config=args.gateway_config,
            api_key=getattr(args, 'api_key', None),
        )
        rc = cmd_analyze(analyze_args)
        if rc != 0:
            logger.warning("Tag generation completed with errors (some slides may have failed)")

    # --- Summary ---
    print(f"\n{'=' * 50}")
    print(f"INGEST COMPLETE")
    print(f"{'=' * 50}")
    print(f"  Deck: {args.deck}")
    print(f"  Deck ID: {deck_id}")
    print(f"  Images: {images_dir}")
    print(f"  Database: {args.db}")
    if args.tags:
        print(f"  Tags: generated")
    print(f"{'=' * 50}\n")

    return 0
```

Note: `catalog_deck` needs to be importable at the module level for mocking. Add this near the top of `cmd_ingest`, or the tests can patch `outline2ppt.cli.catalog_deck`. Since the function does `from outline2ppt.catalog import catalog_deck` inside the function body, tests should patch `outline2ppt.cli.catalog_deck` which won't work. Instead, keep the import inside the function and patch `outline2ppt.catalog.catalog_deck`. Update the test patches accordingly:

```python
# In tests, use:
@patch('outline2ppt.catalog.catalog_deck')
@patch('outline2ppt.cli.cmd_export_images')
```

**Step 4: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/test_cli.py::TestIngestCommand -v`
Expected: All 5 tests PASS.

**Step 5: Run full test suite**

Run: `venv/bin/python -m pytest tests/ --ignore=tests/test_e2e_pipeline.py --ignore=tests/test_gateway_live.py -q`
Expected: All tests pass, no regressions.

**Step 6: Commit**

```bash
git add outline2ppt/cli.py tests/test_cli.py
git commit -m "feat: implement cmd_ingest with export-images and catalog"
```

---

### Task 3: Implement `cmd_ingest()` — optional `--tags` step

**Files:**
- Modify: `outline2ppt/cli.py` — `cmd_ingest()` (already has the tag code from Task 2, just needs test coverage)
- Test: `tests/test_cli.py`

**Step 1: Write the failing tests**

Add to `TestIngestCommand` in `tests/test_cli.py`:

```python
    @patch('outline2ppt.cli.cmd_analyze')
    @patch('outline2ppt.catalog.catalog_deck')
    @patch('outline2ppt.cli.cmd_export_images')
    def test_tags_flag_runs_analyze(self, mock_export, mock_catalog, mock_analyze, tmp_path):
        deck = tmp_path / 'test.pptx'
        deck.touch()
        mock_export.return_value = 0
        mock_catalog.return_value = 1
        mock_analyze.return_value = 0

        parser = build_parser()
        args = parser.parse_args(['ingest', str(deck), '--tags', '--model', 'gpt-4o'])
        result = cmd_ingest(args)

        assert result == 0
        mock_analyze.assert_called_once()
        analyze_args = mock_analyze.call_args[0][0]
        assert analyze_args.mode == 'tags'
        assert analyze_args.model == 'gpt-4o'

    @patch('outline2ppt.cli.cmd_analyze')
    @patch('outline2ppt.catalog.catalog_deck')
    @patch('outline2ppt.cli.cmd_export_images')
    def test_tags_with_taxonomy(self, mock_export, mock_catalog, mock_analyze, tmp_path):
        deck = tmp_path / 'test.pptx'
        deck.touch()
        mock_export.return_value = 0
        mock_catalog.return_value = 1
        mock_analyze.return_value = 0

        parser = build_parser()
        args = parser.parse_args([
            'ingest', str(deck), '--tags', '--taxonomy', 'tags.csv'
        ])
        result = cmd_ingest(args)

        assert result == 0
        analyze_args = mock_analyze.call_args[0][0]
        assert analyze_args.taxonomy == 'tags.csv'

    @patch('outline2ppt.cli.cmd_analyze')
    @patch('outline2ppt.catalog.catalog_deck')
    @patch('outline2ppt.cli.cmd_export_images')
    def test_tags_failure_still_returns_success(self, mock_export, mock_catalog, mock_analyze, tmp_path):
        """Tag generation errors are warnings, not failures (deck is already cataloged)."""
        deck = tmp_path / 'test.pptx'
        deck.touch()
        mock_export.return_value = 0
        mock_catalog.return_value = 1
        mock_analyze.return_value = 1  # analyze fails

        parser = build_parser()
        args = parser.parse_args(['ingest', str(deck), '--tags'])
        result = cmd_ingest(args)

        assert result == 0  # still succeeds — deck is cataloged
```

**Step 2: Run tests to verify they pass**

These should pass immediately since the tag logic was included in Task 2's implementation. If not, fix accordingly.

Run: `venv/bin/python -m pytest tests/test_cli.py::TestIngestCommand -v`
Expected: All 8 tests PASS.

**Step 3: Run full test suite**

Run: `venv/bin/python -m pytest tests/ --ignore=tests/test_e2e_pipeline.py --ignore=tests/test_gateway_live.py -q`
Expected: All tests pass.

**Step 4: Commit**

```bash
git add tests/test_cli.py
git commit -m "test: add tag generation tests for cmd_ingest"
```

---

### Task 4: Manual smoke test + final cleanup

**Files:**
- No code changes expected

**Step 1: Test basic ingest (no tags)**

Run: `venv/bin/python outline2ppt.py ingest --help`
Expected: Help text showing all flags with descriptions.

**Step 2: Run full unit test suite**

Run: `venv/bin/python -m pytest tests/ --ignore=tests/test_e2e_pipeline.py --ignore=tests/test_gateway_live.py -q`
Expected: All tests pass.

**Step 3: Commit any cleanup if needed**

If no cleanup is needed, this task is complete.
