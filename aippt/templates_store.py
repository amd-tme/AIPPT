"""Restore the corporate PPTX template from object storage on startup.

The corporate template is a proprietary binary kept out of git (``.gitignore``
excludes ``*.pptx`` and ``templates/``). In object-storage (``s3``) mode it is
the durable source of truth under ``templates/corp.pptx``; on a cold pod the app
restores it into the writable data volume before serving, mirroring the catalog
snapshot/restore in ``catalog.py``.

Filesystem (``fs``) mode never calls this -- the template already lives at its
local path. All operations are best-effort: a storage hiccup is logged and
``False`` is returned so the caller can fall back to a template already on disk,
never breaking startup.
"""
from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from aippt.storage import Storage

logger = logging.getLogger(__name__)

# Object-storage key for the corporate template (relative to the storage prefix,
# e.g. asic/aippt/templates/corp.pptx in production).
TEMPLATE_SNAPSHOT_KEY = "templates/corp.pptx"


def restore_template(
    local_path: str, storage: "Storage", key: str = TEMPLATE_SNAPSHOT_KEY
) -> bool:
    """Restore the corporate template from *storage* into *local_path*.

    Returns True if the object was found and written, False if it is absent or a
    backend error occurred (best-effort -- callers fall back to a baked/local
    template). Parent directories are created as needed and an existing local
    file is overwritten.
    """
    try:
        if not storage.exists(key):
            logger.info("No corporate template at %s; nothing to restore", key)
            return False
        data = storage.get(key)
    except Exception:
        logger.exception("Corporate template restore from object storage failed")
        return False

    os.makedirs(os.path.dirname(os.path.abspath(local_path)), exist_ok=True)
    with open(local_path, "wb") as fh:
        fh.write(data)
    logger.info("Corporate template restored from %s (%d bytes)", key, len(data))
    return True
