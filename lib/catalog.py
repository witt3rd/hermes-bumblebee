"""Catalog management — sync exposure catalogs from upstream perplexityai/bumblebee."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

UPSTREAM_REPO = "https://github.com/perplexityai/bumblebee.git"
THREAT_INTEL_SUBPATH = "threat_intel"


def catalog_dir(hermes_home: Path) -> Path:
    """Where catalogs live: <hermes_home>/state/bumblebee/catalogs/"""
    d = hermes_home / "state" / "bumblebee" / "catalogs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def state_dir(hermes_home: Path) -> Path:
    """Where last-scan state lives: <hermes_home>/state/bumblebee/"""
    d = hermes_home / "state" / "bumblebee"
    d.mkdir(parents=True, exist_ok=True)
    return d


def inventory(cat_dir: Path) -> list[dict]:
    """Return [{name, entries, schema_version, mtime}, ...] for all catalogs."""
    out = []
    for p in sorted(cat_dir.glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            out.append({
                "name": p.name,
                "schema_version": d.get("schema_version"),
                "entries": len(d.get("entries", [])),
                "mtime": p.stat().st_mtime,
            })
        except (OSError, json.JSONDecodeError):
            continue
    return out


def freshness_seconds(cat_dir: Path) -> float | None:
    """Seconds since the newest catalog was modified. None if no catalogs."""
    items = list(cat_dir.glob("*.json"))
    if not items:
        return None
    newest = max(p.stat().st_mtime for p in items)
    return time.time() - newest


def refresh(cat_dir: Path) -> dict:
    """Pull latest threat_intel/*.json from upstream into cat_dir.

    Returns a delta dict: {added, updated, removed, total_after}.
    Uses git sparse-checkout into a tmpdir, then rsync-like copy.
    """
    if not shutil.which("git"):
        raise RuntimeError("git not found on PATH")

    before = {p.name: p.read_bytes() for p in cat_dir.glob("*.json")}

    with tempfile.TemporaryDirectory(prefix="bumblebee-catalogs-") as tmp:
        tmp_path = Path(tmp)
        subprocess.run(
            ["git", "clone", "--depth", "1", "--filter=blob:none",
             "--sparse", UPSTREAM_REPO, str(tmp_path / "repo")],
            check=True, capture_output=True, text=True, timeout=120,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path / "repo"),
             "sparse-checkout", "set", THREAT_INTEL_SUBPATH],
            check=True, capture_output=True, text=True, timeout=30,
        )
        src = tmp_path / "repo" / THREAT_INTEL_SUBPATH
        if not src.is_dir():
            raise RuntimeError(f"upstream threat_intel/ missing from {UPSTREAM_REPO}")

        new_files = {p.name: p.read_bytes() for p in src.glob("*.json")}

    added = sorted(set(new_files) - set(before))
    removed = sorted(set(before) - set(new_files))
    updated = sorted(
        name for name in (set(new_files) & set(before))
        if new_files[name] != before[name]
    )

    # Apply changes
    for name in removed:
        (cat_dir / name).unlink(missing_ok=True)
    for name, content in new_files.items():
        (cat_dir / name).write_bytes(content)

    return {
        "added": added,
        "updated": updated,
        "removed": removed,
        "total_after": len(new_files),
    }
