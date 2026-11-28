#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

echo "=== Build frontend ==="
cd "$ROOT_DIR/front"
npm ci
npm run build

echo "=== Install Cloudflare dependencies ==="
cd "$ROOT_DIR/infra/cloudflare"
npm ci

echo "=== Apply D1 migrations ==="
npx wrangler d1 migrations apply ito-db --remote

echo "=== Deploy to Cloudflare ==="
npx wrangler deploy

echo "=== Deployment completed ==="