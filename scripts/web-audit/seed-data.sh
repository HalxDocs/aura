#!/usr/bin/env bash
# Seed the production data the audit needs:
#   1. a recruiter invite (3 custom questions)          — via the live API
#   2. the candidate's interview session                — via SQL (see NOTE)
#   3. admin writes a fabricated report + transcript    — via the live API
#
# NOTE: step 2 bypasses the API because the endpoint's claim-then-create flow
# spends a recruiter's monthly quota on the session it creates, while the
# audit wants a reusable throwaway session that doesn't burn quota. Going
# through SQL here keeps the audit data reproducible and quota-free. The
# FK on interview_invites.session_id is DEFERRABLE INITIALLY DEFERRED
# (migration e7f8a9b0c1d2), so this INSERT-then-claim order is valid on
# Postgres too — both rows land before the script's implicit commit.
#
# JWTs come from the already-logged-in agent-browser sessions (localStorage),
# so no /auth/login calls are spent. IDs land in state/seed.json.
#
# This script MUTATES its target environment (creates rows, writes reports).
# Nothing is defaulted: exporting AURA_BASE_URL and AURA_ENV_FILE is the
# explicit "yes, that environment" signal, so a stray run can't touch prod.
set -euo pipefail

cd "$(dirname "$0")"
BASE="${AURA_BASE_URL:?Set AURA_BASE_URL to the API base (e.g. export AURA_BASE_URL=https://aura.techa.pro/api) — this script mutates that environment}"
ENV_FILE="${AURA_ENV_FILE:?Set AURA_ENV_FILE to the deployment .env holding DATABASE_URL (e.g. export AURA_ENV_FILE=/home/ubuntu/aura/.env)}"
PG_CONTAINER="${AURA_PG_CONTAINER:-my_postgres_db}"
SITE_ORIGIN="${BASE%/api}"

db_user=$(sed -nE 's|^DATABASE_URL=postgresql\+asyncpg://([^:]+):.*|\1|p' "$ENV_FILE")
db_name=$(sed -nE 's|^DATABASE_URL=postgresql\+asyncpg://[^@]+@[^/]+/||p' "$ENV_FILE")
psql() { docker exec -i "$PG_CONTAINER" psql -U "$db_user" -d "$db_name" -qtA; }

tok() { agent-browser --session "$1" eval "localStorage.getItem('aura_token')" | tr -d '"'; }

REC=$(tok rec); CAND=$(tok cand); ADM=$(tok adm)
[[ -n "$REC" && -n "$CAND" && -n "$ADM" ]] || { echo "missing JWT from a session" >&2; exit 1; }

# --- 1. recruiter creates the invite ---
INVITE=$(curl -s -X POST "$BASE/recruiter/invites" \
  -H "Authorization: Bearer $REC" -H 'Content-Type: application/json' \
  -d '{
    "title": "Aura Web Audit Interview",
    "context": "Sample context for the audit run. Exercises the invite preview and interview flow.",
    "questions": [
      "Tell me about a project you are proud of and your role in it.",
      "How do you approach debugging a problem you cannot reproduce?",
      "Where do you want to grow in the next two years?"
    ]
  }')
INVITE_ID=$(echo "$INVITE" | python3 -c 'import json,sys;print(json.load(sys.stdin)["invite_id"])')
INVITE_TOKEN=$(echo "$INVITE" | python3 -c 'import json,sys;print(json.load(sys.stdin)["token"])')

# --- 2. session row + invite claim via SQL (see NOTE) ---
# psql variables + :'var' quoting: an apostrophe in any seeded string stays a
# literal instead of breaking (or rewriting) the statement.
SESSION_ID=$(python3 -c 'import uuid;print(uuid.uuid4())')
PLAN_JSON=$(python3 - <<'PY'
import json
print(json.dumps({
    "candidate_name": "Audit Candidate",
    "extracted_skills": [],
    "question_bank": [
        "Tell me about a project you are proud of and your role in it.",
        "How do you approach debugging a problem you cannot reproduce?",
        "Where do you want to grow in the next two years?",
    ],
    "job_description": "Sample context for the audit run. Exercises the invite preview and interview flow.",
}))
PY
)

