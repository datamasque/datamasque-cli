.PHONY: install lint format mypy test test-integration test-integration-local check build publish release-patch release-minor release-major

install:
	uv sync

lint:
	uv run ruff check src/ tests/

format:
	uv run ruff format src/ tests/
	uv run ruff check --fix --select I src/ tests/

mypy:
	uv run mypy src/

test:
	uv run pytest

test-integration:
	uv run pytest -m integration

# Run integration tests against the DataMasque instance in your active
# `~/.config/datamasque-cli/config.toml` profile. Saves typing DM_TEST_* env
# vars when smoke-testing a branch against your own dev instance.
test-integration-local:
	@eval "$$(python3 scripts/active_profile_env.py)" && uv run pytest -m integration

check: lint format-check mypy test

format-check:
	uv run ruff format --check src/ tests/

build:
	uv build

publish: check build
	uv publish --index datamasque-private-pypi -u "" -p "" dist/*

# Bump version, commit, tag, push — CI publishes automatically.
# Usage: make release-patch  (0.1.0 → 0.1.1)
#        make release-minor  (0.1.0 → 0.2.0)
#        make release-major  (0.1.0 → 1.0.0)
release-patch: check
	$(eval VERSION := $(shell python3 scripts/bump_version.py patch))
	uv lock
	git add pyproject.toml uv.lock
	git commit -m "Release v$(VERSION)"
	git tag "v$(VERSION)"
	git push && git push --tags
	@echo "Released v$(VERSION) — CI will publish to pypi.dtq.tools"

release-minor: check
	$(eval VERSION := $(shell python3 scripts/bump_version.py minor))
	uv lock
	git add pyproject.toml uv.lock
	git commit -m "Release v$(VERSION)"
	git tag "v$(VERSION)"
	git push && git push --tags
	@echo "Released v$(VERSION) — CI will publish to pypi.dtq.tools"

release-major: check
	$(eval VERSION := $(shell python3 scripts/bump_version.py major))
	uv lock
	git add pyproject.toml uv.lock
	git commit -m "Release v$(VERSION)"
	git tag "v$(VERSION)"
	git push && git push --tags
	@echo "Released v$(VERSION) — CI will publish to pypi.dtq.tools"
