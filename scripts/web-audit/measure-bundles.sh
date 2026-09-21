#!/usr/bin/env bash
# Measure real transfer sizes of the SPA bundles via curl (browser HTTP cache
# makes performance-entry transferSize unreliable for first-load numbers).
# Writes results/bundle.json.
set -uo pipefail
cd "$(dirname "$0")"
BASE="${AURA_BASE_URL:-https://aura.techa.pro}"
mkdir -p results

HTML=$(curl -s --compressed --max-time 15 "$BASE/")
ASSETS=$(echo "$HTML" | grep -oE '(src|href)="/assets/[^"]+"' | grep -oE '/assets/[^"]+' | tr -d '"' | sort -u)

python3 - "$BASE" "$ASSETS" <<'PY'
import json, subprocess, sys
base = sys.argv[1]
assets = sorted({a for a in sys.argv[2].split() if a})
out = []
for a in assets:
    url = base + a
    r = subprocess.run(
        ["curl", "-s", "-o", "/dev/null", "--compressed", "--max-time", "30",
         "-w", "%{size_download} %{content_type} %{http_code}", url],
        capture_output=True, text=True, timeout=35)
    parts = (r.stdout or "").split()
    size = int(parts[0]) if parts and parts[0].isdigit() else 0
    ctype = parts[1] if len(parts) > 1 else "?"
    code = parts[2] if len(parts) > 2 else "?"
    out.append({"asset": a, "bytes": size, "content_type": ctype, "status": code})
out.sort(key=lambda x: -x["bytes"])
json.dump({"measured_with": "curl --compressed (no browser cache)", "bundles": out},
          open("results/bundle.json", "w"), indent=1)
total = sum(x["bytes"] for x in out)
print(f"{len(out)} bundles, {total/1024:.0f} KB total, largest:")
for x in out[:5]:
    print(f"  {x['asset'][-60:]:60} {x['bytes']/1024:8.1f} KB  {x['content_type']}")
PY
