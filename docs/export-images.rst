Exporting Slides to Images
==========================

Several AIPPT features (e.g. ``analyze``, ``catalog --images-dir``) require
slide images exported as individual PNG files. AIPPT supports two paths:
PowerPoint COM automation on Windows, or Microsoft Graph on Linux
(``PPTX → SharePoint → PDF → pdftoppm → PNGs``).

Both paths produce files named ``Slide1.png`` / ``Slide2.png`` / etc.
in the output directory — the naming convention ``analyze`` and ``catalog``
expect when looking up slide images by position.

Choose the path that matches your host:

- **Windows with PowerPoint installed:** the bundled PowerShell script
  drives PowerPoint via COM. No network calls, no Microsoft Graph setup.
  See `Windows (PowerPoint COM)`_.
- **Linux / containerized deployments:** PowerPoint COM is unavailable.
  Use the Microsoft Graph pipeline. Requires a SharePoint staging library
  and a Graph access token. See `Linux (Microsoft Graph)`_.

Slide Thumbnails (Live Preview → Save)
--------------------------------------

The image-export paths above render a deck's slides on the **server**. Decks
created through **Live Preview → Save to Library** take a different, lighter
route that does **not** need PowerPoint, Microsoft Graph, or ``pdftoppm``:
the deck is already rendered in the browser by PptxViewJS, so on save each
slide is captured directly from the viewer canvas
(``renderSlide`` → ``canvas.toBlob``) and posted alongside the catalog request.

The server (``aippt.thumbnails``) stores each captured slide as
``Slide{N}.png`` in the deck's images directory — the same layout and naming
the catalog expects — wires it into ``slides.image_path``, and writes a
downscaled ``Slide{N}.thumb.jpg`` grid tier next to it. This *supplements* the
image-export pipeline rather than replacing it: server-side export remains the
path for uploaded decks and for full-resolution renders, while the
canvas-capture path exists so script/preview-origin decks get previews without
a Graph token.

Capture is best-effort. If the browser can't render a slide, or PptxViewJS is
unavailable, the save still succeeds and the deck simply keeps placeholder
cards — no error. Thumbnails are stored only on the writable data volume, so
the feature works under ``readOnlyRootFilesystem``.

Windows (PowerPoint COM)
------------------------

Prerequisites
^^^^^^^^^^^^^

- **Windows** with **Microsoft PowerPoint** installed (desktop version, not
  the web or Store versions).
- PowerShell 5.1+ (ships with Windows 10/11).

Quick Start
^^^^^^^^^^^

Using the CLI wrapper:

.. code-block:: bash

   # From the project root (Git Bash)
   venv/Scripts/python.exe aippt.py export-images deck.pptx images/deck-name/

Using PowerShell directly:

.. code-block:: powershell

   .\scripts\Export-SlidesToImages.ps1 -PptxPath deck.pptx -OutDir images\deck-name

Custom resolution (Windows only — the Linux path uses 150 dpi PDF
rasterisation):

.. code-block:: powershell

   .\scripts\Export-SlidesToImages.ps1 -PptxPath deck.pptx -OutDir images\deck-name -Width 2560 -Height 1440

The ``--width`` and ``--height`` flags on ``aippt export-images`` apply
only to the Windows path (default 1920x1080).

Linux (Microsoft Graph)
-----------------------

The Linux pipeline uploads the ``.pptx`` to a SharePoint staging library,
requests it back as a PDF via Graph's ``?format=pdf`` conversion, and
splits the PDF into per-slide PNGs with ``pdftoppm``.

Prerequisites
^^^^^^^^^^^^^

- ``poppler-utils`` installed for ``pdftoppm``. On Debian/Ubuntu::

    sudo apt install poppler-utils

- A SharePoint document library provisioned for staging. See the
  ``sharepoint-setup`` page (``docs/sharepoint-setup.md``) for the
  provisioning steps and how to find the site / drive IDs.
- ``gateway.yaml`` with a ``sharepoint:`` block populated. See
  :doc:`configuration` for the schema.
