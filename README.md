# hermes-bumblebee

Supply-chain exposure scanning for [Hermes Agent](https://github.com/NousResearch/hermes-agent), built on Perplexity's [bumblebee](https://github.com/perplexityai/bumblebee).

Checks on-disk package, extension, and developer-tool metadata against curated advisory catalogs — Shai-Hulud npm/PyPI worm, Laravel-Lang Composer compromise, Nx Console VS Code extension, node-ipc credential stealer, GemStuffer RubyGems, and ongoing campaigns updated upstream.

**Read-only.** Does not execute package managers (`npm ls`, `pip show`, `go list`). Does not read source files. Does not emit env values from MCP host configs.

## What you get

Three tools, one hook, one skill:

| Surface | Behavior |
|---|---|
| `bumblebee_scan` | Run a scan against the local catalog set. Profiles: `baseline` (system-wide), `project` (workspace roots), `deep` (explicit `--root` paths). Returns finding summary; clean returns `count=0`. |
| `bumblebee_refresh_catalogs` | Pull the latest exposure catalogs from `perplexityai/bumblebee/threat_intel/` via sparse git clone. |
| `bumblebee_status` | Read-only: binary version, catalog inventory + freshness, last-scan summary. |
| `on_session_start` hook | Opportunistic background baseline scan (silent unless findings). Refreshes catalogs if older than 24h, scans if last run was >6h ago. Never blocks session start. |
| `triaging-supply-chain-finding` skill | Triage playbook: verify advisory → quarantine artifact → rotate credentials → patch lockfile → confirm clean. |

## Prerequisites

You need the `bumblebee` binary on `PATH`. The plugin gates tools on its presence — if it's missing, tools are hidden and the hook is a no-op.

```bash
# Install Go 1.25+ (Arch: pacman -S go; macOS: brew install go)
go install github.com/perplexityai/bumblebee/cmd/bumblebee@latest

# Ensure $GOBIN (or ~/go/bin) is on PATH, then verify:
bumblebee version
bumblebee selftest
```

Bumblebee supports **macOS and Linux** developer endpoints. No Windows support upstream.

## Install

```bash
hermes plugins install witt3rd/hermes-bumblebee
hermes plugins enable bumblebee
```

Verify:

```
/plugins
# → ✓ bumblebee v0.1.0 (3 tools, 1 hooks)
```

In a fresh Hermes session:

```
What supply-chain scanning is in place?
# → model calls bumblebee_status, reports binary version + catalog inventory

Are we exposed to the Shai-Hulud npm worm?
# → model calls bumblebee_scan profile=baseline, reports clean or finding count
```

## State layout

The plugin writes state under the active Hermes profile:

```
<HERMES_HOME>/state/bumblebee/
├── catalogs/                  # exposure catalogs (synced from upstream)
│   ├── antv-mini-shai-hulud.json
│   ├── gemstuffer.json
│   └── ...
└── last-scan.json             # most recent scan summary
```

Nothing is written outside `<HERMES_HOME>`.

## Scheduled scans via Hermes cron

For continuous monitoring, schedule a silent watchdog. The job stays quiet on clean runs and only delivers when findings appear:

```bash
hermes cron create \
  --name "bumblebee-watch" \
  --schedule "every 6h" \
  --no-agent \
  --script ~/.hermes/plugins/bumblebee/scripts/cron-watchdog.sh
```

A reference `scripts/cron-watchdog.sh` is bundled in this repo — copy or symlink it.

## How catalog updates work

Catalogs are PR-contributed to `perplexityai/bumblebee/threat_intel/`. The plugin pulls the latest set via a sparse git clone (no full checkout) into `<HERMES_HOME>/state/bumblebee/catalogs/`. The `on_session_start` hook refreshes opportunistically; you can also trigger a refresh manually via `bumblebee_refresh_catalogs`.

If a catalog entry is stale or a false positive, open an issue against `perplexityai/bumblebee` — not this repo.

## Security model

- **No source-file reads.** Only on-disk metadata (lockfiles, manifest.json, *.dist-info, etc.).
- **No package-manager execution.** Pure on-disk parsing.
- **No credential emission.** MCP host configs are parsed for inventory; the `env` block is not read.
- **All scans run as the current user.** Bumblebee never asks for elevation.
- **Plugin code is gated.** Tools are hidden when the binary is absent. Catalog refresh and scan tools require user approval per Hermes's standard tool approval flow.

## License

MIT. See [LICENSE](LICENSE).

## Acknowledgments

- [perplexityai/bumblebee](https://github.com/perplexityai/bumblebee) — the binary and the curated threat catalogs. The hard work is theirs.
- [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) — the host.
