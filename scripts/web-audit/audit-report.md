# Aura Web Audit Report

**Overall score: 38.5/100 (grade F)** — target: `https://aura.techa.pro`

> **Baseline snapshot — this is the BEFORE.** Scores, headers and findings below were measured
> on 2026-09-20 against the pre-fix site; they document what motivated the fixes, not the
> current state. Re-run `audit.sh` + the helper scripts for the after score. The raw
> `results/` and `shots/` corpora are intentionally untracked — they carry production URLs
> and row IDs, and page identifiers below are redacted accordingly.

| Category | Weight | Score |
|---|---|---|
| a11y | 30% | 0.0 |
| integrity | 25% | 100.0 |
| seo | 15% | 0.0 |
| perf | 15% | 75.0 |
| headers | 15% | 15.0 |

**Findings:** 12 errors · 20 warnings · 4 notices — across 17 audited page states

> Perf numbers are repeat-visit (warm browser cache): in-page transferSize only counts cache misses. Real bundle weights were measured out-of-band with curl: see `results/bundle.json`.

## Findings

### Errors (fix first) (12)
- **[a11y] 5 pages** — Elements must meet minimum color contrast ratio thresholds (1 nodes)
  rule=color-contrast tags=['wcag2aa', 'wcag143'] targets=button evidence=shots/pub__forgot.png
  pages: pub__forgot, pub__login, pub__reset, rec__invite-builder, rec__profile
- **[a11y] adm__admin-dashboard** — Elements must meet minimum color contrast ratio thresholds (2 nodes)
  rule=color-contrast tags=['wcag2aa', 'wcag143'] targets=.active[role="tab"]; .active[type="button"] evidence=shots/adm__admin-dashboard.png
- **[a11y] adm__admin-session** — Elements must meet minimum color contrast ratio thresholds (20 nodes)
  rule=color-contrast tags=['wcag2aa', 'wcag143'] targets=.active[type="button"]; .page-eyebrow > span:nth-child(3); .rubric-row:nth-child(1) > .rubric-meter > .meter-foot > span:nth-child(2) evidence=shots/adm__admin-session.png
- **[a11y] cand__report** — Certain ARIA roles must contain particular children (1 nodes)
  rule=aria-required-children tags=['wcag2a', 'wcag131'] targets=.filter-bar evidence=shots/cand__report.png
- **[a11y] cand__report** — Elements must meet minimum color contrast ratio thresholds (11 nodes)
  rule=color-contrast tags=['wcag2aa', 'wcag143'] targets=.action-meta > span:nth-child(1); .action-meta > span:nth-child(3); .rubric-row:nth-child(1) > .rubric-meter > .meter-foot > span:nth-child(2) evidence=shots/cand__report.png
- **[a11y] pub__home** — Elements must meet minimum color contrast ratio thresholds (2 nodes)
  rule=color-contrast tags=['wcag2aa', 'wcag143'] targets=.footer-row > .footer-meta; .footer-row > div:nth-child(1) > .footer-meta evidence=shots/pub__home.png
- **[a11y] rec__dashboard** — Elements must meet minimum color contrast ratio thresholds (3 nodes)
  rule=color-contrast tags=['wcag2aa', 'wcag143'] targets=.active[type="button"]; tr:nth-child(2) > td:nth-child(4) > .pill-muted.pill; tr:nth-child(3) > td:nth-child(4) > .pill-muted.pill evidence=shots/rec__dashboard.png
- **[a11y] rec__invite-detail** — Elements must meet minimum color contrast ratio thresholds (10 nodes)
  rule=color-contrast tags=['wcag2aa', 'wcag143'] targets=.action-meta > span:nth-child(1); .action-meta > span:nth-child(3); .rubric-row:nth-child(1) > .rubric-meter > .meter-foot > span:nth-child(2) evidence=shots/rec__invite-detail.png
- **[backend] POST /invite/{token}/start** — Recruiter invite redemption 500s in production (FK violation)
  redeem_invite's atomic claim UPDATE writes interview_invites.session_id before the interview_sessions row exists; Postgres enforces interview_invites_session_id_fkey immediately, so every /invite/{token}/start returns 500 and no recruiter invite can be redeemed. Shipped on SQLite, which does not enforce FKs by default; broken since the Postgres cutover (commit d89b63b). Reproduced twice via the live API (Sentry event ids redacted) and in-container with a full traceback. Fix direction: drop the FK (the column is a forward pointer by design) or split the claim into candidate-bind + post-session-link steps; needs a migration plus a regression test on Postgres.
- **[headers] all pages** — Missing content-security-policy header
- **[headers] all pages** — Missing strict-transport-security header
- **[perf] all pages** — Main JS bundle is 1203 KB served uncompressed
  Vite emits one index-*.js (code-splitting would shrink it; gzip/brotli at nginx would cut ~70% on the wire). See results/bundle.json.