SQL_OUT=$(psql \
  -v session_id="$SESSION_ID" \
  -v invite_id="$INVITE_ID" \
  -v plan_json="$PLAN_JSON" \
  -v cand_email='aura-audit-candidate@example.com' <<'SQL'
INSERT INTO interview_sessions (id, user_id, candidate_name, plan_json, status, created_at)
SELECT :'session_id', u.id, 'Audit Candidate', :'plan_json', 'pending', now()
  FROM users u WHERE u.email = :'cand_email';

UPDATE interview_invites
   SET candidate_user_id = (SELECT id FROM users WHERE email = :'cand_email'),
       session_id = :'session_id',
       redeemed_at = now()
 WHERE id = :'invite_id' AND status = 'pending';
SQL
)
echo "sql seed: $SQL_OUT" | tr '\n' ' '; echo

# --- 3. admin writes the report + transcript (real API path) ---
curl -s -X POST "$BASE/report/$SESSION_ID" \
  -H "Authorization: Bearer $ADM" -H 'Content-Type: application/json' \
  -d '{
    "candidate_name": "Audit Candidate",
    "overall_score": 78,
    "section_grades": [
      {"section_name": "Technical", "score": 8, "comments": "Clear reasoning on architecture trade-offs; solid debugging methodology."},
      {"section_name": "Behavioral", "score": 7, "comments": "Concrete examples, well structured; could quantify impact more."},
      {"section_name": "Growth", "score": 8, "comments": "Focused learning goals aligned with the role."}
    ],
    "strengths": [
      "Explains technical trade-offs clearly",
      "Structured problem-solving approach",
      "Concrete project examples"
    ],
    "weaknesses": [
      "Occasionally over-explains context before answering",
      "Impact metrics were vague"
    ],
    "recommendation": "Hire",
    "summary": "A balanced interview covering technical depth, collaboration and growth. The candidate demonstrated strong fundamentals with room to sharpen impact storytelling."
  }' > /dev/null

curl -s -X POST "$BASE/transcript/$SESSION_ID" \
  -H "Authorization: Bearer $ADM" -H 'Content-Type: application/json' \
  -d '{
    "candidate_name": "Audit Candidate",
    "entries": [
      {"speaker": "interviewer", "text": "Welcome! Let us start: tell me about a project you are proud of and your role in it.", "timestamp_s": 0.0},
      {"speaker": "candidate", "text": "I led the migration of a monolith to three services, owning the decomposition plan and rollout.", "timestamp_s": 6.0},
      {"speaker": "interviewer", "text": "How do you approach debugging a problem you cannot reproduce?", "timestamp_s": 30.0},
      {"speaker": "candidate", "text": "I start with observability: logs, metrics, traces, then binary-search the variables around the failure window.", "timestamp_s": 38.0},
      {"speaker": "interviewer", "text": "Where do you want to grow in the next two years?", "timestamp_s": 66.0},
      {"speaker": "candidate", "text": "Distributed systems depth and leading a small team.", "timestamp_s": 72.0}
    ]
  }' > /dev/null

cat > state/seed.json <<EOF
{
  "invite_id": "$INVITE_ID",
  "invite_token": "$INVITE_TOKEN",
  "session_id": "$SESSION_ID",
  "invite_url": "$SITE_ORIGIN/invite/$INVITE_TOKEN",
  "note": "session row created via SQL (see NOTE at the top of seed-data.sh)"
}
EOF
echo "seeded:"
echo "  invite:   $INVITE_ID"
echo "  session:  $SESSION_ID"
echo "  invite_url: $SITE_ORIGIN/invite/$INVITE_TOKEN"
psql -v invite_id="$INVITE_ID" -v session_id="$SESSION_ID" <<'SQL'
SELECT status, candidate_user_id IS NOT NULL AS claimed, session_id IS NOT NULL AS linked FROM interview_invites WHERE id = :'invite_id';
SELECT status, completed_at IS NOT NULL AS has_completed_at FROM interview_sessions WHERE id = :'session_id';
SQL
