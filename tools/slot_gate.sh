#!/usr/bin/env bash
#
# Decide whether this run should fire, given a list of weekly Central-time slots.
#
# GitHub's scheduled runs are minutes-to-hours late and are sometimes dropped altogether, so the
# workflows fire on a wide hourly window instead of once per slot. This gate picks the most recent
# slot that is already due rather than demanding an exact match, and the caller's cache lock keeps
# the extra firings from sending the same report twice.
#
# Usage: slot_gate.sh <dow>-<HHMM> [...]     dow is Central-time 0=Sun .. 6=Sat
#
# Outputs to $GITHUB_OUTPUT:
#   slot=<slot date>-<dow>-<HHMM>  the slot this run is about (empty when nothing is due)
#   run=true                       send the report
#   stale=true                     the slot came due but is now too late to be worth sending;
#                                  the caller warns once instead of staying silent
set -euo pipefail

# How late a report may be and still be worth sending. Kickoff-sensitive jobs pass a tight budget;
# a recap is happy to arrive in the afternoon. Delays of five hours have been observed.
MAX_LATE_MIN=${MAX_LATE_MIN:-240}

emit() { printf '%s\n' "$@" >> "$GITHUB_OUTPUT"; }

if [ "${GITHUB_EVENT_NAME:-}" = "workflow_dispatch" ]; then
  echo "manual run"
  emit "run=true" "slot=manual-${GITHUB_RUN_ID:-0}"
  exit 0
fi

# SLOT_GATE_NOW ("<today> <yesterday> <dow> <HHMM>", Central) stands in for the clock when testing.
if [ -n "${SLOT_GATE_NOW:-}" ]; then
  read -r today yday dow hhmm <<< "$SLOT_GATE_NOW"
else
  read -r today dow hhmm <<< "$(TZ=America/Chicago date '+%F %w %H%M')"
  # A late waiver run lands after Central midnight, so yesterday's slots have to stay reachable.
  yday=$(TZ=America/Chicago date -d yesterday +%F 2>/dev/null || TZ=America/Chicago date -v-1d +%F)
fi
now=$(( 10#${hhmm:0:2} * 60 + 10#${hhmm:2:2} ))
clock="$today ${hhmm:0:2}:${hhmm:2:2} Central"

# The slot that came due most recently, looking back through yesterday.
best="" best_date="" best_late=-1
for slot in "$@"; do
  d=${slot%%-*} t=${slot##*-}
  at=$(( 10#${t:0:2} * 60 + 10#${t:2:2} ))
  for back in 0 1; do
    [ "$d" = "$(( (dow - back + 7) % 7 ))" ] || continue
    late=$(( now + back * 1440 - at ))
    [ "$late" -ge 0 ] || continue                                   # not due yet
    [ "$best_late" -lt 0 ] || [ "$late" -lt "$best_late" ] || continue  # an even fresher slot won
    best=$slot best_late=$late
    [ "$back" = 0 ] && best_date=$today || best_date=$yday
  done
done

if [ -z "$best" ]; then
  echo "skip: no slot due at $clock"
  emit "slot=" "run=false" "stale=false"
  exit 0
fi

emit "slot=$best_date-$best"
if [ "$best_late" -le "$MAX_LATE_MIN" ]; then
  echo "slot $best is due at $clock, $best_late min late (budget $MAX_LATE_MIN)"
  emit "run=true" "stale=false"
else
  echo "slot $best is $best_late min late at $clock, past its $MAX_LATE_MIN min budget: warn instead of sending"
  emit "run=false" "stale=true"
fi
