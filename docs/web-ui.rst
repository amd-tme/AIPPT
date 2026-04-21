Web UI Guide
============

AIPPT includes a web-based interface for browsing, searching, and managing
your slide library. It is built with FastAPI, htmx, and Pico CSS.

Launching the Server
--------------------

Start the web UI::

    python aippt.py serve --port 8000

Open ``http://localhost:8000`` in your browser.

Options:

- ``--port N`` -- Port number (default: ``8000``)
- ``--gateway-config PATH`` -- Gateway config for LLM access
- ``--uploads-dir DIR`` -- Directory for uploaded files (default: ``uploads``)
- ``--view-only`` -- Disable LLM features (auto-detected when no gateway/API keys)

Deck List
---------

The default view shows all cataloged decks in a table with columns for deck
name, slide count, author, creation date, and modified date.

From the deck list you can:

- **Click a deck name** to browse its slides
- **Upload** a new PowerPoint file (click the upload button)
- **Download** the original ``.pptx`` file
- **Write Notes to Deck** -- push database notes back into the PPTX file
  (creates a ``.pptx.bak`` backup first)

Slide Browser
-------------

Clicking a deck shows its slides as a grid of thumbnail cards. Each card
displays the slide image (if available), title, and tags.

**Detail modal**: Click any slide card to open a full-size detail view showing:

- Slide image
- Title and section
- Content text
- Speaker notes (editable)
- Tags (with add/remove controls)
- Metadata (author, creation date, slide position)

**Navigation**: Use the next/prev buttons or left/right arrow keys to move
between slides. The modal header shows your position (e.g. "3 of 15").

Search
------

Click **Search** in the nav bar to open the search view.

- **Title search** -- Filter slides by title substring
- **Tag search** -- Filter by one or more tags (comma-separated)

Results appear as slide cards. Click any result to open the detail modal.

Tag Sidebar
-----------

Click the **Tags** button in the nav bar to toggle the tag sidebar. The
sidebar displays all tags grouped by category, with slide counts.

- Click a tag to filter slides across all decks
- Select multiple tags for AND filtering (only slides with *all* selected tags
  are shown)
- Click **Clear all** to reset the tag filter

The sidebar state (open/closed) is saved in ``localStorage`` and persists
across page loads.

Notes Editing
-------------

Speaker notes can be edited directly in the slide detail modal:

1. Click into the notes text area
2. Edit the notes content
3. Click **Save** or press **Ctrl+S** / **Cmd+S**
4. Click **Cancel** to discard changes

A dirty-state indicator warns you of unsaved changes. The notes history panel
shows previous versions with timestamps (accessible below the notes editor).

Notes can be written back to the original PPTX file using the **Write Notes to
Deck** button in the deck list.

Settings
--------

Click **Settings** in the nav bar to access configuration:

- **Models** -- View and change default models for each operation (enhance,
  improve, feedback, notes, tags, image)
- **Template** -- Set the default PowerPoint template path
- **Taxonomy** -- Manage the taxonomy of predefined tags (add, remove, import,
  export)

Creating Presentations
----------------------

The web UI supports creating presentations from markdown outlines:

1. Click the **Create** section in the deck list view
2. Paste markdown text or upload a ``.md`` file
3. Toggle **Enhanced mode** for AI-powered layout selection and speaker notes
4. Select a model (when enhanced mode is on)
5. Click **Create** to generate the deck

Progress is streamed in real time via SSE.

View-Only Mode
--------------

When no LLM gateway or API keys are configured, the web UI automatically
enters **Library Mode** (view-only). This can also be forced with
``--view-only``.

In view-only mode:

- Browsing, searching, tagging, and downloading all work normally
- LLM-dependent features (enhance, analyze, improve, AI tagging) are disabled
  and show "LLM not configured" tooltips
- A "Library Mode" badge appears in the nav bar
- Upload still works (cataloging doesn't require an LLM)

This mode is ideal for deploying a shared, read-only slide library (e.g. via
the :doc:`backup/restore workflow <backup-restore>`).

Export CSV
----------

Click **Export CSV** in the nav bar to download a CSV file containing metadata
for all cataloged slides (title, notes, tags, deck name, image path, etc.).
