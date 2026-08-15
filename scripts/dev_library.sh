#!/usr/bin/env bash
#
# Build (or reset) the dev Calibre library — a three-book copy of the real one.
#
# Dev must never write to the prod library, but ingest experiments need a library
# that can be written to and thrown away. This clones the prod library and prunes
# the clone to the eval books, so `calibre_id`s and paths survive exactly and
# backend/evals/eval.toml still resolves its EPUBs.
#
#   scripts/dev_library.sh [--source PATH] [--dest PATH]
#
# Re-run it any time to reset the dev library to those three books.
#
# The clone is made with hardlinks, so it costs seconds and almost no disk. Only
# metadata.db is a real copy — calibredb writes to it, and a shared inode would
# reach back into the prod library.
set -euo pipefail

SOURCE=${COOKMARKS_PROD_LIBRARY:-/home/aaron/docker/cookmarks/library}
# Deliberately outside ~/books: that tree is a Syncthing folder, and a library the dev
# stack writes to has no business being mirrored anywhere.
DEST=${COOKMARKS_DEV_LIBRARY:-$HOME/cookmarks-dev-library}
KEEP_IDS=${COOKMARKS_DEV_LIBRARY_IDS:-"751 502 227"}   # craveable · curry-guy · nothing-fancy

while [ $# -gt 0 ]; do
	case "$1" in
		--source) SOURCE=$2; shift 2 ;;
		--dest) DEST=$2; shift 2 ;;
		*) echo "unknown argument: $1" >&2; exit 2 ;;
	esac
done

command -v calibredb >/dev/null || {
	echo "calibredb not found — install Calibre (see CLAUDE.md)" >&2
	exit 1
}
[ -f "$SOURCE/metadata.db" ] || { echo "no Calibre library at $SOURCE" >&2; exit 1; }

echo "Cloning $SOURCE -> $DEST"
rm -rf "$DEST"
mkdir -p "$(dirname "$DEST")"
cp -al "$SOURCE" "$DEST" 2>/dev/null || cp -a "$SOURCE" "$DEST"
rm -f "$DEST/metadata.db" "$DEST/metadata_db_prefs_backup.json" "$DEST/full-text-search.db"
cp "$SOURCE/metadata.db" "$DEST/metadata.db"
[ -f "$SOURCE/metadata_db_prefs_backup.json" ] &&
	cp "$SOURCE/metadata_db_prefs_backup.json" "$DEST/metadata_db_prefs_backup.json"

# Calibre's search takes no comma list of ids, and a bad query exits non-zero — which
# once made this prune a silent no-op. Build the disjunction, and let a failure stop us.
keep_query=""
for id in $KEEP_IDS; do
	keep_query="${keep_query:+$keep_query or }id:$id"
done

errors=$(mktemp)
if ! victims=$(calibredb search --with-library "$DEST" "not ($keep_query)" 2>"$errors"); then
	grep -q 'No books matching' "$errors" || { cat "$errors" >&2; rm -f "$errors"; exit 1; }
	victims=""
fi
rm -f "$errors"

if [ -n "$victims" ]; then
	echo "$victims" | tr ',' '\n' | xargs -n 50 | tr ' ' ',' | while read -r chunk; do
		calibredb remove --permanent --with-library "$DEST" "$chunk" >/dev/null
	done
fi

# calibredb deletes rows synchronously but files in a background thread it does not
# wait for, so directories outlive their books. Clear whatever it left behind.
sqlite3 -readonly "$DEST/metadata.db" 'SELECT path FROM books;' | sort > /tmp/dev-library-keep.$$
(cd "$DEST" && find . -mindepth 2 -maxdepth 2 -type d -printf '%P\n') | sort > /tmp/dev-library-have.$$
comm -13 /tmp/dev-library-keep.$$ /tmp/dev-library-have.$$ | while read -r stale; do
	rm -rf "${DEST:?}/$stale"
done
rm -f /tmp/dev-library-keep.$$ /tmp/dev-library-have.$$
# The library is mirrored from a Mac, so .DS_Store files keep emptied author folders alive.
find "$DEST" -name .DS_Store -delete
find "$DEST" -mindepth 1 -maxdepth 2 -type d -empty -delete

left=$(sqlite3 -readonly "$DEST/metadata.db" 'SELECT count(*) FROM books;')
wanted=$(echo "$KEEP_IDS" | wc -w)
if [ "$left" -ne "$wanted" ]; then
	echo "prune failed: $left book(s) left, expected $wanted" >&2
	exit 1
fi

echo "Dev library ready: $left book(s) at $DEST"
echo "Point dev at it:  COOKMARKS_CALIBRE_LIBRARY_PATH=$DEST  (backend/.env)"
