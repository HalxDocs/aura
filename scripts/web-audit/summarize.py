#!/usr/bin/env python3
"""Aggregate the audit collection into audit-report.md + results/summary.json.

Scoring model: each category starts at 100 and loses points per finding
(severity-weighted). Overall = weighted mean of a11y, integrity, seo, perf,
headers. Extra backend findings can be injected via results/extra-findings.json
(shown in the report, not scored against the web pages).
"""
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent
RES = ROOT / "results"

IMPACT_PENALTY = {"critical": 12, "serious": 8, "moderate": 5, "minor": 2, None: 3}
CAT_WEIGHTS = {"a11y": 0.30, "integrity": 0.25, "seo": 0.15, "perf": 0.15, "headers": 0.15}

findings = []  # {severity, category, page, title, detail}


def add(sev, cat, page, title, detail=""):
    findings.append({"severity": sev, "category": cat, "page": page, "title": title, "detail": detail})


pages = []
for f in sorted(RES.glob("*.json")):
    if f.name in ("headers.json", "links.json", "summary.json", "extra-findings.json", "bundle.json"):
        continue
    try:
        pages.append(json.loads(f.read_text()))
    except Exception:
        pass

scores = {k: 100.0 for k in CAT_WEIGHTS}

# ---------------- per-page ----------------
for p in pages:
    key = p.get("key", "?")
    meta = p.get("meta") or {}
    axe = p.get("axe") or {}
    errors = p.get("errors") or []
    shots = p.get("shots") or []

    # a11y
    a11y_pen = 0.0
    if axe.get("error"):
        add("notice", "a11y", key, "axe-core could not run", str(axe.get("error"))[:200])
    for v in axe.get("violations") or []:
        pen = IMPACT_PENALTY.get(v.get("impact"), 3) * min(v.get("nodeCount", 1), 3)
        a11y_pen += pen
        sev = "error" if v.get("impact") in ("critical", "serious") else "warning"
        targets = "; ".join(sorted({n.get("target", "") for n in v.get("nodes", [])})[:3])
        add(sev, "a11y", key, f"{v.get('help', v.get('id'))} ({v.get('nodeCount')} nodes)",
            f"rule={v.get('id')} tags={v.get('tags')} targets={targets} evidence={shots[0] if shots else ''}")
    for v in axe.get("incomplete") or []:
        a11y_pen += 1
        add("notice", "a11y", key, f"needs manual check: {v.get('help', v.get('id'))}",
            f"rule={v.get('id')} nodes={v.get('nodeCount')}")
    scores["a11y"] -= a11y_pen

    # seo / meta
    seo_pen = 0.0
    checks = [
        (not meta.get("title"), 12, "error", "Missing <title>"),
        (not meta.get("metaDescription"), 10, "warning", "Missing meta description"),
        (not meta.get("viewport"), 10, "error", "Missing viewport meta"),
        (not meta.get("lang"), 8, "warning", "No lang attribute on <html>"),
        (not meta.get("favicon"), 5, "notice", "No favicon link"),
        (not meta.get("canonical"), 4, "notice", "No canonical URL"),
        ((meta.get("og") or {}).get("title") is None, 5, "warning", "Missing og:title"),
        ((meta.get("og") or {}).get("image") is None, 5, "warning", "Missing og:image"),
        (meta.get("h1Count") == 0, 8, "warning", "No <h1> on page"),
        (meta.get("h1Count") not in (None, 0, 1), 8, "warning", f"Multiple <h1> ({meta.get('h1Count')})"),
    ]
    for bad, pen, sev, title in checks:
        if bad:
            seo_pen += pen
            add(sev, "seo", key, title)
    scores["seo"] -= seo_pen

    # integrity (errors, buttons, inputs)
    int_pen = 0.0
    counts = {}
    for e in errors:
        counts[e.get("kind", "?")] = counts.get(e.get("kind", "?"), 0) + 1
    if counts.get("error"):
        n = counts["error"]
        int_pen += min(n * 8, 24)
        add("error", "integrity", key, f"{n} uncaught JS error(s)", "; ".join(
            e.get("msg", "") for e in errors if e.get("kind") == "error")[:400])
    if counts.get("promise"):
        int_pen += min(counts["promise"] * 6, 18)
        add("error", "integrity", key, f"{counts['promise']} unhandled promise rejection(s)", "; ".join(
            e.get("msg", "") for e in errors if e.get("kind") == "promise")[:400])
    if counts.get("resource"):
        int_pen += min(counts["resource"] * 4, 12)
        add("warning", "integrity", key, f"{counts['resource']} failed resource load(s)", "; ".join(
            e.get("msg", "") for e in errors if e.get("kind") == "resource")[:400])
    if counts.get("console.error"):
        int_pen += min(counts["console.error"] * 4, 12)
        add("warning", "integrity", key, f"{counts['console.error']} console.error call(s)", "; ".join(
            e.get("msg", "") for e in errors if e.get("kind") == "console.error")[:400])
    if meta.get("buttonsUnnamed"):
        int_pen += min(meta["buttonsUnnamed"] * 4, 12)
        add("warning", "integrity", key, f"{meta['buttonsUnnamed']} button(s) with no accessible name")
    if meta.get("inputsNoLabel"):
        int_pen += min(meta["inputsNoLabel"] * 6, 18)
        add("error", "integrity", key, f"{meta['inputsNoLabel']} input(s) with no label")
    scores["integrity"] -= int_pen

    # performance
    perf = meta.get("perf") or {}
    perf_pen = 0.0
    kb = perf.get("transferKB") or 0
    if kb > 5000:
        perf_pen += 20
        add("error", "perf", key, f"Page transfers {kb} KB")
    elif kb > 2500:
        perf_pen += 10
        add("warning", "perf", key, f"Page transfers {kb} KB")
    if (perf.get("requests") or 0) > 80:
        perf_pen += 10
        add("warning", "perf", key, f"{perf['requests']} network requests")
    if (meta.get("domNodes") or 0) > 4000:
        perf_pen += 20
        add("warning", "perf", key, f"DOM size {meta['domNodes']} nodes")
    elif (meta.get("domNodes") or 0) > 2500:
        perf_pen += 10
        add("notice", "perf", key, f"DOM size {meta['domNodes']} nodes")
    load = perf.get("load") or 0
    if load > 5000:
        perf_pen += 25
        add("error", "perf", key, f"load event at {load} ms")
    elif load > 3000:
        perf_pen += 15
        add("warning", "perf", key, f"load event at {load} ms")
    if (perf.get("ttfb") or 0) > 800:
        perf_pen += 10
        add("warning", "perf", key, f"TTFB {perf['ttfb']} ms")
    scores["perf"] -= perf_pen

