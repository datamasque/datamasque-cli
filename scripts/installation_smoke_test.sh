#!/usr/bin/env bash
# Tests that the built wheel installs into a clean venv and `dm` runs,
# resolving from PyPI as a user does rather than from `uv.lock`,
# which pins transitive packages and so hides undeclared imports.
#
# Does not test:
#   - imports inside functions (deptry catches those)
#   - platforms or Pythons other than Linux and 3.11
#   - behaviour beyond startup
set -euo pipefail

VENV="$(mktemp -d)/smoke"

uv venv --python 3.11 "$VENV"
uv pip install --python "$VENV/bin/python" dist/*.whl
uv pip check --python "$VENV/bin/python"

# `dm --help` only imports what the entry path touches,
# so a module used by a single subcommand needs importing directly.
"$VENV/bin/python" -c '
import importlib
import pkgutil

import datamasque_cli

for module in pkgutil.walk_packages(datamasque_cli.__path__, "datamasque_cli."):
    importlib.import_module(module.name)
'

"$VENV/bin/dm" --help
