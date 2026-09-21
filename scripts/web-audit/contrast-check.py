#!/usr/bin/env python3
"""WCAG contrast checker for the Aura design tokens.

Each entry: (label, fg, bg, kind) where kind is "text" (needs 4.5:1) or
"large" (large text / UI component, needs 3:1). Backgrounds may be a CSS
composite — an rgba surface over the page bg — expressed as
("over", rgba_tuple, base_hex). Exits non-zero when any pair fails, so the
fix loop can re-run it.

Usage: python3 contrast-check.py [--fix-candidates]
"""
import sys
from dataclasses import dataclass

def srgb(c: str) -> tuple:
    c = c.lstrip("#")
    return tuple(int(c[i:i+2], 16) for i in (0, 2, 4))

def lum(rgb: tuple) -> float:
    def chan(v):
        v = v / 255
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * chan(r) + 0.7152 * chan(g) + 0.0722 * chan(b)

def over(rgba: tuple, base: tuple) -> tuple:
    (r, g, b, a), (br, bg_, bb) = rgba, base
    return (round(r * a + br * (1 - a)), round(g * a + bg_ * (1 - a)), round(b * a + bb * (1 - a)))

def ratio(fg: tuple, bg: tuple) -> float:
    l1, l2 = sorted((lum(fg), lum(bg)), reverse=True)
    return (l1 + 0.05) / (l2 + 0.05)

BG = "#09090b"
SURFACE = over((255, 255, 255, 0.03), srgb(BG))
SURFACE_2 = over((255, 255, 255, 0.04), srgb(BG))   # hover surfaces
ACCORDION = over((255, 255, 255, 0.02), srgb(BG))   # btn-ghost background

PAIRS = [
    # Token values AFTER the AA nudges (feat/web-audit):
    # --muted-2 #71717a -> #8e8e99, --muted-3 #52525b -> #7c7c87,
    # --accent #6366f1 -> #6063ef, button gradients re-pointed off accent-2.
    ("muted-2 on bg (eyebrows/footer/pills)", "#8e8e99", BG, "text"),
    ("muted-2 on surface (pill bg)", "#8e8e99", SURFACE, "text"),
    ("muted-3 on bg (meter-foot captions)", "#7c7c87", BG, "text"),
    ("muted-3 on surface (meter captions on card)", "#7c7c87", SURFACE, "text"),
    ("muted on bg (body muted text)", "#a1a1aa", BG, "text"),
    ("fg-2 on bg (pre btn-ghost label)", "#e4e4e7", ACCORDION, "text"),
    # active tab/segment: white on accent
    ("white on accent (active tabs/segments)", "#ffffff", "#6063ef", "text"),
    ("white on btn-primary top (accent)", "#ffffff", "#6063ef", "text"),
    ("white on btn-primary bottom (accent-deep)", "#ffffff", "#4338ca", "text"),
    # shadcn muted-foreground on card (login page .inline-flex was
    # likely the muted helper text inside an inline-flex container)
    ("shadcn muted-foreground on card", "#a1a1aa", SURFACE, "text"),
    # accent-2 stays light: it is text/decoration on dark, never a white-text bg
    ("accent-2 as text on bg (kicker)", "#818cf8", BG, "text"),
    ("accent-3 as text on bg (eyebrow lit)", "#a5b4fc", BG, "text"),
]

# Candidate replacements for the muted ladder (zinc ladder):
CANDIDATES = {
    "--muted-2 (was #71717a)": ["#8e8e99", "#90909a", "#95959f", "#a1a1aa"],
    "--muted-3 (was #52525b)": ["#7c7c87", "#80808b", "#8e8e99", "#a1a1aa"],
}

def check_btn_primary_gradients() -> int:
    """Fail when any .btn-primary rule paints white text over light --accent-2.

    The pair table above models the intended gradient (--accent → --accent-deep),
    but only a scan can catch a stylesheet drifting back to the pre-AA
    `linear-gradient(180deg, var(--accent-2), var(--accent))` — the exact bug
    the audit found on the dashboard/report pages while landing/pre were fixed.
    accent-2 (#818cf8, ~3:1 under white) is text/decoration on dark, never a
    white-text background.
    """
    import re
    from pathlib import Path

    styles_dir = Path(__file__).resolve().parents[2] / "frontend" / "src" / "styles"
    offenders = []
    for css in sorted(styles_dir.glob("*.css")):
        for i, line in enumerate(css.read_text().splitlines(), 1):
            if ".btn-primary" in line and "--accent-2" in line:
                offenders.append(f"{css.name}:{i}")
    print("\nbtn-primary gradient guard (no white-on-accent-2):")
    if offenders:
        for off in offenders:
            print(f"  FAIL  {off} uses --accent-2 under white text")
        return 1
    print(f"  PASS  all .btn-primary rules in {styles_dir.name}/ avoid --accent-2")
    return 0


def check_muted_tokens() -> int:
    """Fail when any stylesheet defines --muted-2/--muted-3 below 4.5:1 on the bg.

    The pair table models the intended values, but only a scan catches one
    stylesheet keeping the pre-AA token while the rest moved — the exact miss
    this guard was added for (aura-landing.css kept #71717a = 4.11:1 for
    footer/hero meta while arena/dashboard/report/pre re-pointed to #8e8e99).
    Assumes the dark design system: these tokens are text on the page bg or
    on rgba surfaces over it (the worst realistic case), never on light fills.
    """
    import re
    from pathlib import Path

    styles_dir = Path(__file__).resolve().parents[2] / "frontend" / "src" / "styles"
    failures = 0
    print("\nmuted token guard (--muted-2/--muted-3 >= 4.5:1 on bg):")
    for css in sorted(styles_dir.glob("*.css")):
        for m in re.finditer(r"--(muted-2|muted-3):\s*(#[0-9a-fA-F]{6})\s*;", css.read_text()):
            token, hexv = m.group(1), m.group(2)
            r = ratio(srgb(hexv), srgb(BG))
            ok = r >= 4.5
            failures += 0 if ok else 1
            print(f"  {'PASS' if ok else 'FAIL'}  {css.name} --{token} {hexv}  {r:4.2f}")
    return 1 if failures else 0


def main() -> int:
    failures = 0
    print(f"{'pair':52} {'ratio':>6}  need  verdict")
    for label, fg, bg, kind in PAIRS:
        need = 4.5 if kind == "text" else 3.0
        r = ratio(srgb(fg), bg if isinstance(bg, tuple) else srgb(bg))
        ok = r >= need
        failures += 0 if ok else 1
        print(f"{label:52} {r:6.2f}  {need:.1f}  {'PASS' if ok else 'FAIL'}")

    print("\nAA-passing candidates for the muted ladder (lightest that passes 4.5:1 on bg):")
    for name, opts in CANDIDATES.items():
        for hexv in opts:
            r = ratio(srgb(hexv), srgb(BG))
            mark = "PASS" if r >= 4.5 else "fail"
            print(f"  {name:26} {hexv}  {r:4.2f}  {mark}")
            if r >= 4.5:
                break
    failures += check_btn_primary_gradients()
    failures += check_muted_tokens()
    return 1 if failures else 0

if __name__ == "__main__":
    sys.exit(main())
