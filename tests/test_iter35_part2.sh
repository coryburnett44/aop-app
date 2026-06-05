#!/bin/bash
# Iter35 part 2: re-test F2 (with start_at) + F6 (with known member id)
set -uo pipefail
BASE="https://club-express-lite.preview.emergentagent.com"
PASS=0; FAIL=0
pass(){ echo "PASS: $1"; PASS=$((PASS+1)); }
fail(){ echo "FAIL: $1 | $2"; FAIL=$((FAIL+1)); }

AT=$(curl -s -X POST "$BASE/api/auth/login" -H "Content-Type: application/json" \
  -d '{"email":"admin@clubhaven.app","password":"Admin123!"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
AH="Authorization: Bearer $AT"

############ F2 RETEST — start_at ############
EVT_NAME="Iter35_EventV2_$(date +%s)"
EVT_DATE=$(python3 -c "from datetime import datetime,timedelta; print((datetime.utcnow()+timedelta(days=30)).isoformat()+'Z')")
ER=$(curl -s -X POST "$BASE/api/events" -H "$AH" -H "Content-Type: application/json" \
  -d "{\"title\":\"$EVT_NAME\",\"start_at\":\"$EVT_DATE\",\"location\":\"Test Hall\",\"description\":\"iter35 test\",\"category\":\"meeting\"}")
EID=$(echo "$ER" | python3 -c "import sys,json;print(json.load(sys.stdin).get('id',''))" 2>/dev/null)
[ -n "$EID" ] && pass "create event $EVT_NAME id=$EID" || { fail "create event" "$ER"; exit 1; }

echo "--- restart backend ---"
sudo supervisorctl restart backend
sleep 6
for i in 1 2 3 4 5 6 7 8; do H=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/api/health"); [ "$H" = "200" ] && break; sleep 2; done

# Check event survived
AT=$(curl -s -X POST "$BASE/api/auth/login" -H "Content-Type: application/json" \
  -d '{"email":"admin@clubhaven.app","password":"Admin123!"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
AH="Authorization: Bearer $AT"

EVTS=$(curl -s -H "$AH" "$BASE/api/events")
SURV=$(echo "$EVTS" | python3 -c "
import sys,json
d=json.load(sys.stdin)
items=d if isinstance(d,list) else (d.get('events') or [])
print('YES' if '$EVT_NAME' in [t.get('title') for t in items] else 'NO')
")
[ "$SURV" = "YES" ] && pass "F2 event SURVIVED restart" || fail "F2 event WIPED" ""

EVTS_UP=$(curl -s -H "$AH" "$BASE/api/events?upcoming=true")
SURV2=$(echo "$EVTS_UP" | python3 -c "
import sys,json
d=json.load(sys.stdin)
items=d if isinstance(d,list) else (d.get('events') or [])
print('YES' if '$EVT_NAME' in [t.get('title') for t in items] else 'NO')
")
[ "$SURV2" = "YES" ] && pass "F2b event in ?upcoming=true" || fail "F2b upcoming filter" ""

############ F6 RETEST ############
MID="8108308c-53a8-4c90-8fe0-ddd438b8bc19"  # Riley Chen / member@clubhaven.app
RR=$(curl -s -X POST "$BASE/api/admin/members/$MID/resend-set-password" -H "$AH" -w "\nHTTP=%{http_code}")
echo "resend-set-pwd response: $RR"
BEFORE=$(curl -s -H "$AH" "$BASE/api/members/$MID")
PB=$(echo "$BEFORE" | python3 -c "import sys,json;print(json.load(sys.stdin).get('pending_set_password'))")
echo "pending BEFORE login: $PB"
[ "$PB" = "True" ] && pass "F6a pending set true via resend" || fail "F6a" "pending=$PB"

ML=$(curl -s -X POST "$BASE/api/auth/login" -H "Content-Type: application/json" \
  -d '{"email":"member@clubhaven.app","password":"Member123!"}')
MT=$(echo "$ML" | python3 -c "import sys,json;print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null)
[ -n "$MT" ] && pass "F6b member login OK" || fail "F6b login" "$ML"

sleep 1
AFTER=$(curl -s -H "$AH" "$BASE/api/members/$MID")
PA=$(echo "$AFTER" | python3 -c "import sys,json;print(json.load(sys.stdin).get('pending_set_password'))")
echo "pending AFTER login: $PA"
[ "$PA" = "False" ] && pass "F6c pending auto-cleared on login" || fail "F6c" "pending still=$PA"

# Cleanup
[ -n "${EID:-}" ] && curl -s -X DELETE "$BASE/api/events/$EID" -H "$AH" -o /dev/null

echo "===== SUMMARY: PASS=$PASS FAIL=$FAIL ====="
exit $FAIL
