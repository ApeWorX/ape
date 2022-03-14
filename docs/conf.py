#
# Configuration file for the Sphinx documentation builder.
#
# This file does only contain a selection of the most common options. For a
# full list see the documentation:
# https://www.sphinx-doc.org/en/master/config
# -- Path setup --------------------------------------------------------------
# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.
#
import os
import re
import sys
from pathlib import Path
from typing import List

sys.path.insert(0, os.path.abspath(".."))

# -- Project information -----------------------------------------------------

project = "ape"
copyright = "2021, ApeWorX LTD"
author = "ApeWorX Team"
extensions = [
    "myst_parser",
    "sphinx_click",
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.napoleon",
    "sphinx_rtd_theme",
]
autosummary_generate = True

# Add any paths that contain templates here, relative to this directory.
templates_path = ["_templates"]

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path.
exclude_patterns: List[str] = ["_build", ".DS_Store"]


# The suffix(es) of source filenames.
# You can specify multiple suffix as a list of string:
source_suffix = [".rst", ".md"]

# The master toctree document.
master_doc = "index"


# -- Options for HTML output -------------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
#
html_theme = "sphinx_rtd_theme"
html_favicon = "favicon.ico"
html_logo = "logo.gif"
html_baseurl = "/ape/"

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ["_static"]

# These paths are either relative to html_static_path
# or fully qualified paths (eg. https://...)
html_css_files = ["custom.css"]

# Currently required for how we handle method docs links in the Myst parser
# since not all links are available in the markdown files pre-build.
myst_all_links_external = True


def fixpath(path: str) -> str:
    """
    Change paths to reference the resources from 'latest/' to save room.
    """
    suffix = path.split("_static")[1]
    new = f"/{project}/latest/_static"

    if suffix:
        new = str(Path(new) / suffix.lstrip("/"))

    return new


def get_versions() -> List[str]:
    build_dir = Path(__file__).parent / "_build" / "ape"
    if not build_dir.exists():
        return []

    versions = [
        d.name
        for d in build_dir.iterdir()
        if d.is_dir
        and re.match(r"v\d+.?\d?.?\d?", d.stem)
        and "beta" not in d.name
        and "alpha" not in d.name
    ]

    return versions


html_context = {
    "fixpath": fixpath,
    "get_versions": get_versions,
}
