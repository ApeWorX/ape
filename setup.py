#!/usr/bin/env python
from setuptools import setup


extras_require = {
    "lint": [
        "black",
    ],
}
extras_require["dev"] = [
    "IPython",
] + extras_require["lint"]

setup(
    name="apeworx",
    version="0.0.0-alpha.0",
    description="",
    long_description="",
    url="https://apeworx.io",
    author="ApeWorX Team",
    author_email="admin@apeworx.io",
    packages=[],
    extras_require=extras_require,
    classifiers=["Development Status :: 1 - Planning"],
)
