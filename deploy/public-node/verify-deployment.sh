#!/bin/sh
set -eu

BASE=${1:?usage: verify-deployment.sh https://host}
case "$BASE" in
    https://*) ;;
    *) echo "verification requires an HTTPS URL" >&2; exit 2 ;;
esac

well_known=$(curl --fail --silent --show-error --location --max-time 10 --max-filesize 1048576 "$BASE/.well-known/mncs-commons")
printf '%s\n' "$well_known" | python3 -c 'import json,sys; v=json.load(sys.stdin); assert v["exchangeVersion"]=="commons.mncs.dev/exchange/v0alpha1"; assert v["participantIdentity"]["technicalAuthority"]=="NONE_GRANTED"; assert v["transport"]["encrypted"] is True; print("discovery PASS")'
curl --fail --silent --show-error --location --max-time 10 "$BASE/healthz" >/dev/null
curl --fail --silent --show-error --location --max-time 10 "$BASE/readyz" >/dev/null
echo "public node discovery/health/readiness PASS"
