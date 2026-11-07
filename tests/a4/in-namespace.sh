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
cp "$A4_ROOT/tests/a4/synthetic.mjs" "$A4_RUN_DIR/work/synthetic.mjs"
cp "$A4_ROOT/tests/a4/react-autosave.cjs" "$A4_RUN_DIR/work/ui/react-autosave.cjs"
cp "$A4_ROOT/ui/.a4-hook.cjs" "$A4_RUN_DIR/work/ui/hook.cjs"
mkdir -p "$A4_RUN_DIR/work/ui/node_modules"
for pkg in react react-test-renderer react-is scheduler object-assign loose-envify; do
  if [[ -d "$A4_ROOT/ui/node_modules/$pkg" ]]; then
    cp -a "$A4_ROOT/ui/node_modules/$pkg" "$A4_RUN_DIR/work/ui/node_modules/$pkg"
  fi
done
mkdir -p "$A4_RUN_DIR/work/config" "$A4_RUN_DIR/work/assets" "$A4_RUN_DIR/work/ui"
cp -a "$A4_ROOT/ui/public" "$A4_RUN_DIR/work/ui/public"
chown -R nobody:nogroup "$A4_RUN_DIR/work"
printf 'A4-ISO-000 PASS\n' > "$A4_RUN_DIR/app-import.started"
cd "$A4_RUN_DIR/work"
behavior_status=0
runuser -u nobody -- env -i PATH="$PATH" HOME="$A4_RUN_DIR/home" TMPDIR="$A4_RUN_DIR/tmp" \
  NODE_ENV=test A4_APP_ROOT="$A4_RUN_DIR/work" A4_RESULTS="$A4_RUN_DIR/results.json" \
  node "$A4_RUN_DIR/work/synthetic.mjs" || behavior_status=$?
react_status=0
runuser -u nobody -- env -i PATH="$PATH" HOME="$A4_RUN_DIR/home" TMPDIR="$A4_RUN_DIR/tmp" \
  NODE_ENV=test A4_APP_ROOT="$A4_RUN_DIR/work" A4_UI_RESULTS="$A4_RUN_DIR/react-results.json" \
  node "$A4_RUN_DIR/work/ui/react-autosave.cjs" || react_status=$?
echo "A4: original behavior status=$behavior_status React hook status=$react_status"
[[ "$behavior_status" -eq 0 && "$react_status" -eq 0 ]]
