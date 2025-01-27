#!/usr/bin/env python

print(__package__)
print(__name__)

import re

match: re.Match | None = re.search(r'/(ape_\w+)/', __file__)
envprefix: str = f'{match.group(1).upper()}_' if match else 'APE_'
print(envprefix)
