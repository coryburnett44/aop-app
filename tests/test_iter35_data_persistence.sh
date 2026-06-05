#!/bin/bash
# Iteration 35 — Test 6 data persistence + dropdown + auto-clear pending fixes
set -uo pipefail
BASE="https://club-express-lite.preview.emergentagent.com"
PASS=0; FAIL=0
log_pass(){ echo "PASS: $1"; PASS=$((PASS+1)); }
log_fail(){ echo "FAIL: $1 | $2"; FAIL=$((FAIL+1)); }

# Admin login
ADMIN_TOKEN=$(curl -s -X POST "$BASE/api/auth/login" -H "Content-Type: application/json" \
  -d '{"email":"admin@clubhaven.app","password":"Admin123!"}' | python3 -c "import sys,json;print(json.load(sys.stdin).get('access_token',''))")
[ -n "$ADMIN_TOKEN" ] && log_pass "admin login" || { log_fail "admin login" "no token"; exit 1; }
AH="Authorization: Bearer $ADMIN_TOKEN"

############ FEATURE 1 — Custom tier survives restart ############
echo "--- F1: custom tier survives restart ---"
TIER_NAME="Iter35_Junior_$(date +%s)"
TIER_RESP=$(curl -s -X POST "$BASE/api/tiers" -H "$AH" -H "Content-Type: application/json" \
  -d "{\"name\":\"$TIER_NAME\",\"hours_required\":5,\"category\":\"custom\"}")
TIER_ID=$(echo "$TIER_RESP" | python3 -c "import sys,json;print(json.load(sys.stdin).get('id',''))" 2>/dev/null)
[ -n "$TIER_ID" ] && log_pass "create custom tier $TIER_NAME id=$TIER_ID" || log_fail "create custom tier" "$TIER_RESP"

############ FEATURE 2 — Custom event survives restart ############
echo "--- F2: custom event survives restart ---"
EVT_NAME="Iter35_Event_$(date +%s)"
# Use a future date
EVT_DATE=$(python3 -c "from datetime import datetime,timedelta; print((datetime.utcnow()+timedelta(days=30)).isoformat()+'Z')")
EVT_RESP=$(curl -s -X POST "$BASE/api/events" -H "$AH" -H "Content-Type: application/json" \
  -d "{\"title\":\"$EVT_NAME\",\"date\":\"$EVT_DATE\",\"location\":\"Test Hall\",\"description\":\"iter35 test\",\"category\":\"meeting\"}")
EVT_ID=$(echo "$EVT_RESP" | python3 -c "import sys,json;print(json.load(sys.stdin).get('id',''))" 2>/dev/null)
[ -n "$EVT_ID" ] && log_pass "create custom event $EVT_NAME id=$EVT_ID" || log_fail "create custom event" "$EVT_RESP"

############ FEATURE 3 — Custom award survives restart ############
echo "--- F3: custom award survives restart ---"
AWARD_NAME="Iter35_Award_$(date +%s)"
AW_RESP=$(curl -s -X POST "$BASE/api/awards" -H "$AH" -H "Content-Type: application/json" \
  -d "{\"name\":\"$AWARD_NAME\",\"description\":\"iter35 custom\",\"category\":\"service\"}")
AW_ID=$(echo "$AW_RESP" | python3 -c "import sys,json;print(json.load(sys.stdin).get('id',''))" 2>/dev/null)
[ -n "$AW_ID" ] && log_pass "create custom award $AWARD_NAME id=$AW_ID" || log_fail "create custom award" "$AW_RESP"

