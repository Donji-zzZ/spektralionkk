#!/usr/bin/env bash
# Run all spektralionkk test suites (headless) on macOS and print a summary.
#   bash scripts/run_tests.sh                              all suites
#   bash scripts/run_tests.sh ~/Pictures/DSC01234.ARW      plus a full-resolution test on one of your RAWs
# test_engine runs first: it writes app/tests/out/test_input.jpg, which the other suites use. test_rawformats
# needs sample RAW files in rawsamples/<format>/ (or in $SPRK_RAWSAMPLES) and is skipped without them.
cd "$(dirname "$0")/.."
PY="${PYTHON:-.venv/bin/python}"
RAW="${1:-}"
if [ ! -x "$PY" ]; then
    echo "Python not found at $PY" >&2
    exit 1
fi
export SPRK_LANG=en  # the suites check English texts (test_i18n switches to Chinese itself)
tests="test_engine test_fastprint test_features test_live test_controls test_ui test_ui_live test_i18n test_platform test_rawformats"
if [ -n "$RAW" ]; then tests="$tests test_raw"; fi
summary=""
failed=0
for t in $tests; do
    case "$t" in
        test_ui*|test_controls|test_i18n|test_platform) export QT_QPA_PLATFORM=offscreen ;;
        *) unset QT_QPA_PLATFORM ;;
    esac
    start=$(date +%s)
    if [ "$t" = "test_raw" ]; then
        "$PY" -I -X utf8 -W ignore "app/tests/$t.py" "$RAW" > "/tmp/sprk_$t.log" 2>&1
    else
        "$PY" -I -X utf8 -W ignore "app/tests/$t.py" > "/tmp/sprk_$t.log" 2>&1
    fi
    code=$?
    grep -E "^(FAIL|SKIP)|Traceback|Error" "/tmp/sprk_$t.log" | sed 's/^/    /'
    if [ $code -eq 0 ]; then result=PASS; else result=FAIL; failed=1; fi
    line=$(printf "%-16s %-6s %5d s" "$t" "$result" $(( $(date +%s) - start )))
    echo "$line"
    summary="$summary$line"$'\n'
done
echo
printf "%s" "$summary"
exit $failed
