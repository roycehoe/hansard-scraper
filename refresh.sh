#!/bin/sh
# Command of the scheduled refresh job. Pings healthchecks.io with refresh.py's
# exit code, so a crash before refresh.py's own alert code runs (an import
# error, a bad DATABASE_URL) marks the check down at once, not after 26 hours.
python refresh.py "$@"
code=$?
if [ -n "$HEALTHCHECKS_PING_URL" ]; then
    python -c 'import sys, urllib.request; urllib.request.urlopen(sys.argv[1], timeout=10)' "$HEALTHCHECKS_PING_URL/$code"
fi
exit $code
