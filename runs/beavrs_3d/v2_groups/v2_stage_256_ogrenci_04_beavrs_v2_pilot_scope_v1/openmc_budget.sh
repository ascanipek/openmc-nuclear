#!/bin/sh
/usr/bin/timeout --signal=TERM --kill-after=30s 7414s /tmp/openmc_016/bin/openmc "$@"
result=$?
if [ "$result" -eq 124 ]; then printf 'group time budget exhausted\n' > kaggle_budget_timeout.txt; fi
exit "$result"
