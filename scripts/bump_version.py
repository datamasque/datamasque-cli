#!/usr/bin/env python3
"""Bump the version in pyproject.toml and print the new version."""

from __future__ import annotations

import re
import sys

LEVEL = sys.argv[1] if len(sys.argv) > 1 else "patch"

with open("pyproject.toml") as f:
    content = f.read()

match = re.search(r'version = "(\d+)\.(\d+)\.(\d+)"', content)
if not match:
    print("Could not find version in pyproject.toml", file=sys.stderr)
    sys.exit(1)

major, minor, patch = int(match.group(1)), int(match.group(2)), int(match.group(3))

if LEVEL == "patch":
    patch += 1
elif LEVEL == "minor":
    minor += 1
    patch = 0
elif LEVEL == "major":
    major += 1
    minor = 0
    patch = 0
else:
    print(f"Unknown level: {LEVEL}. Use patch, minor, or major.", file=sys.stderr)
    sys.exit(1)

new_version = f"{major}.{minor}.{patch}"
new_content = content.replace(match.group(0), f'version = "{new_version}"')

with open("pyproject.toml", "w") as f:
    f.write(new_content)

print(new_version)
