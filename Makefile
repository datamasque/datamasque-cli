.PHONY: install lint format mypy test test-integration test-integration-local check build release-patch release-minor release-major

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

release-patch:
	@sh scripts/release.sh patch

release-minor:
	@sh scripts/release.sh minor

release-major:
	@sh scripts/release.sh major
