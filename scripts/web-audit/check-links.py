#!/usr/bin/env python3
"""Check every same-origin link harvested from the audit pages.

Reads results/*.json (the driver's per-page output), resolves hrefs against
each page's final URL, and GETs each unique same-origin URL once (parallel,
8 at a time). Writes results/links.json.
"""
import json
import subprocess
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urljoin, urlparse

BASE = sys.argv[1] if len(sys.argv) > 1 else "https://aura.techa.pro"
ORIGIN = urlparse(BASE).netloc
results = Path(__file__).parent / "results"

found = defaultdict(list)  # url -> [page keys]
for f in sorted(results.glob("*.json")):
    if f.name in ("headers.json", "links.json", "summary.json", "extra-findings.json"):
        continue
    try:
        page = json.loads(f.read_text())
    except Exception:
        continue
    if not isinstance(page, dict):
        continue
    meta = page.get("meta") or {}
    final_url = page.get("final_url") or (BASE + (page.get("path") or "/"))
    for href in meta.get("links") or []:
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        absu = urljoin(final_url, href)
        p = urlparse(absu)
        if p.scheme not in ("http", "https"):
            continue
        if p.netloc != ORIGIN:
            continue  # externals are counted, not fetched
        clean = absu.split("#")[0]
        found[clean].append(page.get("key", f.stem))

externals = set()
for f in sorted(results.glob("*.json")):
    try:
        page = json.loads(f.read_text())
    except Exception:
        continue
    if not isinstance(page, dict):
        continue
    for href in (page.get("meta") or {}).get("links") or []:
        if href and href.startswith("http") and urlparse(href).netloc not in ("", ORIGIN):
            externals.add(href)


def check(url):
    try:
        out = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", "15", url],
            capture_output=True, text=True, timeout=20,
        ).stdout.strip()
        return url, int(out) if out.isdigit() else 0
    except Exception:
        return url, 0


with ThreadPoolExecutor(max_workers=8) as ex:
    codes = dict(ex.map(check, sorted(found)))

report = {
    "checked": len(codes),
    "broken": [{"url": u, "status": c, "on_pages": found[u]} for u, c in sorted(codes.items()) if c >= 400 or c == 0],
    "external_count": len(externals),
    "externals": sorted(externals)[:40],
}
json.dump(report, open(results / "links.json", "w"), indent=1)
print(f"checked {report['checked']} internal links, {len(report['broken'])} broken, {report['external_count']} external refs")
