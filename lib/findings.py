"""Findings — parse and summarize bumblebee finding records."""

from __future__ import annotations

from collections import defaultdict


def summarize_findings(records: list[dict]) -> dict:
    """Return a compact summary of finding records suitable for LLM display.

    Each finding record has fields like:
      - record_type: "finding"
      - ecosystem, package_name, version, file_path
      - exposure: { catalog, advisory_id, severity, ... }
    """
    findings = [r for r in records if r.get("record_type") == "finding"]
    if not findings:
        return {"count": 0, "by_ecosystem": {}, "by_advisory": {}, "examples": []}

    by_eco: dict[str, int] = defaultdict(int)
    by_adv: dict[str, int] = defaultdict(int)
    for f in findings:
        by_eco[f.get("ecosystem", "?")] += 1
        adv = (f.get("exposure", {}) or {}).get("advisory_id") or \
              (f.get("exposure", {}) or {}).get("catalog", "?")
        by_adv[adv] += 1

    examples = []
    for f in findings[:10]:
        exp = f.get("exposure", {}) or {}
        examples.append({
            "ecosystem": f.get("ecosystem"),
            "package": f.get("package_name"),
            "version": f.get("version"),
            "path": f.get("file_path"),
            "advisory": exp.get("advisory_id") or exp.get("catalog"),
            "severity": exp.get("severity"),
        })

    return {
        "count": len(findings),
        "by_ecosystem": dict(by_eco),
        "by_advisory": dict(by_adv),
        "examples": examples,
        "truncated": len(findings) > 10,
    }
