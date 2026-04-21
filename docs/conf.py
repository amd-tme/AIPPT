# Configuration file for the Sphinx documentation builder.

project = "AIPPT"
copyright = "2026"
author = "Matt"

import os, sys
sys.path.insert(0, os.path.abspath(".."))
from aippt import __version__
version = __version__
release = __version__

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.viewcode",
    "sphinx_rtd_theme",
]

html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]

exclude_patterns = ["_build", "plans", "*.md"]
