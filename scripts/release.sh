#!/usr/bin/env sh
# Cut a release by creating a tag only:
# the version is derived from the tag, so nothing is committed to main.
set -eu

level=${1:-patch}
git fetch --tags --quiet
latest=$(git describe --tags --abbrev=0 --match 'v*.*.*')

IFS=. read -r major minor patch <<EOF
${latest#v}
EOF

case "$level" in
  patch) patch=$((patch + 1)) ;;
  minor) minor=$((minor + 1)); patch=0 ;;
  major) major=$((major + 1)); minor=0; patch=0 ;;
  *) echo "usage: release.sh patch|minor|major" >&2; exit 1 ;;
esac

next="v$major.$minor.$patch"
printf 'Release %s (from %s)? This publishes to PyPI and cannot be undone. [y/N] ' "$next" "$latest"
read -r reply
case "$reply" in
  [yY]*) gh release create "$next" --generate-notes --target main ;;
  *) echo "Aborted." >&2; exit 1 ;;
esac
