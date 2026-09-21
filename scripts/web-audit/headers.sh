#!/usr/bin/env bash
# HTTP-level checks the browser can't see: security headers, HSTS, HTTPS
# redirect, compression, cache policy. Writes results/headers.json.
set -uo pipefail
cd "$(dirname "$0")"

BASE="${AURA_BASE_URL:-https://aura.techa.pro}"
HOST=$(python3 -c 'from urllib.parse import urlparse;print(urlparse("'"$BASE"'").netloc)')
mkdir -p results

curl -s -o /dev/null -D - --max-time 15 "http://$HOST/" > results/h-http.raw
curl -s -o /dev/null -D - --max-time 15 "$BASE/" > results/h-root.raw
curl -s -o /dev/null -D - --compressed --max-time 15 "$BASE/" > results/h-root-get.raw

python3 - <<'PY'
import json

def parse(path):
    """Return (status_line, {lowercased header: value}) from a raw header dump."""
    status, headers = None, {}
    for line in open(path).read().splitlines():
        line = line.strip()
        if not line:
            continue
        if status is None and line.upper().startswith("HTTP/"):
            status = line
            continue
        if ":" in line:
            k, v = line.split(":", 1)
            headers[k.strip().lower()] = v.strip()
    return status, headers

status_http, _ = parse("results/h-http.raw")
status_root, h_root = parse("results/h-root.raw")
status_get, h_get = parse("results/h-root-get.raw")

SEC = ["content-security-policy", "strict-transport-security", "x-frame-options",
       "x-content-type-options", "referrer-policy", "permissions-policy"]
out = {
  "http_redirect": {"status": status_http, "location": h_get.get("_", None) or None},
  "root": {h: h_root.get(h) for h in SEC},
  "root_get": {
     "status": status_get,
     "content_encoding": h_get.get("content-encoding"),
     "cache_control": h_get.get("cache-control"),
     "content_type": h_get.get("content-type"),
     "etag": h_get.get("etag"),
     "server": h_get.get("server"),
  },
}
# location lives in the http dump's headers, parse it there
_, h_http = parse("results/h-http.raw")
out["http_redirect"]["location"] = h_http.get("location")
json.dump(out, open("results/headers.json", "w"), indent=1)
print(json.dumps(out, indent=1))
PY
rm -f results/h-http.raw results/h-root.raw results/h-root-get.raw
