"""hermes-bumblebee — supply-chain exposure scanning for Hermes Agent.

Wraps Perplexity's bumblebee binary (https://github.com/perplexityai/bumblebee)
with three tools, a session-start opportunistic-scan hook, and a triage skill.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path

from . import schemas, tools
from .lib import catalog as cat_mod
from .lib import runner
from .lib.findings import summarize_findings

logger = logging.getLogger(__name__)

# Catalog freshness threshold: only refresh in-hook if older than this.
_CATALOG_STALE_AFTER = 24 * 3600  # 24h
# Skip the session-start scan if we ran one this recently.
_SCAN_COOLDOWN = 6 * 3600  # 6h
# How long the background scan thread is allowed to run.
_HOOK_SCAN_TIMEOUT = 60  # seconds


def _binary_present() -> bool:
    return runner.is_available()


def _background_scan(hermes_home: Path) -> None:
    """Run silently. Persist findings to last-scan.json. Log on hit."""
    try:
        cat_dir = cat_mod.catalog_dir(hermes_home)
        state_d = cat_mod.state_dir(hermes_home)

        # Refresh catalogs if stale
        freshness = cat_mod.freshness_seconds(cat_dir)
        if freshness is None or freshness > _CATALOG_STALE_AFTER:
            try:
                delta = cat_mod.refresh(cat_dir)
                logger.info(
                    "bumblebee: catalogs refreshed (+%d updated, +%d added, %d total)",
                    len(delta["updated"]), len(delta["added"]), delta["total_after"],
                )
            except Exception as exc:
                logger.warning("bumblebee: catalog refresh failed: %s", exc)

        if not cat_mod.inventory(cat_dir):
            return  # no catalogs, nothing to scan against

        # Cooldown check
        last_scan_path = state_d / "last-scan.json"
        if last_scan_path.exists():
            try:
                last = json.loads(last_scan_path.read_text(encoding="utf-8"))
                if time.time() - last.get("ts", 0) < _SCAN_COOLDOWN:
                    return
            except (OSError, json.JSONDecodeError):
                pass

        records, summary, _ = runner.run_scan(
            profile="baseline",
            exposure_catalog=cat_dir,
            findings_only=True,
            max_duration="2m",
            timeout=_HOOK_SCAN_TIMEOUT,
        )
        fsum = summarize_findings(records)

        last_scan_path.write_text(json.dumps({
            "ts": time.time(),
            "profile": "baseline",
            "trigger": "session-start-hook",
            "summary": summary,
            "findings": fsum,
        }, indent=2), encoding="utf-8")

        if fsum["count"] > 0:
            logger.warning(
                "bumblebee: %d supply-chain finding(s) detected — by ecosystem: %s",
                fsum["count"], fsum["by_ecosystem"],
            )
    except Exception as exc:
        logger.debug("bumblebee background scan failed: %s", exc, exc_info=True)


def _on_session_start(session_id: str, **kwargs) -> None:
    """Fire a non-blocking baseline scan on new sessions."""
    if not _binary_present():
        return  # silent — tools' check_fn already hides them

    # Resolve hermes_home here (not at import) so profile env is current
    try:
        from hermes_constants import get_hermes_home  # type: ignore
        hermes_home = Path(get_hermes_home())
    except Exception:
        import os
        hermes_home = Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes")))

    t = threading.Thread(
        target=_background_scan,
        args=(hermes_home,),
        name="bumblebee-session-start-scan",
        daemon=True,
    )
    t.start()


def register(ctx):
    """Wire schemas to handlers and register hooks + skill."""
    check = _binary_present

    ctx.register_tool(
        name="bumblebee_scan",
        toolset="bumblebee",
        schema=schemas.SCAN,
        handler=tools.bumblebee_scan,
        check_fn=check,
        emoji="🐝",
    )
    ctx.register_tool(
        name="bumblebee_refresh_catalogs",
        toolset="bumblebee",
        schema=schemas.REFRESH_CATALOGS,
        handler=tools.bumblebee_refresh_catalogs,
        check_fn=check,
        emoji="🐝",
    )
    ctx.register_tool(
        name="bumblebee_status",
        toolset="bumblebee",
        schema=schemas.STATUS,
        handler=tools.bumblebee_status,
        emoji="🐝",
    )

    ctx.register_hook("on_session_start", _on_session_start)

    # Bundle the triage skill so the agent can load it on a finding
    skills_dir = Path(__file__).parent / "skills"
    if skills_dir.is_dir() and hasattr(ctx, "register_skill"):
        for child in sorted(skills_dir.iterdir()):
            skill_md = child / "SKILL.md"
            if child.is_dir() and skill_md.exists():
                try:
                    ctx.register_skill(child.name, skill_md)
                except Exception as exc:
                    logger.warning("bumblebee: failed to register skill %s: %s", child.name, exc)
