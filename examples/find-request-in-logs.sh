#!/usr/bin/env bash
# Example only: find a request id in access logs on one or more hosts over SSH.
# Adapt LOG_HOSTS and LOG_FILE to your setup. Read only: it runs grep on the remote logs.
#
#   LOG_HOSTS="web1 web2" LOG_FILE=/var/log/nginx/access.log ./find-request-in-logs.sh <request-id> [...]
#
# No line on any host means the request never reached your servers.
set -euo pipefail
: "${LOG_HOSTS:?set LOG_HOSTS to a space separated list of SSH hosts}"
: "${LOG_FILE:?set LOG_FILE to the access log path on those hosts}"
[ "$#" -ge 1 ] || { echo "usage: $0 <request-id> [...]" >&2; exit 2; }
for id in "$@"; do
  case "$id" in *[!A-Za-z0-9._:-]*) echo "refusing odd request id: $id" >&2; exit 2;; esac
  found=0
  for host in $LOG_HOSTS; do
    # -F: the id is a literal string. Rotated logs are not searched.
    if out=$(ssh -o BatchMode=yes "$host" grep -F -- "$id" "$LOG_FILE" 2>/dev/null) && [ -n "$out" ]; then
      printf '%s  %s\n%s\n' "$host" "$id" "$out"; found=1
    fi
  done
  [ "$found" = 1 ] || echo "no line for $id on: $LOG_HOSTS"
done
