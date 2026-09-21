# Aura UX Review — Walkthrough Findings

Method: interactive walkthroughs at 1920×1080 (candidate upload flow, recruiter
invite build → create → cancel, candidate invite edge states) plus a 390×844
mobile pass over the core pages, all against the live site with real accounts.
Evidence: `shots/ux__*.png` and `shots/m__*.png`.

## What's genuinely good

- **Invite builder**: valid-state discipline throughout — "Prepare/Create"
  buttons disabled until inputs are valid, a `QUESTIONS (2 / 5)` counter,
  expiry presets (4h/24h/3d/7d) with explanatory microcopy ("The candidate must
  start the interview within this window — after it passes the link stops
  working").
- **Post-create screen is textbook**: "Send the private link." — copyable link
  field, big Copy action, expiry spelled out as a date ("This link stops
  working Sep 21, 2026, 06:10 PM."), and Back-to-dashboard / Create-another
  next actions.
- **Destructive actions are guarded**: cancelling an invite raises a native
  confirm naming the invite and the consequence ("Cancel 'Senior Backend
  Engineer'? Its link will stop working.").
- **Edge states are graceful**: cancelled invite → "Invite unavailable — This
  invite was cancelled"; bogus token → "Invite not found"; both keep the
  "Interview invitation / Ready when you are." framing and give a way out
  ("Go home"). No dead ends.
- **Upload flow sets expectations**: dropzone states constraints ("PDF only ·
  max 10 MB"), Prepare stays disabled until a file is chosen, and the plan step
  ("Step 2 — Plan / Ready when you are.") shows who was parsed, identified
  skills, and the honest "Voice interview · approx. 10–15 min" before any
  commitment.
- **Candidate funnel is mobile-clean**: at 390×844 the landing, login, invite
  preview, upload, interviews list and report view have **zero horizontal
  overflow**.
- **No dark patterns anywhere** in the flows walked; zero JS/console errors
  across the entire walkthrough.

## Problems (by severity)

### Errors

1. **Broken app header on the `aura-pre.css` pages** — on InviteBuilder,
   RecruiterProfile, CandidateProfile (and RolePicker, same construction) the
   full app header renders with **no spacing between nav links**
   ("New interviewMy interviewsRecruiterProfile"), an oversized avatar that
   overflows its pill, and clipped elements at the top edge. Root cause: these
   four pages import `@/styles/aura-pre.css` (the landing/pre-app stylesheet)
   while rendering the AppHeader that is designed against the dashboard
   stylesheet — `RecruiterDashboard`/`CandidateSessionReport` etc. render the
   same header correctly. Evidence: `shots/ux__rec-builder-filled.png`,
   `shots/rec__profile.png`, `shots/cand__profile.png` (vs. correct header in
   `shots/rec__dashboard.png`). Fix: give these pages the dashboard page class
   or port the header styles into `aura-pre.css`.

2. **Recruiter + Admin dashboards overflow horizontally on mobile** — at
   390×844 both dashboards scroll sideways (measured `scrollWidth >
   innerWidth`): the interviews table keeps its desktop column set. On a phone
   a recruiter must pan to reach status/actions. Evidence:
   `shots/m__rec-dashboard.png`, `shots/m__adm-dashboard.png`. Fix: responsive
   table (card-per-row under a breakpoint) or a scroll container with a sticky
   identifying column.

### Warnings

3. ~~Silently disabled primary buttons~~ — **corrected during the fix pass**:
   the builder already renders "Add a role name and 2–5 non-empty questions
   to continue." under the disabled button; the walkthrough missed it because
   it sits below the 1080px fold. No code change needed.
4. **Every screen shares one browser-tab title** (also in the scored report's
   SEO findings) — during the walkthrough, every tab/history entry read
   "Aura — AI Interviewer".

### Notices

5. The plan step says "Here's what Aura will explore" but shows only skill
   pills — showing the question count or the questions themselves would match
   the copy.
6. User name wraps under the avatar in the mobile header
   (`shots/m__rec-dashboard.png`).

## Walkthrough coverage

| Flow | Steps exercised | Result |
|---|---|---|
| Recruiter: build invite | fill role/context/3 questions, expiry presets | works (see error 1 for header; warning 3 for silent disable) |
| Recruiter: create invite | Create → success screen with link | works |
| Recruiter: cancel invite | Cancel → confirm dialog → dashboard status | works |
| Candidate: cancelled invite | open cancelled link | graceful "cancelled" state |
| Candidate: bogus token | open invalid link | graceful "not found" state |
| Candidate: upload → plan | real PDF, real parser run (~20 s) → plan screen | works; stopped before voice join |
| Mobile 390×844 | landing, login, invite preview, upload, list, report, recruiter, admin | candidate pages clean; dashboards overflow |

Prod data touched: one cancelled invite, one pending invite
("Mobile Preview Test"), one pending practice session — all inside the audit
test accounts.
