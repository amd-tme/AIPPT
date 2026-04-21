# Error Recovery for /edit-deck

## Script Execution Failure

When `run_script()` returns `success: False`:

### 1. Show the Error

```
Regeneration failed:
{stderr content}
```

### 2. Offer Recovery Options

```
The edited script failed to run. Options:
1. Restore from backup (.bak) and undo the edit
2. Let me try to fix the error
3. Show the full error output
```

### 3. Restore from Backup

```python
from aippt.source_resolver import restore_backup
restore_backup(script_path)
```

After restoring, the script is back to its pre-edit state. The `.bak` file is preserved so the user can restore again if a subsequent fix attempt also fails.

### 4. LLM Fix Attempt

Read the error output and the script. Common issues:
- **Syntax error:** Missing bracket, quote, or semicolon. Fix the specific line.
- **Undefined variable:** Typo in variable name or missing import.
- **Module not found:** Missing `require()` or `import`.

After fixing, run the script again. If it still fails, offer restore.

## File Lock Detection

When `run_script()` returns `file_locked: True`:

```
The PPTX file appears to be open in another application (likely PowerPoint).
Please close the file and try again.
```

Wait for user confirmation, then retry `run_script()`.

**Detection markers in stderr:**
- `PermissionError` (Python/Windows)
- `EBUSY` (Node/Linux)
- `being used by another process` (Windows)

## Missing Source Script

When `resolve_source()` returns an error:

| Error | User Message |
|-------|-------------|
| "No deck found" | "I couldn't find a deck matching '{name}'. Try a more specific name or provide the script path directly." |
| "Multiple decks" | Show the choices list and ask user to pick by ID |
| "No source script tracked" | "This deck doesn't have source tracking. You can: (1) provide the script path directly, (2) re-ingest with `aippt ingest deck.pptx --source output/deck.mjs`" |

## Script Not Found on Disk

If `resolve_source()` returns a `script_path` from the catalog but the file doesn't exist:

```
The catalog says the source script is at '{script_path}', but the file
doesn't exist. It may have been moved or deleted.

Options:
1. Provide the current script path
2. Search for .mjs/.py files in output/
```