# ---------------- links ----------------
try:
    links = json.loads((RES / "links.json").read_text())
    if links.get("broken"):
        scores["integrity"] -= min(len(links["broken"]) * 6, 24)
        for b in links["broken"][:15]:
            add("error", "integrity", ", ".join(b["on_pages"])[:60], f"Broken link ({b['status']}): {b['url'][:90]}")
except FileNotFoundError:
    pass

# ---------------- headers ----------------
try:
    h = json.loads((RES / "headers.json").read_text())
    r = h.get("root") or {}
    red = h.get("http_redirect") or {}
    g = h.get("root_get") or {}
    hdr_pen = 0.0
    for name, pen, sev in [("content-security-policy", 20, "error"),
                           ("strict-transport-security", 15, "error"),
                           ("x-frame-options", 10, "warning"),
                           ("x-content-type-options", 10, "warning"),
                           ("referrer-policy", 10, "warning"),
                           ("permissions-policy", 5, "notice")]:
        if not r.get(name):
            hdr_pen += pen
            add(sev, "headers", "all pages", f"Missing {name} header")
    if not (red.get("status") or ""):
        hdr_pen += 15
        add("error", "headers", "all pages", "HTTP→HTTPS redirect could not be verified")
    else:
        m = re.search(r"HTTP/[\d.]+\s+(\d+)", red["status"])
        code = m.group(1) if m else None
        if code and not code.startswith("3"):
            hdr_pen += 15
            add("error", "headers", "all pages", f"HTTP does not redirect to HTTPS (status {code})")
    enc = (g.get("content_encoding") or "").lower()
    if "gzip" not in enc and "br" not in enc and "zstd" not in enc:
        hdr_pen += 15
        add("warning", "headers", "all pages", "HTML served without compression")
    scores["headers"] -= hdr_pen
except FileNotFoundError:
    pass

# ---------------- bundles (out-of-band first-load weights) ----------------
try:
    b = json.loads((RES / "bundle.json").read_text())
    js_kb = sum(x["bytes"] for x in b.get("bundles", []) if "javascript" in x.get("content_type", "")) / 1024
    css_kb = sum(x["bytes"] for x in b.get("bundles", []) if "css" in x.get("content_type", "")) / 1024
    if js_kb > 500:
        scores["perf"] -= 20
        add("error", "perf", "all pages",
            f"Main JS bundle is {js_kb:.0f} KB served uncompressed",
            "Vite emits one index-*.js (code-splitting would shrink it; gzip/brotli at nginx would cut ~70% on the wire). See results/bundle.json.")
    elif js_kb > 250:
        scores["perf"] -= 10
        add("warning", "perf", "all pages", f"Main JS bundle is {js_kb:.0f} KB")
    if css_kb > 100:
        scores["perf"] -= 5
        add("warning", "perf", "all pages", f"CSS bundle is {css_kb:.0f} KB")
except FileNotFoundError:
    pass
try:
    extra = json.loads((RES / "extra-findings.json").read_text())
    for e in extra:
        add(e.get("severity", "warning"), e.get("category", "backend"), e.get("page", "-"),
            e.get("title", ""), e.get("detail", ""))
