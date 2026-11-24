import json
from pathlib import Path

import pytest

CLAUDE_MANIFESTS = sorted((Path(__file__).parent.parent / "claude-skills").glob("*/.claude-plugin/plugin.json"))


# Kiro reads `plugin.json` and Claude Code reads `.claude-plugin/plugin.json`, so a version bump must change both.
@pytest.mark.parametrize("claude_manifest", CLAUDE_MANIFESTS, ids=lambda p: p.parent.parent.name)
def test_kiro_manifest_matches_claude_manifest(claude_manifest: Path) -> None:
    claude = json.loads(claude_manifest.read_text())
    kiro = json.loads((claude_manifest.parent.parent / "plugin.json").read_text())

    assert (kiro["name"], kiro["version"]) == (claude["name"], claude["version"])
