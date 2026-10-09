# Claude Code plugins for this repo

Project-level plugins are declared in `.claude/settings.json` (`extraKnownMarketplaces` + `enabledPlugins`). Trust the folder in Claude Code and the plugin installs on its own.

- **ponytail** (`ponytail@ponytail`, from `DietrichGebert/ponytail`, MIT): a "lazy senior dev" skill set for smallest-change coding. Commands: `/ponytail`, `/ponytail-review`, `/ponytail-audit`, `/ponytail-debt`. It does not replace the "Ponytail Principle" section in `CLAUDE.md`; that section is the repo's own rule and still applies.

Not enabled here: caveman (deferred), context-mode (analytics not confirmed off; Elastic License 2.0), rtk (needs a global hook outside the repo).