- A Microsoft Graph access token for the current user, supplied via the
  ``MS_ACCESS_TOKEN`` environment variable or the ``--ms-token`` flag.

Quick Start
^^^^^^^^^^^

.. code-block:: bash

   export MS_ACCESS_TOKEN='eyJ0eXAi...'    # Graph bearer for the current user
   venv/bin/python aippt.py export-images deck.pptx images/deck-name/

Or pass the token explicitly::

    venv/bin/python aippt.py export-images deck.pptx images/deck-name/ \
        --ms-token "$MS_ACCESS_TOKEN" --gateway-config gateway.yaml

The Linux pipeline scopes uploads to a per-user subfolder under the staging
library. Set ``AIPPT_USER_NTID`` to control the subfolder name (falls back
to the ``USER`` env var, then ``anonymous``). For multi-user CI runs, set
``AIPPT_USER_NTID`` explicitly.

How to obtain a token
~~~~~~~~~~~~~~~~~~~~~

The web UI captures a token via the in-browser Microsoft device-code flow
and uses it on each request. For the CLI, you need to obtain one out-of-band
— easiest path is to sign in via the web UI, then copy the bearer from your
browser's ``localStorage`` (``aippt_ms_token``) for use on the command line.
The token typically lives 60–90 minutes before refresh is required.

Output
------

Both paths produce ``Slide1.png``, ``Slide2.png``, etc. in the output
directory. The Linux Graph path renames ``pdftoppm``'s native output
(``slide-NN.png``) to the ``Slide{i}.png`` pattern for consistency with the
Windows COM output, so downstream commands (``analyze``, ``catalog``) can
match images by slide position regardless of which path produced them.

Typical Workflow
----------------

.. code-block:: bash

   # 1. Export slides as images (Windows path shown; Linux substitutes the
   #    env-var + venv/bin/python invocation from above)
   venv/Scripts/python.exe aippt.py export-images deck.pptx images/deck/

   # 2. Catalog the deck with image paths
   venv/Scripts/python.exe aippt.py catalog deck.pptx --images-dir images/deck/

   # 3. Run AI analysis using the images
   venv/Scripts/python.exe aippt.py analyze deck.pptx --mode feedback --images-dir images/deck/

Troubleshooting
---------------

.. list-table::
   :header-rows: 1
   :widths: 40 60

   * - Symptom
     - Fix
   * - ``New-Object: Cannot create COM object``
     - PowerPoint is not installed, or only the Store/web version is
       available. Install the desktop version. (Windows path only.)
   * - Orphaned ``POWERPNT.EXE`` process
     - The script cleans up COM references in a ``finally`` block, but if
       it crashes hard, kill the process manually via Task Manager.
       (Windows path only.)
   * - Images are blank or wrong size
     - Ensure the ``.pptx`` file is not corrupt. Try opening it in
       PowerPoint first.
   * - Permission error on output dir
     - Run PowerShell or your shell as your normal user (not Admin) and
       check folder permissions.
   * - ``SharePoint render config missing``
     - The ``sharepoint:`` block in ``gateway.yaml`` is absent or has
       placeholder values. See :doc:`configuration` and the
       ``sharepoint-setup`` page. (Linux path.)
   * - ``Microsoft sign-in required. Set MS_ACCESS_TOKEN or pass --ms-token``
     - No Graph token available. Export ``MS_ACCESS_TOKEN`` or pass
       ``--ms-token``. (Linux path.)
   * - ``pdftoppm: command not found`` / ``FileNotFoundError`` for pdftoppm
     - ``poppler-utils`` not installed. ``sudo apt install poppler-utils``
       on Debian/Ubuntu, or the equivalent for your distribution.
       (Linux path.)
   * - Graph 401 / token expired
     - The Microsoft Graph token has expired (typical lifetime 60–90 min).
       Obtain a fresh one and retry. (Linux path.)
   * - Graph 403 on the SharePoint upload
     - The signed-in user lacks write access to the staging library. Check
       SharePoint permissions or the configured ``sharepoint.render_drive_id``.
       (Linux path.)
