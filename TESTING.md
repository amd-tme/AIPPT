# Testing Guide - AIPPT v2

## Test Status
- **Total Tests**: 211 passing, 3 skipped
- **Test Coverage**: All modules have unit tests
- **Gateway Tests**: Skipped unless `AMD_LLM_KEY` env var is set

## Running Tests

```bash
# Activate virtual environment
source venv/Scripts/activate  # Windows Git Bash
# OR
source venv/bin/activate      # Linux/Mac

# Run all tests
pytest tests/ -v

# Run specific test module
pytest tests/test_catalog.py -v
pytest tests/test_analyze.py -v

# Run with coverage
pytest tests/ --cov=aippt --cov-report=html
```

## Manual Testing Guide

### 1. CLI Help & Documentation

```bash
# Main help
python aippt.py --help

# Subcommand help
python aippt.py create --help
python aippt.py reverse --help
python aippt.py catalog --help
python aippt.py analyze --help
python aippt.py search --help
python aippt.py remix --help
python aippt.py export --help
python aippt.py serve --help
```

### 2. Reverse Conversion (PowerPoint → Markdown)

**Basic conversion:**
```bash
python aippt.py reverse your-deck.pptx output.md
```

**Exclude speaker notes:**
```bash
python aippt.py reverse your-deck.pptx output.md --no-notes
```

**Expected output:** Markdown file with H1 headers for slide titles, bullet points for content.

### 3. Create Presentation (Markdown → PowerPoint)

**Prerequisites:**
- Markdown outline file with `# Title` for slides
- PowerPoint template file

**Basic creation:**
```bash
python aippt.py create outline.md template.pptx output.pptx
```

**With AI enhancement:**
```bash
python aippt.py create outline.md template.pptx output.pptx \
  --enhance \
  --model claude-3.5-sonnet
```

**Test mode (first N slides):**
```bash
python aippt.py create outline.md template.pptx output.pptx \
  --test 3 \
  --enhance
```

**Using gateway:**
```bash
# Ensure AMD_LLM_KEY is set
export AMD_LLM_KEY=your-key-here

python aippt.py create outline.md template.pptx output.pptx \
  --enhance \
  --model gpt-4o \
  --gateway-config gateway.yaml
```

### 4. Catalog Operations

**Catalog a deck:**
```bash
python aippt.py catalog your-deck.pptx --db slides.db
```

**Catalog with images directory:**
```bash
# First, export slides as PNG from PowerPoint to images/deck-name/
python aippt.py catalog your-deck.pptx \
  --images-dir images/deck-name \
  --db slides.db
```

**Expected output:**
- SQLite database created at `slides.db`
- Deck and slide metadata stored
- Content hashes computed for versioning

**Verify cataloging:**
```bash
# Use SQLite CLI to inspect
sqlite3 slides.db "SELECT * FROM decks;"
sqlite3 slides.db "SELECT id, position, title FROM slides LIMIT 10;"
```

### 5. Multimodal Analysis

**Prerequisites:**
- Deck must be cataloged
- Slide images exported to `images/deck-name/Slide1.png`, `Slide2.png`, etc.
  - In PowerPoint: File → Export → Change File Type → PNG
  - Save each slide as `Slide1.png`, `Slide2.png`, etc.

#### 5.1 Design Feedback

```bash
python aippt.py analyze your-deck.pptx \
  --mode feedback \
  --images-dir images/deck-name \
  --model gpt-4o
```

**Expected output:** Console feedback for each slide (3-5 bullet points per slide).

#### 5.2 Generate Speaker Notes

```bash
python aippt.py analyze your-deck.pptx \
  --mode notes \
  --images-dir images/deck-name \
  --model gpt-4o
```

**Expected output:**
- Console progress messages
- Notes written back into the PPTX file
- Open `your-deck.pptx` to verify notes in presenter view

#### 5.3 Auto-Tagging (Freeform)

```bash
python aippt.py analyze your-deck.pptx \
  --mode tags \
  --images-dir images/deck-name \
  --model gpt-4o
```

