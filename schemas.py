"""Tool schemas — what the LLM sees."""

SCAN = {
    "name": "bumblebee_scan",
    "description": (
        "Run a supply-chain exposure scan via bumblebee against curated "
        "advisory catalogs (Shai-Hulud npm/PyPI worm, Laravel-Lang Composer "
        "compromise, node-ipc credential stealer, GemStuffer RubyGems, "
        "Nx Console VS Code, and ongoing). Reads on-disk package, extension, "
        "and MCP-host metadata — does not execute package managers. "
        "Returns a finding summary; on clean returns count=0. "
        "Use this when: the user names a supply-chain campaign or advisory, "
        "after installing new dependencies, or when investigating an incident."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "profile": {
                "type": "string",
                "enum": ["baseline", "project", "deep"],
                "description": (
                    "baseline = global/user package roots + extensions + MCP configs. "
                    "project = configured developer workspace roots (requires roots). "
                    "deep = explicit roots including $HOME, for on-demand incident sweeps."
                ),
                "default": "baseline",
            },
            "roots": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Filesystem paths to scan. Required for project and deep profiles. "
                    "Ignored for baseline."
                ),
            },
            "ecosystems": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Optional ecosystem filter: npm, pypi, go, rubygems, packagist, "
                    "mcp, editor-extension, browser-extension. Omit to scan all."
                ),
            },
            "max_duration": {
                "type": "string",
                "description": "Scan time budget (e.g. '5m', '30s'). Default 5m.",
                "default": "5m",
            },
        },
        "required": [],
    },
}

REFRESH_CATALOGS = {
    "name": "bumblebee_refresh_catalogs",
    "description": (
        "Pull the latest exposure catalogs from perplexityai/bumblebee upstream "
        "into the local cache. Use when: the user mentions a new advisory, "
        "before an incident scan, or as a periodic refresh. Catalogs are "
        "small JSON files; the operation clones a sparse checkout and copies "
        "threat_intel/*.json into ~/.hermes/state/bumblebee/catalogs/."
    ),
    "parameters": {"type": "object", "properties": {}, "required": []},
}

STATUS = {
    "name": "bumblebee_status",
    "description": (
        "Read-only: report installed bumblebee binary version, catalog inventory "
        "with entry counts and freshness, and the last opportunistic scan result "
        "(if any). Use when: the user asks 'what supply-chain scanning is in place?' "
        "or 'when was the last scan?' or 'what catalogs are loaded?'"
    ),
    "parameters": {"type": "object", "properties": {}, "required": []},
}
