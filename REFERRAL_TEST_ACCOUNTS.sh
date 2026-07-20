#!/usr/bin/env bash
# AIR-0224 — Test account provisioning via the Supabase Admin API.
#
# WHY THIS IS A SEPARATE SCRIPT, NOT PART OF REFERRAL_TEST_FIXTURE.sql:
# profiles.id REFERENCES auth.users(id) ON DELETE CASCADE (auth-web/supabase_schema.sql:10).
# auth.users has many GoTrue-internal columns (encrypted password, confirmation
# tokens, etc.) that are fragile to hand-write correctly via raw SQL against a
# live production auth schema. This uses the exact same mechanism
# services/web_admin_client.py's create_auth_user() already uses for real
# signups (POST /auth/v1/admin/users) — not a new mechanism, just pointed at
# test data. The already-live on_auth_user_created trigger then creates each
# profiles row and sets referred_by from raw_user_meta_data.referred_by_id
# (AIR-0122, unmodified).
#
# NOT EXECUTED AS PART OF WRITING THIS FILE. Requires explicit go-ahead —
# see REFERRAL_E2E_TEST_PLAN.md §7 (this creates real auth.users rows, a
# shared system, even though they're clearly .test-tagged and fully
# reversible via cascade delete).
#
# Usage: SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY read from .env (same
# pattern used throughout this project's verification steps this session).
# Run from repo root: bash REFERRAL_TEST_ACCOUNTS.sh

set -euo pipefail

SUPABASE_URL=$(grep -oE '^NEXT_PUBLIC_SUPABASE_URL="?[^"]*' .env | sed -E 's/^[^=]+="?//')
SUPABASE_KEY=$(grep SUPABASE_SERVICE_ROLE_KEY .env | sed -E 's/^[^=]+="?//; s/"$//')

create_user() {
    local email="$1"
    local full_name="$2"
    local referred_by_id="$3"   # empty string for the root (Default Sponsor)

    local meta
    if [ -n "$referred_by_id" ]; then
        meta="{\"full_name\":\"${full_name}\",\"referred_by_id\":\"${referred_by_id}\",\"signup_source\":\"air_0224_e2e_fixture\"}"
    else
        meta="{\"full_name\":\"${full_name}\",\"signup_source\":\"air_0224_e2e_fixture\"}"
    fi

    curl -s -X POST "${SUPABASE_URL}/auth/v1/admin/users" \
        -H "apikey: ${SUPABASE_KEY}" -H "Authorization: Bearer ${SUPABASE_KEY}" \
        -H "Content-Type: application/json" \
        -d "{\"email\":\"${email}\",\"password\":\"$(openssl rand -hex 16 2>/dev/null || echo E2eTestFixture2026)\",\"email_confirm\":true,\"user_metadata\":${meta}}"
}

echo "--- Creating Default Sponsor ---"
DS_RESPONSE=$(create_user "e2e-default-sponsor@airqa.test" "E2E Default Sponsor" "")
DS_ID=$(echo "$DS_RESPONSE" | python -c "import json,sys; print(json.load(sys.stdin).get('id',''))")
echo "Default Sponsor id: $DS_ID"
[ -z "$DS_ID" ] && { echo "FAILED: $DS_RESPONSE"; exit 1; }

echo "--- Creating User A (referred_by = Default Sponsor) ---"
A_RESPONSE=$(create_user "e2e-user-a@airqa.test" "E2E User A" "$DS_ID")
A_ID=$(echo "$A_RESPONSE" | python -c "import json,sys; print(json.load(sys.stdin).get('id',''))")
echo "User A id: $A_ID"
[ -z "$A_ID" ] && { echo "FAILED: $A_RESPONSE"; exit 1; }

echo "--- Creating User B (referred_by = User A) ---"
B_RESPONSE=$(create_user "e2e-user-b@airqa.test" "E2E User B" "$A_ID")
B_ID=$(echo "$B_RESPONSE" | python -c "import json,sys; print(json.load(sys.stdin).get('id',''))")
echo "User B id: $B_ID"
[ -z "$B_ID" ] && { echo "FAILED: $B_RESPONSE"; exit 1; }

echo "--- Creating User C (referred_by = User B) ---"
C_RESPONSE=$(create_user "e2e-user-c@airqa.test" "E2E User C" "$B_ID")
C_ID=$(echo "$C_RESPONSE" | python -c "import json,sys; print(json.load(sys.stdin).get('id',''))")
echo "User C id: $C_ID"
[ -z "$C_ID" ] && { echo "FAILED: $C_RESPONSE"; exit 1; }

echo
echo "=== Account IDs (feed these into REFERRAL_TEST_FIXTURE.sql's variables, or verify the fixture's by-email lookups resolve correctly) ==="
echo "DEFAULT_SPONSOR_ID=$DS_ID"
echo "USER_A_ID=$A_ID"
echo "USER_B_ID=$B_ID"
echo "USER_C_ID=$C_ID"

echo
echo "--- Setting referral_code + country on each profile (deterministic values for the fixture) ---"
patch_profile() {
    local id="$1" code="$2" country="$3"
    curl -s -X PATCH "${SUPABASE_URL}/rest/v1/profiles?id=eq.${id}" \
        -H "apikey: ${SUPABASE_KEY}" -H "Authorization: Bearer ${SUPABASE_KEY}" \
        -H "Content-Type: application/json" -H "Prefer: return=minimal" \
        -d "{\"referral_code\":\"${code}\",\"my_referral_code\":\"${code}\",\"country_code\":\"${country}\",\"referral_country\":\"${country}\"}"
}
patch_profile "$DS_ID" "E2ETESTDS" "KR"
patch_profile "$A_ID"  "E2ETESTA"  "KR"
patch_profile "$B_ID"  "E2ETESTB"  "US"
patch_profile "$C_ID"  "E2ETESTC"  "US"
echo "Done."

echo
echo "=== TEARDOWN (run when finished with E2E testing) ==="
echo "# IMPORTANT: referral_audit_logs does NOT cascade-delete (entity_id has no FK,"
echo "# actor_id is ON DELETE SET NULL not CASCADE) — delete those FIRST, by the"
echo "# air_0224_fixture metadata tag every fixture-inserted row carries:"
echo "#   DELETE FROM public.referral_audit_logs WHERE metadata->>'air_0224_fixture' = 'true';"
echo "# referral_commissions (beneficiary_id ON DELETE CASCADE) and referral_withdrawals"
echo "# (user_id ON DELETE CASCADE) DO cascade-delete once the accounts below are removed."
echo "for ID in $DS_ID $A_ID $B_ID $C_ID; do"
echo "  curl -s -X DELETE \"\${SUPABASE_URL}/auth/v1/admin/users/\$ID\" -H \"apikey: \${SUPABASE_KEY}\" -H \"Authorization: Bearer \${SUPABASE_KEY}\""
echo "done"
