#!/usr/bin/env bash
#
# Launch the dev stack (honcho) on a free port "slot", keeping the house port
# convention intact:
#
#   slot digit D  ->  web=D789  api=D788  redis=D787
#
#   8 = prod      (8789 / 8788)        reserved
#   9 = trunk     (9789 / 9788)        reserved — this is plain `make dev`
#   2..7          ad-hoc dev servers — what this script hands out
#
# With no argument it scans slots 2..7 in order and picks the first whose web,
# api and redis ports are all free, so several dev servers can run side by side
# without colliding. Pass a digit to force a slot: `scripts/dev.sh 5`.
# Pass --print to show the chosen slot + exported env and exit without launching.
#
# Each slot gets its own Redis (port D787, broker db 0 / result db 1) so workers
# never poach each other's extraction tasks.
set -euo pipefail

cd "$(dirname "$0")/.."

PRINT_ONLY=0
SLOTS="2 3 4 5 6 7"
for arg in "$@"; do
	case "$arg" in
		--print|-n) PRINT_ONLY=1 ;;
		[2-9]) SLOTS="$arg" ;;
		*) echo "usage: scripts/dev.sh [2-9] [--print]" >&2; exit 2 ;;
	esac
done

is_free() {
	local port="$1"
	if command -v ss >/dev/null 2>&1; then
		! ss -ltnH "sport = :$port" 2>/dev/null | grep -q .
	else
		! (exec 3<>"/dev/tcp/127.0.0.1/$port") 2>/dev/null
	fi
}

slot=""
for d in $SLOTS; do
	web=$((d * 1000 + 789))
	api=$((d * 1000 + 788))
	redis=$((d * 1000 + 787))
	if is_free "$web" && is_free "$api" && is_free "$redis"; then
		slot="$d"
		break
	fi
done

if [ -z "$slot" ]; then
	echo "No free slot in: $SLOTS (web/api/redis ports all taken)." >&2
	exit 1
fi

export COOKMARKS_WEB_PORT=$((slot * 1000 + 789))
export COOKMARKS_API_PORT=$((slot * 1000 + 788))
export COOKMARKS_REDIS_PORT=$((slot * 1000 + 787))
export COOKMARKS_CELERY_BROKER_URL="redis://localhost:${COOKMARKS_REDIS_PORT}/0"
export COOKMARKS_CELERY_RESULT_BACKEND="redis://localhost:${COOKMARKS_REDIS_PORT}/1"

echo "▶ slot $slot — web http://localhost:${COOKMARKS_WEB_PORT}  api :${COOKMARKS_API_PORT}  redis :${COOKMARKS_REDIS_PORT}"

if [ "$PRINT_ONLY" -eq 1 ]; then
	env | grep '^COOKMARKS_' | sort
	exit 0
fi

exec uvx honcho start
