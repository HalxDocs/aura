#!/usr/bin/env bash
# Aura web audit driver.
#
# For every page in the inventory: open it in a logged-in persona session,
# wait for the SPA to settle, then collect
#   - axe-core a11y violations (injected into the live page)
#   - SEO/meta + DOM integrity + performance entries
#   - JS/console/resource errors (via an init-script collector)
#   - viewport + full-page screenshots at 1920x1080
# One JSON per page lands in results/, screenshots in shots/.
#
# Re-runnable: sessions are recreated from the saved login states each run.
set -uo pipefail
cd "$(dirname "$0")"

BASE="${AURA_BASE_URL:-https://aura.techa.pro}"
export AGENT_BROWSER_ARGS=--no-sandbox
mkdir -p results shots

# axe-core is fetched on demand — vendor/ is gitignored (third-party minified
# lib), so a fresh clone needs this before the first axe injection.
if [[ ! -f vendor/axe.min.js ]]; then
  mkdir -p vendor
  curl -fsSL --max-time 30 -o vendor/axe.min.js \
    "https://cdn.jsdelivr.net/npm/axe-core@4/axe.min.js" \
    || { echo "cannot fetch axe-core; place axe.min.js at vendor/axe.min.js" >&2; exit 1; }
fi

# Authenticated pages need the seeded IDs (state/seed.json is gitignored —
# written by seed-data.sh). The public pages audit fine without it; the
# persona states below just fall back to "-", which logs them out.
SEED_FILE="state/seed.json"
if [[ -f "$SEED_FILE" ]]; then
  SESSION_ID=$(python3 -c 'import json;print(json.load(open("state/seed.json"))["session_id"])')
  INVITE_ID=$(python3 -c 'import json;print(json.load(open("state/seed.json"))["invite_id"])')
  INVITE_TOKEN=$(python3 -c 'import json;print(json.load(open("state/seed.json"))["invite_token"])')
else
  echo "note: $SEED_FILE not found — run setup-accounts.sh + seed-data.sh first." >&2
  echo "      Auditing public pages only; authenticated inventory entries are skipped." >&2
  SESSION_ID="" INVITE_ID="" INVITE_TOKEN=""
fi

# persona|session|name|path|state
INVENTORY=$(cat <<EOF
pub|audit-pub|home|/|-
pub|audit-pub|login|/login|-
pub|audit-pub|forgot|/forgot-password|-
pub|audit-pub|reset|/reset-password?token=audit-expired-token|-
pub|audit-pub|notfound|/this-page-does-not-exist|-
EOF
)
if [[ -n "$SESSION_ID" ]]; then
INVENTORY+=$(cat <<EOF
pub|audit-pub|invite-public|/invite/$INVITE_TOKEN|-
cand|audit-cand|interview|/interview|state/cand.json
cand|audit-cand|profile|/profile/candidate|state/cand.json
cand|audit-cand|my-interviews|/my-interviews|state/cand.json
cand|audit-cand|report|/my-interviews/$SESSION_ID|state/cand.json
cand|audit-cand|invite-candidate|/invite/$INVITE_TOKEN|state/cand.json
rec|audit-rec|dashboard|/recruiter|state/rec.json
rec|audit-rec|invite-builder|/recruiter/new|state/rec.json
rec|audit-rec|invite-detail|/recruiter/invites/$INVITE_ID|state/rec.json
rec|audit-rec|profile|/profile/recruiter|state/rec.json
adm|audit-adm|admin-dashboard|/admin|state/adm.json
adm|audit-adm|admin-session|/admin/session/$SESSION_ID|state/adm.json
EOF
)
fi

declare -A BOOTED=()   # session -> state restored + init script registered?

