Backup & Restore
================

AIPPT includes ``backup.sh`` and ``restore.sh`` scripts for backing up your
slide library and deploying it to other machines.

backup.sh
---------

Two modes are available: **copy** (default) and **export**.

Copy Mode
^^^^^^^^^

Creates a local backup directory with a copy of the database and working
directories::

    ./backup.sh

This copies into ``backup/``:

- ``slides.db`` -- the SQLite database
- ``dbinfo.txt`` and ``dbinfo.json`` -- database statistics
- ``outlines/``, ``output/``, ``templates/``, ``uploads/`` -- working directories
  (if they exist)

Export Mode
^^^^^^^^^^^

Creates a portable ``.tar.gz`` archive suitable for transferring to another
machine::

    ./backup.sh --export

The archive is saved to ``backups/aippt-export-YYYY-MM-DD.tar.gz`` and
contains:

- ``slides.db`` -- the database (with paths migrated to relative)
- ``dbinfo.json`` -- database statistics snapshot
- ``dirs.yaml`` -- directory configuration (if it exists)
- ``images/`` -- exported slide images
- ``uploads/`` -- uploaded PowerPoint files

Before archiving, the script runs ``migrate-paths`` to convert any absolute
database paths to relative paths, ensuring portability.

restore.sh
-----------

Import an export archive and set up a working library directory::

    ./restore.sh archive.tar.gz [target-dir]

Arguments:

- ``archive.tar.gz`` -- The archive file created by ``backup.sh --export``
- ``target-dir`` -- Where to extract (default: current directory)

The restore script:

1. Validates the archive format
2. Extracts to the target directory
3. Verifies ``slides.db`` exists in the extracted files
4. Creates a default ``dirs.yaml`` if one wasn't in the archive
5. Prints a summary of restored decks, slides, and directory sizes

After restoring, start the server::

    cd target-dir
    python aippt.py serve

Workflow: Team Sharing
----------------------

A typical workflow for sharing a slide library with your team:

1. **On your workstation** -- ingest decks, run analysis, add tags::

    python aippt.py ingest deck1.pptx --tags
    python aippt.py ingest deck2.pptx --tags
    python aippt.py analyze deck1.pptx --mode notes --images-dir images/deck1/

2. **Export** the library::

    ./backup.sh --export

3. **Transfer** the archive to the shared server::

    scp backups/aippt-export-2026-03-05.tar.gz server:/opt/aippt/

4. **Restore** on the server::

    cd /opt/aippt
    ./restore.sh aippt-export-2026-03-05.tar.gz

5. **Launch** in view-only mode::

    python aippt.py serve --port 8000 --view-only

Team members can now browse the slide library at ``http://server:8000`` without
needing LLM API keys.
