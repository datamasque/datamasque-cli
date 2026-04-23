# Claude Code skills

- **`datamasque-cli/`** — teaches Claude how to operate a DataMasque
  instance via the `dm` command (authenticate, list connections,
  start runs, fetch discovery reports).
- **`ruleset-builder/`** — turns auto-generated rulesets into
  production-ready ones (extracts a `ruleset_library`, adds
  `hash_columns`, applies `skip_defaults`, validates).
- **`ruleset-splitter/`** — joins DataMasque's many-file generated
  rulesets into one file for editing, then re-splits back to the
  original filenames.

## Install

Each directory is a bare skill (`SKILL.md` at its root).
[Claude Code](https://claude.com/claude-code) auto-discovers anything under
`~/.claude/skills/<name>/`, so install by symlinking both skills in:

```bash
ln -sfn ~/repos/datamasque-cli/claude-skills/datamasque-cli \
  ~/.claude/skills/datamasque-cli

ln -sfn ~/repos/datamasque-cli/claude-skills/ruleset-builder \
  ~/.claude/skills/ruleset-builder

ln -sfn ~/repos/datamasque-cli/claude-skills/ruleset-splitter \
  ~/.claude/skills/ruleset-splitter
```

Then reload inside Claude Code:

```
/reload-plugins
```

(or start a new session)

Edits to either `SKILL.md` go live on next reload — no reinstall.

## Uninstall

```bash
rm ~/.claude/skills/datamasque-cli
rm ~/.claude/skills/ruleset-builder
rm ~/.claude/skills/ruleset-splitter
```
