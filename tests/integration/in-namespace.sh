#!/usr/bin/env bash
set -euo pipefail
: "${A4_ROOT:?missing root}" "${A4_RUN_DIR:?missing disposable path}" "${A4_PARENT_NETNS:?missing outer net namespace}"
[[ "$(readlink /proc/self/ns/net)" != "$A4_PARENT_NETNS" ]] || { echo "FAIL: not isolated"; exit 20; }
[[ "$(id -u)" == "0" ]] || { echo "FAIL: namespace setup requires root"; exit 21; }
ip link set lo up
[[ "$(ip -o link show | wc -l)" == 1 ]] && ip -o link show lo >/dev/null || { echo "FAIL: non-loopback interface"; exit 22; }
mkdir -p "$A4_RUN_DIR"/{home,work,tmp}
chmod 755 "$(dirname "$A4_RUN_DIR")"
cp "$A4_ROOT/tests/a4/isolation-probe.mjs" "$A4_RUN_DIR/probe.mjs"
chown -R nobody:nogroup "$A4_RUN_DIR"
runuser -u nobody -- env -i PATH="$PATH" HOME="$A4_RUN_DIR/home" TMPDIR="$A4_RUN_DIR/tmp" \
  A4_FORCE_FAIL="${A4_FORCE_FAIL:-0}" node "$A4_RUN_DIR/probe.mjs"
echo "A4-ISO-000: network namespace $(readlink /proc/self/ns/net); only lo; TCP v4/v6 and DNS denied; local loopback PASS"
cp -a "$A4_ROOT/dist" "$A4_RUN_DIR/work/dist"
cp "$A4_ROOT/package.json" "$A4_RUN_DIR/work/package.json"
cp -a "$A4_ROOT/node_modules" "$A4_RUN_DIR/work/node_modules"
cp "$A4_ROOT"/tests/integration/*.mjs "$A4_RUN_DIR/work/"
# Shared Parity helpers live in a subfolder so they are not run as scenarios.
cp -a "$A4_ROOT/tests/integration/parity" "$A4_RUN_DIR/work/parity"
# Real archives some scenarios post to the fake news server.
mkdir -p "$A4_RUN_DIR/work/fixtures" && cp -a "$A4_ROOT/tests/fixtures/archives" "$A4_RUN_DIR/work/fixtures/archives"
mkdir -p "$A4_RUN_DIR/work/ui/public" && cp "$A4_ROOT/ui/public/nzb_failure_video.mp4" "$A4_RUN_DIR/work/ui/public/"  # the failure video the app serves
mkdir -p "$A4_RUN_DIR/work/config"
chown -R nobody:nogroup "$A4_RUN_DIR/work"
printf 'integration isolation PASS\n' > "$A4_RUN_DIR/app-import.started"
cd "$A4_RUN_DIR/work"
# KaijuFlow: run each scenario in a fresh process (module state, env and caches don't leak).
# Each scenario gets its own memory cap so a runaway test fails alone instead of
# letting the kernel OOM-kill whatever else runs on the machine (retro of #16).
SCENARIO_MEMORY_MAX=4G
memory_cap=0
if command -v systemd-run >/dev/null 2>&1 && systemd-run --scope -q -p MemoryMax=64M true >/dev/null 2>&1; then
  memory_cap=1
else
  echo "INTEGRATION MEMORY WARNING: systemd-run scopes unavailable, scenarios run without a memory cap"
fi
peak_report=0
if [[ -x /usr/bin/time ]]; then
  peak_report=1
else
  echo "INTEGRATION MEMORY WARNING: /usr/bin/time missing, peak memory not reported"
fi
# with_memory_cap <scenario name> <command...>
with_memory_cap() {
  local name="$1"; shift
  local report=()
  if [[ "$peak_report" -eq 1 ]]; then report=(/usr/bin/time -f "INTEGRATION MEMORY $name peak_rss_kb=%M"); fi
  if [[ "$memory_cap" -eq 1 ]]; then
    systemd-run --scope -q -p MemoryMax="$SCENARIO_MEMORY_MAX" -p MemorySwapMax=0 -- "${report[@]}" "$@"
  else
    "${report[@]}" "$@"
  fi
}
# INTEGRATION_ONLY: the suite names to run (run-ci.sh's arguments, `.mjs` optional); empty runs every suite.
scenarios=()
for only in ${INTEGRATION_ONLY:-}; do
  only="$(basename "$only" .mjs)"
  [[ -f "$A4_RUN_DIR/work/$only.mjs" ]] || {
    echo "INTEGRATION UNKNOWN SUITE $only; the suites: $(cd "$A4_RUN_DIR/work" && ls -- *.mjs | sed 's/\.mjs$//' | tr '\n' ' ')"; exit 30; }
  scenarios+=("$A4_RUN_DIR/work/$only.mjs")
done
[[ ${#scenarios[@]} -gt 0 ]] || scenarios=("$A4_RUN_DIR"/work/*.mjs)
overall=0
for scenario in "${scenarios[@]}"; do
  name="$(basename "$scenario" .mjs)"
  rm -rf "$A4_RUN_DIR/work/config"; mkdir -p "$A4_RUN_DIR/work/config"; chown nobody:nogroup "$A4_RUN_DIR/work/config"
  rc=0
  with_memory_cap "$name" runuser -u nobody -- env -i PATH="$PATH" HOME="$A4_RUN_DIR/home" TMPDIR="$A4_RUN_DIR/tmp" \
    NODE_ENV=test A4_APP_ROOT="$A4_RUN_DIR/work" INTEGRATION_RESULTS="$A4_RUN_DIR/results-$name.json" \
    timeout 120 node "$scenario" || rc=$?
  if [[ "$rc" -eq 137 || "$rc" -eq 143 ]]; then
    echo "INTEGRATION MEMORY $name killed: over the $SCENARIO_MEMORY_MAX memory cap; look for a runaway buffer or assertion diff"
  fi
  echo "INTEGRATION SCENARIO $name exit=$rc"
  [[ "$rc" -eq 0 ]] || overall=1
done
exit "$overall"