except FileNotFoundError:
    pass

# ---------------- collapse systemic findings ----------------
# The same finding on many pages is one fix, not N findings: collapse any
# (category, title) seen on >= 4 pages into a single systemic entry.
from collections import defaultdict
rank = {"error": 0, "warning": 1, "notice": 2}
by_title = defaultdict(list)
for f in findings:
    by_title[(f["category"], f["title"])].append(f)
systemic = []
for (cat, title), group in by_title.items():
    if len(group) >= 4:
        pages_hit = sorted({g["page"] for g in group})
        worst = min(group, key=lambda g: rank.get(g["severity"], 3))
        systemic.append({"severity": worst["severity"], "category": cat, "page": f"{len(pages_hit)} pages",
                         "title": title,
                         "detail": (worst.get("detail", "") + f"\n  pages: {', '.join(pages_hit)}")[:600]})
        for g in group:
            findings.remove(g)
findings.extend(systemic)

# duplicate static <title> across routes
titles = {(p.get("meta") or {}).get("title") for p in pages if (p.get("meta") or {}).get("title")}
if len(pages) > 3 and len(titles) == 1:
    add("warning", "seo", "all pages",
        f"Every route serves the same static <title> (\"{titles.pop()}\")",
        "The SPA never updates document.title per route; browser tabs, history, "
        "bookmarks and search results all read identically. Set a per-route title "
        "(and description) in each page component.")

# ---------------- scores ----------------
for k in scores:
    scores[k] = max(0.0, round(scores[k], 1))
overall = round(sum(scores[k] * CAT_WEIGHTS[k] for k in CAT_WEIGHTS), 1)
grade = ("A" if overall >= 90 else "B" if overall >= 80 else "C" if overall >= 70 else
         "D" if overall >= 55 else "F")

findings.sort(key=lambda x: (rank.get(x["severity"], 3), x["category"], x["page"]))

summary = {"overall": overall, "grade": grade, "categories": scores, "weights": CAT_WEIGHTS,
           "finding_counts": {s: sum(1 for f in findings if f["severity"] == s) for s in ("error", "warning", "notice")},
           "pages": [{"key": p.get("key"), "title": (p.get("meta") or {}).get("title"),
                      "final_url": p.get("final_url"), "shots": p.get("shots")} for p in pages]}
json.dump(summary, open(RES / "summary.json", "w"), indent=1)

# ---------------- report.md ----------------
lines = []
lines.append("# Aura Web Audit Report")
lines.append("")
lines.append(f"**Overall score: {overall}/100 (grade {grade})** — target: `{os.environ.get('AURA_BASE_URL', 'https://aura.techa.pro')}`")
lines.append("")
lines.append("| Category | Weight | Score |")
lines.append("|---|---|---|")
for k, w in CAT_WEIGHTS.items():
    lines.append(f"| {k} | {int(w*100)}% | {scores[k]} |")
fc = summary["finding_counts"]
lines.append("")
lines.append(f"**Findings:** {fc['error']} errors · {fc['warning']} warnings · {fc['notice']} notices — across {len(pages)} audited page states")
lines.append("")
lines.append("> Perf numbers are repeat-visit (warm browser cache): in-page transferSize only counts cache misses. "
            "Real bundle weights were measured out-of-band with curl: see `results/bundle.json`.")
lines.append("")
lines.append("## Findings")
sev_title = {"error": "Errors (fix first)", "warning": "Warnings", "notice": "Notices"}
for sev in ("error", "warning", "notice"):
    sub = [f for f in findings if f["severity"] == sev]
    if not sub:
        continue
    lines.append("")
    lines.append(f"### {sev_title[sev]} ({len(sub)})")
    for f in sub:
        lines.append(f"- **[{f['category']}] {f['page']}** — {f['title']}")
        if f.get("detail"):
            lines.append(f"  {f['detail']}")
lines.append("")
lines.append("## Page inventory")
lines.append("")
lines.append("| Page | Persona | Title | Errors | axe violations | Transfer KB |")
lines.append("|---|---|---|---|---|---|")
for p in pages:
    meta = p.get("meta") or {}
    axe = p.get("axe") or {}
    nv = len(axe.get("violations") or [])
    ne = len(p.get("errors") or [])
    kb = (meta.get("perf") or {}).get("transferKB")
    lines.append(f"| `{p.get('path')}` | {p.get('persona')} | {(meta.get('title') or '?')[:40]} | {ne} | {nv} | {kb} |")
lines.append("")
lines.append("## Screenshots")
lines.append("")
for p in pages:
    for s in p.get("shots") or []:
        lines.append(f"- `{p.get('key')}`: {s}")
(ROOT / "audit-report.md").write_text("\n".join(lines) + "\n")
print(f"overall {overall}/100 ({grade}); findings: {fc['error']}E/{fc['warning']}W/{fc['notice']}N")
print("report: scripts/web-audit/audit-report.md")
