#!/bin/sh

# Ensure config.json exists in the mounted volume
if [ ! -f /app/config/config.json ]; then
  echo '{"indexers":[],"cacheEnabled":true,"cacheTTL":0,"indexManager":"newznab"}' > /app/config/config.json
  echo "✅ Created default config.json"
fi

exec "$@"
