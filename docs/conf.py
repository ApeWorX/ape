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
from functools import lru_cache
from pathlib import Path
from typing import List

import requests
from packaging.version import Version

sys.path.insert(0, os.path.abspath(".."))

# -- Project information -----------------------------------------------------

project = "ape"
copyright = "2023, ApeWorX LTD"
author = "ApeWorX Team"
extensions = [
    "myst_parser",
    "sphinx_click",
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.napoleon",
    "sphinx_rtd_theme",
    "sphinx_plausible",
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

# Configure Pluasible
plausible_domain = "docs.apeworx.io"

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

# Set some default to avoid unnecessary repetitious directives.
autodoc_default_options = {
    "exclude-members": "__repr__,__weakref__,__metaclass__,__init__,model_config,model_fields,model_post_init"
}


def fixpath(path: str) -> str:
    """
    Change paths to reference the resources from 'latest/' to save room.
    """
    suffix = path.split("_static")[1]
    new = f"/{project}/latest/_static"

    if suffix:
        new = str(Path(new) / suffix.lstrip("/"))

    return new


@lru_cache(maxsize=None)
def get_versions() -> List[str]:
    """
    Get all the versions from the Web.
    """
    api_url = "https://api.github.com/repos/ApeWorx/ape/git/trees/gh-pages?recursive=1"
    response = requests.get(api_url)
    response.raise_for_status()
    pattern = re.compile(r"v\d+.?\d+.?\d+$")
    data = response.json()
    tree = data.get("tree", [])
    versions = list({x["path"] for x in tree if x["type"] == "tree" and pattern.match(x["path"])})
    sorted_version_objs = sorted([Version(v.lstrip("v")) for v in versions], reverse=True)
    return [f"v{x}" for x in sorted_version_objs]


def setup(app):
    from ape import project

    # Disable accessing contracts via __getattr__
    # For ease of sphinx.
    project._getattr_contracts = False


html_context = {
    "fixpath": fixpath,
    "get_versions": get_versions,
    "display_github": True,
    "github_user": "ApeWorX",
    "github_repo": "ape",
    "github_version": "main",
    "conf_py_path": "/docs/",
}
