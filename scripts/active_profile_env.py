#!/usr/bin/env python3
"""Emit `export DM_TEST_*=value` lines from the active profile in
`~/.config/datamasque-cli/config.toml`.

Intended to be eval'd by `make test-integration-local` so the integration
suite picks up whatever instance the operator is already logged into.
"""

from __future__ import annotations

import os
import sys

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]

path = os.path.expanduser("~/.config/datamasque-cli/config.toml")

try:
    data = tomllib.loads(open(path).read())
except FileNotFoundError:
    sys.exit(f"No profile config at {path}. Run 'dm auth login' first.")

profile = data["profiles"][data["active_profile"]]
print(f"export DM_TEST_URL={profile['url']!r}")
print(f"export DM_TEST_USERNAME={profile['username']!r}")
print(f"export DM_TEST_PASSWORD={profile['password']!r}")
