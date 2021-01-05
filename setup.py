#!/usr/bin/env python
from setuptools import find_packages, setup


extras_require = {
    "lint": [
        "black",
    ],
}
extras_require["dev"] = [
    "IPython",
] + extras_require["lint"]

setup(
    name="ape",
    version="0.0.0-alpha.0",
    description="",
    long_description="",
    url="https://apeworx.io",
    author="ApeWorX Team",
    author_email="admin@apeworx.io",
    packages=find_packages(),
    install_requires=[
        "click>=7.1.2",
    ],
    entry_points={
        "console_scripts": ["ape=ape._cli.__init__:cli"],
    },
    include_package_data=True,
    python_requires=">=3.6,<4",
    extras_require=extras_require,
    classifiers=["Development Status :: 1 - Planning"],
)