audit_page() {
  local persona=$1 sess=$2 name=$3 path=$4 state=$5
  local key="${persona}__${name}"
  local url="$BASE$path"
  local ab=(agent-browser --session "$sess")
  local tmp="results/.${key}.tmp"
  echo "==> [$persona] $name  $path"

  if [[ -z "${BOOTED[$sess]:-}" && "$state" != "-" ]]; then
    # restore login state on the very first navigation, BEFORE anything that
    # could auto-launch the daemon (set viewport) — otherwise --state is
    # ignored with "daemon already running".
    local open_args0=(--state "$state" --init-script eval/error-collector.js)
    if ! "${ab[@]}" open "${open_args0[@]}" "$url" > /dev/null; then
      echo "    OPEN FAILED" | tee -a results/failures.log
      return 1
    fi
    "${ab[@]}" set viewport 1920 1080 > /dev/null
    BOOTED[$sess]=1
  fi

  local open_args=()
  [[ -z "${BOOTED[$sess]:-}" && "$state" != "-" ]] && open_args+=(--state "$state")
  [[ -z "${BOOTED[$sess]:-}" ]] && open_args+=(--init-script eval/error-collector.js)
  if ! "${ab[@]}" open "${open_args[@]}" "$url" > /dev/null; then
    echo "    OPEN FAILED" | tee -a results/failures.log
    return 1
  fi
  BOOTED[$sess]=1

  "${ab[@]}" wait --load networkidle > /dev/null 2>&1
  "${ab[@]}" get url > "$tmp.url"

  if ! cat eval/meta.js | "${ab[@]}" eval --stdin > "$tmp.meta" 2>"$tmp.metaerr"; then
    echo "    META EXTRACT FAILED: $(head -c 200 "$tmp.metaerr")" | tee -a results/failures.log
  fi

  # axe-core: inject + run, wait, read, clean up
  if cat vendor/axe.min.js eval/axe-runner.js | "${ab[@]}" eval --stdin > /dev/null 2>"$tmp.axeerr"; then
    "${ab[@]}" wait --fn "window.__axeDone === true" > /dev/null 2>&1
    "${ab[@]}" eval "JSON.stringify(window.__axeResult)" > "$tmp.axe" 2>/dev/null
  else
    echo "    AXE INJECT FAILED: $(head -c 200 "$tmp.axeerr")" | tee -a results/failures.log
    echo '{"error":"injection failed"}' > "$tmp.axe"
  fi
  "${ab[@]}" eval "window.__axeResult=null;window.__axeDone=false" > /dev/null 2>&1

  "${ab[@]}" eval "JSON.stringify(window.__auraErrors || [])" > "$tmp.errors" 2>/dev/null

  "${ab[@]}" screenshot "shots/${key}.png" > /dev/null
  "${ab[@]}" screenshot --full "shots/${key}.full.png" > /dev/null

  python3 - "$key" "$persona" "$path" "$tmp" <<'PY'
import json, sys
key, persona, path, tmp = sys.argv[1:5]
def load(name):
    try:
        return json.load(open(tmp + name))
    except Exception:
        return None
def deep(v, depth=0):
    # agent-browser eval prints string returns JSON-encoded; unwrap layers
    if isinstance(v, str) and depth < 3:
        try:
            return deep(json.loads(v), depth + 1)
        except Exception:
            return v
    return v
try:
    final_url = open(tmp + ".url").read().strip()
except Exception:
    final_url = None
meta_raw = deep(load(".meta"))
meta = meta_raw if isinstance(meta_raw, dict) else {"_raw": str(meta_raw)[:300] if meta_raw else None}
axe = deep(load(".axe")) or {"error": "no result"}
errors = deep(load(".errors")) or []
out = {
    "key": key,
    "persona": persona,
    "path": path,
    "final_url": final_url,
    "meta": meta,
    "axe": axe,
    "errors": errors,
    "shots": [f"shots/{key}.png", f"shots/{key}.full.png"],
}
json.dump(out, open(f"results/{key}.json", "w"), indent=1)
PY
  rm -f "$tmp".*
  echo "    done -> results/${key}.json"
}

while IFS='|' read -r persona sess name path state; do
  [[ -z "$persona" || "$persona" == \#* ]] && continue
  audit_page "$persona" "$sess" "$name" "$path" "$state"
done <<< "$INVENTORY"

echo "audit collection finished"
