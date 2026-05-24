#!/usr/bin/env bash
# Cron watchdog — runs bumblebee scan, silent on clean, loud on findings.
#
# Wire via:
#   hermes cron create --name "bumblebee-watch" --schedule "every 6h" \
#     --no-agent --script /path/to/this/cron-watchdog.sh
#
# With no_agent=true, stdout is delivered verbatim. Empty stdout = silent.
set -euo pipefail

BIN="${BUMBLEBEE_BIN:-$(command -v bumblebee || true)}"
if [[ -z "$BIN" ]]; then
  echo "bumblebee binary not on PATH — install: go install github.com/perplexityai/bumblebee/cmd/bumblebee@latest" >&2
  exit 0
fi

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
CAT_DIR="$HERMES_HOME/state/bumblebee/catalogs"
STATE_DIR="$HERMES_HOME/state/bumblebee"
mkdir -p "$CAT_DIR" "$STATE_DIR"

# Refresh catalogs if older than 24h or empty
NEWEST=0
if compgen -G "$CAT_DIR/*.json" > /dev/null; then
  NEWEST=$(find "$CAT_DIR" -name '*.json' -printf '%T@\n' | sort -nr | head -1 | cut -d. -f1)
fi
NOW=$(date +%s)
AGE=$(( NOW - ${NEWEST:-0} ))

if [[ "${NEWEST:-0}" -eq 0 ]] || [[ "$AGE" -gt 86400 ]]; then
  TMP=$(mktemp -d)
  trap 'rm -rf "$TMP"' EXIT
  if git clone --depth 1 --filter=blob:none --sparse \
       https://github.com/perplexityai/bumblebee.git "$TMP/repo" >/dev/null 2>&1; then
    git -C "$TMP/repo" sparse-checkout set threat_intel >/dev/null 2>&1 || true
    if [[ -d "$TMP/repo/threat_intel" ]]; then
      cp -f "$TMP/repo/threat_intel"/*.json "$CAT_DIR"/ 2>/dev/null || true
    fi
  fi
fi

if ! compgen -G "$CAT_DIR/*.json" > /dev/null; then
  echo "bumblebee: no catalogs available, skipping scan" >&2
  exit 0
fi

# Scan
OUT="$STATE_DIR/last-cron-scan.ndjson"
"$BIN" scan --profile baseline \
  --exposure-catalog "$CAT_DIR" \
  --findings-only \
  --max-duration 2m \
  > "$OUT" 2>/dev/null || true

# Count findings (excluding the scan_summary record)
COUNT=$(grep -c '"record_type":"finding"' "$OUT" 2>/dev/null || echo 0)

if [[ "$COUNT" -eq 0 ]]; then
  # Silent — exits cleanly, nothing delivered
  exit 0
fi

# Loud — print to stdout, gets delivered verbatim
echo "🐝 bumblebee: $COUNT supply-chain finding(s) on $(hostname)"
echo ""
grep '"record_type":"finding"' "$OUT" | head -10 | while IFS= read -r line; do
  ECO=$(echo "$line" | python3 -c "import json,sys; r=json.loads(sys.stdin.read()); print(r.get('ecosystem','?'))")
  PKG=$(echo "$line" | python3 -c "import json,sys; r=json.loads(sys.stdin.read()); print(r.get('package_name','?'))")
  VER=$(echo "$line" | python3 -c "import json,sys; r=json.loads(sys.stdin.read()); print(r.get('version','?'))")
  ADV=$(echo "$line" | python3 -c "import json,sys; r=json.loads(sys.stdin.read()); e=r.get('exposure',{}) or {}; print(e.get('advisory_id') or e.get('catalog','?'))")
  echo "  • $ECO: $PKG@$VER ($ADV)"
done
echo ""
echo "Full output: $OUT"
echo "Triage: load skill 'bumblebee:triaging-supply-chain-finding'"
