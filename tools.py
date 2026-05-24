"""Tool handlers — bumblebee scan / refresh / status."""

from __future__ import annotations

import json
import time
from pathlib import Path

from .lib import catalog as cat_mod
from .lib import runner
from .lib.findings import summarize_findings


def _hermes_home() -> Path:
    """Resolve the active hermes profile home directory."""
    try:
        from hermes_constants import get_hermes_home  # type: ignore
        return Path(get_hermes_home())
    except Exception:
        # Fallback for tests / standalone use
        import os
        return Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes")))


def bumblebee_scan(args: dict, **kwargs) -> str:
    """Run a one-shot scan against the local catalog set."""
    if not runner.is_available():
        return json.dumps({
            "error": "bumblebee binary not installed",
            "hint": "Install with: go install github.com/perplexityai/bumblebee/cmd/bumblebee@latest",
        })

    profile = args.get("profile", "baseline")
    roots = args.get("roots") or []
    ecosystems = args.get("ecosystems") or []
    max_duration = args.get("max_duration", "5m")

    if profile in ("project", "deep") and not roots:
        return json.dumps({
            "error": f"profile={profile} requires explicit roots",
            "hint": "Pass roots=['~/code', '~/src', ...]",
        })

    cat_dir = cat_mod.catalog_dir(_hermes_home())
    cat_inv = cat_mod.inventory(cat_dir)
    if not cat_inv:
        return json.dumps({
            "error": "no exposure catalogs loaded",
            "hint": "Run bumblebee_refresh_catalogs first.",
        })

    try:
        records, summary, stderr = runner.run_scan(
            profile=profile,
            roots=[str(Path(r).expanduser()) for r in roots],
            ecosystems=ecosystems,
            exposure_catalog=cat_dir,
            findings_only=True,
            max_duration=max_duration,
            timeout=900,
        )
    except runner.BumblebeeNotInstalled as exc:
        return json.dumps({"error": str(exc)})
    except Exception as exc:
        return json.dumps({"error": f"scan failed: {type(exc).__name__}: {exc}"})

    fsum = summarize_findings(records)

    # Persist last-scan state
    try:
        state_path = cat_mod.state_dir(_hermes_home()) / "last-scan.json"
        state_path.write_text(json.dumps({
            "ts": time.time(),
            "profile": profile,
            "roots": roots,
            "ecosystems": ecosystems,
            "summary": summary,
            "findings": fsum,
        }, indent=2), encoding="utf-8")
    except OSError:
        pass

    return json.dumps({
        "profile": profile,
        "status": summary.get("status", "complete"),
        "files_considered": summary.get("files_considered"),
        "duration_ms": summary.get("duration_ms"),
        "catalogs_used": len(cat_inv),
        "findings": fsum,
    }, indent=2)


def bumblebee_refresh_catalogs(args: dict, **kwargs) -> str:
    """Pull latest exposure catalogs from upstream."""
    cat_dir = cat_mod.catalog_dir(_hermes_home())
    try:
        delta = cat_mod.refresh(cat_dir)
    except Exception as exc:
        return json.dumps({"error": f"refresh failed: {type(exc).__name__}: {exc}"})

    inv = cat_mod.inventory(cat_dir)
    total_entries = sum(c["entries"] for c in inv)
    return json.dumps({
        "status": "ok",
        "added": delta["added"],
        "updated": delta["updated"],
        "removed": delta["removed"],
        "total_catalogs": delta["total_after"],
        "total_advisory_entries": total_entries,
    }, indent=2)


def bumblebee_status(args: dict, **kwargs) -> str:
    """Report binary version, catalog inventory, last scan."""
    home = _hermes_home()
    cat_dir = cat_mod.catalog_dir(home)
    inv = cat_mod.inventory(cat_dir)
    freshness = cat_mod.freshness_seconds(cat_dir)

    last_scan_path = cat_mod.state_dir(home) / "last-scan.json"
    last_scan = None
    if last_scan_path.exists():
        try:
            last_scan = json.loads(last_scan_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass

    out = {
        "binary": {
            "installed": runner.is_available(),
            "version": runner.version(),
            "path": runner.find_binary(),
        },
        "catalogs": {
            "directory": str(cat_dir),
            "count": len(inv),
            "total_entries": sum(c["entries"] for c in inv),
            "freshness_seconds": freshness,
            "items": [{"name": c["name"], "entries": c["entries"]} for c in inv],
        },
        "last_scan": (
            {
                "ts": last_scan["ts"],
                "age_seconds": time.time() - last_scan["ts"],
                "profile": last_scan.get("profile"),
                "findings_count": last_scan.get("findings", {}).get("count", 0),
            }
            if last_scan else None
        ),
    }
    return json.dumps(out, indent=2)