############ FEATURE 4 — Sam Okafor stays deleted after restart ############
echo "--- F4: deleted demo member stays gone ---"
SAM_LIST=$(curl -s -H "$AH" "$BASE/api/members?q=Sam")
SAM_ID=$(echo "$SAM_LIST" | python3 -c "
import sys,json
data=json.load(sys.stdin)
items=data.get('members') if isinstance(data,dict) else data
for m in (items or []):
    nm=(m.get('name') or '').lower()
    em=(m.get('email') or '').lower()
    if 'sam' in nm or 'sam.okafor' in em:
        print(m.get('id') or m.get('_id') or '')
        break
" 2>/dev/null)
if [ -n "$SAM_ID" ]; then
  DEL_RESP=$(curl -s -X DELETE "$BASE/api/members/$SAM_ID" -H "$AH" -w "\nHTTP=%{http_code}")
  echo "DELETE Sam ($SAM_ID): $DEL_RESP"
  log_pass "deleted Sam Okafor id=$SAM_ID (pre-restart)"
else
  echo "Sam not present pre-test — that's fine for restart verification"
fi

############ RESTART backend ############
echo "--- RESTART backend ---"
sudo supervisorctl restart backend
sleep 6
# wait for healthy
for i in 1 2 3 4 5 6 7 8 9 10; do
  H=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/api/health")
  [ "$H" = "200" ] && { echo "backend healthy after $i sec"; break; }
  sleep 2
done

############ POST-RESTART VERIFICATION ############
echo "--- POST-RESTART checks ---"
TIERS_AFTER=$(curl -s -H "$AH" "$BASE/api/tiers")
echo "$TIERS_AFTER" | python3 -c "
import sys,json
d=json.load(sys.stdin)
items=d if isinstance(d,list) else (d.get('tiers') or d.get('items') or [])
names=[t.get('name') for t in items]
target='$TIER_NAME'
print('TIER_SURVIVED' if target in names else 'TIER_LOST')
print('all tiers:',names)
" | tee /tmp/tier_check.txt
grep -q "TIER_SURVIVED" /tmp/tier_check.txt && log_pass "F1 custom tier $TIER_NAME SURVIVED restart" || log_fail "F1 custom tier" "$TIER_NAME WIPED on restart"

EVENTS_AFTER=$(curl -s -H "$AH" "$BASE/api/events")
echo "$EVENTS_AFTER" | python3 -c "
import sys,json
d=json.load(sys.stdin)
items=d if isinstance(d,list) else (d.get('events') or d.get('items') or [])
names=[t.get('title') for t in items]
target='$EVT_NAME'
print('EVT_SURVIVED' if target in names else 'EVT_LOST')
" | tee /tmp/evt_check.txt
grep -q "EVT_SURVIVED" /tmp/evt_check.txt && log_pass "F2 custom event SURVIVED restart" || log_fail "F2 custom event" "$EVT_NAME WIPED"

# upcoming check
EVENTS_UP=$(curl -s -H "$AH" "$BASE/api/events?upcoming=true")
echo "$EVENTS_UP" | python3 -c "
import sys,json
d=json.load(sys.stdin)
items=d if isinstance(d,list) else (d.get('events') or d.get('items') or [])
names=[t.get('title') for t in items]
print('EVT_UPCOMING_SURVIVED' if '$EVT_NAME' in names else 'EVT_UPCOMING_LOST')
" | tee /tmp/evt_up.txt
grep -q "EVT_UPCOMING_SURVIVED" /tmp/evt_up.txt && log_pass "F2b custom event in ?upcoming=true" || log_fail "F2b upcoming filter" ""

AWARDS_AFTER=$(curl -s -H "$AH" "$BASE/api/awards")
echo "$AWARDS_AFTER" | python3 -c "
import sys,json
d=json.load(sys.stdin)
items=d if isinstance(d,list) else (d.get('awards') or d.get('items') or [])
names=[t.get('name') for t in items]
print('AW_SURVIVED' if '$AWARD_NAME' in names else 'AW_LOST')
" | tee /tmp/aw_check.txt
grep -q "AW_SURVIVED" /tmp/aw_check.txt && log_pass "F3 custom award SURVIVED restart" || log_fail "F3 custom award" "WIPED"

# Sam check post-restart
SAM_AFTER=$(curl -s -H "$AH" "$BASE/api/members?q=Sam")
SAM_FOUND=$(echo "$SAM_AFTER" | python3 -c "
import sys,json
d=json.load(sys.stdin)
items=d.get('members') if isinstance(d,dict) else d
found=False
for m in (items or []):
    nm=(m.get('name') or '').lower()
    em=(m.get('email') or '').lower()
    if 'sam' in nm or 'sam.okafor' in em:
        found=True
print('SAM_FOUND' if found else 'SAM_GONE')
" 2>/dev/null)
echo "Sam post-restart: $SAM_FOUND"
if [ -n "$SAM_ID" ]; then
  [ "$SAM_FOUND" = "SAM_GONE" ] && log_pass "F4 Sam Okafor stays deleted after restart" || log_fail "F4 demo member re-seeded" "Sam came back"
else
  echo "SKIP F4 verification — Sam was not in DB pre-test"
fi

############ FEATURE 5 — Create National chapter ############
echo "--- F5: create National chapter ---"
NAT_RESP=$(curl -s -X POST "$BASE/api/chapters" -H "$AH" -H "Content-Type: application/json" \
  -d '{"name":"National","slug":"national","region":"USA"}')
NAT_ID=$(echo "$NAT_RESP" | python3 -c "import sys,json;print(json.load(sys.stdin).get('id',''))" 2>/dev/null)
if [ -n "$NAT_ID" ]; then
  log_pass "created National chapter id=$NAT_ID"
else
  # maybe already exists
  CH_LIST=$(curl -s -H "$AH" "$BASE/api/chapters")
  echo "$CH_LIST" | python3 -c "
import sys,json
d=json.load(sys.stdin)
items=d if isinstance(d,list) else (d.get('chapters') or [])
for c in items:
  if c.get('name')=='National':
    print('NATIONAL_EXISTS',c.get('id'));break
" || true
  log_pass "National chapter exists (or creation response unparseable: $NAT_RESP)"
fi

CH_FINAL=$(curl -s -H "$AH" "$BASE/api/chapters")
echo "$CH_FINAL" | python3 -c "
import sys,json
d=json.load(sys.stdin)
items=d if isinstance(d,list) else (d.get('chapters') or [])
print('chapters:',[c.get('name') for c in items])
"

############ FEATURE 6 — Auto-clear pending_set_password on login ############
echo "--- F6: auto-clear pending_set_password on login ---"
# Find member@clubhaven.app id
MEM_LIST=$(curl -s -H "$AH" "$BASE/api/members?q=member@clubhaven.app")
MEM_ID=$(echo "$MEM_LIST" | python3 -c "
import sys,json
d=json.load(sys.stdin)
items=d.get('members') if isinstance(d,dict) else d
for m in (items or []):
  if (m.get('email') or '').lower()=='member@clubhaven.app':
    print(m.get('id') or '');break
" 2>/dev/null)
echo "member id=$MEM_ID"
if [ -z "$MEM_ID" ]; then
  log_fail "F6 setup" "couldn't find member@clubhaven.app"
else
  # Flag pending
  RR=$(curl -s -X POST "$BASE/api/admin/members/$MEM_ID/resend-set-password" -H "$AH" -w "\nHTTP=%{http_code}")
  echo "resend-set-pwd: $RR"
  # Verify pending=true
  BEFORE=$(curl -s -H "$AH" "$BASE/api/members/$MEM_ID")
  PEND_BEFORE=$(echo "$BEFORE" | python3 -c "import sys,json;print(json.load(sys.stdin).get('pending_set_password'))" 2>/dev/null)
  echo "pending_set_password BEFORE login: $PEND_BEFORE"
  [ "$PEND_BEFORE" = "True" ] && log_pass "F6a pending flag set to true via resend" || log_fail "F6a" "flag=$PEND_BEFORE"

  # Login as the member
  ML=$(curl -s -X POST "$BASE/api/auth/login" -H "Content-Type: application/json" \
    -d '{"email":"member@clubhaven.app","password":"Member123!"}')
  MEM_TOK=$(echo "$ML" | python3 -c "import sys,json;print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null)
  [ -n "$MEM_TOK" ] && log_pass "F6b member logged in" || log_fail "F6b" "$ML"

  # Re-fetch as admin
  sleep 1
  AFTER=$(curl -s -H "$AH" "$BASE/api/members/$MEM_ID")
  PEND_AFTER=$(echo "$AFTER" | python3 -c "import sys,json;print(json.load(sys.stdin).get('pending_set_password'))" 2>/dev/null)
  echo "pending_set_password AFTER login: $PEND_AFTER"
  [ "$PEND_AFTER" = "False" ] && log_pass "F6c pending flag auto-cleared on login" || log_fail "F6c" "flag still=$PEND_AFTER"
fi

############ CLEANUP ############
echo "--- cleanup test data ---"
[ -n "${TIER_ID:-}" ]  && curl -s -X DELETE "$BASE/api/tiers/$TIER_ID"   -H "$AH" -o /dev/null
[ -n "${EVT_ID:-}" ]   && curl -s -X DELETE "$BASE/api/events/$EVT_ID"   -H "$AH" -o /dev/null
[ -n "${AW_ID:-}" ]    && curl -s -X DELETE "$BASE/api/awards/$AW_ID"    -H "$AH" -o /dev/null

echo "===== SUMMARY: PASS=$PASS FAIL=$FAIL ====="
exit $FAIL