**Expected output:** Tags added to database, console shows tags per slide.

**Verify tags:**
```bash
sqlite3 slides.db "SELECT t.name, COUNT(*) as count FROM tags t JOIN slide_tags st ON t.id = st.tag_id GROUP BY t.name;"
```

#### 5.4 Auto-Tagging (Taxonomy-Constrained)

**Create taxonomy CSV:**
```csv
name,category
security,topic
cloud,topic
architecture,topic
aws,provider
azure,provider
diagram,content-type
code,content-type
```

```bash
python aippt.py analyze your-deck.pptx \
  --mode tags \
  --taxonomy taxonomy.csv \
  --images-dir images/deck-name \
  --model gpt-4o
```

**Expected output:** Only tags from taxonomy are applied.

### 6. Gateway Configuration

**Setup gateway.yaml:**
```yaml
gateway:
  base_url: "https://llm-api.amd.com"
  auth_header: "Ocp-Apim-Subscription-Key"
  auth_value_env: "AMD_LLM_KEY"
providers:
  anthropic:
    path: "/Anthropic"
  openai:
    path: "/OpenAI"
  google:
    path: "/VertexAI"
```

**Set environment variable:**
```bash
export AMD_LLM_KEY=your-key-here
```

**Test with different providers:**
```bash
# OpenAI via gateway
python aippt.py analyze deck.pptx --mode tags --model gpt-4o

# Anthropic via gateway
python aippt.py analyze deck.pptx --mode tags --model claude-3.5-sonnet

# Google via gateway
python aippt.py analyze deck.pptx --mode tags --model gemini-2.0-flash
```

### 7. Database Inspection

**View all decks:**
```bash
sqlite3 slides.db "SELECT id, name, slide_count, updated_at FROM decks;"
```

**View slides for a deck:**
```bash
sqlite3 slides.db "SELECT position, title FROM slides WHERE deck_id = 1;"
```

**View tags:**
```bash
sqlite3 slides.db "SELECT t.name, COUNT(*) as count FROM tags t JOIN slide_tags st ON t.id = st.tag_id GROUP BY t.name ORDER BY count DESC;"
```

**View tagged slides:**
```bash
sqlite3 slides.db "
SELECT s.position, s.title, GROUP_CONCAT(t.name, ', ') as tags
FROM slides s
JOIN slide_tags st ON s.id = st.slide_id
JOIN tags t ON st.tag_id = t.id
WHERE s.deck_id = 1
GROUP BY s.id
ORDER BY s.position;
"
```

## Common Issues & Troubleshooting

### Issue: "No module named 'aippt'"

**Solution:** Ensure you're in the project directory and virtual environment is activated.

### Issue: "Images directory not found"

**Solution:** Export slides from PowerPoint:
1. Open PowerPoint
2. File → Export → Change File Type → PNG
3. Save to `images/your-deck-name/`
4. Ensure files are named `Slide1.png`, `Slide2.png`, etc.

### Issue: Gateway authentication fails

**Solution:**
- Verify `AMD_LLM_KEY` environment variable is set
- Check `gateway.yaml` configuration
- Ensure auth header name matches gateway requirements

### Issue: "Model does not support vision"

**Solution:** Use a vision-capable model for analyze command:
- `gpt-4o`, `gpt-4o-mini` (OpenAI)
- `claude-3.5-sonnet`, `claude-3.5-haiku` (Anthropic)
- `gemini-2.0-flash`, `gemini-2.5-pro` (Google)

### Issue: Tests fail with import errors

**Solution:**
```bash
# Reinstall dependencies
pip install -r requirements.txt

# Verify installation
python -c "import aippt; print(aippt.__version__)"
```

## Related Guides

- **UITESTING.md**: Manual validation walkthrough for export, search, remix, and web UI
- **CHANGELOG.md**: Version history in Keep a Changelog format
- **docs/plans/PRD-TEMPLATE.md**: Template for planning new features
