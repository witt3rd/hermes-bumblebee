---
name: triaging-supply-chain-finding
description: Triage a bumblebee supply-chain finding — verify the advisory, identify the on-disk artifact, quarantine, rotate any credentials in scope, and patch the lockfile.
when_to_use: A bumblebee scan returned count > 0, OR a user pastes a finding record asking what to do, OR a session-start banner flagged exposure.
---

# Triaging a supply-chain finding

A finding means **on-disk metadata matched an advisory entry**. It does not
mean the malicious code ran. It does not mean credentials are gone. It
means: **this exact package@version is named in a campaign, and your
machine has metadata for it on disk right now.**

The order below is shaped to answer *"how bad is this, and what's the
fastest containment?"* — not to investigate root cause first.

## 1. Verify the advisory

Don't trust the catalog blindly — catalogs are PR-contributed and can lag,
duplicate, or false-positive. Cross-check with one external source:

```
# The advisory_id or catalog name from the finding
gh search issues "<package@version>" --owner=<ecosystem-registry>
# Or the catalog's own source link (Socket, StepSecurity, Snyk)
```

Compare:
- **Package name** matches exactly (no typosquat near-miss like `node-ipc` vs `nodeipc`)
- **Version** is in the advisory's affected range (not just the bare package)
- **Ecosystem** matches (npm `node-ipc` ≠ PyPI `node-ipc`)

If verification fails — wrong package, wrong version, wrong ecosystem —
the catalog has a stale or bad entry. Open an issue upstream
(`perplexityai/bumblebee`) with the false match.

## 2. Identify the on-disk artifact

The finding record has a `file_path`. Three shapes:

| Path looks like... | Means |
|---|---|
| `~/.cache/.../package-lock.json` or `node_modules/.../package.json` | npm/pnpm/yarn — installed dependency |
| `~/.local/lib/python*/.../METADATA` | PyPI — installed Python package |
| `~/.config/Code/User/extensions/<id>/manifest.json` | Editor extension |
| `~/.config/<browser>/.../manifest.json` | Browser extension |
| `mcp.json` / `claude_desktop_config.json` | MCP server config (NOT installed code — just a configuration reference) |

MCP findings are **lower urgency**: nothing ran. Editor/browser extensions
and language packages are **higher urgency**: code is on disk and may have
been loaded.

## 3. Quarantine before remediation

Move the artifact aside before deleting — preserves evidence and lets you
roll back if verification turns out wrong.

```bash
mkdir -p ~/.hermes/state/bumblebee/quarantine/<date>/
mv <file_path>'s containing directory ~/.hermes/state/bumblebee/quarantine/<date>/
```

For npm: also delete the lockfile entry, not just `node_modules/`. The
lockfile pins the version; a reinstall will pull the same bytes back.

For editor/browser extensions: disable in the UI **and** remove from disk.
Just disabling leaves the malicious code on the filesystem.

## 4. Rotate credentials in the artifact's scope

This is the load-bearing step most people skip. Assume the malicious
version executed at install/load time and exfiltrated anything readable:

- **npm postinstall hooks** see your shell env at `npm install` time
- **VS Code / Cursor extensions** see workspace files, env vars, and the
  editor's own credentials (GitHub Copilot tokens, etc.)
- **Browser extensions** see the cookies and tabs of the profile they're in
- **MCP servers** see whatever the host config grants — env block,
  filesystem paths

Rotate based on what was in scope **when the artifact was installed or
last updated**, not just what's in scope now.

Bumblebee parses MCP host configs for inventory but does NOT emit the
`env` block contents — you have to read your own config to know what
credentials the MCP server saw.

## 5. Patch the lockfile / pin the next version

For each affected package, pin the next known-good version (from the
advisory's remediation field, or the registry's latest non-affected
version). Regenerate the lockfile from a clean cache.

```bash
# npm — wipe both cache and node_modules before reinstall
npm cache verify
rm -rf node_modules package-lock.json
npm install --package-lock-only
```

## 6. Re-scan to confirm clean

```
bumblebee_scan profile=baseline
```

Expected: `findings.count == 0`. If a finding persists, you missed an
artifact location (commonly: pnpm's `.pnpm/` store, a second profile,
a global install).

## 7. Document the incident

Write a brief in `~/.hermes/state/bumblebee/incidents/<date>-<package>.md`:

- Advisory ID and source link
- Package@version, ecosystem, on-disk path
- Quarantine timestamp
- Credentials rotated (which, to where, when)
- Lockfile diff (before → pinned version)
- Re-scan confirmation

This is for your future self in 3 months when an audit asks "did you
respond to GHSA-XXXX-XXXX-XXXX?"

## Pitfalls

- **MCP host configs are not installed code.** Don't quarantine your
  `claude_desktop_config.json` — read it, find the offending server entry,
  remove that entry only.
- **Lockfile-only fixes don't help if `node_modules/` is intact.** Wipe
  both, then reinstall.
- **Don't `git restore` the lockfile** — the affected version may still
  be in the cache. Use `npm cache verify` first.
- **Browser extension uninstall** through the UI is a soft delete on
  some browsers (state preserved for reinstall). Confirm the directory
  under `~/.config/<browser>/.../Extensions/<id>/` is actually gone.
