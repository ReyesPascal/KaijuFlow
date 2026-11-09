#!/usr/bin/env bash
# Build the React hook bundle the A4 suite tests (ui/.a4-hook.cjs).
# Used by CI (a4-isolated.yml) and by `npm run test:a4` locally.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
if [[ ! -d ui/node_modules/react-test-renderer ]]; then
  npm ci --prefix ui --ignore-scripts --no-audit --no-fund
  npm install --prefix ui --no-save --package-lock=false --ignore-scripts --no-audit --no-fund react-test-renderer@18.3.1
fi
./ui/node_modules/.bin/esbuild ui/src/hooks/useAppConfig.ts --bundle --platform=node --format=cjs --external:react --outfile=ui/.a4-hook.cjs
