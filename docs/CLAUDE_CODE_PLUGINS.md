# Claude Code plugins for this repo

Project-level plugins are declared in `.claude/settings.json` (`extraKnownMarketplaces` + `enabledPlugins`). Trust the folder in Claude Code and the plugins install on their own.

- **ponytail** (`ponytail@ponytail`, from `DietrichGebert/ponytail`): token-saving skills, e.g. `/ponytail`, `/ponytail-review`, `/ponytail-audit`.
- **caveman** (`caveman@caveman`, from `JuliusBrussee/caveman`): terse-output skills, e.g. `/caveman`, `/caveman-commit`.

Not enabled here: context-mode (analytics not confirmed off) and rtk (needs a global hook outside the repo).
