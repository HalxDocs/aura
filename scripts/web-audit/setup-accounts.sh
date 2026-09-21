#!/usr/bin/env bash
# One-time seeding of audit accounts in the target database.
#
# Creates three clearly-named accounts via the live API (so password hashing
# and any register-side effects follow the normal path), then flips the
# account flags directly in Postgres: email verification (registration
# emails go to example.com dummies that can never be clicked) and the
# role/capability each persona needs for the audit.
#
# Credentials are written to state/creds.json (gitignored), never echoed.
#
# This script MUTATES its target environment (creates accounts, grants roles —
# including an admin). Nothing is defaulted: exporting AURA_BASE_URL and
# AURA_ENV_FILE is the explicit "yes, that environment" signal, so a stray
# run can't touch prod.
set -euo pipefail

cd "$(dirname "$0")"
BASE="${AURA_BASE_URL:?Set AURA_BASE_URL to the API base (e.g. export AURA_BASE_URL=https://aura.techa.pro/api) — this script mutates that environment}"
ENV_FILE="${AURA_ENV_FILE:?Set AURA_ENV_FILE to the deployment .env holding DATABASE_URL (e.g. export AURA_ENV_FILE=/home/ubuntu/aura/.env)}"
PG_CONTAINER="${AURA_PG_CONTAINER:-my_postgres_db}"

# --- resolve the Postgres user/database from DATABASE_URL (values stay local) ---
db_user=$(sed -nE 's|^DATABASE_URL=postgresql\+asyncpg://([^:]+):.*|\1|p' "$ENV_FILE")
db_name=$(sed -nE 's|^DATABASE_URL=postgresql\+asyncpg://[^@]+@[^/]+/||p' "$ENV_FILE")
[[ -n "$db_user" && -n "$db_name" ]] || { echo "cannot parse DATABASE_URL from $ENV_FILE" >&2; exit 1; }

# Pass-through so callers can supply psql -v variables; SQL values go in as
# :'var' literals rather than interpolated into the statement text.
psql() { docker exec -i "$PG_CONTAINER" psql -U "$db_user" -d "$db_name" -qtA "$@"; }

# --- accounts: email|name|role|is_recruiter ---
ACCOUNTS=(
  "aura-audit-candidate@example.com|Audit Candidate|candidate|false"
  "aura-audit-recruiter@example.com|Audit Recruiter|recruiter|true"
  "aura-audit-admin@example.com|Audit Admin|admin|true"
)

creds_file="state/creds.json"
echo "{" > "$creds_file"

first=true
for row in "${ACCOUNTS[@]}"; do
  IFS='|' read -r email name role recruiter <<<"$row"
  password=$(openssl rand -hex 16)

  status=$(curl -s -o /tmp/register-resp.json -w "%{http_code}" \
    -X POST "$BASE/auth/register" -H 'Content-Type: application/json' \
    -d "{\"email\":\"$email\",\"password\":\"$password\",\"name\":\"$name\"}")
  if [[ "$status" != "200" && "$status" != "201" ]]; then
    echo "register failed for $email (HTTP $status):" >&2
    cat /tmp/register-resp.json >&2
    exit 1
  fi

  recruiter_sql="false"; [[ "$recruiter" == "true" ]] && recruiter_sql="true"
  updated=$(psql -v email="$email" -v role="$role" -v recruiter="$recruiter_sql" <<'SQL'
UPDATE users
   SET email_verified = true,
       role = :'role',
       is_recruiter = :'recruiter'::boolean
 WHERE email = :'email'
RETURNING id;
SQL
)
  [[ -n "$updated" ]] || { echo "user row not found for $email after register" >&2; exit 1; }

  $first || echo "," >> "$creds_file"; first=false
  printf '  "%s": {"email": "%s", "password": "%s", "user_id": "%s", "role": "%s"}\n' \
    "$role" "$email" "$password" "$updated" "$role" >> "$creds_file"
  echo "seeded: $email (role=$role)"
done

echo "}" >> "$creds_file"
chmod 600 "$creds_file"
echo "--- db check ---"
psql <<'SQL'
SELECT email, role, is_recruiter, email_verified FROM users WHERE email LIKE 'aura-audit-%' ORDER BY email;
SQL
