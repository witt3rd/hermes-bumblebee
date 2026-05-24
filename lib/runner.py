"""Subprocess wrapper around the bumblebee binary."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Iterable


class BumblebeeNotInstalled(RuntimeError):
    """Raised when the bumblebee binary is not on PATH."""


def find_binary() -> str | None:
    """Locate bumblebee on PATH. Returns None if not found."""
    return shutil.which("bumblebee")


def is_available() -> bool:
    return find_binary() is not None


def version() -> str | None:
    """Return the bumblebee binary version string, or None if unavailable."""
    bin_path = find_binary()
    if not bin_path:
        return None
    try:
        result = subprocess.run(
            [bin_path, "version"],
            capture_output=True, text=True, timeout=10,
        )
        # First line is like "bumblebee v0.1.1"
        return result.stdout.splitlines()[0].strip() if result.stdout else None
    except (subprocess.TimeoutExpired, OSError):
        return None


def run_scan(
    *,
    profile: str = "baseline",
    roots: Iterable[str] | None = None,
    ecosystems: Iterable[str] | None = None,
    exposure_catalog: str | Path | None = None,
    findings_only: bool = True,
    max_duration: str = "5m",
    timeout: int = 600,
) -> tuple[list[dict], dict, str]:
    """Run bumblebee scan, return (records, summary, stderr_text).

    records: parsed NDJSON records from stdout (one per line).
    summary: the final scan_summary record (or {} if missing).
    stderr_text: full stderr (also NDJSON, diagnostics).
    """
    bin_path = find_binary()
    if not bin_path:
        raise BumblebeeNotInstalled(
            "bumblebee binary not found on PATH. Install with: "
            "`go install github.com/perplexityai/bumblebee/cmd/bumblebee@latest` "
            "and ensure $GOBIN (or ~/go/bin) is on PATH."
        )

    cmd = [bin_path, "scan", "--profile", profile, "--max-duration", max_duration]

    if findings_only:
        if not exposure_catalog:
            raise ValueError("findings_only=True requires exposure_catalog")
        cmd.append("--findings-only")

    if exposure_catalog:
        cmd.extend(["--exposure-catalog", str(exposure_catalog)])

    for root in roots or []:
        cmd.extend(["--root", str(root)])

    if ecosystems:
        cmd.extend(["--ecosystem", ",".join(ecosystems)])

    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout,
    )

    records: list[dict] = []
    summary: dict = {}
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("record_type") == "scan_summary":
            summary = rec
        else:
            records.append(rec)

    return records, summary, result.stderr


def selftest() -> tuple[bool, str]:
    """Run `bumblebee selftest`. Returns (ok, output)."""
    bin_path = find_binary()
    if not bin_path:
        return False, "bumblebee not installed"
    try:
        result = subprocess.run(
            [bin_path, "selftest"],
            capture_output=True, text=True, timeout=30,
        )
        return result.returncode == 0, (result.stdout + result.stderr).strip()
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, f"selftest failed: {exc}"
