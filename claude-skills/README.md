# Claude Code skills

- **`datamasque-cli/`** —
teaches Claude how to operate a DataMasque instance with `dm`:
  - authenticate,
  - list connections,
  - start runs,
  - fetch discovery reports.
- **`ruleset-builder/`** —
turns auto-generated rulesets into production-ready ones:
  - extracts a `ruleset_library`,
  - adds `hash_columns`,
  - applies `skip_defaults`,
  - validates.
- **`ruleset-splitter/`** —
joins DataMasque's many-file generated rulesets into one file for editing, then re-splits back to the original filenames.

## Install

In [Claude Code](https://claude.com/claude-code), add this repo as a plugin marketplace and install the plugins you want:

```
/plugin marketplace add datamasque/datamasque-cli
/plugin install datamasque-cli@datamasque-tools
/plugin install ruleset-builder@datamasque-tools
/plugin install ruleset-splitter@datamasque-tools
```

## Uninstall

```
/plugin uninstall datamasque-cli@datamasque-tools
/plugin uninstall ruleset-builder@datamasque-tools
/plugin uninstall ruleset-splitter@datamasque-tools
```

## Working on these skills locally

If you're editing these skills in-repo and want Claude Code to pick up changes without reinstalling, symlink each directory into `~/.claude/skills/`:

```bash
ln -sfn ~/repos/datamasque-cli/claude-skills/datamasque-cli \
  ~/.claude/skills/datamasque-cli

ln -sfn ~/repos/datamasque-cli/claude-skills/ruleset-builder \
  ~/.claude/skills/ruleset-builder

ln -sfn ~/repos/datamasque-cli/claude-skills/ruleset-splitter \
  ~/.claude/skills/ruleset-splitter
```

Reload inside Claude Code (`/reload-plugins` or start a new session). Edits to any `SKILL.md` go live on the next reload — no reinstall.

Remove the symlinks when done:

```bash
rm ~/.claude/skills/datamasque-cli
rm ~/.claude/skills/ruleset-builder
rm ~/.claude/skills/ruleset-splitter
```