### Warnings (20)
- **[a11y] 4 pages** — Document should have one main landmark (1 nodes)
  rule=landmark-one-main tags=['best-practice'] targets=html evidence=shots/pub__forgot.png
  pages: pub__forgot, pub__home, pub__login, pub__reset
- **[a11y] adm__admin-session** — Main landmark should not be contained in another landmark (1 nodes)
  rule=landmark-main-is-top-level tags=['best-practice'] targets=div:nth-child(4) > main evidence=shots/adm__admin-session.png
- **[a11y] adm__admin-session** — Document should not have more than one main landmark (1 nodes)
  rule=landmark-no-duplicate-main tags=['best-practice'] targets=.aura-dashboard-page > main evidence=shots/adm__admin-session.png
- **[a11y] adm__admin-session** — Landmarks should have a unique role or role/label/title (i.e. accessible name) combination (2 nodes)
  rule=landmark-unique tags=['best-practice'] targets=.aura-dashboard-page > main; .aura-dashboard-page > nav evidence=shots/adm__admin-session.png
- **[a11y] cand__report** — Main landmark should not be contained in another landmark (1 nodes)
  rule=landmark-main-is-top-level tags=['best-practice'] targets=div:nth-child(4) > main evidence=shots/cand__report.png
- **[a11y] cand__report** — Document should not have more than one main landmark (1 nodes)
  rule=landmark-no-duplicate-main tags=['best-practice'] targets=.aura-dashboard-page > main evidence=shots/cand__report.png
- **[a11y] cand__report** — Landmarks should have a unique role or role/label/title (i.e. accessible name) combination (2 nodes)
  rule=landmark-unique tags=['best-practice'] targets=.aura-dashboard-page > main; .aura-dashboard-page > nav evidence=shots/cand__report.png
- **[a11y] pub__forgot** — All page content should be contained by landmarks (5 nodes)
  rule=region tags=['best-practice'] targets=.mb-8; .mt-6.text-muted-foreground.text-sm; h1 evidence=shots/pub__forgot.png
- **[a11y] pub__login** — All page content should be contained by landmarks (8 nodes)
  rule=region tags=['best-practice'] targets=.mb-8; .mt-6.text-muted-foreground.text-sm; .my-5 evidence=shots/pub__login.png
- **[a11y] pub__reset** — All page content should be contained by landmarks (6 nodes)
  rule=region tags=['best-practice'] targets=.mb-8; .mt-6.text-muted-foreground; h1 evidence=shots/pub__reset.png
- **[backend] backend observability** — Unhandled-exception tracebacks never reach the container logs
  The 500 above was invisible in `docker logs aura-backend` — api/error_handlers.py logs via logging.getLogger('api.errors').error(exc_info=True), but uvicorn's default dictConfig configures no root handler, so the record is dropped. Sentry receives events, but the response error_id is a fresh uuid4 that does not match the Sentry event id, so correlation from the client side is impossible. Fix direction: attach a root/stderr handler at startup, or log through the uvicorn.error logger.
- **[headers] all pages** — Missing x-frame-options header
- **[headers] all pages** — Missing x-content-type-options header
- **[headers] all pages** — Missing referrer-policy header
- **[headers] all pages** — HTML served without compression
- **[perf] all pages** — CSS bundle is 124 KB
- **[seo] 17 pages** — Missing og:title
  
  pages: adm__admin-dashboard, adm__admin-session, cand__interview, cand__invite-candidate, cand__my-interviews, cand__profile, cand__report, pub__forgot, pub__home, pub__invite-public, pub__login, pub__notfound, pub__reset, rec__dashboard, rec__invite-builder, rec__invite-detail, rec__profile
- **[seo] 17 pages** — Missing og:image
  
  pages: adm__admin-dashboard, adm__admin-session, cand__interview, cand__invite-candidate, cand__my-interviews, cand__profile, cand__report, pub__forgot, pub__home, pub__invite-public, pub__login, pub__notfound, pub__reset, rec__dashboard, rec__invite-builder, rec__invite-detail, rec__profile
- **[seo] adm__admin-session** — Multiple <h1> (2)
- **[seo] all pages** — Every route serves the same static <title> ("Aura — AI Interviewer")
  The SPA never updates document.title per route; browser tabs, history, bookmarks and search results all read identically. Set a per-route title (and description) in each page component.

### Notices (4)
- **[a11y] 14 pages** — needs manual check: Elements must meet minimum color contrast ratio thresholds
  rule=color-contrast nodes=35
  pages: adm__admin-dashboard, adm__admin-session, cand__interview, cand__invite-candidate, cand__my-interviews, cand__profile, cand__report, pub__home, pub__invite-public, pub__notfound, rec__dashboard, rec__invite-builder, rec__invite-detail, rec__profile
- **[a11y] 5 pages** — needs manual check: Elements must only use permitted ARIA attributes
  rule=aria-prohibited-attr nodes=1
  pages: adm__admin-dashboard, adm__admin-session, cand__report, rec__dashboard, rec__invite-detail
- **[headers] all pages** — Missing permissions-policy header
- **[seo] 17 pages** — No canonical URL
  
  pages: adm__admin-dashboard, adm__admin-session, cand__interview, cand__invite-candidate, cand__my-interviews, cand__profile, cand__report, pub__forgot, pub__home, pub__invite-public, pub__login, pub__notfound, pub__reset, rec__dashboard, rec__invite-builder, rec__invite-detail, rec__profile

## Page inventory

| Page | Persona | Title | Errors | axe violations | Transfer KB |
|---|---|---|---|---|---|
| `/admin` | adm | Aura — AI Interviewer | 0 | 1 | 2 |
| `/admin/session/<session-id>` | adm | Aura — AI Interviewer | 0 | 4 | 4 |
| `/interview` | cand | Aura — AI Interviewer | 0 | 0 | 1 |
| `/invite/<invite-token>` | cand | Aura — AI Interviewer | 0 | 0 | 2 |
| `/my-interviews` | cand | Aura — AI Interviewer | 0 | 0 | 2 |
| `/profile/candidate` | cand | Aura — AI Interviewer | 0 | 0 | 2 |
| `/my-interviews/<session-id>` | cand | Aura — AI Interviewer | 0 | 5 | 4 |
| `/forgot-password` | pub | Aura — AI Interviewer | 0 | 3 | 1 |
| `/` | pub | Aura — AI Interviewer | 0 | 2 | 1 |
| `/invite/<invite-token>` | pub | Aura — AI Interviewer | 0 | 0 | 1 |
| `/login` | pub | Aura — AI Interviewer | 0 | 3 | 1 |
| `/this-page-does-not-exist` | pub | Aura — AI Interviewer | 0 | 0 | 1 |
| `/reset-password?token=audit-expired-token` | pub | Aura — AI Interviewer | 0 | 3 | 1 |
| `/recruiter` | rec | Aura — AI Interviewer | 0 | 1 | 3 |
| `/recruiter/new` | rec | Aura — AI Interviewer | 0 | 1 | 2 |
| `/recruiter/invites/<invite-id>` | rec | Aura — AI Interviewer | 0 | 1 | 5 |
| `/profile/recruiter` | rec | Aura — AI Interviewer | 0 | 1 | 2 |

## Screenshots

- `adm__admin-dashboard`: shots/adm__admin-dashboard.png
- `adm__admin-dashboard`: shots/adm__admin-dashboard.full.png
- `adm__admin-session`: shots/adm__admin-session.png
- `adm__admin-session`: shots/adm__admin-session.full.png
- `cand__interview`: shots/cand__interview.png
- `cand__interview`: shots/cand__interview.full.png
- `cand__invite-candidate`: shots/cand__invite-candidate.png
- `cand__invite-candidate`: shots/cand__invite-candidate.full.png
- `cand__my-interviews`: shots/cand__my-interviews.png
- `cand__my-interviews`: shots/cand__my-interviews.full.png
- `cand__profile`: shots/cand__profile.png
- `cand__profile`: shots/cand__profile.full.png
- `cand__report`: shots/cand__report.png
- `cand__report`: shots/cand__report.full.png
- `pub__forgot`: shots/pub__forgot.png
- `pub__forgot`: shots/pub__forgot.full.png
- `pub__home`: shots/pub__home.png
- `pub__home`: shots/pub__home.full.png
- `pub__invite-public`: shots/pub__invite-public.png
- `pub__invite-public`: shots/pub__invite-public.full.png
- `pub__login`: shots/pub__login.png
- `pub__login`: shots/pub__login.full.png
- `pub__notfound`: shots/pub__notfound.png
- `pub__notfound`: shots/pub__notfound.full.png
- `pub__reset`: shots/pub__reset.png
- `pub__reset`: shots/pub__reset.full.png
- `rec__dashboard`: shots/rec__dashboard.png
- `rec__dashboard`: shots/rec__dashboard.full.png
- `rec__invite-builder`: shots/rec__invite-builder.png
- `rec__invite-builder`: shots/rec__invite-builder.full.png
- `rec__invite-detail`: shots/rec__invite-detail.png
- `rec__invite-detail`: shots/rec__invite-detail.full.png
- `rec__profile`: shots/rec__profile.png
- `rec__profile`: shots/rec__profile.full.png

## UX review

A qualitative UX walkthrough (flows, edge states, mobile 390×844) was run
separately from the scored rule audit — see **[ux-findings.md](ux-findings.md)**.
Headline: two UX errors found (broken app header on the four `aura-pre.css`
pages; recruiter/admin dashboards overflow horizontally on phones), otherwise
the flows, guardrails and edge states are notably well built.
